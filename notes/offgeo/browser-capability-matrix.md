# Browser capability matrix (`OFF-013`, Group 6)

Status: Probed live 2026-08-23 against one real device/browser
Scope: [`todo.md`](./todo.md) Group 6. This is a **measured baseline from the one browser available in this dev environment**, not the production target-device matrix -- `roadmap.md` §13 separately tracks "Reference Android/browser matrix" as its own decision due at R1 start, once real target devices/browsers are chosen. Re-run `node tests/e2e/run.mjs` (regenerates this file) against each browser added to that matrix as it's decided.

Probed with: playwright-core driving system Chromium (`/data/data/com.termux/files/usr/bin/chromium-browser`), version `149.0.7827.155`, via `tests/e2e/run.mjs`.

| Capability | Supported here | Degraded/unsupported behavior required |
| --- | --- | --- |
| IndexedDB | Yes | Live calls stay usable; install disabled with explanation |
| Web Workers | Yes | Distance engine disabled with explicit reason, not a silent hang |
| Streaming `fetch` (`Response.body`) | Yes | Fall back to full-buffer download-then-decompress |
| `DecompressionStream("gzip")` | Yes | Fall back to full-buffer download-then-decompress |
| Web Crypto (`crypto.subtle.digest`, for SHA-256) | Yes | Refuse pack install outright (no unverified activation) |
| Storage API — `navigator.storage.estimate()` | Yes | Skip quota preflight; surface size risk as unknown |
| Storage API — `navigator.storage.persist()` | Yes | Proceed without persistence guarantee; note eviction risk |
| Web Locks (`navigator.locks`) | Yes | BroadcastChannel-based leader election, or refuse concurrent installs |
| BroadcastChannel | Yes | Fall back to poll-based cross-tab update detection |
| Service Workers | Yes | Stay online-only; do not register a no-op worker |
| Geolocation (`navigator.geolocation`) | Yes | Keep calls/geocoding usable; explicit recovery action |
| Secure context (`isSecureContext`) | Yes | Several APIs above are unavailable outside a secure context by spec |

Storage estimate sample from this probe run: `{"quota":1073765064,"usage":23240,"usageDetails":{"caches":22838,"serviceWorkerRegistrations":402}}`.

## Required degraded/unsupported behavior (per `spec.md`)

None of these may fail silently -- each missing API needs its own explicit state, not a caught-and-ignored error:

- **IndexedDB missing/blocked** (private browsing in some browsers): keep live calls usable (the feed doesn't need IndexedDB), disable install with an explicit explanation (`spec.md` §15 "IndexedDB/private-mode unsupported").
- **Web Workers missing**: the geocoder/distance engine (R4) would need a same-thread fallback or to disable distance calculation with an explicit reason, never a silent hang.
- **Streaming fetch / DecompressionStream missing**: pack download falls back to a full-buffer download-then-decompress path, or is disabled with an explicit size/compatibility warning -- must not attempt a partial/streaming read that then fails opaquely.
- **Web Crypto missing**: pack checksum verification cannot run; installing a pack must be refused outright rather than skipping verification, since `spec.md` §13.6 requires checksum verification before activation unconditionally.
- **Storage estimate/persist missing**: proceed without a quota preflight, but surface that the size/eviction risk is unknown rather than asserting persistence succeeded.
- **Web Locks missing**: multi-tab install coordination (`spec.md` §8's compare-and-swap/fencing language) needs a fallback coordination strategy (e.g. a single `BroadcastChannel`-based leader election) or must refuse concurrent installs from multiple tabs rather than racing them.
- **BroadcastChannel missing**: cross-tab "another tab installed/upgraded" notification (`spec.md` §15) degrades to poll-based detection on next load instead of instant cross-tab notice.
- **Service Workers missing**: offline/PWA behavior (R6) is simply unavailable; the app must keep working online-only rather than registering a worker that silently no-ops (the audit already found the *current* worker does exactly that silent no-op -- see `index-html-audit.md` finding 9).
- **Geolocation missing/denied/timed out**: `spec.md` §10/§15 already requires calls/geocoding to keep working with an explicit recovery action; this probe only confirms the API's presence, not permission-grant behavior (that needs a manual/interactive test, not a headless probe).
- **Not a secure context**: several of the above APIs (Web Crypto, Storage API, Service Workers) are themselves unavailable outside a secure context; `spec.md` §13.10 already requires HTTPS in production for exactly this reason.

## Smoke-test outcome from this same probe run

- Status panel reached: `live`
- Console errors: none
- Uncaught page errors: none

This section is regenerated every run of `node tests/e2e/run.mjs` and reflects that specific run's live-feed reachability, not a fixed guarantee.
