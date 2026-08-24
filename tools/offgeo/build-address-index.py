#!/usr/bin/env python3
"""Build a small, honest address -> WGS84 coordinate lookup for the map
prototype (notes/offgeo/todo.md Group 4 follow-on, map-view feature).

This is NOT the real OffGeo geocoder (that's R1-R4: normalization, range
interpolation over road geometry, confidence scoring). It's a much smaller
thing, scoped to only the communities the live calls feed has actually
been observed dispatching to (tests/offgeo/fixtures/community-crosswalk.json
's mapped communities, built in Group 3):

- Index key: the street name portion of an address ("PDIR NAME POSTD SFX",
  normalized), mapping to every known SanGIS address point's (house
  number, lat, lon) on that street, sorted by number.
- Client-side lookup (src/app/geocoder.js) splits a call's Address into
  a leading house number and the street-key remainder, and either finds
  an exact house-number match, or the nearest known point on that same
  street within a bounded delta (see MAX_NEAREST_DELTA there) --
  explicitly labeled "approximate" when it's a nearest-match, not an
  exact one. An initial exact-only version of this script measured only
  4/43 hits against the Group 3 fixture corpus: SanGIS's address points
  are real parcels, not every integer house number, so exact-only
  matching badly undercounts. Nearest-on-street is a bounded, explainable
  approximation (not the same as inventing a result), and is exactly the
  gap the real R1/R2 range-interpolation compiler is meant to close
  properly later.

Usage: python3 tools/offgeo/build-address-index.py
Output: src/app/data/address-index.json (checked in; small enough to ship)
        build/offgeo-sources/address-index-report.json (gitignored detail)
"""
from __future__ import annotations

import json
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import dbf  # noqa: E402
from coords import batch_state_plane_2230_feet_to_wgs84, is_plausible_san_diego_point  # noqa: E402

LOCK_PATH = REPO_ROOT / "tools/offgeo/config/sources.lock.json"
CROSSWALK_PATH = REPO_ROOT / "tests/offgeo/fixtures/community-crosswalk.json"
OUTPUT_PATH = REPO_ROOT / "src/app/data/address-index.json"
REPORT_PATH = REPO_ROOT / "build/offgeo-sources/address-index-report.json"

# Confirmed against the real Group 3 calls-feed fixture corpus
# (tests/offgeo/fixtures/addresses.json): the feed uses these shorter
# suffix forms where SanGIS's ADDRSFX spells them out (e.g. feed
# "2300 ALPINE BL" vs SanGIS ADDRSFX "BLVD" for the same street). Only
# aliases with direct evidence from real captured addresses are added --
# guessing at unconfirmed abbreviations risks a wrong street match.
FEED_SUFFIX_ALIASES = {"BLVD": "BL", "AVE": "AV"}


def load_allowed_communities() -> set[str]:
    crosswalk = json.loads(CROSSWALK_PATH.read_text())
    allowed = set()
    for info in crosswalk["mappedCommunities"].values():
        for variant in info["sangisRawVariants"]:
            allowed.add(variant["raw"])
    return allowed


def street_key(row: dict, suffix: str) -> str:
    parts = [row["ADDRPDIR"], row["ADDRNAME"], row["ADDRPOSTD"], suffix]
    return " ".join(p for p in parts if p).strip().upper()


def main() -> None:
    lock = json.loads(LOCK_PATH.read_text())
    entry = next(e for e in lock["sources"] if e["id"] == "sangis-address-points")
    if not entry.get("retainedPath"):
        raise SystemExit("sangis-address-points not retained yet -- run fetch-sources.py first")

    allowed_communities = load_allowed_communities()
    print(f"Scoping to {len(allowed_communities)} SanGIS COMMUNITY raw values (from the feed crosswalk).")

    path = REPO_ROOT / entry["retainedPath"]
    # street_key -> list of (number, x_ft, y_ft)
    by_street: dict[str, list[tuple[int, float, float]]] = defaultdict(list)
    total_rows = 0
    in_scope_rows = 0
    skipped_no_number = 0
    skipped_zero_coord = 0

    with zipfile.ZipFile(path) as zf:
        member = next(n for n in zf.namelist() if n.lower().endswith(".dbf"))
        with zf.open(member) as stream:
            header, records = dbf.open_dbf(stream)
            for row in records:
                total_rows += 1
                if row["COMMUNITY"] not in allowed_communities:
                    continue
                in_scope_rows += 1

                number_raw = row["ADDRNMBR"]
                if not number_raw:
                    skipped_no_number += 1
                    continue
                try:
                    number = int(float(number_raw))
                    x, y = float(row["X_COORD"]), float(row["Y_COORD"])
                except ValueError:
                    skipped_no_number += 1
                    continue
                if x == 0.0 and y == 0.0:
                    skipped_zero_coord += 1
                    continue  # the zero-coordinate sentinel found during Group 2 profiling

                sfx = row["ADDRSFX"]
                for key in {street_key(row, sfx), street_key(row, FEED_SUFFIX_ALIASES.get(sfx, sfx))}:
                    if key:
                        by_street[key].append((number, x, y))

    print(f"Scanned {total_rows} address points, {in_scope_rows} in scope, {len(by_street)} distinct streets.")
    print("Transforming State Plane -> WGS84 via cs2cs ...")

    all_points = [(x, y) for points in by_street.values() for (_n, x, y) in points]
    all_coords = iter(batch_state_plane_2230_feet_to_wgs84(all_points))

    index: dict[str, list[list[float]]] = {}
    total_points = 0
    implausible = 0
    for key, points in by_street.items():
        entries = []
        for number, _x, _y in sorted(points):
            lat, lon = next(all_coords)
            if not is_plausible_san_diego_point(lat, lon):
                implausible += 1
                continue
            entries.append([number, round(lat, 6), round(lon, 6)])
            total_points += 1
        if entries:
            index[key] = entries

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(index, separators=(",", ":")) + "\n")
    size_bytes = OUTPUT_PATH.stat().st_size

    report = {
        "allowedCommunityCount": len(allowed_communities),
        "totalAddressPointRows": total_rows,
        "inScopeRows": in_scope_rows,
        "skippedNoParsableNumber": skipped_no_number,
        "skippedZeroCoordinate": skipped_zero_coord,
        "implausibleCoordinateCount": implausible,
        "streetKeyCount": len(index),
        "totalPointCount": total_points,
        "outputBytes": size_bytes,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n")

    print(
        f"Wrote {len(index)} streets / {total_points} points "
        f"({size_bytes / 1_000_000:.2f} MB) to {OUTPUT_PATH.relative_to(REPO_ROOT)}"
    )
    print(f"Wrote {REPORT_PATH.relative_to(REPO_ROOT)}")

    fixtures_path = REPO_ROOT / "tests/offgeo/fixtures/addresses.json"
    if fixtures_path.exists():
        fixtures = json.loads(fixtures_path.read_text())["fixtures"]
        non_intersection = [
            f
            for f in fixtures
            if "slash_intersection_unspaced" not in f["categories"] and "slash_intersection_spaced" not in f["categories"]
        ]
        exact_hits = 0
        nearest_hits = 0
        MAX_DELTA = 300
        for f in non_intersection:
            addr = f["address"].strip().upper()
            head, _, rest = addr.partition(" ")
            if not head.isdigit():
                continue
            number = int(head)
            points = index.get(rest)
            if not points:
                continue
            numbers = [p[0] for p in points]
            if number in numbers:
                exact_hits += 1
            else:
                nearest = min(numbers, key=lambda n: abs(n - number))
                if abs(nearest - number) <= MAX_DELTA:
                    nearest_hits += 1
        print(
            f"Validation against Group 3 fixture corpus: {exact_hits} exact + {nearest_hits} nearest-within-{MAX_DELTA} "
            f"= {exact_hits + nearest_hits}/{len(non_intersection)} non-intersection addresses resolvable."
        )


if __name__ == "__main__":
    main()
