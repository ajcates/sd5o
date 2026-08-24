#!/usr/bin/env python3
"""Compact pack-format prototyping (`OFF-104`, R1 Group D). Compares a
custom binary block format against SQLite -- the maintained alternative
`roadmap.md` §5 explicitly asks for -- encoding the *same* real roads
data (`compile-sangis-roads.py`'s output: 164,555 segments, deduplicated
geometry, address ranges, street names) into each, then measures size
(raw and gzip-compressed, as a stand-in for "bytes actually transferred"
regardless of container), a whole-blob SHA-256 checksum, and exact
street-key lookup latency for both.

Deliberately does NOT decide anything (`OFF-109` is the recorded-decision
item) -- this produces the comparison data that decision needs. Also
does not attempt PBF: Python has no stdlib protobuf implementation, and
prototyping a third format on top of two working ones was judged lower
value than getting the custom-vs-SQLite comparison right first; SQLite
alone already satisfies roadmap.md §5's "at least one maintained
alternative" requirement.

Known limitation, disclosed rather than hidden: the custom format's
lookup benchmark here fully decodes every record into an in-memory
Python dict before timing lookups -- it does not simulate the
block-partitioned, decode-only-what-you-need reading `OFF-105`'s real
benchmark reader (and the eventual browser runtime) will need. SQLite's
own B-tree index naturally supports that kind of partial/lazy read
without extra engineering; the custom format's own would need it built
deliberately in OFF-105/OFF-206 and isn't credited or debited here.

Usage: python3 tools/offgeo/prototype-pack-formats.py
  (requires build/offgeo-sources/r1-sangis-roads.jsonl -- run
   compile-sangis-roads.py first)
Output: build/offgeo-sources/r1-pack-format-comparison-report.json (gitignored)
        build/offgeo-sources/r1-pack-custom.bin(.gz) (gitignored)
        build/offgeo-sources/r1-pack.sqlite(.gz) (gitignored)
"""
from __future__ import annotations

import gzip
import hashlib
import json
import random
import sqlite3
import struct
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from normalize import canonicalize_street_core_name  # noqa: E402
from varint import read_svarint, read_uvarint, write_svarint, write_uvarint  # noqa: E402

ROADS_PATH = REPO_ROOT / "build/offgeo-sources/r1-sangis-roads.jsonl"
REPORT_PATH = REPO_ROOT / "build/offgeo-sources/r1-pack-format-comparison-report.json"
CUSTOM_PATH = REPO_ROOT / "build/offgeo-sources/r1-pack-custom.bin"
SQLITE_PATH = REPO_ROOT / "build/offgeo-sources/r1-pack.sqlite"

COORD_SCALE = 1_000_000  # 6 decimal degrees, ~0.11 m at this latitude -- plenty for interpolation
MAGIC = b"OGP0"  # OffGeo Prototype format 0 -- explicitly NOT "OFG1" (roadmap.md reserves that name for the actual R1 decision)
FORMAT_VERSION = 0

DIRECTION_CODES = [None, "N", "S", "E", "W", "NE", "NW", "SE", "SW"]
DIRECTION_TO_CODE = {d: i for i, d in enumerate(DIRECTION_CODES)}

CONFIDENCE_CODES = {"ORDINARY": 0, "FALLBACK": 1, "EXCLUDED": 2}
CONFIDENCE_BY_CODE = {v: k for k, v in CONFIDENCE_CODES.items()}


def iter_jsonl(path: Path):
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def load_records() -> list[dict]:
    """One simplified record per road, using the same fields for both
    candidates -- confidenceReasons/rawStatus are build diagnostics
    (spec.md 6.1 step 6), not shipped-pack fields, so both candidates
    correctly omit them."""
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
                # Single-part confirmed for the full real dataset (see
                # tools/offgeo/README.md); take part 0 directly rather
                # than carrying multi-part complexity neither candidate
                # below actually needs yet.
                "points": [(pt[1], pt[0]) for pt in road["geometryWgs84"][0]],  # -> (lat, lon)
            }
        )
    return records


# --- Candidate A: custom binary block format --------------------------------


def build_custom_format(records: list[dict]) -> tuple[bytes, dict]:
    t0 = time.time()

    # One shared string pool for names, suffixes, and ZIPs -- all are
    # small, highly-repeated vocabularies (suffix, ZIP) or a name column
    # with heavy repetition across many segments of the same street.
    strings: list[str] = sorted({r["name"] for r in records if r["name"]}
                                 | {r["sfx"] for r in records if r["sfx"]}
                                 | {r["leftZip"] for r in records if r["leftZip"]}
                                 | {r["rightZip"] for r in records if r["rightZip"]})
    string_index = {s: i for i, s in enumerate(strings)}

    # Geometry dedup: identical (lat,lon) point sequences share one
    # entry. Group 2/OFF-103 already found only 3 duplicate groups in
    # the real data, so this saves little bytes-wise here, but spec.md
    # 6.3 requires the de-dup step exist regardless of how much any one
    # dataset happens to benefit from it today.
    geometry_index: dict[tuple, int] = {}
    geometry_table: list[list[tuple[int, int]]] = []
    record_geometry_idx = []
    for r in records:
        scaled = tuple((round(lat * COORD_SCALE), round(lon * COORD_SCALE)) for lat, lon in r["points"])
        idx = geometry_index.get(scaled)
        if idx is None:
            idx = len(geometry_table)
            geometry_index[scaled] = idx
            geometry_table.append(list(scaled))
        record_geometry_idx.append(idx)

    # Serialize strings.
    strings_blob = bytearray()
    strings_blob += write_uvarint(len(strings))
    for s in strings:
        encoded = s.encode("utf-8")
        strings_blob += write_uvarint(len(encoded))
        strings_blob += encoded

    # Serialize geometry: each entry is num_points, then the first point
    # as absolute signed-scaled coords, then each subsequent point as a
    # zigzag-varint delta from the previous one (consecutive polyline
    # vertices are typically tens of meters apart, so deltas are small).
    geometry_blob = bytearray()
    geometry_blob += write_uvarint(len(geometry_table))
    for points in geometry_table:
        geometry_blob += write_uvarint(len(points))
        prev_lat, prev_lon = 0, 0
        for lat, lon in points:
            geometry_blob += write_svarint(lat - prev_lat)
            geometry_blob += write_svarint(lon - prev_lon)
            prev_lat, prev_lon = lat, lon

    # Serialize records.
    records_blob = bytearray()
    records_blob += write_uvarint(len(records))
    for r, geom_idx in zip(records, record_geometry_idx):
        records_blob += write_uvarint(r["roadsegid"])
        records_blob += write_uvarint(string_index[r["name"]] + 1 if r["name"] else 0)
        records_blob.append(DIRECTION_TO_CODE[r["pdir"]])
        records_blob.append(DIRECTION_TO_CODE[r["postd"]])
        records_blob += write_uvarint(string_index[r["sfx"]] + 1 if r["sfx"] else 0)
        records_blob += write_uvarint(r["lLow"])
        records_blob += write_uvarint(r["lHigh"])
        records_blob += write_uvarint(r["rLow"])
        records_blob += write_uvarint(r["rHigh"])
        flags = (1 if r["lMix"] else 0) | (2 if r["rMix"] else 0) | (CONFIDENCE_CODES[r["confidence"]] << 2)
        records_blob.append(flags)
        records_blob += write_uvarint(string_index[r["leftZip"]] + 1 if r["leftZip"] else 0)
        records_blob += write_uvarint(string_index[r["rightZip"]] + 1 if r["rightZip"] else 0)
        records_blob += write_uvarint(geom_idx)

    header = MAGIC + struct.pack("<B", FORMAT_VERSION)
    header += write_uvarint(len(strings_blob))
    header += write_uvarint(len(geometry_blob))
    header += write_uvarint(len(records_blob))

    blob = bytes(header) + bytes(strings_blob) + bytes(geometry_blob) + bytes(records_blob)

    stats = {
        "distinctStrings": len(strings),
        "distinctGeometries": len(geometry_table),
        "buildSeconds": round(time.time() - t0, 2),
        "stringsBlobBytes": len(strings_blob),
        "geometryBlobBytes": len(geometry_blob),
        "recordsBlobBytes": len(records_blob),
    }
    return blob, stats


def decode_custom_format(blob: bytes) -> list[dict]:
    """Round-trip decode, both to prove correctness and to build the
    in-memory structure the lookup benchmark below queries."""
    if blob[:4] != MAGIC:
        raise ValueError("bad magic")
    version = blob[4]
    if version != FORMAT_VERSION:
        raise ValueError(f"unsupported version {version}")
    offset = 5
    strings_len, offset = read_uvarint(blob, offset)
    geometry_len, offset = read_uvarint(blob, offset)
    records_len, offset = read_uvarint(blob, offset)

    strings_start = offset
    geometry_start = strings_start + strings_len
    records_start = geometry_start + geometry_len

    # Decode strings.
    o = strings_start
    n_strings, o = read_uvarint(blob, o)
    strings = []
    for _ in range(n_strings):
        slen, o = read_uvarint(blob, o)
        strings.append(blob[o : o + slen].decode("utf-8"))
        o += slen
    assert o == geometry_start

    # Decode geometry.
    o = geometry_start
    n_geoms, o = read_uvarint(blob, o)
    geometry_table = []
    for _ in range(n_geoms):
        n_points, o = read_uvarint(blob, o)
        points = []
        prev_lat = prev_lon = 0
        for _ in range(n_points):
            dlat, o = read_svarint(blob, o)
            dlon, o = read_svarint(blob, o)
            prev_lat += dlat
            prev_lon += dlon
            points.append((prev_lat / COORD_SCALE, prev_lon / COORD_SCALE))
        geometry_table.append(points)
    assert o == records_start

    # Decode records.
    o = records_start
    n_records, o = read_uvarint(blob, o)
    out = []
    for _ in range(n_records):
        roadsegid, o = read_uvarint(blob, o)
        name_idx, o = read_uvarint(blob, o)
        pdir_code = blob[o]; o += 1
        postd_code = blob[o]; o += 1
        sfx_idx, o = read_uvarint(blob, o)
        l_low, o = read_uvarint(blob, o)
        l_high, o = read_uvarint(blob, o)
        r_low, o = read_uvarint(blob, o)
        r_high, o = read_uvarint(blob, o)
        flags = blob[o]; o += 1
        left_zip_idx, o = read_uvarint(blob, o)
        right_zip_idx, o = read_uvarint(blob, o)
        geom_idx, o = read_uvarint(blob, o)
        out.append(
            {
                "roadsegid": roadsegid,
                "name": strings[name_idx - 1] if name_idx else "",
                "pdir": DIRECTION_CODES[pdir_code],
                "postd": DIRECTION_CODES[postd_code],
                "sfx": strings[sfx_idx - 1] if sfx_idx else None,
                "lLow": l_low, "lHigh": l_high, "rLow": r_low, "rHigh": r_high,
                "lMix": bool(flags & 1), "rMix": bool(flags & 2),
                "confidence": CONFIDENCE_BY_CODE[flags >> 2],
                "leftZip": strings[left_zip_idx - 1] if left_zip_idx else None,
                "rightZip": strings[right_zip_idx - 1] if right_zip_idx else None,
                "points": geometry_table[geom_idx],
            }
        )
    assert o == len(blob)
    return out


# --- Candidate B: SQLite -----------------------------------------------------


def build_sqlite_format(records: list[dict], db_path: Path) -> dict:
    t0 = time.time()
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE streets (
            id INTEGER PRIMARY KEY,
            pdir TEXT, name TEXT NOT NULL, postd TEXT, sfx TEXT
        );
        CREATE UNIQUE INDEX idx_streets_key ON streets(pdir, name, postd, sfx);

        CREATE TABLE geometry (
            id INTEGER PRIMARY KEY,
            points BLOB NOT NULL
        );

        CREATE TABLE segments (
            roadsegid INTEGER PRIMARY KEY,
            street_id INTEGER NOT NULL REFERENCES streets(id),
            geometry_id INTEGER NOT NULL REFERENCES geometry(id),
            l_low INTEGER, l_high INTEGER, r_low INTEGER, r_high INTEGER,
            l_mix INTEGER, r_mix INTEGER, confidence INTEGER,
            left_zip TEXT, right_zip TEXT
        );
        CREATE INDEX idx_segments_street ON segments(street_id);
        """
    )

    street_ids: dict[tuple, int] = {}
    geometry_ids: dict[tuple, int] = {}

    for r in records:
        street_key = (r["pdir"], r["name"], r["postd"], r["sfx"])
        street_id = street_ids.get(street_key)
        if street_id is None:
            cur.execute(
                "INSERT INTO streets (pdir, name, postd, sfx) VALUES (?, ?, ?, ?)",
                street_key,
            )
            street_id = cur.lastrowid
            street_ids[street_key] = street_id

        scaled = tuple((round(lat * COORD_SCALE), round(lon * COORD_SCALE)) for lat, lon in r["points"])
        geometry_id = geometry_ids.get(scaled)
        if geometry_id is None:
            # Idiomatic SQLite candidate: no manual delta/varint packing
            # -- packed float32 pairs, the straightforward way anyone
            # would store point geometry in a BLOB column.
            blob = struct.pack(f"<{len(scaled) * 2}f", *[c for pair in r["points"] for c in pair])
            cur.execute("INSERT INTO geometry (points) VALUES (?)", (blob,))
            geometry_id = cur.lastrowid
            geometry_ids[scaled] = geometry_id

        cur.execute(
            """INSERT INTO segments
               (roadsegid, street_id, geometry_id, l_low, l_high, r_low, r_high,
                l_mix, r_mix, confidence, left_zip, right_zip)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                r["roadsegid"], street_id, geometry_id,
                r["lLow"], r["lHigh"], r["rLow"], r["rHigh"],
                int(r["lMix"]), int(r["rMix"]), CONFIDENCE_CODES[r["confidence"]],
                r["leftZip"], r["rightZip"],
            ),
        )

    conn.commit()
    cur.execute("ANALYZE")
    conn.commit()
    conn.execute("VACUUM")
    conn.close()

    build_seconds = round(time.time() - t0, 2)
    return {
        "distinctStreets": len(street_ids),
        "distinctGeometries": len(geometry_ids),
        "buildSeconds": build_seconds,
    }


# --- Lookup benchmarks --------------------------------------------------------


def benchmark_custom_lookup(decoded: list[dict], sample_keys: list[tuple]) -> float:
    index: dict[tuple, list[int]] = {}
    for i, r in enumerate(decoded):
        key = (r["pdir"] or "", r["name"], r["postd"] or "", r["sfx"] or "")
        index.setdefault(key, []).append(i)

    t0 = time.time()
    for key in sample_keys:
        _ = index.get(key, [])
    elapsed = time.time() - t0
    return elapsed / len(sample_keys) * 1e6  # microseconds/lookup


def benchmark_sqlite_lookup(db_path: Path, sample_keys: list[tuple]) -> float:
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    t0 = time.time()
    for pdir, name, postd, sfx in sample_keys:
        cur.execute(
            """SELECT segments.roadsegid FROM segments
               JOIN streets ON streets.id = segments.street_id
               WHERE streets.pdir IS ? AND streets.name = ? AND streets.postd IS ? AND streets.sfx IS ?""",
            (pdir or None, name, postd or None, sfx or None),
        )
        cur.fetchall()
    elapsed = time.time() - t0
    conn.close()
    return elapsed / len(sample_keys) * 1e6


def gzip_size(data: bytes) -> int:
    return len(gzip.compress(data, compresslevel=9))


def main() -> None:
    if not ROADS_PATH.exists():
        raise SystemExit(f"{ROADS_PATH} missing -- run compile-sangis-roads.py first")

    print("Loading real roads reader output...")
    records = load_records()
    print(f"  {len(records)} records")

    print("\nBuilding candidate A (custom binary format)...")
    custom_blob, custom_stats = build_custom_format(records)
    CUSTOM_PATH.write_bytes(custom_blob)
    custom_gz_bytes = gzip_size(custom_blob)
    custom_sha256 = hashlib.sha256(custom_blob).hexdigest()
    print(f"  raw {len(custom_blob):,} bytes, gzip {custom_gz_bytes:,} bytes, built in {custom_stats['buildSeconds']}s")

    print("Round-trip decoding candidate A to verify correctness...")
    decoded = decode_custom_format(custom_blob)
    assert len(decoded) == len(records)
    for original, got in zip(records, decoded):
        assert original["roadsegid"] == got["roadsegid"]
        assert original["name"] == got["name"]
        assert original["pdir"] == got["pdir"]
        assert original["postd"] == got["postd"]
        assert original["sfx"] == got["sfx"]
        assert original["lLow"] == got["lLow"] and original["lHigh"] == got["lHigh"]
        assert original["rLow"] == got["rLow"] and original["rHigh"] == got["rHigh"]
        assert original["lMix"] == got["lMix"] and original["rMix"] == got["rMix"]
        assert original["confidence"] == got["confidence"]
        assert original["leftZip"] == got["leftZip"] and original["rightZip"] == got["rightZip"]
        assert len(original["points"]) == len(got["points"])
        for (olat, olon), (glat, glon) in zip(original["points"], got["points"]):
            assert abs(olat - glat) < 1e-5 and abs(olon - glon) < 1e-5
    print("  round-trip verified byte-exact on all fields (geometry within COORD_SCALE precision)")

    print("\nBuilding candidate B (SQLite)...")
    sqlite_stats = build_sqlite_format(records, SQLITE_PATH)
    sqlite_raw_bytes = SQLITE_PATH.stat().st_size
    sqlite_bytes = SQLITE_PATH.read_bytes()
    sqlite_gz_bytes = gzip_size(sqlite_bytes)
    sqlite_sha256 = hashlib.sha256(sqlite_bytes).hexdigest()
    print(f"  raw {sqlite_raw_bytes:,} bytes, gzip {sqlite_gz_bytes:,} bytes, built in {sqlite_stats['buildSeconds']}s")

    print("\nBenchmarking exact street-key lookup (2000-key seeded random sample)...")
    all_keys = sorted({(r["pdir"] or "", r["name"], r["postd"] or "", r["sfx"] or "") for r in records})
    sample_keys = random.Random(20260824).sample(all_keys, min(2000, len(all_keys)))
    custom_us = benchmark_custom_lookup(decoded, sample_keys)
    sqlite_us = benchmark_sqlite_lookup(SQLITE_PATH, sample_keys)
    print(f"  custom (in-memory dict, full-decode): {custom_us:.2f} us/lookup")
    print(f"  SQLite (indexed query):               {sqlite_us:.2f} us/lookup")

    report = {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "recordCount": len(records),
        "method": (
            "Both candidates encode the identical real roads dataset (compile-sangis-roads.py's "
            "output, confidenceReasons/rawStatus omitted as build-only diagnostics per spec.md 6.1 "
            "step 6). Size figures are raw bytes on disk and gzip -9 compressed (a stand-in for "
            "bytes actually transferred over a static host, regardless of container format). Lookup "
            "benchmark: 2000 real distinct street keys, seeded random sample, exact match only."
        ),
        "customFormat": {
            "magic": MAGIC.decode(), "version": FORMAT_VERSION,
            "rawBytes": len(custom_blob), "gzipBytes": custom_gz_bytes,
            "sha256": custom_sha256,
            "lookupMicrosecondsPerQuery": round(custom_us, 2),
            **custom_stats,
            "roundTripVerified": True,
        },
        "sqlite": {
            "rawBytes": sqlite_raw_bytes, "gzipBytes": sqlite_gz_bytes,
            "sha256": sqlite_sha256,
            "lookupMicrosecondsPerQuery": round(sqlite_us, 2),
            **sqlite_stats,
        },
        "comparison": {
            "gzipBytesRatioCustomOverSqlite": round(custom_gz_bytes / sqlite_gz_bytes, 3),
            "lookupSpeedRatioSqliteOverCustom": round(sqlite_us / custom_us, 1),
        },
        "knownLimitations": [
            "PBF not prototyped -- Python has no stdlib protobuf; SQLite alone satisfies the "
            "roadmap's 'at least one maintained alternative' requirement for this pass.",
            "Custom format's lookup benchmark fully decodes every record before timing lookups; "
            "it does not simulate block-partitioned, decode-only-what-you-need reads the way "
            "SQLite's B-tree index naturally supports and the eventual browser runtime will need "
            "(that partial-read design is OFF-105/OFF-206 scope, not built here).",
            "Neither candidate's browser-loading feasibility (a WASM SQLite build like sql.js vs "
            "plain JS decoding the custom format) is tested here -- that's OFF-108/OFF-115 scope.",
        ],
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True))

    print(f"\nSize comparison (gzip): custom {custom_gz_bytes:,} bytes vs SQLite {sqlite_gz_bytes:,} bytes "
          f"({report['comparison']['gzipBytesRatioCustomOverSqlite']}x)")
    print(f"Lookup speed: SQLite is {report['comparison']['lookupSpeedRatioSqliteOverCustom']}x the "
          f"custom format's latency in this (unfair, full-decode) comparison")
    print(f"\nReport: {REPORT_PATH}")


if __name__ == "__main__":
    main()
