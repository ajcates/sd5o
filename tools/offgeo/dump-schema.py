#!/usr/bin/env python3
"""Quick schema dump: field list + a few sample rows for each locked
source's .dbf. Read-only exploration helper for Group 2 profiling; not part
of the eventual compiler.

Usage: python3 tools/offgeo/dump-schema.py [source-id ...]
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import dbf  # noqa: E402

LOCK_PATH = REPO_ROOT / "tools/offgeo/config/sources.lock.json"
SAMPLE_ROWS = 3


def dbf_member_name(zf: zipfile.ZipFile) -> str | None:
    for name in zf.namelist():
        if name.lower().endswith(".dbf"):
            return name
    return None


def dump_one(entry: dict) -> None:
    path = REPO_ROOT / entry["retainedPath"]
    print(f"\n=== {entry['id']} ({entry['dataset']}) ===")
    with zipfile.ZipFile(path) as zf:
        member = dbf_member_name(zf)
        if member is None:
            print("  no .dbf member found")
            return
        with zf.open(member) as stream:
            header, records = dbf.open_dbf(stream)
            print(f"  dbf member: {member}")
            print(f"  record_count: {header.record_count}")
            print(f"  header_size: {header.header_size}  record_size: {header.record_size}")
            print(f"  field_count: {len(header.fields)}")
            for f in header.fields:
                print(f"    {f.name:<12} type={f.type} length={f.length} decimals={f.decimal_count}")
            print(f"  sample rows:")
            for i, row in enumerate(records):
                if i >= SAMPLE_ROWS:
                    break
                print(f"    {json.dumps(row, ensure_ascii=False)}")


def main() -> None:
    lock = json.loads(LOCK_PATH.read_text())
    wanted = set(sys.argv[1:]) or None
    for entry in lock["sources"]:
        if wanted and entry["id"] not in wanted:
            continue
        if not entry.get("retainedPath"):
            print(f"\n=== {entry['id']} === not retained yet, skipping")
            continue
        dump_one(entry)


if __name__ == "__main__":
    main()
