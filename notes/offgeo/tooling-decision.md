# Module and test scaffolding decision (`OFF-012`, Group 6)

Status: Decided and verified 2026-08-23
Scope: [`todo.md`](./todo.md) Group 6. Covers the no-build-vs-bundler decision `roadmap.md` §3 requires before runtime feature work begins, plus wiring the sibling `../playwright-termux` pattern into a project-local E2E harness.

## Decision

**No-build native ES modules for everything the browser runs; a small, pinned, dev-only dependency set for testing only.** This was already the de facto choice from Group 4's framework work (`src/framework/`, `src/app/`) and Group 1-3's stdlib-only Python tooling (`tools/offgeo/`) — this ticket makes it explicit, adds the test runners, and proves they work.

| Layer | Choice | Why |
| --- | --- | --- |
| Browser runtime (`src/framework/`, `src/app/`) | Plain ES modules, `<script type="module">`, zero build step | `roadmap.md` §3 requires "ordinary static JavaScript compatible with the current app and deployment"; already shipped this way since Group 4 |
| `tools/offgeo/` (build-time Python) | Stdlib only (`struct`, `dataclasses`, no pip installs); one external system binary, PROJ's `cs2cs` | Established in Groups 1-4 (`lib/dbf.py`, `lib/shp.py` docstrings: "exploration tooling, not a library commitment"); this ticket doesn't change it |
| JS unit tests | Node's built-in `node:test` + `node:assert/strict` | Zero dependencies, runs native ESM directly, no transpilation |
| JS end-to-end/integration tests | `playwright-core` (pinned exact `1.59.1`), driving system-installed Chromium via `executablePath`, no browser download | Matches the sibling `../playwright-termux` harness pattern already used ad hoc in Group 4's verification (`index-html-audit.md` Part C); `playwright-core` is a `devDependency` only — never shipped to the browser, doesn't touch `roadmap.md` §3's no-build constraint |
| Python unit tests | Stdlib `unittest` | Same zero-install rationale as the tooling itself |

## What was built and verified, not just decided

- `package.json` — `type: "module"`, `playwright-core@1.59.1` as the only `devDependency`, four npm scripts (`test:unit`, `test:e2e`, `test`, `test:py`).
- `tests/unit/core.test.mjs`, `tests/unit/format.test.mjs` — 11 tests against `src/framework/core.js`'s `html`/`raw` escaping and `src/app/format.js`'s `ageMinutes`/`prettyTime`/`fetchJson` (including the double-JSON-encoding quirk noted in [`feed-adapter-contract.md`](./feed-adapter-contract.md)). `Component`/`mount` are intentionally **not** unit-tested here — they need a real DOM, which Node doesn't have; that coverage lives in the E2E run instead, not behind a `jsdom`-style dependency added just to simulate one.
- `tests/offgeo/unit/test_dbf.py`, `test_shp.py`, `test_coords.py` — 15 tests against `tools/offgeo/lib/`, run against small hand-built synthetic byte buffers rather than the real multi-hundred-MB retained archives. This is new coverage: those library modules had previously only been exercised indirectly, against live retained sources. `test_coords.py` pins the exact 611 W G St regression the map-prototype work found by hand (a ~1,400 km miss from a hand-rolled projection) as a permanent, automatically-skipped-if-`cs2cs`-missing test.
- `tests/e2e/run.mjs` — launches system Chromium (`/data/data/com.termux/files/usr/bin/chromium-browser`), serves the repo root over plain `http://localhost` (Chromium treats that as a secure context, matching the deployed HTTPS origin's capabilities without needing a local cert), loads `index.html` against the real live feed, confirms the status panel leaves "loading" and no console/page errors occur, then probes the OFF-013 browser capability matrix in that same page and (re)writes [`browser-capability-matrix.md`](./browser-capability-matrix.md). Run live for this ticket: status panel reached `live`, zero console/page errors, all 12 probed capabilities present.

All three (`npm run test:unit`, `npm run test:py`, `npm run test:e2e`) were run and passed as part of writing this ticket, not left as an unverified plan.

## A real environment-specific finding, recorded so it isn't re-debugged later

`playwright-core` (both `1.59.1` and `1.62.1` were tried) throws `Error: Unsupported platform: android` **at import time** on this Termux host, because Node here reports `process.platform === "android"` and the installed package's browser-registry module hard-rejects that value before any `chromium.launch()` call even runs — it happens whether or not `executablePath` is supplied. Two things worth recording:

1. This is not about which package version is installed — a byte-for-byte diff against the sibling `../playwright-termux` project's own installed copy of the *same claimed version and tarball integrity hash* showed genuinely different file contents (the sibling's copy has an explicit `android` branch that a fresh install of the same version here does not). That's an anomaly in this environment's package resolution, not a real npm immutability violation, and not worth chasing further here.
2. The fix used in `tests/e2e/run.mjs`: report `process.platform` as `"linux"` (accurate — this is a genuine Linux-userland/ELF Chromium build via Termux's `x11-repo`, not an Android WebView) via `Object.defineProperty(process, "platform", { value: "linux" })`, executed **before** a dynamic `await import("playwright-core")` (a static top-level `import` is hoisted above any code that would set this first, so it has to be the dynamic form). This is a narrow, well-scoped workaround for a Termux-only import-time check; `executablePath` still does the real work of pointing at the actual browser binary, and nothing about browser download/management logic is exercised on any platform.

## Run commands

```sh
npm install          # one-time; installs playwright-core (devDependency only)
npm run test:unit    # node:test, ~11 tests, no browser needed
npm run test:py      # python3 -m unittest, ~15 tests, no browser needed
npm run test:e2e     # real Chromium + live feed; needs CHROMIUM_PATH if not at the Termux default
npm test             # test:unit then test:e2e
```

`CHROMIUM_PATH` defaults to `/data/data/com.termux/files/usr/bin/chromium-browser`; override it for any other host running these tests.

## What this doesn't cover

- A CI wiring (GitHub Actions or similar) to run these commands automatically on push — not asked for by this ticket's scope (`roadmap.md` §3 only requires the decision + commands to exist) and not built here.
- Coverage for `tools/offgeo/`'s larger orchestration scripts (`fetch-sources.py`, `profile-sources.py`, `build-*.py`) — those are still only exercised end-to-end against live retained sources, as before; only the small stdlib-only leaf libraries (`dbf.py`, `shp.py`, `coords.py`) got new unit coverage here.
- `Component`/`mount` unit coverage (needs a real DOM; covered by the E2E run instead, see above).
