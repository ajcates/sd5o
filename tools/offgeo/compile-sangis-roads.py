#!/usr/bin/env python3
"""Thin source reader for SanGIS Roads-All (`OFF-101`, R1 Group A -- the
first of the sources listed there; Address Points and the two Census
sources are follow-on work, not done by this script).

Per spec.md 6.1's compiler pipeline steps 3-6:

3. Read geometry and required attributes in the declared source CRS.
4. Transform to WGS84 with an explicit, versioned datum/CRS pipeline.
5. Restrict to San Diego County and usable road/address-range feature
   classes (SanGIS's own Roads-All extract is already county-scoped, so
   this step is the road-status inclusion matrix, not a spatial clip).
6. Normalize names while retaining raw source values for build
   diagnostics.

This is a *thin* reader: it does no geometry simplification, no varint/
dictionary encoding, no cross-source merge with Census. Those are later
pipeline stages (OFF-104 compact-representation prototyping, OFF-105
benchmark reader, R2's real compiler) that this reader's deterministic
output is meant to feed, not duplicate.

Usage: python3 tools/offgeo/compile-sangis-roads.py
Output: build/offgeo-sources/r1-sangis-roads.jsonl (gitignored, ~165k
        lines, one per ROADSEGID, sorted deterministically)
        build/offgeo-sources/r1-sangis-roads-report.json (gitignored)
"""
from __future__ import annotations

import json
import resource
import sys
import time
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import dbf  # noqa: E402
import shp  # noqa: E402
from coords import batch_state_plane_2230_feet_to_wgs84, is_plausible_san_diego_point  # noqa: E402
from normalize import canonicalize_direction, canonicalize_suffix, NORMALIZE_VERSION  # noqa: E402
from road_status import classify_segment, ORDINARY, FALLBACK, EXCLUDED  # noqa: E402

LOCK_PATH = REPO_ROOT / "tools/offgeo/config/sources.lock.json"
OUTPUT_PATH = REPO_ROOT / "build/offgeo-sources/r1-sangis-roads.jsonl"
REPORT_PATH = REPO_ROOT / "build/offgeo-sources/r1-sangis-roads-report.json"

# spec.md 6.1: "Do not merely relabel NAD83 or State Plane coordinates as
# WGS84." This transform pipeline (State Plane EPSG:2230 feet -> WGS84 via
# PROJ cs2cs) is the same one prototyped and control-point-validated in
# tools/offgeo/lib/coords.py -- see notes/offgeo/todo.md OFF-014 for the
# three-landmark validation. Recorded explicitly here per spec.md's
# requirement that the transform be named, not implicit.
TRANSFORM_ID = "state-plane-2230-feet-to-wgs84-cs2cs-v1"


def normalize_street_field(pdir: str, name: str, sfx: str, postd: str) -> dict:
    """SanGIS's RD30* fields are already structurally split (unlike a free-
    text feed address), so this only needs to canonicalize the direction/
    suffix sub-fields, not the full free-text parse normalize.parse_street_name
    does. Raw values are kept alongside per spec.md 6.1 step 6."""
    return {
        "pdirRaw": pdir,
        "pdir": canonicalize_direction(pdir) if pdir else None,
        "name": name,
        "sfxRaw": sfx,
        "sfx": canonicalize_suffix(sfx) if sfx else None,
        "postdRaw": postd,
        "postd": canonicalize_direction(postd) if postd else None,
    }


def read_attributes(retained_path: Path) -> list[dict]:
    with zipfile.ZipFile(retained_path) as zf:
        member = next(n for n in zf.namelist() if n.lower().endswith(".dbf"))
        with zf.open(member) as stream:
            header, records = dbf.open_dbf(stream)
            rows = list(records)
            if len(rows) != header.record_count:
                raise RuntimeError(
                    f"DBF record_count ({header.record_count}) != rows actually yielded ({len(rows)}) "
                    "-- likely deleted records present, which would desync the .shp/.dbf join this "
                    "script assumes. Investigate before trusting this run's output."
                )
            return rows


def read_geometry(retained_path: Path) -> list[tuple[tuple, list[list[tuple[float, float]]]]]:
    with zipfile.ZipFile(retained_path) as zf:
        member = next(n for n in zf.namelist() if n.lower().endswith(".shp"))
        with zf.open(member) as stream:
            header = shp.read_header(stream)
            if header["shapeType"] not in (3, 13):
                raise RuntimeError(f"unexpected shape type {header['shapeType']}")
            return list(shp.iter_polylines(stream))


def main() -> None:
    t0 = time.time()
    lock = json.loads(LOCK_PATH.read_text())
    entry = next(e for e in lock["sources"] if e["id"] == "sangis-roads-all")
    if not entry.get("retainedPath"):
        raise SystemExit("sangis-roads-all not retained yet -- run fetch-sources.py first")
    retained_path = REPO_ROOT / entry["retainedPath"]

    print("Reading attributes (.dbf)...")
    attr_rows = read_attributes(retained_path)
    print(f"  {len(attr_rows)} attribute rows")

    print("Reading geometry (.shp)...")
    geom_rows = read_geometry(retained_path)
    print(f"  {len(geom_rows)} geometry records")

    if len(attr_rows) != len(geom_rows):
        raise SystemExit(
            f".dbf row count ({len(attr_rows)}) != .shp record count ({len(geom_rows)}) -- "
            "cannot safely join by position"
        )

    # Flatten every vertex from every part of every record into one big
    # ordered list, transform once in a single batched cs2cs call (the
    # approach coords.py already establishes: one subprocess for the whole
    # dataset, not one per point/segment), then re-assemble.
    flat_points: list[tuple[float, float]] = []
    part_boundaries: list[list[int]] = []  # per record: list of part lengths
    for _bbox, parts in geom_rows:
        lengths = []
        for part in parts:
            lengths.append(len(part))
            flat_points.extend(part)
        part_boundaries.append(lengths)

    print(f"Transforming {len(flat_points)} vertices via cs2cs ({TRANSFORM_ID})...")
    t_transform_start = time.time()
    flat_wgs84 = batch_state_plane_2230_feet_to_wgs84(flat_points)
    transform_seconds = time.time() - t_transform_start
    print(f"  done in {transform_seconds:.1f}s ({len(flat_points) / max(transform_seconds, 0.001):.0f} pts/sec)")

    confidence_counts = {ORDINARY: 0, FALLBACK: 0, EXCLUDED: 0}
    reason_counts: dict[str, int] = {}
    zero_sentinel_count = 0
    implausible_transformed_count = 0

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    cursor = 0
    records_out = []
    for attrs, (bbox, parts), lengths in zip(attr_rows, geom_rows, part_boundaries):
        wgs84_parts: list[list[list[float]]] = []
        for length in lengths:
            pts = flat_wgs84[cursor : cursor + length]
            cursor += length
            # GeoJSON-style [lon, lat] order, called out explicitly to
            # avoid the exact class of axis-order mistake this project has
            # already found once (see coords.py's Texas-panhandle finding).
            wgs84_parts.append([[lon, lat] for lat, lon in pts])

        has_zero_sentinel = any(
            (x == 0.0 and y == 0.0)
            for key_x, key_y in (("FRXCOORD", "FRYCOORD"), ("TOXCOORD", "TOYCOORD"))
            for x, y in [(float(attrs[key_x] or 0), float(attrs[key_y] or 0))]
        )
        if has_zero_sentinel:
            zero_sentinel_count += 1

        any_implausible = any(
            not is_plausible_san_diego_point(lat, lon) for part in wgs84_parts for lon, lat in part
        )
        if any_implausible:
            implausible_transformed_count += 1

        classification = classify_segment(
            segstat=attrs["SEGSTAT"], dedstat=attrs["DEDSTAT"], pending=attrs["PENDING"], funclass=attrs["FUNCLASS"]
        )
        confidence_counts[classification.confidence] += 1
        for reason in classification.reasons:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

        records_out.append(
            {
                "roadsegid": int(attrs["ROADSEGID"]),
                "geometryWgs84": wgs84_parts,
                "hasZeroCoordSentinel": has_zero_sentinel,
                "street": normalize_street_field(
                    attrs["RD30PRED"], attrs["RD30NAME"], attrs["RD30SFX"], attrs["RD30POSTD"]
                ),
                "addressRange": {
                    "lLow": attrs["LLOWADDR"],
                    "lHigh": attrs["LHIGHADDR"],
                    "rLow": attrs["RLOWADDR"],
                    "rHigh": attrs["RHIGHADDR"],
                    "lMix": attrs["LMIXADDR"],
                    "rMix": attrs["RMIXADDR"],
                },
                "jurisdiction": {"left": attrs["LJURISDIC"], "right": attrs["RJURISDIC"]},
                "zip": {"left": attrs["L_ZIP"], "right": attrs["R_ZIP"]},
                "confidence": classification.confidence,
                "confidenceReasons": classification.reasons,
                "rawStatus": {
                    "segstat": attrs["SEGSTAT"],
                    "dedstat": attrs["DEDSTAT"],
                    "pending": attrs["PENDING"],
                    "funclass": attrs["FUNCLASS"],
                },
            }
        )

    # Deterministic output per spec.md 6.1: identical source bytes must
    # produce an identical output. ROADSEGID is confirmed 100% unique
    # (Group 2 profiling), so sorting by it alone is a total, stable order.
    records_out.sort(key=lambda r: r["roadsegid"])

    with OUTPUT_PATH.open("w") as f:
        for record in records_out:
            f.write(json.dumps(record, separators=(",", ":"), sort_keys=True))
            f.write("\n")

    peak_rss_mib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    report = {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sourceId": "sangis-roads-all",
        "sourceSha256": entry["sha256"],
        "transformId": TRANSFORM_ID,
        "normalizeVersion": NORMALIZE_VERSION,
        "recordCount": len(records_out),
        "vertexCount": len(flat_points),
        "transformSeconds": round(transform_seconds, 2),
        "totalSeconds": round(time.time() - t0, 2),
        "peakRssMib": round(peak_rss_mib, 1),
        "confidenceCounts": confidence_counts,
        "fallbackExcludedReasonCounts": reason_counts,
        "zeroCoordSentinelCount": zero_sentinel_count,
        "implausibleAfterTransformCount": implausible_transformed_count,
        "outputPath": str(OUTPUT_PATH.relative_to(REPO_ROOT)),
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True))

    print(f"\nWrote {len(records_out)} records to {OUTPUT_PATH}")
    print(f"Confidence: {confidence_counts}")
    print(f"Zero-coord-sentinel segments: {zero_sentinel_count}")
    print(f"Implausible-after-transform segments: {implausible_transformed_count}")
    print(f"Peak RSS: {peak_rss_mib:.0f} MiB, total time: {time.time() - t0:.1f}s")
    print(f"Report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
