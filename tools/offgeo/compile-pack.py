#!/usr/bin/env python3
"""Compile the real v0 OffGeo pack the live app actually loads.

This is the first *shipped* (not build/offgeo-sources-scratch) OffGeo
artifact. It reuses, unchanged, the real pipeline R1 prototyping already
proved out: `compile-sangis-roads.py`'s thin-reader output
(`build/offgeo-sources/r1-sangis-roads.jsonl`) encoded via
`lib/packformat.py`'s `encode_records` -- the same codec
`prototype-pack-formats.py` (`OFF-104`) and `prototype-benchmark-reader.py`
(`OFF-105`) already round-trip-verified against all 164,555 real records
and cross-checked against an independent JS port.

Deliberately v0, not the frozen R2 format or full spec.md compliance:

- SanGIS Roads-All only. No Census fallback merge (that's R2 `OFF-204`),
  no address-point join repair, no alias/fuzzy index, no intersection
  topology. A caller whose address doesn't resolve to a road SanGIS
  itself has simply gets no result -- same honest "never invent a
  result" stance the old map-prototype geocoder already had.
- Whole-file, not block-partitioned (`OFF-105`'s design). The browser
  decodes the entire pack once, on first map open, into an in-memory
  index -- simpler than staged IndexedDB installation (R3), acceptable
  for a single ~10 MiB one-time fetch+decode.
- Magic stays `"OGP0"` (`lib/packformat.py`'s prototype magic), not
  `"OFG1"` -- `roadmap.md` reserves that name for the actual frozen R1
  format decision (`OFF-109`), which hasn't been made yet.

Usage: python3 tools/offgeo/compile-pack.py
  (requires build/offgeo-sources/r1-sangis-roads.jsonl -- run
   compile-sangis-roads.py first)
Output: offgeo/packs/v0/sd-06073.ogp0 (committed to git -- this is the
        real shipped asset, not build scratch)
        offgeo/manifest.json (committed)
"""
from __future__ import annotations

import gzip
import hashlib
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import packformat  # noqa: E402
from normalize import canonicalize_street_core_name  # noqa: E402

ROADS_PATH = REPO_ROOT / "build/offgeo-sources/r1-sangis-roads.jsonl"
LOCK_PATH = REPO_ROOT / "tools/offgeo/config/sources.lock.json"
PACK_VERSION = "v0"
PACK_PATH = REPO_ROOT / f"offgeo/packs/{PACK_VERSION}/sd-06073.ogp0"
MANIFEST_PATH = REPO_ROOT / "offgeo/manifest.json"


def iter_jsonl(path: Path):
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def load_records() -> list[dict]:
    """Same record shape prototype-pack-formats.py's load_records()
    established -- confidenceReasons/rawStatus stay out (build-only
    diagnostics per spec.md 6.1 step 6, not shipped-pack fields)."""
    records = []
    for road in iter_jsonl(ROADS_PATH):
        s = road["street"]
        ar = road["addressRange"]
        records.append(
            {
                "roadsegid": road["roadsegid"],
                "pdir": s["pdir"],
                "name": canonicalize_street_core_name(s["name"]) if s["name"] else "",
                "postd": s["postd"],
                "sfx": s["sfx"],
                "lLow": int(ar["lLow"]), "lHigh": int(ar["lHigh"]),
                "rLow": int(ar["rLow"]), "rHigh": int(ar["rHigh"]),
                "lMix": ar["lMix"] == "Y", "rMix": ar["rMix"] == "Y",
                "confidence": road["confidence"],
                "leftZip": road["zip"]["left"] or None,
                "rightZip": road["zip"]["right"] or None,
                "points": [(pt[1], pt[0]) for pt in road["geometryWgs84"][0]],
            }
        )
    return records


def main() -> None:
    if not ROADS_PATH.exists():
        raise SystemExit(f"{ROADS_PATH} missing -- run compile-sangis-roads.py first")

    print("Loading real roads reader output...")
    records = load_records()
    print(f"  {len(records)} records")

    print("Encoding pack (lib/packformat.py, whole-file)...")
    t0 = time.time()
    blob = packformat.encode_records(records)
    encode_seconds = time.time() - t0

    print("Verifying round-trip decode against all records...")
    decoded = packformat.decode_records(blob)
    assert len(decoded) == len(records)
    for original, got in zip(records, decoded):
        assert original["roadsegid"] == got["roadsegid"]
        assert original["name"] == got["name"]
        assert original["confidence"] == got["confidence"]
    print("  verified")

    PACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    PACK_PATH.write_bytes(blob)
    pack_sha256 = hashlib.sha256(blob).hexdigest()
    gzip_bytes = len(gzip.compress(blob, compresslevel=9))

    lock = json.loads(LOCK_PATH.read_text())
    roads_entry = next(e for e in lock["sources"] if e["id"] == "sangis-roads-all")

    confidence_counts: dict[str, int] = {}
    for r in records:
        confidence_counts[r["confidence"]] = confidence_counts.get(r["confidence"], 0) + 1

    manifest = {
        "version": PACK_VERSION,
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "format": {
            "magic": packformat.MAGIC.decode(),
            "formatVersion": packformat.FORMAT_VERSION,
            "note": (
                "Prototype format, not the frozen R1 OFG1 decision (OFF-109, still open). "
                "See notes/offgeo/r1-todo.md Group D for the size/speed evidence gathered so far."
            ),
        },
        "pack": {
            "path": str(PACK_PATH.relative_to(REPO_ROOT)),
            "byteLength": len(blob),
            "gzipByteLength": gzip_bytes,
            "sha256": pack_sha256,
            "recordCount": len(records),
            "confidenceCounts": confidence_counts,
        },
        "scope": (
            "SanGIS Roads-All only (San Diego County, 06073). No Census fallback merge, "
            "no address-point join repair, no alias/fuzzy index, no intersection topology. "
            "v0 prototype integration, not R2's frozen production compiler."
        ),
        "sources": [
            {
                "publisher": roads_entry["publisher"],
                "dataset": roads_entry["dataset"],
                "attribution": roads_entry["attribution"],
                "licenseName": roads_entry["licenseName"],
                "licenseUrl": roads_entry["licenseUrl"],
                "documentationUrl": roads_entry["documentationUrl"],
                "publisherDisplayedVintage": roads_entry["publisherDisplayedVintage"],
                "sourceSha256": roads_entry["sha256"],
            }
        ],
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    print(f"\nWrote {PACK_PATH} ({len(blob):,} bytes raw, {gzip_bytes:,} bytes gzip)")
    print(f"SHA-256: {pack_sha256}")
    print(f"Confidence: {confidence_counts}")
    print(f"Encode time: {encode_seconds:.1f}s")
    print(f"Wrote {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
