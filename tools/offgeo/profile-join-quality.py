#!/usr/bin/env python3
"""Range and join-quality profiling over the real R1 reader output
(`OFF-103`, R1 Group B). Unlike Group 2's `profile-sources.py` (which
profiled raw source bytes before any reader existed), this runs against
`compile-sangis-roads.py` and `compile-sangis-address-points.py`'s actual
JSONL output -- so the join-rate/range-validity numbers here measure
what a downstream compiler stage would actually see, not just each
source's internal shape.

Four passes:

1. Roads range validity (spec.md 6.1 step 9's neighbor requirement,
   §6.3): for each side (left/right) of each road segment, classify the
   address range as absent (both bounds zero), descending (low > high),
   one-sided-zero (exactly one bound zero -- malformed, not "absent"),
   or a plausible ascending range; separately flag extreme spans.
2. Address-point join quality: for every address point, classify its
   `ROADSEGID` reference as the zero sentinel (intentionally unjoined,
   e.g. condo sub-records), joined (resolves to a road this reader also
   emitted), or dangling (a nonzero `ROADSEGID` that doesn't resolve --
   Group 2 profiling found ~0.02% of these directly in the raw source;
   this reruns that measurement against the real reader output). For
   every joined address point, also checks numeric containment against
   the joined road's own combined range as a coarse plausibility signal
   -- not the real interpolation/parity logic R4's geocoder will need,
   just a profiling-grade sanity check.
3. Mix/parity/offset flag distributions: SanGIS `LMIXADDR`/`RMIXADDR`
   (does a side mix odd/even numbers) and Census `PARITYL`/`PARITYR`/
   `OFFSETL`/`OFFSETR` (odd/even/both, and whether the range is offset
   from the true parcel line) -- counted but not yet consumed by any
   scoring logic (that's R4's job); this just proves the fields parse
   and reports their real distribution.
4. Duplicate road geometry: how many distinct `ROADSEGID`s share an
   exactly identical vertex sequence with at least one other segment --
   spec.md 6.3 asks this be de-duplicated before it reaches range/name
   records, so it needs to be counted first.
5. ZIP consistency: for joined address points, does the point's own
   `ADDRZIP` match either side's `L_ZIP`/`R_ZIP` on its joined road --
   a locality/ZIP gap signal, counted, not repaired here.

Usage: python3 tools/offgeo/profile-join-quality.py
  (requires build/offgeo-sources/r1-sangis-roads.jsonl and
   r1-sangis-address-points.jsonl -- run compile-sangis-roads.py and
   compile-sangis-address-points.py first)
Output: build/offgeo-sources/r1-join-quality-report.json (gitignored)
"""
from __future__ import annotations

import json
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROADS_PATH = REPO_ROOT / "build/offgeo-sources/r1-sangis-roads.jsonl"
ADDRESS_POINTS_PATH = REPO_ROOT / "build/offgeo-sources/r1-sangis-address-points.jsonl"
REPORT_PATH = REPO_ROOT / "build/offgeo-sources/r1-join-quality-report.json"

EXTREME_SPAN_THRESHOLD = 20000  # a single block rarely spans more than a few hundred numbers


def classify_side(low: int, high: int) -> str:
    if low == 0 and high == 0:
        return "absent"
    if (low == 0) != (high == 0):
        return "one_bound_zero"  # malformed: a real range needs both ends
    if low > high:
        return "descending"
    return "ascending"


def iter_jsonl(path: Path):
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def main() -> None:
    t0 = time.time()
    if not ROADS_PATH.exists():
        raise SystemExit(f"{ROADS_PATH} missing -- run compile-sangis-roads.py first")
    if not ADDRESS_POINTS_PATH.exists():
        raise SystemExit(f"{ADDRESS_POINTS_PATH} missing -- run compile-sangis-address-points.py first")

    print("Loading roads reader output...")
    roads_by_id: dict[int, dict] = {}
    side_classification_counts = {"left": {}, "right": {}}
    both_sides_absent = 0
    extreme_span_count = 0
    confidence_counts = {"ORDINARY": 0, "FALLBACK": 0, "EXCLUDED": 0}
    lmix_counts: dict[str, int] = {}
    rmix_counts: dict[str, int] = {}
    geometry_hash_counts: dict[str, int] = {}

    for road in iter_jsonl(ROADS_PATH):
        roads_by_id[road["roadsegid"]] = road
        confidence_counts[road["confidence"]] += 1

        ar = road["addressRange"]
        l_low, l_high = int(ar["lLow"]), int(ar["lHigh"])
        r_low, r_high = int(ar["rLow"]), int(ar["rHigh"])

        l_class = classify_side(l_low, l_high)
        r_class = classify_side(r_low, r_high)
        side_classification_counts["left"][l_class] = side_classification_counts["left"].get(l_class, 0) + 1
        side_classification_counts["right"][r_class] = side_classification_counts["right"].get(r_class, 0) + 1

        if l_class == "absent" and r_class == "absent":
            both_sides_absent += 1

        spans = []
        if l_class == "ascending":
            spans.append(l_high - l_low)
        if r_class == "ascending":
            spans.append(r_high - r_low)
        if spans and max(spans) > EXTREME_SPAN_THRESHOLD:
            extreme_span_count += 1

        lmix_key = ar["lMix"] or "(blank)"
        rmix_key = ar["rMix"] or "(blank)"
        lmix_counts[lmix_key] = lmix_counts.get(lmix_key, 0) + 1
        rmix_counts[rmix_key] = rmix_counts.get(rmix_key, 0) + 1

        geom_key = json.dumps(road["geometryWgs84"], separators=(",", ":"))
        geometry_hash_counts[geom_key] = geometry_hash_counts.get(geom_key, 0) + 1

    print(f"  {len(roads_by_id)} roads loaded")

    duplicate_geometry_groups = sum(1 for c in geometry_hash_counts.values() if c > 1)
    duplicate_geometry_segments = sum(c for c in geometry_hash_counts.values() if c > 1)
    del geometry_hash_counts  # only needed for the two counts above

    print("Streaming address points, joining by ROADSEGID...")
    total_points = 0
    unjoined_sentinel = 0
    joined = 0
    dangling = 0
    joined_confidence_counts = {"ORDINARY": 0, "FALLBACK": 0, "EXCLUDED": 0}
    contained_count = 0
    outside_range_count = 0
    no_range_to_check_count = 0
    zip_matched = 0
    zip_mismatched = 0
    zip_not_checkable = 0

    for point in iter_jsonl(ADDRESS_POINTS_PATH):
        total_points += 1
        roadsegid = point["roadsegid"]

        if point["hasZeroRoadsegidSentinel"]:
            unjoined_sentinel += 1
            continue

        road = roads_by_id.get(roadsegid)
        if road is None:
            dangling += 1
            continue

        joined += 1
        joined_confidence_counts[road["confidence"]] += 1

        # ZIP consistency is independent of range containment below --
        # deliberately checked before that block's `continue` so a point
        # with no usable range still gets a ZIP check (an earlier version
        # of this script coupled the two, silently skipping ZIP checks
        # for the 247 no-range points; fixed so the two counts are each
        # complete over the full joined population).
        point_zip = point["zip"]
        road_zips = {z for z in (road["zip"]["left"], road["zip"]["right"]) if z}
        if not point_zip or not road_zips:
            zip_not_checkable += 1
        elif point_zip in road_zips:
            zip_matched += 1
        else:
            zip_mismatched += 1

        ar = road["addressRange"]
        bounds = [int(ar[k]) for k in ("lLow", "lHigh", "rLow", "rHigh") if int(ar[k]) != 0]
        if not bounds:
            no_range_to_check_count += 1
            continue
        lo, hi = min(bounds), max(bounds)
        if lo <= point["houseNumber"] <= hi:
            contained_count += 1
        else:
            outside_range_count += 1

    peak_checked = joined
    report = {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "roads": {
            "recordCount": len(roads_by_id),
            "confidenceCounts": confidence_counts,
            "leftSideClassification": side_classification_counts["left"],
            "rightSideClassification": side_classification_counts["right"],
            "bothSidesAbsentCount": both_sides_absent,
            "bothSidesAbsentRate": round(both_sides_absent / len(roads_by_id), 4),
            "extremeSpanThreshold": EXTREME_SPAN_THRESHOLD,
            "extremeSpanCount": extreme_span_count,
            "lMixAddrCounts": lmix_counts,
            "rMixAddrCounts": rmix_counts,
            "duplicateGeometryGroupCount": duplicate_geometry_groups,
            "duplicateGeometrySegmentCount": duplicate_geometry_segments,
        },
        "addressPointJoin": {
            "totalAddressPoints": total_points,
            "unjoinedSentinelCount": unjoined_sentinel,
            "unjoinedSentinelRate": round(unjoined_sentinel / total_points, 4),
            "joinedCount": joined,
            "joinedRate": round(joined / total_points, 4),
            "danglingCount": dangling,
            "danglingRate": round(dangling / total_points, 4),
            "joinedByRoadConfidence": joined_confidence_counts,
            "rangeContainmentAmongJoined": {
                "checked": peak_checked,
                "containedCount": contained_count,
                "containedRate": round(contained_count / peak_checked, 4) if peak_checked else 0,
                "outsideRangeCount": outside_range_count,
                "outsideRangeRate": round(outside_range_count / peak_checked, 4) if peak_checked else 0,
                "noRangeToCheckCount": no_range_to_check_count,
                "note": (
                    "Coarse min/max-of-all-nonzero-bounds containment, not real "
                    "side/parity-aware interpolation (that's R4). A point failing "
                    "this check is a real candidate for later investigation, not "
                    "proof of a data error on its own -- SanGIS ranges can still be "
                    "revised after an address point was captured."
                ),
            },
            "zipConsistencyAmongJoined": {
                "matched": zip_matched,
                "mismatched": zip_mismatched,
                "notCheckable": zip_not_checkable,
                "matchedRateOfCheckable": (
                    round(zip_matched / (zip_matched + zip_mismatched), 4)
                    if (zip_matched + zip_mismatched)
                    else 0
                ),
                "note": (
                    "Point's ADDRZIP compared against both sides of its joined "
                    "road's L_ZIP/R_ZIP (not just the side its house number is "
                    "actually on -- that needs the same parity/side logic the "
                    "range-containment check above doesn't have either). A "
                    "mismatch here is a real locality/ZIP gap candidate, not "
                    "proof of an error -- ZIP boundaries don't always follow "
                    "road-segment boundaries exactly."
                ),
            },
        },
        "totalSeconds": round(time.time() - t0, 2),
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True))

    print(f"\nRoads: {len(roads_by_id)} records, confidence {confidence_counts}")
    print(f"  Both-sides-absent (no address range at all): {both_sides_absent} ({report['roads']['bothSidesAbsentRate']:.1%})")
    print(f"  Left side classification: {side_classification_counts['left']}")
    print(f"  Right side classification: {side_classification_counts['right']}")
    print(f"  Extreme spans (>{EXTREME_SPAN_THRESHOLD}): {extreme_span_count}")
    print(f"  LMIXADDR: {lmix_counts}, RMIXADDR: {rmix_counts}")
    print(f"  Duplicate geometry: {duplicate_geometry_groups} groups covering {duplicate_geometry_segments} segments")
    print(f"\nAddress points: {total_points} total")
    print(f"  Unjoined (ROADSEGID=0 sentinel): {unjoined_sentinel} ({report['addressPointJoin']['unjoinedSentinelRate']:.1%})")
    print(f"  Joined: {joined} ({report['addressPointJoin']['joinedRate']:.1%})")
    print(f"  Dangling (ROADSEGID set but not found in roads output): {dangling} ({report['addressPointJoin']['danglingRate']:.2%})")
    print(f"  Joined-by-road-confidence: {joined_confidence_counts}")
    print(
        f"  Range containment among joined: {contained_count}/{peak_checked} contained "
        f"({report['addressPointJoin']['rangeContainmentAmongJoined']['containedRate']:.1%}), "
        f"{outside_range_count} outside range, {no_range_to_check_count} had no usable range to check"
    )
    zip_rate = report["addressPointJoin"]["zipConsistencyAmongJoined"]["matchedRateOfCheckable"]
    print(
        f"  ZIP consistency: {zip_matched} matched, {zip_mismatched} mismatched "
        f"({zip_rate:.1%} of checkable), {zip_not_checkable} not checkable"
    )
    print(f"\nReport: {REPORT_PATH}")


if __name__ == "__main__":
    main()
