# OffGeo Implementation Roadmap

Status: Proposed

Last updated: 2026-08-22

Companion specification: [spec.md](./spec.md)

## 1. Delivery strategy

Build OffGeo in dependency order and require evidence at each promotion gate:

```text
R0 source/schema proof
  -> R1 feasibility pack and measured budgets
    -> R2 deterministic compiler and frozen format
      -> R3 transactional IndexedDB installer
        -> R4 offline geocoder
          -> R5 location, distance, and UI
            -> R6 full offline/PWA integration
              -> R7 release automation and four-month maintenance
```

The first milestone is not a polished download screen. It is a reproducible prototype proving that public-government road/address data can cover the real event-address shapes, fit below 30 MiB, and be queried quickly enough on the target phone. Failed gates produce documented decisions or a revised design; they do not silently become technical debt.

## 2. Workstream map

| Workstream | Owns | Starts | Depends on |
| --- | --- | --- | --- |
| Data/source | Government downloads, adapters, provenance, merge rules | R0 | Nothing |
| Compiler | Normalization, validation, binary encoding, reports | R1 | Source/schema proof |
| Runtime storage | Pack reader, worker, IndexedDB install/update/recovery | R2 | Frozen format candidate |
| Geocoder | Parsing, lookup, interpolation, confidence/reasons | R1 fixtures; completes R4 | Shared normalization + storage |
| Product UI | Offline-data controls, permission, distance, sorting/filtering | Wireframes in R1; implementation R5 | Stable runtime APIs |
| PWA/offline | App shell and cached calls, airplane-mode behavior | R3 | Storage conventions |
| Release | Hosting, active manifest, rollback, cadence | R2 | Reproducible compiler |
| QA/privacy | Benchmarks, fixtures, network/storage instrumentation | Every phase | Phase deliverables |

## 3. Planned repository layout

The current app is a small static site with its application logic embedded in `index.html`, no package/test setup, and a minimal service worker. Introduce boundaries without requiring a framework migration, but do not add the compiler, installer, and worker to the existing monolithic script.

```text
notes/offgeo/
  spec.md
  roadmap.md
tools/offgeo/
  fetch-sources.*
  compile.*
  validate.*
  config/
  fixtures/
  README.md
offgeo/
  manifest.json                 # active small release manifest
  packs/<version>/sd-06073.offgeo
  notices/<version>.txt
src/offgeo/                     # or equivalent modules chosen in R1
  format.*
  normalize.*
  parser.*
  database.*
  installer.*
  geocoder.*
  distance.*
  worker.*
tests/offgeo/
  unit/
  integration/
  fixtures/
  reports/
```

Generated source archives, expanded shapefiles, scratch databases, and candidate packs do not belong in Git. Published pack artifacts may be deployed separately from the source checkout; their manifest, checksum, notices, and validation reports must remain versioned and reviewable.

The exact implementation language/toolchain is an R1 decision. A native geospatial compiler can be Python or Node-based, but the browser runtime must remain ordinary static JavaScript compatible with the current app and deployment. R0 must choose either a documented no-build ES-module layout or a small reproducible bundler/test setup before runtime feature work begins.

## 4. Phase R0 — Public source and input-contract proof

Objective: prove that the selected public-government sources are downloadable, attributable, schema-stable enough to automate, and capable of supplying the required range/geometry fields.

Dependencies: none.

### Work items

- [ ] **OFF-001 — Pin the primary SanGIS sources.** Download Roads - All geometry and Address Points to APN from their public endpoints; capture URL, byte length, SHA-256, retrieval time, displayed vintage/license/attribution, and documentation URL.
- [ ] **OFF-002 — Inspect the SanGIS schemas.** Record CRS, record/geometry counts, fields/types/null rates, address-range quality, `ROADSEGID` uniqueness, road-to-address-point join cardinality, community coverage, status/classification values, and county bounds. Explicitly exclude APN, parcel, and unit fields from output.
- [ ] **OFF-003 — Pin and profile federal fallback sources.** Capture the current `06073 ADDRFEAT` and `FEATNAMES` inputs, technical documentation/repackaging notice, string-house-number forms, duplicate `TLID` geometry, and gaps caused by potential/suppressed ranges. Evaluate minimal `EDGES` topology only for intersection coverage.
- [ ] **OFF-004 — Prove source precedence and value.** Quantify SanGIS-primary coverage, Census fallback/alias gains, conflicts, missing joins, new roads, and valid ranges. Do not add a source or field whose benefit cannot be measured.
- [ ] **OFF-005 — Define source precedence.** Write deterministic field-level merge and conflict rules; include stable source IDs and never average conflicts.
- [ ] **OFF-006 — Create a source lock file.** Make one machine-readable config the authority for source URL, expected checksum, adapter, vintage, and attribution.
- [ ] **OFF-007 — Create acquisition safeguards.** Reject redirects to unapproved hosts, changed checksums without review, path traversal, archive bombs, unexpected entry counts, and schema drift.
- [ ] **OFF-008 — Capture representative input shapes.** Build a rolling sanitized fixture set from calls-to-service addresses: ordinary numbered, hundred-block, slash intersections with/without spaces, directionals, numbered streets, highways, aliases, street-only locations, missing locality, malformed, and non-address text. Avoid treating a single live snapshot as representative.
- [ ] **OFF-009 — Build the feed-community crosswalk.** Profile `Community` and `ServiceArea` values over time and map them deterministically to SanGIS community/jurisdiction sets; report unknown and many-to-many mappings.
- [ ] **OFF-010 — Audit the existing privacy/runtime path.** Inventory and plan removal of the Google geocoder/key, `latitude`/`longitude` and `{lat,lng}` localStorage entries, coordinate logs/URLs, per-event indefinite cache, and implicit Google Maps iframe.
- [ ] **OFF-011 — Define the calls-feed adapter contract.** Separate feed 401/403/CORS/timeout/schema errors from pack errors; specify schema validation, one-snapshot caching, source/local timestamps, and stale/hide/purge policy. If authentication is secret, choose a controlled same-origin server/serverless proxy; otherwise document the source-approved public-client credential. Never ship a secret or treat URL encoding/third-party CORS proxying as protection.
- [ ] **OFF-012 — Choose module/test scaffolding.** Decide no-build modules versus a minimal locked toolchain, add deterministic commands, and wire the sibling `../playwright-termux` `playwright-core`/system-Chromium harness into the planned Android E2E path.
- [ ] **OFF-013 — Establish the browser capability matrix.** Test target versions for IndexedDB, workers, streaming fetch, `DecompressionStream("gzip")`, Web Crypto, Storage API, Web Locks, BroadcastChannel, service workers, and geolocation; define an explicit unsupported/degraded state for each missing API.
- [ ] **OFF-014 — Define CRS control points.** Record source CRS/datum definitions and known coordinate checks that will catch axis swaps, wrong State Plane units, or NAD83-as-WGS84 relabeling.
- [ ] **OFF-015 — Define legacy cleanup safety.** Specify exact known coordinate keys, `{lat,lng}` values, and per-event records where `value.EventNumber === key` (including location-derived `nearby`); define an idempotent migration version, provider-key revocation/restriction action, and tests proving unrelated origin data survives.
- [ ] **OFF-016 — Retain immutable source snapshots.** Put exact downloaded archives in content-addressed build storage outside Git, verify them against the source lock, and prove a clean rebuild does not depend on a weekly URL retaining old bytes.
- [ ] **OFF-017 — Budget build-host resources.** Measure download/expanded/intermediate peak disk and RAM, define an ignored cache and bounded Termux-safe scratch path, preflight free space, and clean only known temporary build directories on success/failure.

### Deliverables

- Source inventory and recommendation in `tools/offgeo/README.md` or a focused source report.
- Pinned source lock/config with checksums.
- Schema/profile report for every enabled source.
- Initial sanitized address fixture corpus with expected parse categories.
- Feed-community crosswalk report and current-app privacy migration plan.
- Browser capability/support matrix and selected module/test setup.
- Content-addressed source retention and build-host disk/RAM budget.
- Attribution and derived-product notice draft.

### R0 exit gate — source ready

Pass only when recorded evidence shows:

- SanGIS primary and Census fallback sources are fetched reproducibly from official government endpoints.
- Geometry and left/right address-range fields required for interpolation exist and parse.
- Address points join to road segments at the approved rate and supply a usable community mapping; gaps and ambiguous joins are counted.
- Census supplies a viable fallback/cross-check, not an unsupported promise of every physical address.
- Every enabled source has a public download, provenance record, and explicit measurable purpose.
- Required source notices can be placed in the pack manifest and UI.
- The fixture corpus represents at least 95% of address syntax categories observed in a sampled calls payload; unsupported categories are counted and documented.
- The existing location/geocoder storage leaks have a precise removal/migration test plan.
- Feed authentication failure, pack failure, storage failure, and permission failure have distinct contracts.
- The feed path has a production-safe credential/CORS design; no secret is recoverable from browser source, URLs, caches, or diagnostics.
- Exact source bytes remain reproducible after an upstream weekly URL changes, and low build-host space fails before extraction without broad deletion.

## 5. Phase R1 — Feasibility compiler and benchmark

Objective: answer size, coverage, accuracy, and performance questions with real San Diego County data before committing to the final format.

Dependencies: R0 passed.

### Work items

- [ ] **OFF-101 — Implement thin source readers.** Read pinned SanGIS primary and Census fallback inputs, apply an explicit CRS/datum transform to WGS84, retain only required IDs/names/ranges/geometry/community data, and emit deterministic records.
- [ ] **OFF-102 — Build shared normalization fixtures.** Define canonical directions, suffixes, whitespace/punctuation, routes, ordinals, unit stripping, block syntax, and intersections.
- [ ] **OFF-103 — Profile range and join quality.** Count missing/malformed/nonstandard string ranges, parity/mix/imputation/offset flags, descending ranges, duplicate geometry, extreme spans, street-only geometry, address-point joins, community mappings, and locality/ZIP gaps.
- [ ] **OFF-104 — Prototype compact representations.** Compare the custom block format with at least one maintained SQLite/PBF-style alternative using equivalent records, indexes, checksums, compression, and browser tests. De-duplicate geometry from range/name records in every candidate.
- [ ] **OFF-105 — Implement a benchmark reader.** Load candidate blocks and perform exact street/range lookup plus polyline interpolation outside the production UI.
- [ ] **OFF-106 — Run the real-address coverage benchmark.** Report parse rate, exact street rate, contained-range rate, fallback rate, ambiguous rate, unmatched categories, and examples safe for review.
- [ ] **OFF-107 — Run held-out spatial validation.** Withhold a deterministic SanGIS address-point sample before any range-repair step; compare interpolated coordinates by confidence/method/community and prevent training/validation leakage.
- [ ] **OFF-108 — Benchmark the target device.** Measure pack bytes, peak memory, decode/import time, warm/cold query latency, and 100-call throughput on the agreed Android browser.
- [ ] **OFF-109 — Decide format/runtime tools.** Record compression, block count/partition scheme, compiler language/dependencies, coordinate precision, and installed-index representation.
- [ ] **OFF-110 — Review feasibility thresholds.** Approve or explicitly revise the provisional size, coverage, accuracy, and speed targets in the specification based on results.
- [ ] **OFF-111 — Benchmark integrity paths.** Compare incremental streaming SHA-256 with bounded per-block Web Crypto plus whole-file verification; record peak memory, CPU, bundle cost, and corruption coverage.
- [ ] **OFF-112 — Prototype community disambiguation.** Measure duplicate street names before/after the feed-community crosswalk and require ambiguous candidates to remain unmatched.
- [ ] **OFF-113 — Prototype intersection topology.** Measure address-range-only intersections, then conditionally add only the minimal derived named-road node data from Roads/`EDGES` needed to meet the intersection gate.
- [ ] **OFF-114 — Spike IndexedDB failure modes.** Exercise transaction auto-commit across event-loop yields, per-block writes, multi-tab install contention, `blocked`/`versionchange`, eviction, private mode, and quota errors before final schema design.
- [ ] **OFF-115 — Test the static host contract.** Verify public-origin content type, manifest/pack byte length, caching, no unintended `Content-Encoding`, cancellation/retry without HTTP ranges, service-worker scope, and the full project-size limit.
- [ ] **OFF-116 — Measure location uncertainty UX inputs.** Capture representative `coords.accuracy`, acquisition latency, power/timeout tradeoffs, and the rounding/filter behavior needed to avoid false precision.

### Required report

The feasibility report must include:

- Source and compiler checksums/versions.
- Raw, intermediate, transfer, single-installed, and active-plus-staged update-peak sizes.
- Counts of streets, aliases, segments, usable ranges, geometry points, blocks, and rejected records.
- Coverage and ambiguity by input category and locality when available.
- Median/p95 spatial error by match class where reference points exist.
- p50/p95 cold and warm lookup latency and peak memory.
- Measured SanGIS primary coverage, Census fallback/alias gain, community disambiguation gain, and address-point join quality.
- Per-component size, including geometry, ranges, strings, community map, exact/alias/fuzzy indexes, and optional intersection topology.
- Browser capability and host-contract results, including unsupported/degraded behavior.
- The exact configuration recommended for R2 and rejected alternatives.

### R1 exit gate — feasible design selected

Pass only when:

- A complete county candidate is no more than 30 MiB compressed, with a preferred path to 20 MiB or less.
- Representative installed and two-version update-peak sizes fit the approved browser quota budget.
- The fixture parse/resolution targets are met or revised with user approval and honest UI wording.
- Performance is acceptable on the reference Android device without main-thread work.
- The chosen precision/geometry encoding does not materially dominate interpolation error.
- The community crosswalk materially reduces duplicate-street ambiguity without cross-community false matches.
- One format, integrity path, compression/fallback strategy, and toolchain are selected in a recorded decision.
- The format can install under multi-tab/event-loop/quota fault injection without relying on long-lived IndexedDB transactions.
- Static-host behavior is proven and does not require byte ranges for correctness.

If the pack exceeds 30 MiB, try measured changes in this order: remove unused attributes, improve dictionaries/varints, tune geometry precision/simplification within error gates, tune compression, and optimize indexes. Do not split into user-visible regional downloads unless the one-pack requirement is revisited.

## 6. Phase R2 — Production compiler and format v1

Objective: make the selected pack format deterministic, defensive, documented, and reproducible enough to publish.

Dependencies: R1 passed.

### Work items

- [ ] **OFF-201 — Freeze the selected format v1.** Specify byte order/storage layout, mandatory/optional fields, directories/pages, compression, checksums, maximums, and compatibility behavior with golden binary fixtures. Use the `OFG1` name only if R1 selects it.
- [ ] **OFF-202 — Productionize source adapters.** Validate schemas explicitly and produce actionable drift errors instead of silently dropping fields.
- [ ] **OFF-203 — Implement validated range transforms.** Handle structured string house numbers, ascending/descending ranges, side/parity/mix/imputation/offset flags, malformed values, duplicate records, and rejected-record reports without lossy integer coercion.
- [ ] **OFF-204 — Implement approved primary/fallback merge.** Join SanGIS addresses/communities to roads, preserve provenance/aliases, apply deterministic SanGIS-to-Census precedence, and emit join/conflict/delta reports.
- [ ] **OFF-205 — Implement geometry encoding.** Apply the approved CRS/datum transform, validate control points, de-duplicate geometry by stable ID, quantize, optionally simplify under accuracy bounds, encode, and retain interpolation orientation.
- [ ] **OFF-206 — Build indexes and blocks.** Produce the approved street-key partition, alias index, candidate descriptors, and individually verifiable blocks.
- [ ] **OFF-207 — Serialize and signpost limits.** Emit declared maximum raw sizes/counts, per-block SHA-256, whole-pack checksum, and release metadata.
- [ ] **OFF-208 — Make output deterministic.** Normalize ordering/metadata and add a test compiling twice to byte-identical output.
- [ ] **OFF-209 — Build an independent validator.** Re-open the pack, validate offsets/counts/checksums/bounds/references, execute smoke queries, and reject truncation/corruption.
- [ ] **OFF-210 — Generate release artifacts.** Produce pack, active-manifest candidate, deterministic internal source manifest, detached build timestamp, notices, checksums, and size/coverage/join/conflict reports plus changelog entry.
- [ ] **OFF-211 — Threat-test source and pack readers.** Cover traversal, excessive expansion, allocation overflow, corrupt varints, invalid coordinates, overlapping/out-of-range offsets, duplicate keys, and incompatible versions.

### Deliverables

- Documented selected format and golden fixtures.
- Deterministic compiler and independent validation command.
- One validated San Diego County candidate pack.
- Machine-readable active-manifest candidate.
- Full provenance, notices, and QA report bundle.

### R2 exit gate — publishable artifact

Pass only when:

- Two clean builds from the same locked inputs have identical SHA-256.
- Pack-internal metadata contains no wall-clock/build-host value that breaks determinism.
- Golden reader/writer tests pass, including unknown-version rejection.
- Corruption and malicious-input tests fail safely.
- Pack is ≤30 MiB and all R1 quality gates still pass.
- Manifest/notices name all sources, vintages, retrieval dates, and derived-product status.
- A clean machine can reproduce and validate the candidate from documented commands.

## 7. Phase R3 — Browser reader and transactional IndexedDB installer

Objective: safely download, verify, stage, activate, update, remove, and recover the pack without freezing the site or losing a working version.

Dependencies: R2 format frozen. R3 may use the R2 candidate before public promotion.

### Work items

- [ ] **OFF-301 — Implement the bounded browser reader.** Capability-test the selected codec, parse headers/directories, enforce sizes/counts, verify hashes with the selected bounded-memory path, decode only requested blocks, and reject unsupported formats.
- [ ] **OFF-302 — Establish the worker protocol.** Version request/response messages for install, cancel, query, batch query, progress, error, and shutdown.
- [ ] **OFF-303 — Implement IndexedDB schema v1.** Add `meta`, versioned `packs`, `streetIndex`, `aliases`, `installState`, and `eventCache` stores with tested upgrades.
- [ ] **OFF-304 — Implement storage capability/preflight.** Detect unavailable/ephemeral storage, treat quota/usage as estimates, include active + staged + bounded working overhead, and surface insufficient/unknown states while making actual writes authoritative. Never delete the active pack merely to make an update fit.
- [ ] **OFF-305 — Implement staged installation.** Stream download/verify and write bounded blocks in short transactions under a pending version, run smoke queries, then atomically swap the active pointer. Never await network/decompression work inside an IndexedDB transaction.
- [ ] **OFF-306 — Implement safe update/rollback.** Keep the active and previous versions through failed updates and old-tab reader leases; clean only after a grace/no-reader check; support manifest rollback.
- [ ] **OFF-307 — Implement cancellation/recovery.** Abort fetch/worker operations, clean only staged records, detect incomplete installs, and restart or resume verified checkpoints.
- [ ] **OFF-308 — Request persistent storage.** Request only after the user initiates the feature; store/display the result without treating denial as failure.
- [ ] **OFF-309 — Implement safe deletion.** Confirm, remove only OffGeo stores/version records, clear state, and leave unrelated site data intact.
- [ ] **OFF-310 — Test eviction and quota failures.** Simulate missing blocks, `QuotaExceededError`, transaction abort, tab close, reload, corrupt pack, and database upgrade failure.
- [ ] **OFF-311 — Coordinate multiple tabs.** Use Web Locks with an IndexedDB lease/fencing fallback, broadcast progress, pin reader versions, and implement `blocked`, `versionchange`, stale-owner, and cleanup behavior.
- [ ] **OFF-312 — Implement legacy privacy migration.** Idempotently remove known `latitude`/`longitude`, legacy `{lat,lng}` geocoder cache entries, and recognized per-event records carrying `nearby`; retain unrelated data and record a non-sensitive migration version.
- [ ] **OFF-313 — Prove bounded-memory integrity.** Instrument compressed/decompressed/hash/structured-clone memory during install and prevent simultaneous whole-pack copies.

### R3 exit gate — reliable local database

Pass only when browser integration evidence proves:

- First install, cancel, retry, update, rollback, delete, and reinstall work.
- A failed/interrupted/corrupt update never replaces or damages the active pack.
- No unbounded whole-pack decompression or main-thread parse occurs.
- Installed-size and install-time gates pass on reference devices.
- Two-version update-peak storage/memory is measured; insufficient space postpones the update without losing the active pack.
- Evicted/missing data is detected and the user can recover.
- IndexedDB upgrade tests preserve an active v1 pack or fail with a safe recovery path.
- Two tabs cannot race install/activation/cleanup, an old tab cannot lose its pinned pack, and a blocked upgrade has a recoverable UI state.
- Forced event-loop yields produce no inactive-transaction failures.
- A migrated live-site profile contains no legacy user coordinates/geocode points and preserves unrelated storage.

## 8. Phase R4 — Offline geocoder and distance engine

Objective: resolve supported call addresses with explainable confidence and calculate distance without network access.

Dependencies: R3 storage/query access; normalization fixtures begin in R1.

### Work items

- [ ] **OFF-401 — Productionize the address parser.** Return typed numbered/block/intersection/street-only/unsupported structures, recognize slash intersections without spaces, model supported house-number strings, and never throw on arbitrary feed text.
- [ ] **OFF-402 — Share/version normalization.** Ensure compiler/runtime produce identical keys for every golden fixture.
- [ ] **OFF-403 — Implement exact candidate lookup.** Use street key, approved aliases, the versioned feed-community/jurisdiction crosswalk, ZIP/service-area hints, and deterministic tie ordering.
- [ ] **OFF-404 — Implement range scoring.** Score containment, parity/mix/imputation, bounded numeric gap, community agreement, and source precedence; explicitly detect ambiguity and never fall back across an incompatible community.
- [ ] **OFF-405 — Implement polyline interpolation.** Follow cumulative geometry length, handle reversed ranges/orientation, and return bounded WGS84 coordinates.
- [ ] **OFF-406 — Implement intersections.** Resolve shared/coincident nodes for two exact street candidate sets with the approved minimal topology and return method/confidence/reason.
- [ ] **OFF-407 — Implement conservative fallbacks.** Apply benchmarked hard limits to nearest exact-street ranges and a bounded fuzzy index with threshold/runner-up margin; never scan the whole pack per query or use user proximity.
- [ ] **OFF-408 — Implement result contracts.** Every result contains status, reason, confidence/method as applicable, pack version, and stable source/segment diagnostics.
- [ ] **OFF-409 — Implement Haversine distance.** Validate inputs, incorporate the geolocation accuracy radius into warning/rounding/filter rules, and format accessible feet/miles without implying driving distance.
- [ ] **OFF-410 — Add batch/cancellation support.** Resolve visible calls progressively, prioritize current viewport if useful, ignore stale feed batches, and keep UI responsive.
- [ ] **OFF-411 — Run correctness/coverage/performance suites.** Include exact, parity, reversed, block, intersection, alias, duplicate, ambiguity, malformed, and out-of-county fixtures.

### R4 exit gate — trustworthy engine

Pass only when:

- Golden parser/normalizer outputs match between compiler and browser.
- Interpolation geometry tests pass for straight, multi-vertex, curved, zero-span, ascending, and descending segments.
- Ambiguous fixtures never return an arbitrary match.
- Nonstandard house numbers return a tested supported result or `NONSTANDARD_HOUSE_NUMBER`, never a partially parsed number.
- Duplicate-street/community and slash-intersection fixtures meet their dedicated coverage gates.
- Every result includes the required reason and pack version.
- Coverage, accuracy, warm/cold latency, batch time, and responsiveness gates pass.
- An offline integration test proves no runtime geocoder network request occurs.

## 9. Phase R5 — Download, permission, and distance UI

Objective: make installation and distance useful, understandable, fast, accessible, and privacy-preserving.

Dependencies: stable R3 installer events and R4 result contract. Wireframes/content can be reviewed during R1.

### Work items

- [ ] **OFF-501 — Add the offline-data card.** Show size, source vintage, version, last check, attribution, not-installed/ready/update/stale states, and accuracy explanation.
- [ ] **OFF-502 — Add install progress.** Show downloaded bytes/total/percent and downloading/verifying/installing stages with cancel/retry actions and `aria-live` updates.
- [ ] **OFF-503 — Add storage states.** Explain persistent versus best-effort storage, quota errors, eviction recovery, and safe deletion.
- [ ] **OFF-504 — Add location education and action.** Explain device-local straight-line calculation before **Use my location**; do not prompt on load.
- [ ] **OFF-505 — Handle location states.** Implement requesting, active with reading age/accuracy, normal-accuracy acquisition, deliberate higher-accuracy retry, refresh, stop, denied, timeout, unavailable, and insecure-context content.
- [ ] **OFF-506 — Add distance chips.** Render uncertainty-aware approximate feet/miles with accessible labels, confidence detail, and stable loading/unmatched/poor-location states.
- [ ] **OFF-507 — Add nearest controls.** Add nearest sorting and radius filtering while keeping unmatched calls visible and preserving stable ordering.
- [ ] **OFF-508 — Add confidence details.** Expose street-range/intersection/fallback method and reason in plain language; do not present source IDs as primary UI.
- [ ] **OFF-509 — Add restrained motion.** Use short opacity/transform transitions for state changes, avoid disruptive list movement, and fully honor `prefers-reduced-motion`.
- [ ] **OFF-510 — Test accessibility/responsiveness.** Keyboard/focus order, screen-reader status text, contrast, 320 px layout, large text, reduced motion, slow download, and one-handed mobile use.
- [ ] **OFF-511 — Test privacy boundaries.** Instrument network and persistence APIs while granting/refreshing/stopping location and resolving/sorting calls.
- [ ] **OFF-512 — Remove the legacy online geocoder.** Delete the Google geocoding request/key and coordinate logs/persistence; complete the provider-console revoke/restrict action before deployment.
- [ ] **OFF-513 — Make external maps explicit.** Replace row-click iframe loading with a labeled external-map action that discloses address sharing and connectivity; ensure ordinary row interaction makes no map-provider request.
- [ ] **OFF-514 — Separate subsystem errors.** Give feed auth/CORS/schema, pack download/integrity, storage/quota, worker/runtime, geocode-unmatched, and location-permission failures distinct states and recovery actions.
- [ ] **OFF-515 — Integrate the approved feed endpoint.** Remove any secret credential from the static page and browser-visible URL. Use the R0 public-client or controlled same-origin proxy contract, constrain proxy inputs/origins/rate limits, and test credential rotation plus 401 recovery.

### R5 exit gate — usable and private

Pass only when recorded browser evidence covers:

- A new user understands the 10–30 MiB download, installs it, and can recover from cancellation/failure.
- Location is requested only from an explicit gesture after the local-only explanation.
- Distance is consistently marked approximate and straight-line.
- Permission denial never blocks calls or pack usage.
- Sorting/filtering remains stable and unmatched calls remain visible.
- Keyboard, screen reader, narrow viewport, large text, and reduced-motion checks pass.
- Captured network traffic and all persistent storage contain no user coordinates.
- An upgraded profile has no legacy coordinate/geocoder cache, the old browser key is absent from shipped source, and unrelated storage survives.
- Clicking/expanding a row does not contact Google; only the disclosed external-map action does.
- A feed 401 cannot be mistaken for a corrupt/missing address pack.
- Browser source/network/cache inspection exposes no secret calls-service credential.

## 10. Phase R6 — Complete offline/PWA behavior

Objective: make the installed app genuinely useful without connectivity, including the most recently fetched calls.

Dependencies: R3 database and R5 UI states.

### Work items

- [ ] **OFF-601 — Replace the current service worker.** The existing worker caches only `/` under an unversioned name and its fetch handler is commented out. Implement a versioned app-shell strategy for required HTML/JS/CSS/icons, old-cache cleanup, navigation fallback, and offline reload without placing the large pack in Cache API.
- [ ] **OFF-602 — Cache one valid calls snapshot.** Validate schema/timestamps, persist the payload atomically, replace rather than accumulate history, and purge old legacy per-event entries under the approved migration.
- [ ] **OFF-603 — Add live/stale/hidden/expired states.** Mark a snapshot non-live immediately after a failed/no-network refresh, show source/local age, hide it after the approved safety window behind an explicit action, and purge it at the retention limit.
- [ ] **OFF-604 — Define service-worker upgrades.** Ensure an app update cannot strand an incompatible active pack and old tabs continue safely.
- [ ] **OFF-605 — Exercise airplane-mode flows.** Reload, view cached calls, geocode, calculate distance, sort/filter, inspect source credits, and recover when connectivity returns.
- [ ] **OFF-606 — Exercise partial states.** App shell cached but no pack, pack installed but no call cache, stale calls, evicted pack, and an update interrupted by loss of network.
- [ ] **OFF-607 — Fault-test the calls feed.** Inject 401, 403, CORS rejection, timeout, malformed JSON, double-encoded JSON, schema mismatch, invalid/missing `LastUpdated`, and device clock skew while preserving only the last valid snapshot.

### R6 exit gate — offline end to end

Pass only when a fresh online setup followed by airplane-mode reload supports cached-call display, geocoding, distance, sorting, and filtering with zero network dependency, every cached/stale state is accurately labeled, and expired snapshots cannot silently appear as active calls.

## 11. Phase R7 — Publishing, operations, and four-month refresh

Objective: ship immutable, auditable packs and keep them current without putting clients at risk.

Dependencies: R2 release artifacts; public activation waits for R3–R6 gates.

### Work items

- [ ] **OFF-701 — Configure immutable pack hosting.** Use versioned same-origin URLs, correct container bytes/content type/length, no accidental HTTP recompression, ordinary caching, HTTPS, and no in-place replacement. HTTP range support is optional and must not be required for correctness.
- [ ] **OFF-702 — Publish the small active manifest.** Include pack URL, length, checksum, format, minimum app version, vintage, release notes, and stale date.
- [ ] **OFF-703 — Build a release command.** Fetch locked inputs, compile twice/determinism-check, validate, test, benchmark, and create the report bundle.
- [ ] **OFF-704 — Add source update checks.** Every four months, compare official metadata/checksums and produce “no source change” or a candidate diff.
- [ ] **OFF-705 — Add regression review.** Compare counts, address-point/road/community join rates, names, ranges, geometry, conflicts, nonstandard-number rejects, size components, coverage, accuracy, and latency to the active pack.
- [ ] **OFF-706 — Require human promotion.** Review provenance/notices, source diffs, all quality reports, app compatibility, and release notes before moving the active manifest.
- [ ] **OFF-707 — Prove rollback.** Point the active manifest to the previous immutable version and verify new clients install it while existing valid clients remain functional.
- [ ] **OFF-708 — Define retention.** Keep at least active and previous pack/report bundles; document when older versions may be removed.
- [ ] **OFF-709 — Publish user-facing data credits.** Include every government publisher, vintage, source link, derived-product notice, and Census citation/repackaging language.
- [ ] **OFF-710 — Record operational evidence.** Date, reviewer, compiler/app commits, source/pack checksums, gate results, deployed URL, and rollback version.
- [ ] **OFF-711 — Retain reproducibility inputs.** Preserve content-addressed source archives, source lock, compiler dependencies, reports, active/previous packs, and notices according to the release retention policy.

### Four-month runbook

1. Check source URLs, metadata, and bytes.
2. Review unexpected redirect, checksum, archive, or schema changes.
3. If all enabled inputs are unchanged, record the check and stop; do not create a cosmetic pack version.
4. If inputs changed, create a locked candidate and compile twice.
5. Run validator, tests, fixture coverage, spatial accuracy, size, device performance, and privacy/offline smoke suites.
6. Review source/segment/join/community/conflict/regression reports and attribution.
7. Publish immutable candidate files.
8. Update the active manifest only after approval.
9. Verify from the public origin on desktop and Android.
10. Retain the prior release, exact candidate source archives, and documented rollback pointer.

### R7 exit gate — operable release

Pass only when a clean public-origin install succeeds, all pack metadata/checksums match, the app works offline on target browsers, credits are visible, rollback is proven, and the release evidence names a responsible reviewer.

## 12. Cross-phase test matrix

| Area | Unit | Integration | Device/E2E | Release evidence |
| --- | --- | --- | --- | --- |
| Source acquisition | Schema/checksum/path validators | Locked source to records | Clean-machine fetch | Source manifest/profile |
| Compiler | Normalize/ranges/geometry/codec | Source to pack to reader | Peak memory/time | Determinism + QA reports |
| Pack reader | Bounds/hash/version/corruption | Golden and candidate pack | Worker responsiveness | Validation report |
| IndexedDB | Stores/migrations/state machine | Install/update/failure/eviction | Android quota and timing | Storage report |
| Geocoder | Parser/scorer/interpolation/reasons | Real fixture corpus | Batch latency | Coverage/accuracy report |
| Location/distance | Haversine/formatting/state | Permission and clearing | Android permission flows | Privacy capture |
| UI | State rendering/sorting/filtering | Worker/feed updates | Mobile/a11y/reduced motion | E2E screenshots/log |
| Offline | Cache policy/stale time | Service worker + event cache | Airplane-mode reload | Offline checklist |
| Release | Manifest compatibility | Publish/rollback | Public-origin install | Signed-off release record |

## 13. Required decisions and decision owners

These decisions must be recorded rather than left implicit:

| Decision | Needed by | Evidence required |
| --- | --- | --- |
| SanGIS primary and Census fallback precedence | R0 exit | Schema/join profile, conflict report, and measured coverage benefit |
| Compiler language/dependencies | R1 exit | Reproducibility, installability, performance, maintenance comparison |
| Container, integrity, compression, and block partition | R1 exit | Custom-versus-maintained comparison; pack-size, random-read, memory, and browser-support benchmark |
| Coordinate quantization/simplification | R1 exit | Spatial error comparison |
| Final quality thresholds | R1 exit | Fixture and device benchmark report |
| Feed community crosswalk | R1 exit | Duplicate-street ambiguity and unknown/many-to-many mapping report |
| Calls snapshot safety/retention windows | R5 start | Feed cadence, stale-risk review, and clock/network fault tests |
| Low-confidence display default | R5 start | UX review using real unmatched/ambiguous examples |
| Reference Android/browser matrix | R1 start | Current supported user devices/browsers |
| Stale warning and support window | R7 start | Refresh cadence and source release behavior |

## 14. Definition of done

OffGeo version 1 is complete only when every item below has evidence:

- [ ] A public-government-source San Diego County pack is reproducibly compiled and is ≤30 MiB.
- [ ] The active pack, source bytes, compiler/app commits, notices, and reports are linked by checksums/versions.
- [ ] Runtime matching needs no geocoding service and returns a confidence/reason for every input.
- [ ] Size, fixture coverage, held-out accuracy where available, and target-device performance meet approved gates.
- [ ] IndexedDB install/update/cancel/failure/eviction/delete flows preserve the last known-good state.
- [ ] Multi-tab locking, reader pinning, blocked upgrades, and short transaction lifetimes are proven under fault injection.
- [ ] Pack and calls cache support the documented airplane-mode journey.
- [ ] Location is opt-in, memory-only, clearable, and absent from captured requests/logs/persistent storage.
- [ ] The old Google geocoder/key, coordinate logs/storage, and implicit map iframe are removed; migration preserves unrelated data.
- [ ] Calls display approximate feet/miles, confidence details, nearest sorting, radius filtering, and visible unmatched rows.
- [ ] Download, permission, offline, stale, and error UI passes accessibility/mobile/reduced-motion checks.
- [ ] Public-origin installation and rollback are proven on desktop Chromium and the selected Android browser.
- [ ] The four-month source-check/build/review/promotion runbook has an owner and a scheduled trigger.
- [ ] User-facing credits and derived-product notices identify every included government source.
- [ ] Feed 401/CORS/schema failures, pack failures, storage failures, and location failures remain distinguishable and recoverable.
- [ ] No secret calls-service credential is present in browser source, browser-visible URLs, caches, or diagnostics.

## 15. Recommended first implementation slice

Start with `OFF-001` through `OFF-017`, then `OFF-101` through `OFF-116`. That slice should end in a disposable but measured SanGIS-primary/Census-fallback county pack, retained source snapshots, build-host resource budget, feed-community crosswalk, format/integrity comparison, browser/host spike, legacy privacy migration plan, and benchmark report. It gives the project the highest-value answers—coverage, source joins, ambiguity, size, accuracy, speed, reproducibility, browser feasibility, and existing-app cleanup—before any permanent format, IndexedDB migration, or download UI is committed.
