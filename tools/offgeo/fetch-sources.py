#!/usr/bin/env python3
"""Fetch, verify, and content-address the OffGeo R0 source archives.

Reads tools/offgeo/config/sources.lock.json, downloads each pinned URL,
enforces the OFF-007 acquisition safeguards (host allowlist, no unreviewed
checksum drift, byte-size cap, zip path-traversal / expansion-ratio check),
and retains the exact bytes content-addressed under build/offgeo-sources/
(gitignored -- see roadmap.md OFF-016). On first run for a source the
observed sha256/byteLength/retrievedAt are written back into the lock file,
pinning it. On later runs a changed sha256 is treated as a hard failure
requiring human review, not a silent update.

Usage:
    python3 tools/offgeo/fetch-sources.py [--only ID [ID ...]] [--force]

--force re-downloads and re-verifies even if a retained copy already
matches the locked checksum; it still refuses to accept a *changed*
checksum without the lock file being edited by hand first.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = REPO_ROOT / "tools/offgeo/config/sources.lock.json"
RETAIN_DIR = REPO_ROOT / "build/offgeo-sources"
REPORT_PATH = REPO_ROOT / "build/offgeo-sources/fetch-report.json"

ALLOWED_HOSTS = {"geo.sandag.org", "www2.census.gov"}
MAX_SOURCE_BYTES = 300 * 1024 * 1024  # single-archive safety cap
MAX_ZIP_ENTRIES = 2000
MAX_EXPANSION_RATIO = 25  # uncompressed / compressed
PREFLIGHT_FREE_MULTIPLIER = 3  # require 3x the sum of declared sizes free
CHUNK = 1024 * 1024


class AllowlistRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        host = urllib.parse.urlsplit(newurl).hostname
        if host not in ALLOWED_HOSTS:
            raise urllib.error.URLError(
                f"refusing redirect to disallowed host: {host!r} (from {newurl!r})"
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def load_lock() -> dict:
    return json.loads(LOCK_PATH.read_text())


def save_lock(lock: dict) -> None:
    LOCK_PATH.write_text(json.dumps(lock, indent=2) + "\n")


def opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(AllowlistRedirectHandler)


def head_content_length(url: str) -> int | None:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "offgeo-fetch/0.1"})
    try:
        with opener().open(req, timeout=30) as resp:
            length = resp.headers.get("Content-Length")
            return int(length) if length is not None else None
    except urllib.error.URLError:
        return None


def preflight(lock: dict, ids: set[str] | None) -> None:
    total_declared = 0
    for entry in lock["sources"]:
        if ids and entry["id"] not in ids:
            continue
        host = urllib.parse.urlsplit(entry["url"]).hostname
        if host not in ALLOWED_HOSTS:
            raise SystemExit(f"{entry['id']}: url host {host!r} is not in the allowlist {ALLOWED_HOSTS}")
        length = head_content_length(entry["url"])
        total_declared += length or 0
        print(f"  HEAD {entry['id']}: {length if length is not None else 'unknown'} bytes declared")

    RETAIN_DIR.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(RETAIN_DIR).free
    required = total_declared * PREFLIGHT_FREE_MULTIPLIER
    print(f"Preflight: {total_declared} bytes declared across selected sources, "
          f"{free} bytes free at {RETAIN_DIR}, requiring >= {required} bytes free.")
    if total_declared and free < required:
        raise SystemExit(
            f"Preflight failed: only {free} bytes free, need at least {required} "
            f"({PREFLIGHT_FREE_MULTIPLIER}x the {total_declared}-byte declared total). "
            "Free up space before fetching."
        )


def fetch_one(entry: dict, force: bool) -> dict:
    url = entry["url"]
    host = urllib.parse.urlsplit(url).hostname
    if host not in ALLOWED_HOSTS:
        raise SystemExit(f"{entry['id']}: refusing to fetch from non-allowlisted host {host!r}")

    expected_sha256 = entry.get("sha256")
    if expected_sha256 and not force:
        existing = RETAIN_DIR / f"{expected_sha256}{Path(urllib.parse.urlsplit(url).path).suffix or '.bin'}"
        if existing.exists():
            digest = sha256_file(existing)
            if digest == expected_sha256:
                print(f"  {entry['id']}: already retained and verified at {existing.name}, skipping download")
                return inspect_and_summarize(entry, existing, digest, existing.stat().st_size, skipped=True)
            raise SystemExit(
                f"{entry['id']}: retained file {existing} no longer matches its recorded sha256 "
                "(local corruption or tampering) -- delete it and re-run."
            )

    print(f"Fetching {entry['id']} ({entry['dataset']}) from {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "offgeo-fetch/0.1"})
    tmp_path = RETAIN_DIR / f".tmp-{entry['id']}"
    RETAIN_DIR.mkdir(parents=True, exist_ok=True)

    digest_hash = hashlib.sha256()
    total = 0
    with opener().open(req, timeout=60) as resp, open(tmp_path, "wb") as out:
        while True:
            chunk = resp.read(CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_SOURCE_BYTES:
                tmp_path.unlink(missing_ok=True)
                raise SystemExit(f"{entry['id']}: exceeded {MAX_SOURCE_BYTES}-byte safety cap, aborted")
            digest_hash.update(chunk)
            out.write(chunk)

    digest = digest_hash.hexdigest()
    if expected_sha256 and digest != expected_sha256:
        tmp_path.unlink(missing_ok=True)
        raise SystemExit(
            f"{entry['id']}: CHECKSUM MISMATCH. Locked sha256={expected_sha256}, "
            f"downloaded sha256={digest}. The source bytes changed at the pinned URL; "
            "this requires human review before the lock file is updated. Aborting."
        )

    suffix = Path(urllib.parse.urlsplit(url).path).suffix or ".bin"
    final_path = RETAIN_DIR / f"{digest}{suffix}"
    tmp_path.replace(final_path)
    print(f"  ok: {total} bytes, sha256={digest}")
    return inspect_and_summarize(entry, final_path, digest, total, skipped=False)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def inspect_zip_safety(entry: dict, path: Path) -> tuple[int, int]:
    """Cheap zip-bomb / path-traversal check without extracting to disk."""
    with zipfile.ZipFile(path) as zf:
        infos = zf.infolist()
        if len(infos) > MAX_ZIP_ENTRIES:
            raise SystemExit(f"{entry['id']}: unexpected archive entry count ({len(infos)})")
        uncompressed = 0
        compressed = 0
        for info in infos:
            name = info.filename
            if name.startswith("/") or name.startswith("\\") or ".." in Path(name).parts:
                raise SystemExit(f"{entry['id']}: unsafe archive entry path {name!r}")
            uncompressed += info.file_size
            compressed += info.compress_size
        ratio = uncompressed / max(compressed, 1)
        if ratio > MAX_EXPANSION_RATIO:
            raise SystemExit(
                f"{entry['id']}: suspicious expansion ratio {ratio:.1f}x "
                f"({uncompressed} uncompressed / {compressed} compressed), refusing"
            )
        return len(infos), uncompressed


def inspect_and_summarize(entry: dict, path: Path, digest: str, total: int, skipped: bool) -> dict:
    entry_count, uncompressed = inspect_zip_safety(entry, path)
    entry["sha256"] = digest
    entry["byteLength"] = total
    entry["retainedPath"] = str(path.relative_to(REPO_ROOT))
    if not skipped:
        entry["retrievedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return {
        "id": entry["id"],
        "dataset": entry["dataset"],
        "bytes": total,
        "sha256": digest,
        "zipEntryCount": entry_count,
        "zipUncompressedBytes": uncompressed,
        "retainedPath": entry["retainedPath"],
        "skippedDownload": skipped,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="+", help="only fetch these source ids")
    parser.add_argument("--force", action="store_true", help="re-download even if already retained")
    args = parser.parse_args()

    lock = load_lock()
    ids = set(args.only) if args.only else None
    known_ids = {entry["id"] for entry in lock["sources"]}
    if ids and not ids.issubset(known_ids):
        raise SystemExit(f"unknown source id(s): {sorted(ids - known_ids)}")

    disk_before = shutil.disk_usage(REPO_ROOT).free
    print("== Preflight ==")
    preflight(lock, ids)

    print("== Fetching ==")
    report = []
    for entry in lock["sources"]:
        if ids and entry["id"] not in ids:
            continue
        report.append(fetch_one(entry, force=args.force))

    save_lock(lock)
    disk_after = shutil.disk_usage(REPO_ROOT).free

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps({
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "diskFreeBeforeBytes": disk_before,
        "diskFreeAfterBytes": disk_after,
        "diskConsumedBytes": disk_before - disk_after,
        "sources": report,
    }, indent=2) + "\n")

    print("== Done ==")
    print(f"Disk free before: {disk_before} bytes, after: {disk_after} bytes, "
          f"consumed: {disk_before - disk_after} bytes")
    print(f"Lock file updated: {LOCK_PATH.relative_to(REPO_ROOT)}")
    print(f"Fetch report: {REPORT_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
