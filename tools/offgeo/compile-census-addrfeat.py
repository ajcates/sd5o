#!/usr/bin/env python3
"""Thin source reader for Census TIGER/Line ADDRFEAT, San Diego County
06073 (`OFF-101`, R1 Group A -- third of the four sources listed there,
after the two SanGIS readers; FEATNAMES is the remaining follow-on work).

Per spec.md 6.1's compiler pipeline steps 3-6, same structure as
compile-sangis-roads.py/compile-sangis-address-points.py, but with a
different source CRS: ADDRFEAT's own .prj declares geographic NAD83
(EPSG:4269, degrees), not SanGIS's projected State Plane feet. That
matters for step 4 specifically -- see tools/offgeo/lib/coords.py's
`batch_nad83_geographic_to_wgs84`, added by this reader, for why a bare
`cs2cs EPSG:4269 EPSG:4326` would have silently used PROJ's ballpark
zero-shift default instead of the real NOAA grid transform.

ADDRFEAT has no field that is unique on its own (`TLID` repeats for
roads with more than one address-range row, confirmed in Group 2
profiling: 5,718 duplicate-TLID groups). A composite of ten fields
(`TLID`, `ARIDL`, `ARIDR`, `LFROMHN`, `LTOHN`, `RFROMHN`, `RTOHN`,
`ZIPL`, `ZIPR`, `FULLNAME`) was checked directly against the full
retained archive and found unique across all 111,770 rows -- used here
as the deterministic sort key in place of a single ID column.

Usage: python3 tools/offgeo/compile-census-addrfeat.py
Output: build/offgeo-sources/r1-census-addrfeat.jsonl (gitignored,
        ~111.8k lines, sorted deterministically)
        build/offgeo-sources/r1-census-addrfeat-report.json (gitignored)
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
from coords import batch_nad83_geographic_to_wgs84, is_plausible_san_diego_point  # noqa: E402
from normalize import NORMALIZE_VERSION  # noqa: E402

LOCK_PATH = REPO_ROOT / "tools/offgeo/config/sources.lock.json"
OUTPUT_PATH = REPO_ROOT / "build/offgeo-sources/r1-census-addrfeat.jsonl"
REPORT_PATH = REPO_ROOT / "build/offgeo-sources/r1-census-addrfeat-report.json"

TRANSFORM_ID = "nad83-4269-socal-hgridshift-cshpgn-to-wgs84-v1"

# Fields checked directly against the full retained archive and found
# unique in combination across all 111,770 rows -- see this file's top
# docstring. Any one alone (especially TLID) is not sufficient.
DEDUP_KEY_FIELDS = ("TLID", "ARIDL", "ARIDR", "LFROMHN", "LTOHN", "RFROMHN", "RTOHN", "ZIPL", "ZIPR", "FULLNAME")


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
            if header["shapeType"] != 3:
                raise RuntimeError(f"unexpected shape type {header['shapeType']} -- expected 3 (PolyLine)")
            return list(shp.iter_polylines(stream))


def main() -> None:
    t0 = time.time()
    lock = json.loads(LOCK_PATH.read_text())
    entry = next(e for e in lock["sources"] if e["id"] == "census-addrfeat-06073")
    if not entry.get("retainedPath"):
        raise SystemExit("census-addrfeat-06073 not retained yet -- run fetch-sources.py first")
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

    seen_keys: set[tuple] = set()
    for row in attr_rows:
        key = tuple(row[f] for f in DEDUP_KEY_FIELDS)
        if key in seen_keys:
            raise SystemExit(f"dedup key {key!r} is duplicated -- uniqueness assumption broken, stop")
        seen_keys.add(key)

    # Same batched-cs2cs-equivalent approach as compile-sangis-roads.py,
    # but vertices are stored (lon, lat) in the .shp per ADDRFEAT's .prj
    # (GEOGCS, x=lon/y=lat is the shapefile's native on-disk order for
    # geographic CRSes) -- batch_nad83_geographic_to_wgs84 wants (lat, lon)
    # per EPSG:4269's officially-defined axis order, so swap on the way in.
    flat_points_latlon: list[tuple[float, float]] = []
    part_boundaries: list[list[int]] = []
    for _bbox, parts in geom_rows:
        lengths = []
        for part in parts:
            lengths.append(len(part))
            flat_points_latlon.extend((lat, lon) for lon, lat in part)
        part_boundaries.append(lengths)

    print(f"Transforming {len(flat_points_latlon)} vertices via cct ({TRANSFORM_ID})...")
    t_transform_start = time.time()
    flat_wgs84 = batch_nad83_geographic_to_wgs84(flat_points_latlon)
    transform_seconds = time.time() - t_transform_start
    print(f"  done in {transform_seconds:.1f}s ({len(flat_points_latlon) / max(transform_seconds, 0.001):.0f} pts/sec)")

    implausible_count = 0
    one_sided_count = 0
    duplicate_tlid_group_sizes: dict[str, int] = {}
    non_digit_house_number_count = 0

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    cursor = 0
    records_out = []
    for attrs, (_bbox, _parts), lengths in zip(attr_rows, geom_rows, part_boundaries):
        wgs84_parts: list[list[list[float]]] = []
        for length in lengths:
            pts = flat_wgs84[cursor : cursor + length]
            cursor += length
            # GeoJSON-style [lon, lat] order, matching compile-sangis-roads.py.
            wgs84_parts.append([[lon, lat] for lat, lon in pts])

        any_implausible = any(
            not is_plausible_san_diego_point(lat, lon) for part in wgs84_parts for lon, lat in part
        )
        if any_implausible:
            implausible_count += 1

        l_present = bool((attrs["LFROMHN"] or "").strip()) or bool((attrs["LTOHN"] or "").strip())
        r_present = bool((attrs["RFROMHN"] or "").strip()) or bool((attrs["RTOHN"] or "").strip())
        is_one_sided = l_present != r_present
        if is_one_sided:
            one_sided_count += 1

        for field in ("LFROMHN", "LTOHN", "RFROMHN", "RTOHN"):
            val = (attrs[field] or "").strip()
            if val and not val.isdigit():
                non_digit_house_number_count += 1

        tlid = attrs["TLID"]
        duplicate_tlid_group_sizes[tlid] = duplicate_tlid_group_sizes.get(tlid, 0) + 1

        records_out.append(
            {
                "tlid": int(tlid),
                "aridl": attrs["ARIDL"] or None,
                "aridr": attrs["ARIDR"] or None,
                "fullname": attrs["FULLNAME"],
                "geometryWgs84": wgs84_parts,
                "addressRange": {
                    "lFromHn": attrs["LFROMHN"] or None,
                    "lToHn": attrs["LTOHN"] or None,
                    "rFromHn": attrs["RFROMHN"] or None,
                    "rToHn": attrs["RTOHN"] or None,
                    "parityL": attrs["PARITYL"] or None,
                    "parityR": attrs["PARITYR"] or None,
                    "offsetL": attrs["OFFSETL"] or None,
                    "offsetR": attrs["OFFSETR"] or None,
                },
                "isOneSided": is_one_sided,
                "zip": {"left": attrs["ZIPL"] or None, "right": attrs["ZIPR"] or None},
                "mtfcc": {"edge": attrs["EDGE_MTFCC"], "road": attrs["ROAD_MTFCC"]},
            }
        )

    duplicate_tlid_groups = sum(1 for count in duplicate_tlid_group_sizes.values() if count > 1)
    extra_rows_from_duplicates = sum(count - 1 for count in duplicate_tlid_group_sizes.values() if count > 1)

    # Deterministic output per spec.md 6.1: identical source bytes must
    # produce an identical output. No single field is unique (see top
    # docstring), so sort by the full composite key instead.
    records_out.sort(
        key=lambda r: (
            r["tlid"],
            r["aridl"] or "",
            r["aridr"] or "",
            r["addressRange"]["lFromHn"] or "",
            r["addressRange"]["lToHn"] or "",
            r["addressRange"]["rFromHn"] or "",
            r["addressRange"]["rToHn"] or "",
            r["zip"]["left"] or "",
            r["zip"]["right"] or "",
            r["fullname"] or "",
        )
    )

    with OUTPUT_PATH.open("w") as f:
        for record in records_out:
            f.write(json.dumps(record, separators=(",", ":"), sort_keys=True))
            f.write("\n")

    peak_rss_mib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    report = {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sourceId": "census-addrfeat-06073",
        "sourceSha256": entry["sha256"],
        "transformId": TRANSFORM_ID,
        "normalizeVersion": NORMALIZE_VERSION,
        "recordCount": len(records_out),
        "vertexCount": len(flat_points_latlon),
        "transformSeconds": round(transform_seconds, 2),
        "totalSeconds": round(time.time() - t0, 2),
        "peakRssMib": round(peak_rss_mib, 1),
        "implausibleAfterTransformCount": implausible_count,
        "distinctTlidCount": len(duplicate_tlid_group_sizes),
        "duplicateTlidGroupCount": duplicate_tlid_groups,
        "extraRowsFromDuplicateTlids": extra_rows_from_duplicates,
        "oneSidedRangeCount": one_sided_count,
        "nonDigitHouseNumberFieldCount": non_digit_house_number_count,
        "outputPath": str(OUTPUT_PATH.relative_to(REPO_ROOT)),
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True))

    print(f"\nWrote {len(records_out)} records to {OUTPUT_PATH}")
    print(f"Distinct TLIDs: {len(duplicate_tlid_group_sizes)}, duplicate-TLID groups: {duplicate_tlid_groups}, extra rows: {extra_rows_from_duplicates}")
    print(f"One-sided ranges: {one_sided_count}")
    print(f"Non-digit house-number fields: {non_digit_house_number_count}")
    print(f"Implausible after transform: {implausible_count}")
    print(f"Peak RSS: {peak_rss_mib:.0f} MiB, total time: {time.time() - t0:.1f}s")
    print(f"Report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
