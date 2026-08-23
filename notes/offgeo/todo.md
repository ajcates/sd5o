# OffGeo Phase R0 TODO — Public Source and Input-Contract Proof

Status: Not started
Last updated: 2026-08-22
Scope: [roadmap.md §4](./roadmap.md#4-phase-r0--public-source-and-input-contract-proof) (`OFF-001`–`OFF-017`), the first slice named in [roadmap.md §15](./roadmap.md#15-recommended-first-implementation-slice).
Reference: [spec.md](./spec.md) for source URLs, merge rules, and privacy requirements cited below.

Nothing here is implementation of the compiler/runtime — R0 only proves the sources exist, are stable, and can be automated safely, and sets up the tooling and safety nets the rest of the roadmap depends on.

## How to use this list

Work items are grouped by dependency, not by `OFF-###` number. Finish a group's prerequisites before starting items that read from it (e.g. the source lock in Group 1 gates the safeguards in Group 1 and the profiling in Group 2). Each item's checkbox is done only when its stated output artifact exists and is reviewable — not when the exploration is "basically done" in a terminal scrollback.

## Group 1 — Pin, lock, and safeguard the sources

- [ ] **OFF-001 — Pin the primary SanGIS sources.**
  - [ ] Download SanGIS *Roads - All* geometry from its public endpoint.
  - [ ] Download SanGIS *Address Points to APN* from its public endpoint.
  - [ ] For each: record URL, byte length, SHA-256, retrieval timestamp, displayed vintage, license, attribution text, and documentation URL.
  - Output: entries in the source inventory (`tools/offgeo/README.md` or a dedicated source report).
- [ ] **OFF-006 — Create a source lock file.** One machine-readable config (e.g. `tools/offgeo/config/sources.lock.json`) as the sole authority for source URL, expected checksum, adapter name, vintage, and attribution — for both SanGIS sources and the Census fallback pinned in OFF-003.
- [ ] **OFF-007 — Create acquisition safeguards.** Build the fetch step so it rejects: redirects to hosts not in the lock file, a checksum mismatch without explicit review/re-lock, path traversal in archive entries, archive bombs (excessive expanded size), unexpected entry counts, and schema drift versus the last accepted shape.
- [ ] **OFF-016 — Retain immutable source snapshots.** Store the exact downloaded archives in content-addressed build storage *outside Git* (see repo layout note below), verify them against the lock on every read, and prove — via a documented test — that a clean rebuild does not depend on a weekly government URL still serving the old bytes.
- [ ] **OFF-017 — Budget build-host resources.** Measure download / expanded / intermediate peak disk and RAM on this Termux host; define an ignored, bounded scratch path; add a preflight free-space check; and clean only known temporary build directories on success or failure.

Repo-layout note (from [roadmap.md §3](./roadmap.md#3-planned-repository-layout)): generated archives, expanded shapefiles, and scratch databases never belong in Git. Create `tools/offgeo/` now (with `fetch-sources.*`, `config/`, `fixtures/`, `README.md`) even though the compiler itself is out of scope until R1.

## Group 2 — Profile and reconcile the schemas

- [ ] **OFF-002 — Inspect the SanGIS schemas.** For both Roads - All and Address Points: CRS, record/geometry counts, fields/types/null rates, address-range quality, `ROADSEGID` uniqueness, road-to-address-point join cardinality, community coverage, status/classification value distribution, county bounds. Explicitly confirm APN, parcel, and unit fields are excluded from any output.
- [ ] **OFF-003 — Pin and profile federal fallback sources.** Pin the current `06073 ADDRFEAT` and `FEATNAMES` TIGER/Line inputs (2025 vintage per spec.md — verify still current at pin time). Capture technical documentation/repackaging notice, string house-number forms, duplicate `TLID` geometry, and gaps from potential/suppressed ranges. Evaluate — do not ship — minimal `EDGES` topology for intersection coverage only.
- [ ] **OFF-004 — Prove source precedence and value.** Quantify: SanGIS-primary coverage, Census fallback/alias gains, conflicts between the two, missing joins, roads present in one source but not the other, and valid-range rates. Drop any source or field whose benefit can't be shown in these numbers.
- [ ] **OFF-005 — Define source precedence.** Write the deterministic field-level merge/conflict rules (SanGIS wins on valid joined data per spec.md §"merge"); include stable source IDs; never average conflicting values.
- [ ] **OFF-014 — Define CRS control points.** Record each source's CRS/datum definition and a set of known-coordinate checks that will catch axis swaps, wrong State Plane units, or NAD83-mislabeled-as-WGS84 during the R1 transform.

Output: schema/profile report per enabled source, plus the written precedence/merge-rule document.

## Group 3 — Fixtures and the community crosswalk

- [ ] **OFF-008 — Capture representative input shapes.** Build a rolling, sanitized fixture set from real calls-for-service addresses, covering: ordinary numbered, hundred-block, slash intersections (with and without spaces), directionals, numbered streets, highways, aliases, street-only locations, missing locality, malformed text, and non-address text. Pull from more than one live snapshot so the set isn't an artifact of a single moment.
- [ ] **OFF-009 — Build the feed-community crosswalk.** Profile `Community` and `ServiceArea` values from the calls feed over time; map them deterministically to SanGIS community/jurisdiction sets; report any value that doesn't map and any many-to-many mapping.

Output: `tests/offgeo/fixtures/` seed corpus with expected parse categories, and the crosswalk report.

## Group 4 — Audit and plan removal of the existing runtime's privacy debt

The current `index.html` already ships a Google Geocoding API key and writes raw coordinates to `localStorage`. This group turns that into a scoped migration plan — no code changes yet, that's `OFF-312`/`OFF-512` in R3/R5.

- [ ] **OFF-010 — Audit the existing privacy/runtime path.** Inventory, with file:line references, everything OffGeo must remove or replace:
  - Google geocoder call and hard-coded API key (`getLatLngForAddress`, currently `index.html` — the `AIzaSyA…` key passed to `maps.googleapis.com/maps/api/geocode/json`).
  - `localStorage` writes of raw `latitude`/`longitude` (currently in the `Nearby.askPermission` handler).
  - The per-event `localStorage` cache keyed by `EventNumber` that can carry a `nearby: true` flag derived from the geocoded location.
  - The implicit Google Maps iframe embed used for the row map-expand view.
  - Note which of these need a revoke/restrict action in the Google Cloud console versus a pure code deletion.
- [ ] **OFF-015 — Define legacy cleanup safety.** From the OFF-010 inventory, specify: the exact `localStorage` keys (`latitude`, `longitude`) and the per-event record shape to remove (`value.EventNumber === key`, including a `nearby` field); an idempotent migration version marker so it only runs once per profile; the provider-key revoke/restrict action as an explicit checklist step; and a test proving unrelated origin `localStorage` data survives the migration untouched.

Output: a written migration plan (can live in `tools/offgeo/README.md` or a dedicated privacy-migration note) that R3 (`OFF-312`) and R5 (`OFF-512`) implement against.

## Group 5 — Feed adapter contract

- [ ] **OFF-011 — Define the calls-feed adapter contract.** Specify, as a written contract (not yet code):
  - Distinct error categories: feed 401/403, CORS failure, timeout, schema mismatch — kept separate from future pack-load errors.
  - Schema validation rules for the feed payload.
  - One-snapshot caching behavior (source timestamp vs. local timestamp) and the stale/hide/purge policy.
  - A production-safe credential path: if the feed truly requires a secret, a same-origin server/serverless proxy under this project's control; otherwise, use the source's documented public-client credential. The current `index.html` uses a third-party CORS proxy (`api.cors.syrins.tech`) with an embedded function key — call this out explicitly as not meeting the "no secret in shipped source" bar, since URL-encoding a key through a third-party proxy is not protection.

Output: written feed-adapter contract, plus an explicit finding on the current proxy/key setup and what replaces it.

## Group 6 — Tooling and browser feasibility

- [ ] **OFF-012 — Choose module/test scaffolding.** Decide: no-build ES modules vs. a small locked bundler/test toolchain for `tools/offgeo/` and (later) `src/offgeo/`. Add deterministic run commands. Wire the sibling `../playwright-termux` (`playwright-core` + system Chromium) harness into the planned Android E2E path so later phases can reuse it without re-deriving a browser-automation setup.
- [ ] **OFF-013 — Establish the browser capability matrix.** For the target browser versions: IndexedDB, Web Workers, streaming `fetch`, `DecompressionStream("gzip")`, Web Crypto (SHA-256), Storage API (quota/estimate/persist), Web Locks, BroadcastChannel, Service Workers, Geolocation. For each, define the explicit unsupported/degraded behavior — not a silent failure.

Output: recorded toolchain decision with run commands, and the capability/support matrix document.

## Deliverables checklist (roadmap §4)

- [ ] Source inventory / recommendation (`tools/offgeo/README.md` or dedicated report)
- [ ] Pinned source lock/config with checksums
- [ ] Schema/profile report for every enabled source
- [ ] Initial sanitized address fixture corpus with expected parse categories
- [ ] Feed-community crosswalk report
- [ ] Current-app privacy migration plan
- [ ] Browser capability/support matrix
- [ ] Selected module/test setup
- [ ] Content-addressed source retention + build-host disk/RAM budget
- [ ] Attribution and derived-product notice draft

## R0 exit gate — do not start R1 until all of these hold

- [ ] SanGIS primary and Census fallback fetch reproducibly from official government endpoints.
- [ ] Required geometry and left/right address-range fields for interpolation exist and parse.
- [ ] Address points join to road segments at an approved rate; gaps/ambiguous joins are counted.
- [ ] Census is shown to be a viable fallback/cross-check, not claimed as full coverage.
- [ ] Every enabled source has a public download, provenance record, and stated purpose.
- [ ] Source notices are ready to place in the pack manifest and UI.
- [ ] The fixture corpus covers ≥95% of address syntax categories seen in a sampled calls payload; the rest are counted and documented.
- [ ] The existing geocoder/location storage leaks have a precise removal/migration test plan.
- [ ] Feed auth failure, pack failure, storage failure, and permission failure have distinct contracts.
- [ ] The feed path has a production-safe credential/CORS design; no secret recoverable from browser source, URLs, caches, or diagnostics.
- [ ] Exact source bytes stay reproducible after an upstream weekly URL changes; low build-host space fails cleanly before extraction.

## Suggested execution order

1. Group 1 (lock + safeguards + retention) first — everything else reads pinned, verified bytes.
2. Group 2 and Group 6 in parallel — schema profiling doesn't block tooling/capability decisions, or vice versa.
3. Group 3 once Group 2's community/schema profile exists (the crosswalk needs SanGIS community values).
4. Group 4 and Group 5 can start anytime — they only depend on reading the current `index.html`, not on new source data.
5. Re-check every exit-gate bullet against the actual deliverables before opening R1 work (`OFF-101`+).
