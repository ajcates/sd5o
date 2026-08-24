#!/usr/bin/env python3
"""Community disambiguation prototype (`OFF-112`, R1). Measures duplicate
street names before and after using the feed-community crosswalk
(`OFF-009`, R0 Group 3) to scope candidates -- the roadmap's own framing
for this item.

"Before": for every canonical street key (from the real SanGIS Address
Points reader output), how many distinct SanGIS communities does it
appear in county-wide? A key appearing in 2+ communities is ambiguous if
a geocoder ignores community entirely.

"After": for each of the 18 real feed `Community` values captured in the
R0 Group 3 crosswalk fixture, resolve it to a SanGIS community via the
crosswalk, then count how many of the *county-wide-ambiguous* keys
actually occur within that one resolved community's own address points.
Scoping to a single community trivially disambiguates any key that
doesn't also repeat *within* that same community (the common case), but
the crosswalk's real disambiguation value depends on whether a feed
community resolves at all -- the 4 unmapped/many-to-many communities
found in `OFF-009` get none of this benefit.

Usage: python3 tools/offgeo/prototype-community-disambiguation.py
  (requires r1-sangis-address-points.jsonl and the R0 Group 3
   community-crosswalk fixture)
Output: build/offgeo-sources/r1-community-disambiguation-report.json (gitignored)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from normalize import canonicalize_direction, canonicalize_street_core_name, canonicalize_suffix, normalize_text  # noqa: E402

ADDRESS_POINTS_PATH = REPO_ROOT / "build/offgeo-sources/r1-sangis-address-points.jsonl"
CROSSWALK_PATH = REPO_ROOT / "tests/offgeo/fixtures/community-crosswalk.json"
REPORT_PATH = REPO_ROOT / "build/offgeo-sources/r1-community-disambiguation-report.json"


def iter_jsonl(path: Path):
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def street_key(street: dict) -> tuple:
    pdir = canonicalize_direction(normalize_text(street["pdirRaw"])) if street["pdirRaw"] else None
    name = canonicalize_street_core_name(street["name"]) if street["name"] else ""
    postd = canonicalize_direction(normalize_text(street["postdRaw"])) if street["postdRaw"] else None
    sfx = canonicalize_suffix(normalize_text(street["sfxRaw"])) if street["sfxRaw"] else None
    return (pdir or "", name, postd or "", sfx or "")


def main() -> None:
    t0 = time.time()
    if not ADDRESS_POINTS_PATH.exists():
        raise SystemExit(f"{ADDRESS_POINTS_PATH} missing -- run compile-sangis-address-points.py first")
    if not CROSSWALK_PATH.exists():
        raise SystemExit(f"{CROSSWALK_PATH} missing -- run build-community-crosswalk.py first")

    print("Building street-key -> community-set map from real address points...")
    key_communities: dict[tuple, set[str]] = {}
    # street_key -> community(case-folded) -> point count, so we can also
    # report how *often* an ambiguous key actually occurs in each community
    # (an ambiguous key with 1 stray address point in a second community is
    # a much smaller practical problem than a 50/50 split).
    key_community_counts: dict[tuple, dict[str, int]] = {}
    total_points = 0
    for point in iter_jsonl(ADDRESS_POINTS_PATH):
        total_points += 1
        community = (point["communityRaw"] or "").strip().casefold()
        if not community:
            continue
        key = street_key(point["street"])
        if not key[1]:
            continue
        key_communities.setdefault(key, set()).add(community)
        counts = key_community_counts.setdefault(key, {})
        counts[community] = counts.get(community, 0) + 1

    total_keys = len(key_communities)
    ambiguous_keys = {k for k, comms in key_communities.items() if len(comms) > 1}
    print(f"  {total_keys} distinct street keys with a known community, from {total_points} address points")
    print(f"  {len(ambiguous_keys)} keys ({len(ambiguous_keys) / total_keys:.1%}) span 2+ communities county-wide")

    print("Loading the real OFF-009 feed-community crosswalk fixture...")
    crosswalk = json.loads(CROSSWALK_PATH.read_text())
    mapped = crosswalk["mappedCommunities"]
    unmapped = crosswalk["unmappedCommunities"]

    per_community_results = []
    total_feed_occurrences_mapped = 0
    total_feed_occurrences_unmapped = 0

    for feed_community, info in sorted(mapped.items()):
        total_feed_occurrences_mapped += info["feedOccurrences"]
        resolved_raw_values = {v["raw"].strip().casefold() for v in info["sangisRawVariants"]}
        # How many of the county-wide-ambiguous keys actually have any
        # presence in this specific resolved community?
        still_relevant = [k for k in ambiguous_keys if resolved_raw_values & key_communities[k]]
        # Of those, does this community hold the dominant share of that
        # key's points, or is it a close/ambiguous split even within reach
        # of this one community (rare, but worth counting rather than
        # assuming scoping always fully resolves it)?
        close_split_count = 0
        for k in still_relevant:
            counts = key_community_counts[k]
            this_count = sum(c for name, c in counts.items() if name in resolved_raw_values)
            other_count = sum(c for name, c in counts.items() if name not in resolved_raw_values)
            if other_count and this_count and min(this_count, other_count) / max(this_count, other_count) > 0.2:
                close_split_count += 1
        per_community_results.append(
            {
                "feedCommunity": feed_community,
                "feedOccurrences": info["feedOccurrences"],
                "resolved": True,
                "resolvedRawCommunityCount": len(resolved_raw_values),
                "ambiguousKeysPresentInCommunity": len(still_relevant),
                "ambiguousKeysWithCloseSplit": close_split_count,
            }
        )

    for feed_community, info in sorted(unmapped.items()):
        total_feed_occurrences_unmapped += info["feedOccurrences"]
        per_community_results.append(
            {
                "feedCommunity": feed_community,
                "feedOccurrences": info["feedOccurrences"],
                "resolved": False,
                "resolvedRawCommunityCount": 0,
                "ambiguousKeysPresentInCommunity": None,
                "ambiguousKeysWithCloseSplit": None,
            }
        )

    total_feed_occurrences = total_feed_occurrences_mapped + total_feed_occurrences_unmapped
    close_split_total = sum(r["ambiguousKeysWithCloseSplit"] or 0 for r in per_community_results if r["resolved"])

    report = {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "method": (
            "'Before' = distinct street keys (from real SanGIS Address Points) that appear in "
            "2+ case-folded SanGIS communities county-wide -- ambiguous without any community "
            "scoping. 'After' = for each of the 18 real feed Community values in the R0 Group 3 "
            "crosswalk fixture, how many of those ambiguous keys still have a presence once "
            "scoped to that feed community's resolved SanGIS community (via the crosswalk), and "
            "whether that presence is a close split (>20% of the smaller side) rather than a "
            "dominant majority."
        ),
        "countyWide": {
            "totalAddressPoints": total_points,
            "distinctStreetKeysWithKnownCommunity": total_keys,
            "ambiguousStreetKeyCount": len(ambiguous_keys),
            "ambiguousStreetKeyRate": round(len(ambiguous_keys) / total_keys, 4),
        },
        "byFeedCommunity": per_community_results,
        "summary": {
            "feedCommunitiesResolved": len(mapped),
            "feedCommunitiesUnresolved": len(unmapped),
            "feedOccurrencesResolved": total_feed_occurrences_mapped,
            "feedOccurrencesUnresolved": total_feed_occurrences_unmapped,
            "feedOccurrencesResolvedRate": (
                round(total_feed_occurrences_mapped / total_feed_occurrences, 4) if total_feed_occurrences else 0
            ),
            "ambiguousKeysWithCloseSplitAcrossResolvedCommunities": close_split_total,
        },
        "totalSeconds": round(time.time() - t0, 2),
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True))

    print(f"\nCounty-wide: {len(ambiguous_keys)}/{total_keys} street keys ({len(ambiguous_keys)/total_keys:.1%}) are ambiguous across communities")
    print(f"\nFeed communities: {len(mapped)} resolved ({total_feed_occurrences_mapped} real occurrences), "
          f"{len(unmapped)} unresolved ({total_feed_occurrences_unmapped} real occurrences)")
    print(f"Real-event resolution rate: {report['summary']['feedOccurrencesResolvedRate']:.1%}")
    print(f"\nPer resolved community, ambiguous keys still present after scoping (close-split count in parens):")
    for r in per_community_results:
        if r["resolved"]:
            print(f"  {r['feedCommunity']:20s} {r['ambiguousKeysPresentInCommunity']:4d} present ({r['ambiguousKeysWithCloseSplit']} close-split)")
    print(f"\nUnresolved feed communities (get NO disambiguation benefit from the crosswalk today):")
    for r in per_community_results:
        if not r["resolved"]:
            print(f"  {r['feedCommunity']:25s} {r['feedOccurrences']} real occurrences")
    print(f"\nReport: {REPORT_PATH}")


if __name__ == "__main__":
    main()
