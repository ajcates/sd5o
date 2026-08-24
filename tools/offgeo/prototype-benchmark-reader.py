#!/usr/bin/env python3
"""Block-partitioned benchmark reader (`OFF-105`, R1 Group D). Builds a
street-key-partitioned custom-format pack (many small self-contained
blocks via `lib/packformat.py`, plus a small always-resident index),
implements exact street-key lookup against it, and performs real
polyline interpolation (`lib/interpolate.py`) to resolve a house number
to a coordinate -- exactly the two operations `roadmap.md` §5 names for
this item ("exact street/range lookup plus polyline interpolation").

This directly answers `OFF-104`'s own disclosed limitation: that
prototype's lookup benchmark fully decoded the *whole* pack into memory
before timing lookups, unlike SQLite's true partial-read B-tree index.
Here, only the one block a query's street key resolves to is ever
decoded -- a fair like-for-like comparison point against that earlier
SQLite number.

Beyond the roadmap's own ask, this also runs the reader end-to-end
against real ground truth: for real SanGIS address points already known
(from `OFF-103`'s join-quality profiling) to sit within their road's
address range, simulate a real geocode using *only* the street name and
house number (never the known `ROADSEGID` -- that would leak the
answer) and measure the resulting coordinate's distance from the
point's real surveyed location. This is a small precursor signal for
`OFF-106`'s real coverage benchmark and `OFF-107`'s held-out spatial
validation, not a substitute for either -- disclosed as such below.

Usage: python3 tools/offgeo/prototype-benchmark-reader.py
  (requires the roads and address-points readers' output)
Output: build/offgeo-sources/r1-benchmark-reader-report.json (gitignored)
"""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import packformat  # noqa: E402
from interpolate import haversine_meters, interpolate_along_polyline, range_fraction  # noqa: E402
from normalize import canonicalize_direction, canonicalize_street_core_name, canonicalize_suffix, normalize_text  # noqa: E402

ROADS_PATH = REPO_ROOT / "build/offgeo-sources/r1-sangis-roads.jsonl"
ADDRESS_POINTS_PATH = REPO_ROOT / "build/offgeo-sources/r1-sangis-address-points.jsonl"
REPORT_PATH = REPO_ROOT / "build/offgeo-sources/r1-benchmark-reader-report.json"

MAX_RECORDS_PER_BLOCK = 500


def iter_jsonl(path: Path):
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def street_key(pdir: str | None, name: str, postd: str | None, sfx: str | None) -> tuple:
    return (pdir or "", canonicalize_street_core_name(name) if name else "", postd or "", sfx or "")


def load_road_records() -> list[dict]:
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


# --- Block-partitioned pack builder ------------------------------------------


class BlockPartitionedPack:
    def __init__(self, blocks: list[bytes], index: dict[tuple, int]):
        self.blocks = blocks  # block_id -> raw block bytes (each independently decodable)
        self.index = index  # street_key -> block_id

    def lookup_segments(self, key: tuple) -> list[dict]:
        """Cold lookup: always decodes the needed block(s) fresh from
        bytes, no cache -- the fair worst-case per-query cost for a
        reader that queries many different streets in a session (the
        realistic calls-list access pattern), not the best-case of
        repeatedly querying the same street."""
        block_ids = self.index.get(key)
        if not block_ids:
            return []
        out = []
        for block_id in block_ids:
            records = packformat.decode_records(self.blocks[block_id])
            out.extend(r for r in records if street_key(r["pdir"], r["name"], r["postd"], r["sfx"]) == key)
        return out


def build_block_partitioned_pack(records: list[dict]) -> tuple[BlockPartitionedPack, dict]:
    t0 = time.time()
    by_key: dict[tuple, list[dict]] = {}
    for r in records:
        key = street_key(r["pdir"], r["name"], r["postd"], r["sfx"])
        by_key.setdefault(key, []).append(r)

    # Real finding while building this: SanGIS uses several generic
    # placeholder names -- "PRIVATE ROAD" alone covers 18,509 segments
    # county-wide, "ALLEY" 4,973, "PRIVATE DRIVEWAY" 4,341, "UNNAMED
    # MILITARY ROAD" 1,349 -- none of which are one real street. A naive
    # "never split a key's records across blocks" design (tried first,
    # abandoned here) creates one pathologically huge block for each of
    # these, which is slow to decode on every cold lookup and wasteful
    # for a real reader that only wants a handful of records. Fixed by
    # letting oversized groups span multiple blocks -- the index maps a
    # key to a *list* of block ids (almost always length 1) instead of
    # one. A real R2 compiler likely wants to exclude these generic
    # names from the exact-name index entirely (a caller is never going
    # to type "PRIVATE ROAD" as a parsed street name), not just chunk
    # them better -- flagged as a design question for OFF-109/OFF-206,
    # not resolved here.
    ordered_keys = sorted(by_key)
    blocks: list[bytes] = []
    index: dict[tuple, list[int]] = {}

    def flush_chunk(chunk_records: list[dict], chunk_keys: list[tuple]):
        if not chunk_records:
            return
        block_id = len(blocks)
        blocks.append(packformat.encode_records(chunk_records))
        for k in chunk_keys:
            index.setdefault(k, []).append(block_id)

    current_block_records: list[dict] = []
    current_block_keys: list[tuple] = []
    for key in ordered_keys:
        group = by_key[key]
        if len(group) > MAX_RECORDS_PER_BLOCK:
            # Oversized single-key group: flush whatever's pending, then
            # chunk this group alone across as many blocks as it needs.
            flush_chunk(current_block_records, current_block_keys)
            current_block_records, current_block_keys = [], []
            for i in range(0, len(group), MAX_RECORDS_PER_BLOCK):
                flush_chunk(group[i : i + MAX_RECORDS_PER_BLOCK], [key])
            continue
        if current_block_records and len(current_block_records) + len(group) > MAX_RECORDS_PER_BLOCK:
            flush_chunk(current_block_records, current_block_keys)
            current_block_records, current_block_keys = [], []
        current_block_records.extend(group)
        current_block_keys.append(key)
    flush_chunk(current_block_records, current_block_keys)

    import gzip

    block_sizes = [len(b) for b in blocks]
    block_gzip_sizes = [len(gzip.compress(b, compresslevel=9)) for b in blocks]
    index_blob_size = sum(len(json.dumps(list(k)).encode()) + 4 * len(v) for k, v in index.items())  # rough estimate
    oversized_keys = {k: len(v) for k, v in by_key.items() if len(v) > MAX_RECORDS_PER_BLOCK}

    stats = {
        "blockCount": len(blocks),
        "recordCount": len(records),
        "distinctStreetKeys": len(by_key),
        "maxRecordsPerBlock": MAX_RECORDS_PER_BLOCK,
        "avgRecordsPerBlock": round(len(records) / len(blocks), 1) if blocks else 0,
        "oversizedKeyGroups": {" ".join(p for p in k if p): n for k, n in oversized_keys.items()},
        "blockRawBytesMin": min(block_sizes), "blockRawBytesMax": max(block_sizes),
        "blockRawBytesTotal": sum(block_sizes),
        "blockGzipBytesTotal": sum(block_gzip_sizes),
        "indexApproxBytes": index_blob_size,
        "buildSeconds": round(time.time() - t0, 2),
    }
    return BlockPartitionedPack(blocks, index), stats


# --- Range-side selection + interpolation ------------------------------------


def resolve_coordinate(record: dict, house_number: int) -> tuple[float, float] | None:
    """Pick a side (L/R) whose range contains house_number, compute the
    fraction along that range, and interpolate along the segment's own
    geometry. Returns None if neither side contains the number -- this
    segment is not a candidate for this house number.

    Side-selection simplification, disclosed: SanGIS doesn't carry a
    direct odd/even parity flag per side (unlike Census's PARITYL/
    PARITYR) -- when both sides' ranges contain the number, this
    arbitrarily prefers the left side rather than guess at parity from
    the numbers alone. Real R4 scoring will need a better rule; this is
    a benchmark-scoped simplification, not a claim of correctness for
    that rare both-contain case."""
    sides = []
    if not (record["lLow"] == 0 and record["lHigh"] == 0):
        lo, hi = min(record["lLow"], record["lHigh"]), max(record["lLow"], record["lHigh"])
        if lo <= house_number <= hi:
            sides.append(("left", record["lLow"], record["lHigh"]))
    if not (record["rLow"] == 0 and record["rHigh"] == 0):
        lo, hi = min(record["rLow"], record["rHigh"]), max(record["rLow"], record["rHigh"])
        if lo <= house_number <= hi:
            sides.append(("right", record["rLow"], record["rHigh"]))
    if not sides:
        return None

    _side, low, high = sides[0]
    fraction = range_fraction(house_number, low, high)
    if fraction is None:
        fraction = 0.5  # degenerate zero-width range -- fall back to the segment midpoint
    return interpolate_along_polyline(record["points"], fraction)


def geocode(pack: BlockPartitionedPack, key: tuple, house_number: int) -> tuple[float, float] | None:
    """Simulate a real geocode: resolve every segment sharing this
    street key, keep the ones whose range contains house_number,
    deterministically prefer the lowest ROADSEGID if more than one
    does (rare -- overlapping ranges on the same named street)."""
    candidates = pack.lookup_segments(key)
    matching = [r for r in candidates if resolve_coordinate(r, house_number) is not None]
    if not matching:
        return None
    matching.sort(key=lambda r: r["roadsegid"])
    return resolve_coordinate(matching[0], house_number)


# --- Benchmarks ---------------------------------------------------------------


def benchmark_lookup_latency(pack: BlockPartitionedPack, sample_keys: list[tuple]) -> float:
    t0 = time.time()
    for key in sample_keys:
        pack.lookup_segments(key)
    elapsed = time.time() - t0
    return elapsed / len(sample_keys) * 1e6


def load_ground_truth_address_points(road_records_by_id: dict[int, dict]) -> list[dict]:
    """Real address points already known (same containment check as
    profile-join-quality.py) to sit within their joined road's range --
    a clean population to validate the interpolation pipeline against,
    not points already flagged as a data-quality problem."""
    ground_truth = []
    for point in iter_jsonl(ADDRESS_POINTS_PATH):
        if point["hasZeroRoadsegidSentinel"]:
            continue
        road = road_records_by_id.get(point["roadsegid"])
        if road is None:
            continue
        bounds = [v for v in (road["lLow"], road["lHigh"], road["rLow"], road["rHigh"]) if v != 0]
        if not bounds:
            continue
        if not (min(bounds) <= point["houseNumber"] <= max(bounds)):
            continue
        s = point["street"]
        ground_truth.append(
            {
                "key": street_key(s["pdir"], s["name"], s["postd"], s["sfx"]),
                "houseNumber": point["houseNumber"],
                "lon": point["positionWgs84"][0],
                "lat": point["positionWgs84"][1],
            }
        )
    return ground_truth


def main() -> None:
    if not ROADS_PATH.exists():
        raise SystemExit(f"{ROADS_PATH} missing -- run compile-sangis-roads.py first")
    if not ADDRESS_POINTS_PATH.exists():
        raise SystemExit(f"{ADDRESS_POINTS_PATH} missing -- run compile-sangis-address-points.py first")

    print("Loading real roads reader output...")
    records = load_road_records()
    road_records_by_id = {r["roadsegid"]: r for r in records}
    print(f"  {len(records)} records")

    print("\nBuilding block-partitioned pack...")
    pack, pack_stats = build_block_partitioned_pack(records)
    print(f"  {pack_stats['blockCount']} blocks, {pack_stats['distinctStreetKeys']} distinct street keys")
    print(f"  block raw bytes: total {pack_stats['blockRawBytesTotal']:,}, "
          f"min {pack_stats['blockRawBytesMin']:,}, max {pack_stats['blockRawBytesMax']:,}")
    print(f"  block gzip bytes total: {pack_stats['blockGzipBytesTotal']:,} "
          f"(index ~{pack_stats['indexApproxBytes']:,} bytes, always resident)")

    print("\nBenchmarking cold block-decode lookup latency (2000-key seeded random sample)...")
    all_keys = sorted(pack.index)
    sample_keys = random.Random(20260825).sample(all_keys, min(2000, len(all_keys)))
    lookup_us = benchmark_lookup_latency(pack, sample_keys)
    print(f"  {lookup_us:.2f} us/lookup (fresh block decode every time, no cache)")

    print("\nLoading ground-truth address points (already known to be within their road's range)...")
    ground_truth = load_ground_truth_address_points(road_records_by_id)
    print(f"  {len(ground_truth)} candidates")

    sample_size = min(2000, len(ground_truth))
    sample = random.Random(20260825).sample(ground_truth, sample_size)

    print(f"\nRunning {sample_size} real geocodes (street key + house number only, ROADSEGID never used)...")
    t0 = time.time()
    matched = 0
    errors_m = []
    for gt in sample:
        result = geocode(pack, gt["key"], gt["houseNumber"])
        if result is None:
            continue
        matched += 1
        lat, lon = result
        errors_m.append(haversine_meters(lat, lon, gt["lat"], gt["lon"]))
    geocode_seconds = time.time() - t0

    errors_m.sort()
    n = len(errors_m)
    median_error = errors_m[n // 2] if n else None
    p95_error = errors_m[int(n * 0.95)] if n else None

    report = {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "method": (
            "Block-partitioned custom format (packformat.py codec, street-key-aligned blocks up to "
            f"{MAX_RECORDS_PER_BLOCK} records each) -- every lookup decodes only the one block a "
            "street key resolves to, unlike prototype-pack-formats.py's whole-pack-decoded benchmark. "
            "Ground-truth geocode sample uses only street key + house number (never the real "
            "ROADSEGID) to simulate a real query, then measures the interpolated point's distance "
            "from the address point's actual surveyed coordinate via haversine."
        ),
        "pack": pack_stats,
        "lookupLatency": {
            "sampleSize": len(sample_keys),
            "microsecondsPerLookup": round(lookup_us, 2),
            "note": "Cold: fresh block decode every query, no cache -- comparable to prototype-pack-formats.py's SQLite number (34-36 us/lookup), unlike that report's own custom-format number which decoded the whole pack upfront.",
        },
        "groundTruthGeocode": {
            "candidatePoolSize": len(ground_truth),
            "sampleSize": sample_size,
            "matchedCount": matched,
            "matchedRate": round(matched / sample_size, 4) if sample_size else 0,
            "totalSeconds": round(geocode_seconds, 2),
            "medianErrorMeters": round(median_error, 1) if median_error is not None else None,
            "p95ErrorMeters": round(p95_error, 1) if p95_error is not None else None,
            "note": (
                "Precursor signal for OFF-106 (real-address coverage benchmark) and OFF-107 "
                "(held-out spatial validation) -- not a substitute for either. Side selection "
                "when both L/R ranges contain the house number arbitrarily prefers left "
                "(SanGIS has no direct parity flag per side unlike Census); unmatched candidates "
                "are segments where no block's records' range contained the house number under "
                "this simplified selection, not necessarily a real geocoding failure."
            ),
        },
        "knownLimitations": [
            "Side selection (L vs R) has no real parity logic -- arbitrary left-preference when "
            "both sides contain the house number. Real R4 scoring needs a better rule.",
            "No fuzzy/nearest-range fallback -- unmatched candidates are simply not resolved, "
            "matching this benchmark's narrow scope (exact containment only), not R4's full design.",
            "Single-segment selection tie-break is lowest ROADSEGID, not geometric/community "
            "plausibility -- fine for this benchmark, not a real scoring rule.",
        ],
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True))

    print(f"\nMatched: {matched}/{sample_size} ({report['groundTruthGeocode']['matchedRate']:.1%})")
    print(f"Median error: {median_error:.1f} m" if median_error is not None else "Median error: n/a")
    print(f"P95 error: {p95_error:.1f} m" if p95_error is not None else "P95 error: n/a")
    print(f"\nReport: {REPORT_PATH}")


if __name__ == "__main__":
    main()
