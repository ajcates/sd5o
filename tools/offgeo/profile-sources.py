#!/usr/bin/env python3
"""Group 2 schema/quality profiling (OFF-002, OFF-003, OFF-004 inputs) for
the four sources pinned by fetch-sources.py.

Streams each retained archive's .dbf (never loads the ~560 MB Address_Points
table fully into memory) and reports: record counts, field null/blank rates,
ROADSEGID/TLID uniqueness and cross-source join rates, address-range
validity, status/classification value distributions, and coordinate bounds.

This is exploration/reporting tooling, not the compiler -- it makes no
normalization or merge decisions (that's R1/R2). It only measures what the
data actually contains so OFF-004/OFF-005 can be written from evidence.

Usage: python3 tools/offgeo/profile-sources.py
Output: build/offgeo-sources/profile-report.json (+ printed summary)
"""
from __future__ import annotations

import json
import sys
import time
import zipfile
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import dbf  # noqa: E402

LOCK_PATH = REPO_ROOT / "tools/offgeo/config/sources.lock.json"
REPORT_PATH = REPO_ROOT / "build/offgeo-sources/profile-report.json"


def open_dbf_stream(entry: dict):
    path = REPO_ROOT / entry["retainedPath"]
    zf = zipfile.ZipFile(path)
    member = next(n for n in zf.namelist() if n.lower().endswith(".dbf"))
    return zf, zf.open(member)


def field_null_rates(header: dbf.DbfHeader, counters: dict[str, int], total: int) -> dict[str, float]:
    return {name: round(count / total, 4) if total else None for name, count in counters.items()}


def is_blank(value: str) -> bool:
    return value == ""


def parse_int(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None


def is_digit_range(value: str) -> bool:
    return value != "" and value.isdigit()


def profile_roads(entry: dict) -> dict:
    zf, stream = open_dbf_stream(entry)
    header, records = dbf.open_dbf(stream)
    blank_counts = Counter()
    roadsegid_set: set[int] = set()
    roadsegid_dupes = 0
    total = 0
    segstat = Counter()
    dedstat = Counter()
    funclass = Counter()
    pending = Counter()
    ljur = Counter()
    rjur = Counter()
    range_issues = Counter()
    xs: list[float] = []
    ys: list[float] = []

    for row in records:
        total += 1
        for k, v in row.items():
            if is_blank(v):
                blank_counts[k] += 1

        rid = parse_int(row["ROADSEGID"])
        if rid is not None:
            if rid in roadsegid_set:
                roadsegid_dupes += 1
            roadsegid_set.add(rid)

        segstat[row["SEGSTAT"]] += 1
        dedstat[row["DEDSTAT"]] += 1
        funclass[row["FUNCLASS"]] += 1
        pending[row["PENDING"]] += 1
        ljur[row["LJURISDIC"]] += 1
        rjur[row["RJURISDIC"]] += 1

        for side, lo_key, hi_key in (("L", "LLOWADDR", "LHIGHADDR"), ("R", "RLOWADDR", "RHIGHADDR")):
            lo, hi = row[lo_key], row[hi_key]
            if is_blank(lo) or is_blank(hi):
                range_issues[f"{side}_missing"] += 1
                continue
            lo_n, hi_n = parse_int(lo), parse_int(hi)
            if lo_n is None or hi_n is None:
                range_issues[f"{side}_nonnumeric"] += 1
            elif lo_n == 0 and hi_n == 0:
                range_issues[f"{side}_zero"] += 1
            elif hi_n < lo_n:
                range_issues[f"{side}_descending"] += 1
            elif hi_n - lo_n > 100000:
                range_issues[f"{side}_implausibly_wide"] += 1

        try:
            xs.append(float(row["FRXCOORD"]))
            ys.append(float(row["FRYCOORD"]))
        except ValueError:
            pass

    zf.close()
    return {
        "recordCount": total,
        "fieldCount": len(header.fields),
        "fields": [f.name for f in header.fields],
        "blankRateByField": field_null_rates(header, blank_counts, total),
        "roadsegidUniqueCount": len(roadsegid_set),
        "roadsegidDuplicateRows": roadsegid_dupes,
        "segStatDistribution": dict(segstat),
        "dedStatDistribution": dict(dedstat),
        "funClassDistribution": dict(funclass),
        "pendingDistribution": dict(pending),
        "leftJurisdictionDistribution": dict(ljur.most_common(15)),
        "rightJurisdictionDistribution": dict(rjur.most_common(15)),
        "addressRangeIssueCounts": dict(range_issues),
        "coordBoundsStatePlaneFeet": {
            "xMin": min(xs) if xs else None, "xMax": max(xs) if xs else None,
            "yMin": min(ys) if ys else None, "yMax": max(ys) if ys else None,
        },
    }, roadsegid_set


def profile_address_points(entry: dict, roads_roadsegid: set[int]) -> dict:
    zf, stream = open_dbf_stream(entry)
    header, records = dbf.open_dbf(stream)
    blank_counts = Counter()
    total = 0
    joined = 0
    zero_roadsegid = 0
    unjoined_nonzero = 0
    community = Counter()
    asource = Counter()
    placement = Counter()
    address_ty = Counter()
    apn_present = 0
    unit_present = 0
    xs: list[float] = []
    ys: list[float] = []

    for row in records:
        total += 1
        for k, v in row.items():
            if is_blank(v):
                blank_counts[k] += 1

        rid = parse_int(row["ROADSEGID"])
        if rid == 0:
            zero_roadsegid += 1
        elif rid is not None and rid in roads_roadsegid:
            joined += 1
        elif rid is not None:
            unjoined_nonzero += 1

        community[row["COMMUNITY"]] += 1
        asource[row["ASOURCE"]] += 1
        placement[row["PLACEMENT_"]] += 1
        address_ty[row["ADDRESS_TY"]] += 1
        if not is_blank(row["APN"]):
            apn_present += 1
        if not is_blank(row["ADDRUNIT"]):
            unit_present += 1

        try:
            xs.append(float(row["X_COORD"]))
            ys.append(float(row["Y_COORD"]))
        except ValueError:
            pass

    zf.close()
    return {
        "recordCount": total,
        "fieldCount": len(header.fields),
        "fields": [f.name for f in header.fields],
        "blankRateByField": field_null_rates(header, blank_counts, total),
        "roadsegidZeroSentinelCount": zero_roadsegid,
        "roadsegidZeroSentinelRate": round(zero_roadsegid / total, 4),
        "roadsegidJoinedCount": joined,
        "roadsegidJoinedRate": round(joined / total, 4),
        "roadsegidUnjoinedNonzeroCount": unjoined_nonzero,
        "communityDistinctCount": len(community),
        "communityBlankRate": round(community.get("", 0) / total, 4),
        "communityTop20": dict(community.most_common(20)),
        "aSourceDistribution": dict(asource),
        "placementDistribution": dict(placement),
        "addressTypeDistribution": dict(address_ty),
        "apnFieldPresentRate": round(apn_present / total, 4),
        "unitFieldPresentRate": round(unit_present / total, 4),
        "excludedFieldsConfirmedPresent": ["APN", "PARCELID", "ADDRUNIT", "ADDRAPNID"],
        "coordBoundsStatePlaneFeet": {
            "xMin": min(xs) if xs else None, "xMax": max(xs) if xs else None,
            "yMin": min(ys) if ys else None, "yMax": max(ys) if ys else None,
        },
    }


def profile_addrfeat(entry: dict) -> dict:
    zf, stream = open_dbf_stream(entry)
    header, records = dbf.open_dbf(stream)
    blank_counts = Counter()
    total = 0
    tlid_counts = Counter()
    nonstandard_house_numbers = Counter()
    parityl = Counter()
    parityr = Counter()
    fromtyp = Counter()
    totyp = Counter()
    zips = Counter()

    for row in records:
        total += 1
        for k, v in row.items():
            if is_blank(v):
                blank_counts[k] += 1

        tlid_counts[row["TLID"]] += 1

        for key in ("LFROMHN", "LTOHN", "RFROMHN", "RTOHN"):
            v = row[key]
            if v and not is_digit_range(v):
                nonstandard_house_numbers[key] += 1

        parityl[row["PARITYL"]] += 1
        parityr[row["PARITYR"]] += 1
        fromtyp[row["LFROMTYP"]] += 1
        fromtyp[row["RFROMTYP"]] += 1
        totyp[row["LTOTYP"]] += 1
        totyp[row["RTOTYP"]] += 1
        if row["ZIPL"]:
            zips[row["ZIPL"]] += 1

    zf.close()
    duplicate_tlids = sum(1 for c in tlid_counts.values() if c > 1)
    return {
        "recordCount": total,
        "fieldCount": len(header.fields),
        "fields": [f.name for f in header.fields],
        "blankRateByField": field_null_rates(header, blank_counts, total),
        "distinctTlidCount": len(tlid_counts),
        "duplicateTlidGroups": duplicate_tlids,
        "duplicateTlidRows": total - len(tlid_counts),
        "nonstandardHouseNumberCountsByField": dict(nonstandard_house_numbers),
        "parityLDistribution": dict(parityl),
        "parityRDistribution": dict(parityr),
        "fromTypeDistribution": dict(fromtyp),
        "toTypeDistribution": dict(totyp),
        "distinctZipCount": len(zips),
        "topZips": dict(zips.most_common(10)),
    }


def profile_featnames(entry: dict, addrfeat_tlids: set[str]) -> dict:
    zf, stream = open_dbf_stream(entry)
    header, records = dbf.open_dbf(stream)
    blank_counts = Counter()
    total = 0
    tlid_counts = Counter()
    paflag = Counter()
    matched_tlid = 0

    for row in records:
        total += 1
        for k, v in row.items():
            if is_blank(v):
                blank_counts[k] += 1
        tlid_counts[row["TLID"]] += 1
        paflag[row["PAFLAG"]] += 1
        if row["TLID"] in addrfeat_tlids:
            matched_tlid += 1

    zf.close()
    return {
        "recordCount": total,
        "fieldCount": len(header.fields),
        "fields": [f.name for f in header.fields],
        "blankRateByField": field_null_rates(header, blank_counts, total),
        "distinctTlidCount": len(tlid_counts),
        "aliasesPerTlidMax": max(tlid_counts.values()) if tlid_counts else 0,
        "paFlagDistribution": dict(paflag),
        "tlidMatchesAddrfeatCount": matched_tlid,
        "tlidMatchesAddrfeatRate": round(matched_tlid / total, 4) if total else None,
    }


def main() -> None:
    lock = json.loads(LOCK_PATH.read_text())
    by_id = {e["id"]: e for e in lock["sources"]}
    for entry in by_id.values():
        if not entry.get("retainedPath"):
            raise SystemExit(f"{entry['id']}: not retained yet -- run fetch-sources.py first")

    t0 = time.time()
    print("Profiling sangis-roads-all ...")
    roads_report, roads_roadsegid = profile_roads(by_id["sangis-roads-all"])
    print(f"  {roads_report['recordCount']} records in {time.time() - t0:.1f}s")

    t1 = time.time()
    print("Profiling sangis-address-points ...")
    addr_report = profile_address_points(by_id["sangis-address-points"], roads_roadsegid)
    print(f"  {addr_report['recordCount']} records in {time.time() - t1:.1f}s")

    t2 = time.time()
    print("Profiling census-addrfeat-06073 ...")
    addrfeat_report = profile_addrfeat(by_id["census-addrfeat-06073"])
    print(f"  {addrfeat_report['recordCount']} records in {time.time() - t2:.1f}s")

    # Re-open ADDRFEAT to collect the TLID set for the FEATNAMES join (kept
    # as a second pass so profile_addrfeat's row loop doesn't need to grow
    # this set redundantly -- it's a plain set of the same key already
    # counted for duplicates above).
    zf, stream = open_dbf_stream(by_id["census-addrfeat-06073"])
    header, records = dbf.open_dbf(stream)
    addrfeat_tlids = {row["TLID"] for row in records}
    zf.close()

    t3 = time.time()
    print("Profiling census-featnames-06073 ...")
    featnames_report = profile_featnames(by_id["census-featnames-06073"], addrfeat_tlids)
    print(f"  {featnames_report['recordCount']} records in {time.time() - t3:.1f}s")

    report = {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sangisRoadsAll": roads_report,
        "sangisAddressPoints": addr_report,
        "censusAddrfeat": addrfeat_report,
        "censusFeatnames": featnames_report,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n")
    print(f"\nWrote {REPORT_PATH.relative_to(REPO_ROOT)} in {time.time() - t0:.1f}s total")


if __name__ == "__main__":
    main()
