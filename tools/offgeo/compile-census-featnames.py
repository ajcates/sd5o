#!/usr/bin/env python3
"""Thin source reader for Census TIGER/Line FEATNAMES, San Diego County
06073 (`OFF-101`, R1 Group A -- fourth and last of the four sources
listed there).

FEATNAMES is an attribute-only alias/name table (no geometry, no `.shp`
member at all -- confirmed directly against the retained archive) that
joins to `ADDRFEAT` by `TLID`. Per spec.md 6.1 steps 3-6, this reader
still normalizes/retains raw values and reports join coverage, even
though there is no CRS transform step here (nothing to transform).

Neither `TLID` alone nor `LINEARID` is unique here (`TLID` legitimately
repeats once per alias name; `LINEARID` repeats across every `TLID` that
shares one physical named feature, e.g. a road that changes `TLID` at
each county-maintained segment break but keeps one linear identity).
The full 18-field row tuple was checked directly against the retained
archive and found unique across all 183,865 rows -- used as the
deterministic sort key, same approach as compile-census-addrfeat.py's
composite key.

Usage: python3 tools/offgeo/compile-census-featnames.py
Output: build/offgeo-sources/r1-census-featnames.jsonl (gitignored,
        ~183.9k lines, sorted deterministically)
        build/offgeo-sources/r1-census-featnames-report.json (gitignored)
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
from normalize import NORMALIZE_VERSION  # noqa: E402

LOCK_PATH = REPO_ROOT / "tools/offgeo/config/sources.lock.json"
OUTPUT_PATH = REPO_ROOT / "build/offgeo-sources/r1-census-featnames.jsonl"
REPORT_PATH = REPO_ROOT / "build/offgeo-sources/r1-census-featnames-report.json"

FIELDS = (
    "TLID", "FULLNAME", "NAME",
    "PREDIRABRV", "PRETYPABRV", "PREQUALABR",
    "SUFDIRABRV", "SUFTYPABRV", "SUFQUALABR",
    "PREDIR", "PRETYP", "PREQUAL",
    "SUFDIR", "SUFTYP", "SUFQUAL",
    "LINEARID", "MTFCC", "PAFLAG",
)


def read_dbf_rows(retained_path: Path, member_suffix: str = ".dbf") -> list[dict]:
    with zipfile.ZipFile(retained_path) as zf:
        member = next(n for n in zf.namelist() if n.lower().endswith(member_suffix))
        with zf.open(member) as stream:
            header, records = dbf.open_dbf(stream)
            rows = list(records)
            if len(rows) != header.record_count:
                raise RuntimeError(
                    f"DBF record_count ({header.record_count}) != rows actually yielded ({len(rows)}) "
                    "-- likely deleted records present. Investigate before trusting this run's output."
                )
            return rows


def load_addrfeat_tlids(lock: dict) -> set[str]:
    """Read TLIDs directly from the retained addrfeat archive, not from
    this project's own r1-census-addrfeat.jsonl output -- so this script
    stays independently runnable and doesn't silently trust another
    script's derived output as ground truth for a join-coverage report."""
    entry = next(e for e in lock["sources"] if e["id"] == "census-addrfeat-06073")
    if not entry.get("retainedPath"):
        raise SystemExit("census-addrfeat-06073 not retained yet -- run fetch-sources.py first")
    rows = read_dbf_rows(REPO_ROOT / entry["retainedPath"])
    return {row["TLID"] for row in rows}


def main() -> None:
    t0 = time.time()
    lock = json.loads(LOCK_PATH.read_text())
    entry = next(e for e in lock["sources"] if e["id"] == "census-featnames-06073")
    if not entry.get("retainedPath"):
        raise SystemExit("census-featnames-06073 not retained yet -- run fetch-sources.py first")
    retained_path = REPO_ROOT / entry["retainedPath"]

    print("Loading ADDRFEAT TLIDs for join-coverage reporting...")
    addrfeat_tlids = load_addrfeat_tlids(lock)
    print(f"  {len(addrfeat_tlids)} distinct ADDRFEAT TLIDs")

    print("Reading attributes (.dbf)...")
    attr_rows = read_dbf_rows(retained_path)
    print(f"  {len(attr_rows)} attribute rows")

    seen_full_rows: set[tuple] = set()
    for row in attr_rows:
        key = tuple(row[f] for f in FIELDS)
        if key in seen_full_rows:
            raise SystemExit(f"full-row key {key!r} is duplicated -- uniqueness assumption broken, stop")
        seen_full_rows.add(key)

    paflag_counts: dict[str, int] = {}
    distinct_tlids: set[str] = set()
    joined_to_addrfeat = 0
    records_out = []

    for attrs in attr_rows:
        tlid = attrs["TLID"]
        distinct_tlids.add(tlid)
        paflag = attrs["PAFLAG"] or ""
        paflag_counts[paflag] = paflag_counts.get(paflag, 0) + 1
        joins = tlid in addrfeat_tlids
        if joins:
            joined_to_addrfeat += 1

        records_out.append(
            {
                "tlid": int(tlid),
                "fullname": attrs["FULLNAME"] or None,
                "name": attrs["NAME"] or None,
                "predirAbbrv": attrs["PREDIRABRV"] or None,
                "pretypAbbrv": attrs["PRETYPABRV"] or None,
                "prequalAbbrv": attrs["PREQUALABR"] or None,
                "sufdirAbbrv": attrs["SUFDIRABRV"] or None,
                "suftypAbbrv": attrs["SUFTYPABRV"] or None,
                "sufqualAbbrv": attrs["SUFQUALABR"] or None,
                "predir": attrs["PREDIR"] or None,
                "pretyp": attrs["PRETYP"] or None,
                "prequal": attrs["PREQUAL"] or None,
                "sufdir": attrs["SUFDIR"] or None,
                "suftyp": attrs["SUFTYP"] or None,
                "sufqual": attrs["SUFQUAL"] or None,
                "linearid": attrs["LINEARID"] or None,
                "mtfcc": attrs["MTFCC"] or None,
                "isPrimaryName": paflag == "P",
                "paflagRaw": paflag,
                "joinsToRetainedAddrfeat": joins,
            }
        )

    # Deterministic output per spec.md 6.1. No compact unique key exists
    # (see top docstring), so sort by the full source-field tuple.
    records_out.sort(
        key=lambda r: (
            r["tlid"], r["fullname"] or "", r["name"] or "", r["predirAbbrv"] or "", r["pretypAbbrv"] or "",
            r["prequalAbbrv"] or "", r["sufdirAbbrv"] or "", r["suftypAbbrv"] or "", r["sufqualAbbrv"] or "",
            r["linearid"] or "", r["paflagRaw"],
        )
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w") as f:
        for record in records_out:
            f.write(json.dumps(record, separators=(",", ":"), sort_keys=True))
            f.write("\n")

    peak_rss_mib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    report = {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sourceId": "census-featnames-06073",
        "sourceSha256": entry["sha256"],
        "normalizeVersion": NORMALIZE_VERSION,
        "recordCount": len(records_out),
        "distinctTlidCount": len(distinct_tlids),
        "paflagCounts": paflag_counts,
        "joinedToRetainedAddrfeatCount": joined_to_addrfeat,
        "joinedToRetainedAddrfeatRate": round(joined_to_addrfeat / len(records_out), 4) if records_out else 0,
        "totalSeconds": round(time.time() - t0, 2),
        "peakRssMib": round(peak_rss_mib, 1),
        "outputPath": str(OUTPUT_PATH.relative_to(REPO_ROOT)),
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True))

    print(f"\nWrote {len(records_out)} records to {OUTPUT_PATH}")
    print(f"Distinct TLIDs: {len(distinct_tlids)}")
    print(f"PAFLAG distribution: {paflag_counts}")
    print(f"Joins to retained ADDRFEAT: {joined_to_addrfeat}/{len(records_out)} ({report['joinedToRetainedAddrfeatRate']:.1%})")
    print(f"Peak RSS: {peak_rss_mib:.0f} MiB, total time: {time.time() - t0:.1f}s")
    print(f"Report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
