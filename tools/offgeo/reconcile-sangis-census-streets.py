#!/usr/bin/env python3
"""SanGIS<->Census street-name reconciliation (`OFF-004`'s cross-source
half, `OFF-103`'s remaining scope). Answers the question Group 2
profiling explicitly deferred to R1: "how many roads does Census add
that SanGIS lacks, and where do they overlap" -- now answerable because
the shared normalization library (`OFF-102`) and all four `OFF-101`
readers exist.

Approach: build one canonical street-name key per source --
`(predirCode, normalizedCoreName, postdirCode, suffixCode)` -- from each
reader's already-structurally-split fields (SanGIS `RD30*`/roads reader
`street.{pdir,name,postd,sfx}`; Census `FEATNAMES` reader's
`{predirAbbrv,name,sufdirAbbrv,suftypAbbrv}`, canonicalized the same way
via `normalize.py`), then compare the two key sets. This is name-level
reconciliation only -- it does not attempt geometry-based segment
matching or address-range conflict detection between the two sources
for streets present in both (that needs a spatial join per matched
street, out of scope for this pass; see the report's own notes).

Census `FEATNAMES` carries both primary (`PAFLAG=P`) and alias
(`PAFLAG=A`) names per `TLID`; both are included in the Census key set,
since an alias-only name could still be the one SanGIS uses. Only
`FEATNAMES` rows whose `TLID` has an actual usable address range in
`ADDRFEAT` are counted as "range-bearing" -- a `FEATNAMES` row for a
`TLID` that never appears in `ADDRFEAT` (or appears with only an
absent/empty range) carries a name but no geocodable address data, so
including it in a "Census adds this street" coverage claim would
overstate the real fallback value, per spec.md 6.1's warning not to
add a source/field whose benefit can't be measured.

Usage: python3 tools/offgeo/reconcile-sangis-census-streets.py
  (requires all four OFF-101 readers' output already generated)
Output: build/offgeo-sources/r1-street-reconciliation-report.json (gitignored)
"""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from normalize import canonicalize_direction, canonicalize_street_core_name, canonicalize_suffix, normalize_text  # noqa: E402

ROADS_PATH = REPO_ROOT / "build/offgeo-sources/r1-sangis-roads.jsonl"
ADDRFEAT_PATH = REPO_ROOT / "build/offgeo-sources/r1-census-addrfeat.jsonl"
FEATNAMES_PATH = REPO_ROOT / "build/offgeo-sources/r1-census-featnames.jsonl"
REPORT_PATH = REPO_ROOT / "build/offgeo-sources/r1-street-reconciliation-report.json"


def iter_jsonl(path: Path):
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def street_key(pdir_raw: str | None, name_raw: str | None, postd_raw: str | None, sfx_raw: str | None) -> tuple:
    pdir = canonicalize_direction(normalize_text(pdir_raw)) if pdir_raw else None
    name = canonicalize_street_core_name(name_raw) if name_raw else ""
    postd = canonicalize_direction(normalize_text(postd_raw)) if postd_raw else None
    sfx = canonicalize_suffix(normalize_text(sfx_raw)) if sfx_raw else None
    return (pdir or "", name, postd or "", sfx or "")


def has_usable_range(addr_range: dict) -> bool:
    for lo_key, hi_key in (("lFromHn", "lToHn"), ("rFromHn", "rToHn")):
        lo, hi = addr_range.get(lo_key), addr_range.get(hi_key)
        if lo or hi:
            return True
    return False


def main() -> None:
    t0 = time.time()
    for p in (ROADS_PATH, ADDRFEAT_PATH, FEATNAMES_PATH):
        if not p.exists():
            raise SystemExit(f"{p} missing -- run all OFF-101 readers first")

    print("Building SanGIS street-key set from the roads reader output...")
    sangis_keys: dict[tuple, set[int]] = {}
    for road in iter_jsonl(ROADS_PATH):
        s = road["street"]
        key = street_key(s["pdirRaw"], s["name"], s["postdRaw"], s["sfxRaw"])
        sangis_keys.setdefault(key, set()).add(road["roadsegid"])
    print(f"  {len(sangis_keys)} distinct SanGIS street keys across {sum(len(v) for v in sangis_keys.values())} segments")

    print("Loading ADDRFEAT to find which TLIDs carry a usable address range...")
    range_bearing_tlids: set[int] = set()
    total_addrfeat = 0
    for rec in iter_jsonl(ADDRFEAT_PATH):
        total_addrfeat += 1
        if has_usable_range(rec["addressRange"]):
            range_bearing_tlids.add(rec["tlid"])
    print(f"  {len(range_bearing_tlids)}/{total_addrfeat} ADDRFEAT rows carry a usable range (distinct TLIDs)")

    print("Building Census street-key set from FEATNAMES (primary + alias)...")
    census_keys_all: dict[tuple, set[int]] = {}
    census_keys_range_bearing: dict[tuple, set[int]] = {}
    total_featnames = 0
    primary_count = 0
    alias_count = 0
    for rec in iter_jsonl(FEATNAMES_PATH):
        total_featnames += 1
        if rec["isPrimaryName"]:
            primary_count += 1
        else:
            alias_count += 1
        key = street_key(rec["predirAbbrv"], rec["name"], rec["sufdirAbbrv"], rec["suftypAbbrv"])
        tlid = rec["tlid"]
        census_keys_all.setdefault(key, set()).add(tlid)
        if tlid in range_bearing_tlids:
            census_keys_range_bearing.setdefault(key, set()).add(tlid)
    print(f"  {len(census_keys_all)} distinct Census street keys ({primary_count} primary + {alias_count} alias rows)")
    print(f"  {len(census_keys_range_bearing)} of those keys have at least one range-bearing TLID")

    # Blank keys (name normalized to empty string, e.g. numbered-highway-only
    # or malformed rows) aren't a meaningful "street" for this comparison --
    # excluded from both sides so an accidental blank-vs-blank match doesn't
    # inflate the matched count.
    def drop_blank(keys: dict[tuple, set]) -> dict[tuple, set]:
        return {k: v for k, v in keys.items() if k[1]}

    sangis_keys = drop_blank(sangis_keys)
    census_keys_range_bearing = drop_blank(census_keys_range_bearing)

    sangis_key_set = set(sangis_keys)
    census_key_set = set(census_keys_range_bearing)

    matched = sangis_key_set & census_key_set
    sangis_only = sangis_key_set - census_key_set
    census_only = census_key_set - sangis_key_set

    def fmt_key(k: tuple) -> str:
        pdir, name, postd, sfx = k
        return " ".join(p for p in (pdir, name, postd, sfx) if p)

    # Alphabetically-first sampling was tried and rejected during
    # development: digit-leading keys (numbered highways/routes, e.g.
    # "10", "76 RAVENSCROFT") sort first and dominated the sample even
    # though they're under 1% of census_only overall -- not representative.
    # A seeded random sample (fixed seed for reproducibility given
    # identical input) gives an honest picture instead.
    sample_rng = random.Random(20260824)
    census_only_examples = sorted(sample_rng.sample(sorted(census_only), min(25, len(census_only))))
    sangis_only_examples = sorted(sample_rng.sample(sorted(sangis_only), min(25, len(sangis_only))))
    census_only_examples = [fmt_key(k) for k in census_only_examples]
    sangis_only_examples = [fmt_key(k) for k in sangis_only_examples]

    census_only_tlid_count = sum(len(census_keys_range_bearing[k]) for k in census_only)
    matched_census_tlid_count = sum(len(census_keys_range_bearing[k]) for k in matched)

    report = {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "method": (
            "Name-level street-key reconciliation only (predir/name/postdir/suffix, "
            "canonicalized via lib/normalize.py). Does not compare geometry or address "
            "ranges for streets matched by name in both sources -- that needs a spatial "
            "join per matched street and is separate future work."
        ),
        "sangis": {
            "totalRoadSegments": sum(len(v) for v in sangis_keys.values()),
            "distinctStreetKeys": len(sangis_key_set),
        },
        "census": {
            "totalFeatnamesRows": total_featnames,
            "primaryNameRows": primary_count,
            "aliasNameRows": alias_count,
            "totalAddrfeatRows": total_addrfeat,
            "rangeBearingTlidCount": len(range_bearing_tlids),
            "distinctStreetKeysAll": len(drop_blank(census_keys_all)),
            "distinctStreetKeysRangeBearing": len(census_key_set),
        },
        "reconciliation": {
            "matchedStreetKeyCount": len(matched),
            "matchedStreetKeyRateOfSangis": round(len(matched) / len(sangis_key_set), 4) if sangis_key_set else 0,
            "sangisOnlyStreetKeyCount": len(sangis_only),
            "censusOnlyRangeBearingStreetKeyCount": len(census_only),
            "censusOnlyRangeBearingStreetKeyRateOfCensus": (
                round(len(census_only) / len(census_key_set), 4) if census_key_set else 0
            ),
            "censusOnlyTlidCount": census_only_tlid_count,
            "matchedKeysCensusTlidCount": matched_census_tlid_count,
            "censusOnlyExamples": census_only_examples,
            "sangisOnlyExamples": sangis_only_examples,
        },
        "totalSeconds": round(time.time() - t0, 2),
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True))

    print(f"\nSanGIS: {len(sangis_key_set)} distinct street keys")
    print(f"Census (range-bearing only): {len(census_key_set)} distinct street keys")
    print(f"Matched: {len(matched)} ({report['reconciliation']['matchedStreetKeyRateOfSangis']:.1%} of SanGIS keys)")
    print(f"SanGIS-only: {len(sangis_only)}")
    print(f"Census-only (range-bearing): {len(census_only)}, covering {census_only_tlid_count} TLIDs")
    print(f"\nSample Census-only street names (seeded random sample, alphabetized for display):")
    for name in census_only_examples:
        print(f"  {name}")
    print(f"\nReport: {REPORT_PATH}")


if __name__ == "__main__":
    main()
