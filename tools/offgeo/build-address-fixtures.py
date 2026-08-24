#!/usr/bin/env python3
"""Build the OFF-008 sanitized address fixture corpus from captured
calls-feed snapshots.

Reads every snapshot under build/offgeo-sources/calls-snapshots/ (see
capture-calls-snapshot.py), de-duplicates by EventNumber, keeps only the
`Address` string plus its source Community/ServiceArea (already public,
non-PII feed fields -- EventType, DateTime, IsOpen and EventNumber itself
are dropped since they carry no parsing signal and are the closest thing to
incident-identifying detail in the payload), and classifies each distinct
address string into the syntax categories notes/offgeo/todo.md OFF-008 asks
for. A single address can match more than one category (e.g. it can be both
`ordinary_numbered` and `has_directional`).

This is a rolling corpus: it is only as representative as the snapshots
captured so far (see the "coverage" section printed at the end). Re-run
capture-calls-snapshot.py at different times/days and re-run this script to
grow it -- this script is idempotent and always rebuilds from whatever
snapshots exist on disk.

Usage: python3 tools/offgeo/build-address-fixtures.py
Output: tests/offgeo/fixtures/addresses.json (checked in)
        build/offgeo-sources/address-fixture-report.json (gitignored detail)
"""
from __future__ import annotations

import glob
import json
import re
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_GLOB = str(REPO_ROOT / "build/offgeo-sources/calls-snapshots/*.json")
FIXTURE_PATH = REPO_ROOT / "tests/offgeo/fixtures/addresses.json"
REPORT_PATH = REPO_ROOT / "build/offgeo-sources/address-fixture-report.json"

# All categories notes/offgeo/todo.md OFF-008 asks the corpus to cover.
# Marked here so the report can show which ones real captures have (not yet)
# produced, rather than silently omitting them.
ALL_CATEGORIES = [
    "ordinary_numbered",
    "hundred_block",
    "slash_intersection_spaced",
    "slash_intersection_unspaced",
    "amp_at_intersection",
    "has_directional",
    "numbered_street",
    "highway",
    "alias",
    "street_only",
    "missing_locality",
    "malformed",
    "non_address_text",
]

DIRECTIONAL_RE = re.compile(
    r"\b(N|S|E|W|NE|NW|SE|SW|NORTH|SOUTH|EAST|WEST)\b"
)
NUMBERED_STREET_RE = re.compile(r"\b\d+(ST|ND|RD|TH)\b")
HIGHWAY_RE = re.compile(
    r"\b(INTERSTATE|STATE ROUTE|HIGHWAY|HWY|FREEWAY|US ROUTE|SR-?\d)\b"
)
HUNDRED_BLOCK_RE = re.compile(r"\bBLOCK\b")
LEADING_NUMBER_RE = re.compile(r"^\d+\s")
# Loose "looks like an address token" check: has letters, and either a
# leading number or a '/' (intersection). Anything that clears this is
# assumed to at least be attempting to name a location.
ADDRESS_LIKE_RE = re.compile(r"[A-Za-z]")


def classify(address: str) -> list[str]:
    addr = address.strip()
    cats: list[str] = []

    if not addr or not ADDRESS_LIKE_RE.search(addr):
        cats.append("non_address_text")
        return cats

    is_intersection = "/" in addr
    if is_intersection:
        left, _, right = addr.partition("/")
        if left.endswith(" ") or right.startswith(" "):
            cats.append("slash_intersection_spaced")
        else:
            cats.append("slash_intersection_unspaced")
    if re.search(r"&| AT |@", addr):
        cats.append("amp_at_intersection")

    has_leading_number = bool(LEADING_NUMBER_RE.match(addr))
    if HUNDRED_BLOCK_RE.search(addr):
        cats.append("hundred_block")
    elif has_leading_number and not is_intersection:
        cats.append("ordinary_numbered")
    elif not has_leading_number and not is_intersection:
        cats.append("street_only")

    if DIRECTIONAL_RE.search(addr):
        cats.append("has_directional")
    if NUMBERED_STREET_RE.search(addr):
        cats.append("numbered_street")
    if HIGHWAY_RE.search(addr):
        cats.append("highway")

    if not cats:
        cats.append("malformed")
    return cats


def load_events() -> dict[str, dict]:
    events: dict[str, dict] = {}
    for path in sorted(glob.glob(SNAPSHOT_GLOB)):
        data = json.loads(Path(path).read_text())
        for event in data.get("Events", []):
            number = event.get("EventNumber")
            if not number:
                continue
            events[number] = event
    return events


def main() -> None:
    snapshot_paths = sorted(glob.glob(SNAPSHOT_GLOB))
    if not snapshot_paths:
        raise SystemExit(
            "no snapshots found -- run capture-calls-snapshot.py first"
        )
    events = load_events()

    # De-duplicate by the address string itself (not EventNumber): the
    # fixture corpus tests parsing, and the same street sees many calls.
    by_address: dict[str, dict] = {}
    for event in events.values():
        addr = (event.get("Address") or "").strip()
        entry = by_address.setdefault(
            addr,
            {
                "address": addr,
                "categories": classify(addr),
                "occurrences": 0,
                "communities": Counter(),
            },
        )
        entry["occurrences"] += 1
        community = event.get("Community") or ""
        entry["communities"][community] += 1
        if not community:
            if "missing_locality" not in entry["categories"]:
                entry["categories"].append("missing_locality")

    fixtures = []
    for entry in sorted(by_address.values(), key=lambda e: e["address"]):
        fixtures.append(
            {
                "address": entry["address"],
                "categories": entry["categories"],
                "occurrences": entry["occurrences"],
                "communities": sorted(entry["communities"]),
            }
        )

    category_counts = Counter()
    for f in fixtures:
        for c in f["categories"]:
            category_counts[c] += 1

    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_text(
        json.dumps(
            {
                "$schema": "OFF-008 sanitized address fixture corpus",
                "source": "leag-caddata calls-for-service feed (public Address/Community/ServiceArea fields only)",
                "snapshotCount": len(snapshot_paths),
                "uniqueEvents": len(events),
                "uniqueAddresses": len(fixtures),
                "fixtures": fixtures,
            },
            indent=2,
        )
        + "\n"
    )

    report = {
        "snapshotFiles": [Path(p).name for p in snapshot_paths],
        "uniqueEvents": len(events),
        "uniqueAddresses": len(fixtures),
        "categoryCounts": dict(category_counts),
        "categoriesNotYetObserved": [
            c for c in ALL_CATEGORIES if category_counts.get(c, 0) == 0
        ],
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n")

    print(f"Snapshots: {len(snapshot_paths)}  unique events: {len(events)}  unique addresses: {len(fixtures)}")
    print(f"Wrote {FIXTURE_PATH.relative_to(REPO_ROOT)}")
    print(f"Wrote {REPORT_PATH.relative_to(REPO_ROOT)}")
    print("\nCategory counts:")
    for cat in ALL_CATEGORIES:
        print(f"  {cat:<28} {category_counts.get(cat, 0)}")
    not_observed = report["categoriesNotYetObserved"]
    if not_observed:
        print(f"\nNot yet observed in real captures: {', '.join(not_observed)}")


if __name__ == "__main__":
    main()
