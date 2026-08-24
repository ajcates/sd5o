#!/usr/bin/env python3
"""Thin source reader for SanGIS Address Points to APN (`OFF-101`, R1
Group A -- second of the sources listed there, alongside
compile-sangis-roads.py; the two Census sources are still follow-on work).

Per spec.md 6.1's compiler pipeline steps 3-6, and 79's explicit scoping
note: "The address-point source is primarily a compiler-side join and
validation set. ... do not ship APN, parcel ID, unit, or other unused
property identifiers." This reader honors that -- `APN`, `PARCELID`,
`ADDRAPNID`, and `ADDRUNIT` are read from the source (to prove they exist
and are excluded on purpose, not by omission) but never written to output.

Unlike compile-sangis-roads.py, this reader does not touch the `.shp`
member at all: Address_Points.dbf already carries `X_COORD`/`Y_COORD` as
attribute fields (confirmed identical in meaning to the point geometry by
SanGIS's own schema), so there is no need to add Point/PointZ support to
tools/offgeo/lib/shp.py (which currently only reads PolyLine/PolyLineZ)
just to duplicate coordinates already present in the table.

This is a *thin* reader in the same sense as the roads one: no geometry
simplification beyond the required CRS transform, no cross-source merge,
no community-crosswalk scoping (unlike the map-prototype's
build-address-index.py, this reads every row county-wide, not just the
communities the live calls feed happens to have hit so far -- OFF-101 is
compiler-grade source coverage, not a feature-scoped prototype).

Usage: python3 tools/offgeo/compile-sangis-address-points.py
Output: build/offgeo-sources/r1-sangis-address-points.jsonl (gitignored,
        ~1.22M lines, one per ORIG_OID, sorted deterministically)
        build/offgeo-sources/r1-sangis-address-points-report.json (gitignored)
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
from coords import batch_state_plane_2230_feet_to_wgs84, is_plausible_san_diego_point  # noqa: E402
from normalize import canonicalize_direction, canonicalize_suffix, NORMALIZE_VERSION  # noqa: E402

LOCK_PATH = REPO_ROOT / "tools/offgeo/config/sources.lock.json"
OUTPUT_PATH = REPO_ROOT / "build/offgeo-sources/r1-sangis-address-points.jsonl"
REPORT_PATH = REPO_ROOT / "build/offgeo-sources/r1-sangis-address-points-report.json"

# Same named transform as compile-sangis-roads.py -- both SanGIS sources
# ship the same State Plane EPSG:2230 feet CRS (confirmed by each
# archive's own .prj, see tools/offgeo/README.md), so this must be the
# identical transform ID, not a second undocumented one.
TRANSFORM_ID = "state-plane-2230-feet-to-wgs84-cs2cs-v1"

# spec.md 6.1 step 6 / line 79: never emit these, but read them from the
# source explicitly so their exclusion is a recorded decision, not an
# accidental omission a future reader could reintroduce unnoticed.
EXCLUDED_SOURCE_FIELDS = ("APN", "PARCELID", "ADDRAPNID", "ADDRUNIT")


def normalize_street_field(pdir: str, name: str, postd: str, sfx: str) -> dict:
    """Address Points' ADDR* fields are already structurally split, same
    situation as compile-sangis-roads.py's RD30* fields -- only the
    sub-field canonicalization is needed, not the free-text parser."""
    return {
        "pdirRaw": pdir,
        "pdir": canonicalize_direction(pdir) if pdir else None,
        "name": name,
        "postdRaw": postd,
        "postd": canonicalize_direction(postd) if postd else None,
        "sfxRaw": sfx,
        "sfx": canonicalize_suffix(sfx) if sfx else None,
    }


def parse_house_number(raw: str) -> int | None:
    """ADDRNMBR is stored as a DBF float field (e.g. "6.11000000000e+02"
    for 611) -- confirmed by dump-schema.py's sample rows, not assumed
    from the field type code alone. House numbers are always whole
    numbers here; ADDRFRAC (read separately) carries the fractional
    portion (e.g. "1/2") as its own free-text field, so this never needs
    to represent a non-integer value."""
    if not raw:
        return None
    try:
        return int(float(raw))
    except ValueError:
        return None


def read_attributes(retained_path: Path) -> list[dict]:
    with zipfile.ZipFile(retained_path) as zf:
        member = next(n for n in zf.namelist() if n.lower().endswith(".dbf"))
        with zf.open(member) as stream:
            header, records = dbf.open_dbf(stream)
            rows = list(records)
            if len(rows) != header.record_count:
                raise RuntimeError(
                    f"DBF record_count ({header.record_count}) != rows actually yielded ({len(rows)}) "
                    "-- likely deleted records present. Investigate before trusting this run's output."
                )
            return rows


def main() -> None:
    t0 = time.time()
    lock = json.loads(LOCK_PATH.read_text())
    entry = next(e for e in lock["sources"] if e["id"] == "sangis-address-points")
    if not entry.get("retainedPath"):
        raise SystemExit("sangis-address-points not retained yet -- run fetch-sources.py first")
    retained_path = REPO_ROOT / entry["retainedPath"]

    print("Reading attributes (.dbf)...")
    attr_rows = read_attributes(retained_path)
    print(f"  {len(attr_rows)} attribute rows")

    # ORIG_OID confirmed 100% unique across all 1,222,722 rows (checked
    # directly against this retained archive) -- safe as the sole sort/
    # join key, same rigor as ROADSEGID for roads.
    seen_oids: set[str] = set()
    for row in attr_rows:
        oid = row["ORIG_OID"]
        if not oid or oid in seen_oids:
            raise SystemExit(f"ORIG_OID {oid!r} is blank or duplicated -- uniqueness assumption broken, stop")
        seen_oids.add(oid)

    no_house_number = 0
    zero_sentinel_count = 0
    points_ft: list[tuple[float, float]] = []
    kept_indices: list[int] = []
    house_numbers: list[int] = []

    for i, attrs in enumerate(attr_rows):
        number = parse_house_number(attrs["ADDRNMBR"])
        if number is None:
            no_house_number += 1
            continue
        x, y = float(attrs["X_COORD"] or 0), float(attrs["Y_COORD"] or 0)
        if x == 0.0 and y == 0.0:
            zero_sentinel_count += 1
            continue  # the zero-coordinate sentinel found during Group 2 profiling
        points_ft.append((x, y))
        kept_indices.append(i)
        house_numbers.append(number)

    print(f"Transforming {len(points_ft)} points via cs2cs ({TRANSFORM_ID})...")
    t_transform_start = time.time()
    points_wgs84 = batch_state_plane_2230_feet_to_wgs84(points_ft)
    transform_seconds = time.time() - t_transform_start
    print(f"  done in {transform_seconds:.1f}s ({len(points_ft) / max(transform_seconds, 0.001):.0f} pts/sec)")

    implausible_count = 0
    zero_roadsegid_count = 0
    dangling_note_count = 0
    community_raw_values: set[str] = set()
    records_out = []

    for idx, number, (lat, lon) in zip(kept_indices, house_numbers, points_wgs84):
        attrs = attr_rows[idx]
        if not is_plausible_san_diego_point(lat, lon):
            implausible_count += 1
            continue

        roadsegid_raw = attrs["ROADSEGID"]
        roadsegid = int(roadsegid_raw) if roadsegid_raw else 0
        if roadsegid == 0:
            zero_roadsegid_count += 1

        community = attrs["COMMUNITY"] or ""
        if community:
            community_raw_values.add(community)

        records_out.append(
            {
                "origOid": int(attrs["ORIG_OID"]),
                "houseNumber": number,
                "houseFractionRaw": attrs["ADDRFRAC"] or "",
                "positionWgs84": [lon, lat],  # GeoJSON-style [lon, lat], see coords.py's axis-order note
                "street": normalize_street_field(
                    attrs["ADDRPDIR"], attrs["ADDRNAME"], attrs["ADDRPOSTD"], attrs["ADDRSFX"]
                ),
                "roadsegid": roadsegid,
                "hasZeroRoadsegidSentinel": roadsegid == 0,
                "communityRaw": community,
                "jurisdiction": attrs["ADDRJUR"],
                "zip": attrs["ADDRZIP"],
                "sourceCode": attrs["ASOURCE"],
                "placementCode": attrs["PLACEMENT_"],
                "addressTypeCode": attrs["ADDRESS_TY"],
            }
        )

    # Deterministic output per spec.md 6.1: identical source bytes must
    # produce an identical output. ORIG_OID confirmed 100% unique above.
    records_out.sort(key=lambda r: r["origOid"])

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w") as f:
        for record in records_out:
            f.write(json.dumps(record, separators=(",", ":"), sort_keys=True))
            f.write("\n")

    peak_rss_mib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    report = {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sourceId": "sangis-address-points",
        "sourceSha256": entry["sha256"],
        "transformId": TRANSFORM_ID,
        "normalizeVersion": NORMALIZE_VERSION,
        "totalSourceRows": len(attr_rows),
        "recordCount": len(records_out),
        "excludedFieldsNeverEmitted": list(EXCLUDED_SOURCE_FIELDS),
        "skippedNoParsableHouseNumber": no_house_number,
        "skippedZeroCoordSentinel": zero_sentinel_count,
        "implausibleAfterTransformCount": implausible_count,
        "zeroRoadsegidSentinelCount": zero_roadsegid_count,
        "distinctRawCommunityCount": len(community_raw_values),
        "transformSeconds": round(transform_seconds, 2),
        "totalSeconds": round(time.time() - t0, 2),
        "peakRssMib": round(peak_rss_mib, 1),
        "outputPath": str(OUTPUT_PATH.relative_to(REPO_ROOT)),
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True))

    print(f"\nWrote {len(records_out)} records to {OUTPUT_PATH}")
    print(f"Skipped (no parsable house number): {no_house_number}")
    print(f"Skipped (zero-coord sentinel): {zero_sentinel_count}")
    print(f"Implausible after transform: {implausible_count}")
    print(f"Zero-ROADSEGID sentinel (unjoined): {zero_roadsegid_count}")
    print(f"Peak RSS: {peak_rss_mib:.0f} MiB, total time: {time.time() - t0:.1f}s")
    print(f"Report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
