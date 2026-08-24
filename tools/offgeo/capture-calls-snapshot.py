#!/usr/bin/env python3
"""Capture a snapshot of the live calls-for-service feed for OFF-008/OFF-009
fixture-building. Read-only, low-frequency (this is meant to be run by hand
a handful of times, not polled) against the same Azure Function the current
index.html already calls in every visitor's browser.

Calls the function directly rather than through the third-party CORS proxy
(`api.cors.syrins.tech`) the current app uses -- a server-side script has no
same-origin restriction to work around, so there's no reason to route a
credentialed request through an uncontrolled third party. This itself is
evidence for the OFF-011/OFF-515 finding that the proxy hop is unnecessary,
not just insecure.

The credential below is the same function key already shipped in
index.html's client-side source (visible to every visitor today) -- this
script does not use anything not already public. Replacing it with a proper
server-side proxy is tracked as OFF-011/OFF-515; this script is temporary
research tooling, not the production path.

Usage: python3 tools/offgeo/capture-calls-snapshot.py
Output: build/offgeo-sources/calls-snapshots/<UTC timestamp>.json (gitignored raw capture)
"""
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_DIR = REPO_ROOT / "build/offgeo-sources/calls-snapshots"

FEED_URL = (
    "https://leag-caddata-dev-fa-leag-caddata-dev-fa-blue.azurewebsites.us/api/GetCADEvents"
    "?code=LrxsShPJ3sVycwPqa_Dk-EajBxZJfQGbDBQK1c5wbBoBAzFu2CxMqA=="
)


def main() -> None:
    req = urllib.request.Request(FEED_URL, headers={"User-Agent": "offgeo-fixture-capture/0.1"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    data = json.loads(raw)
    if not isinstance(data.get("Events"), list):
        raise SystemExit("unexpected feed shape: no Events array")

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out_path = SNAPSHOT_DIR / f"{stamp}.json"
    out_path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"Captured {len(data['Events'])} events (LastUpdated={data.get('LastUpdated')!r}) -> "
          f"{out_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
