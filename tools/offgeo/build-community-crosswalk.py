#!/usr/bin/env python3
"""Build the OFF-009 feed-community crosswalk: map the calls-feed's
`Community`/`ServiceArea` strings deterministically onto SanGIS Address
Points' `COMMUNITY` values, and report anything that doesn't map cleanly.

Reads:
  - Every snapshot under build/offgeo-sources/calls-snapshots/ (see
    capture-calls-snapshot.py) for feed Community/ServiceArea values.
  - The retained sangis-address-points archive (see fetch-sources.py) for
    the full distinct COMMUNITY value set -- streamed directly from the
    .dbf rather than reused from profile-sources.py's report, because that
    report only keeps the top 20 communities and this crosswalk needs every
    value, including the rare ones the small sheriff-only feed uses.

Match rule: case-fold both sides (Group 2 profiling already found SanGIS
COMMUNITY is not case-normalized at the source -- e.g. "San Diego" and
"SAN DIEGO" are distinct raw strings) and compare on exact case-folded
string equality. This is deliberately not fuzzy/substring matching: a
crosswalk that guesses at near-matches (e.g. "CARDIFF" vs
"CARDIFF BY THE SEA") would be non-deterministic and unreviewable. Anything
that doesn't clear exact case-folded equality is reported as unmapped for a
human to add as an explicit alias, not silently guessed.

Usage: python3 tools/offgeo/build-community-crosswalk.py
Output: tests/offgeo/fixtures/community-crosswalk.json (checked in)
"""
from __future__ import annotations

import glob
import json
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import dbf  # noqa: E402

LOCK_PATH = REPO_ROOT / "tools/offgeo/config/sources.lock.json"
SNAPSHOT_GLOB = str(REPO_ROOT / "build/offgeo-sources/calls-snapshots/*.json")
OUTPUT_PATH = REPO_ROOT / "tests/offgeo/fixtures/community-crosswalk.json"


def load_sangis_communities() -> Counter:
    lock = json.loads(LOCK_PATH.read_text())
    entry = next(e for e in lock["sources"] if e["id"] == "sangis-address-points")
    path = REPO_ROOT / entry["retainedPath"]
    counts: Counter = Counter()
    with zipfile.ZipFile(path) as zf:
        member = next(n for n in zf.namelist() if n.lower().endswith(".dbf"))
        with zf.open(member) as stream:
            header, records = dbf.open_dbf(stream)
            for row in records:
                counts[row["COMMUNITY"]] += 1
    return counts


def load_feed_events() -> list[dict]:
    events: dict[str, dict] = {}
    for path in sorted(glob.glob(SNAPSHOT_GLOB)):
        data = json.loads(Path(path).read_text())
        for event in data.get("Events", []):
            number = event.get("EventNumber")
            if number:
                events[number] = event
    return list(events.values())


def main() -> None:
    sangis_raw_counts = load_sangis_communities()
    # Case-folded canonical set: uppercase value -> total record count across
    # all case variants, plus the distinct raw spellings observed.
    canonical: dict[str, dict] = defaultdict(lambda: {"recordCount": 0, "rawVariants": []})
    for raw, count in sangis_raw_counts.items():
        if raw == "":
            continue
        key = raw.upper()
        canonical[key]["recordCount"] += count
        canonical[key]["rawVariants"].append({"raw": raw, "recordCount": count})

    events = load_feed_events()
    if not events:
        raise SystemExit("no calls-feed snapshots found -- run capture-calls-snapshot.py first")

    feed_community_counts: Counter = Counter()
    feed_service_area_counts: Counter = Counter()
    community_to_service_areas: dict[str, set[str]] = defaultdict(set)
    service_area_to_communities: dict[str, set[str]] = defaultdict(set)

    for event in events:
        community = (event.get("Community") or "").strip()
        service_area = (event.get("ServiceArea") or "").strip()
        feed_community_counts[community] += 1
        feed_service_area_counts[service_area] += 1
        if community and service_area:
            community_to_service_areas[community].add(service_area)
            service_area_to_communities[service_area].add(community)

    mapped = {}
    unmapped = {}
    for community, count in sorted(feed_community_counts.items()):
        if not community:
            continue
        key = community.upper()
        if key in canonical:
            mapped[community] = {
                "feedOccurrences": count,
                "sangisRecordCount": canonical[key]["recordCount"],
                "sangisRawVariants": canonical[key]["rawVariants"],
            }
        else:
            unmapped[community] = {"feedOccurrences": count}

    # Many-to-many check: does any feed Community value appear under more
    # than one ServiceArea in captured data? If so, ServiceArea alone can't
    # disambiguate that community (relevant to spec.md Section 8 duplicate-
    # street resolution).
    community_many_service_areas = {
        c: sorted(areas)
        for c, areas in community_to_service_areas.items()
        if len(areas) > 1
    }

    report = {
        "$schema": "OFF-009 feed-community crosswalk",
        "generatedAt": None,
        "snapshotFilesUsed": [Path(p).name for p in sorted(glob.glob(SNAPSHOT_GLOB))],
        "uniqueFeedEvents": len(events),
        "matchRule": "case-fold exact string equality between feed Community and SanGIS Address Points COMMUNITY",
        "feedCommunityCount": len([c for c in feed_community_counts if c]),
        "feedServiceAreaCount": len([a for a in feed_service_area_counts if a]),
        "mappedCommunities": mapped,
        "unmappedCommunities": unmapped,
        "communitiesSpanningMultipleServiceAreas": community_many_service_areas,
        "serviceAreaToCommunities": {
            area: sorted(communities)
            for area, communities in sorted(service_area_to_communities.items())
        },
    }
    import time
    report["generatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, indent=2) + "\n")

    print(f"Feed events: {len(events)}  distinct feed communities: {report['feedCommunityCount']}  distinct service areas: {report['feedServiceAreaCount']}")
    print(f"Mapped: {len(mapped)}  Unmapped: {len(unmapped)}")
    if unmapped:
        print("Unmapped feed communities (no case-folded SanGIS COMMUNITY match):")
        for c, info in unmapped.items():
            print(f"  {c!r}  ({info['feedOccurrences']} occurrences)")
    if community_many_service_areas:
        print("Communities spanning multiple ServiceAreas in captured data:")
        for c, areas in community_many_service_areas.items():
            print(f"  {c!r} -> {areas}")
    else:
        print("No community spans multiple ServiceAreas in captured data (sample may be too small to be conclusive).")
    print(f"Wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
