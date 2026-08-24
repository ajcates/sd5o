# OffGeo Phase R1 TODO — Feasibility Compiler and Benchmark

Status: Early — Group A (`OFF-101`, `OFF-102`) is done; Group B (`OFF-103`) is essentially done except one deliberately-deferred piece. Everything else (`OFF-104`–`OFF-116`) is not started.
Last updated: 2026-08-24
Scope: [roadmap.md §5](./roadmap.md#5-phase-r1--feasibility-compiler-and-benchmark) (`OFF-101`–`OFF-116`).
Reference: [spec.md](./spec.md) for merge rules and quality-gate language cited below; [`tools/offgeo/README.md`](../../tools/offgeo/README.md) for implementation detail, real numbers, and run commands — this file tracks status and links out, it doesn't duplicate the numbers.

R0 is closed (see [todo.md](./todo.md)); this file exists because R1 work accumulated across several sessions without a tracking document the way R0 had one. Written retroactively for Group A/B, prospectively for the rest.

## Group A — Thin source readers and shared normalization — done 2026-08-24

- [x] **OFF-101 — Implement thin source readers.** All four sources: `tools/offgeo/compile-sangis-roads.py`, `compile-sangis-address-points.py`, `compile-census-addrfeat.py`, `compile-census-featnames.py`. Each reads its retained archive directly (no `pyshp`/`gdal`), applies an explicit named CRS transform (`state-plane-2230-feet-to-wgs84-cs2cs-v1` for both SanGIS sources; `nad83-4269-socal-hgridshift-cshpgn-to-wgs84-v1` for the two Census sources), retains only required fields (SanGIS's `APN`/`PARCELID`/`ADDRAPNID`/`ADDRUNIT` explicitly read-then-never-emitted per spec.md 6.1 line 79), and writes deterministic sorted JSONL + a report. Real runs against the full retained archives are documented in `tools/offgeo/README.md`'s per-reader sections, not just unit-tested.
  - Found and fixed a real transform bug along the way: `cs2cs EPSG:4269 EPSG:4326`'s default operation is PROJ's "Ballpark geographic offset" (`+proj=noop`, unknown accuracy) — exactly the silent NAD83-as-WGS84 relabeling spec.md 6.1 forbids. Fixed with `lib/coords.py`'s `batch_nad83_geographic_to_wgs84`, which forces the real NOAA `us_noaa_cshpgn.tif` grid via an explicit `cct` pipeline.
- [x] **OFF-102 — Build shared normalization fixtures.** `tools/offgeo/lib/normalize.py`, versioned via `NORMALIZE_VERSION`: canonical directions, suffixes (SanGIS's own two abbreviation tables plus a Census-specific vocabulary added when reconciliation needed it), whitespace/punctuation, routes, ordinals (leading-zero-ordinal fix, see below), unit stripping, block syntax, and intersections. Full unit coverage in `tests/offgeo/unit/test_normalize.py`, including a corpus-wide check against the real Group 3 calls-feed fixtures.
  - Found and fixed a real cross-source mismatch while building the street reconciliation (`OFF-103`/`OFF-004` below): SanGIS zero-pads ordinal street numbers (`01ST`..`09TH`, 2,018 SanGIS segments including downtown's numbered avenues) while Census does not. `canonicalize_street_core_name` fixes it, scoped narrowly enough it can never touch a house number.

Output: `tools/offgeo/compile-sangis-roads.py`, `compile-sangis-address-points.py`, `compile-census-addrfeat.py`, `compile-census-featnames.py`, `tools/offgeo/lib/normalize.py`, `tools/offgeo/lib/coords.py` (extended). Real run numbers, source citations, and both bug writeups in `tools/offgeo/README.md`'s R1 sections.

## Group B — Range and join-quality profiling — mostly done 2026-08-24

- [x] **OFF-103 — Profile range and join quality (within-source and roads<->address-points join).** `tools/offgeo/profile-join-quality.py`: address-range side classification (absent/ascending/descending/malformed-one-bound-zero, extreme spans), address-point-to-road join quality by `ROADSEGID` (sentinel/joined/dangling, joined-by-road-confidence, numeric range-containment among joined), `LMIXADDR`/`RMIXADDR` mix-flag distributions, duplicate road geometry, and ZIP consistency between joined address points and their road's `L_ZIP`/`R_ZIP`. Real run: 64.1% of address points join, 98.3% range-containment among joined, only 3 duplicate-geometry groups out of 164,555 roads, 99.4% ZIP consistency.
- [x] **OFF-103 continued / OFF-004 cross-source half — SanGIS<->Census street-name reconciliation.** `tools/offgeo/reconcile-sangis-census-streets.py`: canonical street-key comparison between the two sources, restricted on the Census side to range-bearing TLIDs. Real run: 75.7% of SanGIS street keys have a same-named Census counterpart; 4,687 Census-only range-bearing keys (15,076 TLIDs) is the measured coverage-gain answer to `OFF-004`'s deferred question.
- [ ] **OFF-103 remaining scope — address-range conflicts between matched streets.** Not done. Requires a geometry-based segment match (which SanGIS `ROADSEGID` and Census `TLID` correspond to the same physical stretch of road, not just the same street name) before ranges from the two sources can be compared for the same segment. Name-level reconciliation above doesn't attempt this — flagged there as deliberately out of scope, not forgotten.
- [ ] **Known remaining gap, not yet fixed** (found during reconciliation, documented in `tools/offgeo/README.md`): some Census `FEATNAMES` rows carry their suffix embedded in the `NAME`/`FULLNAME` field itself with `SUFTYPABRV` blank (e.g. `"Adelaide Gln"`). Undercounts `OFF-103`/`OFF-004`'s matched-street rate slightly. Would need `lib/normalize.py`'s free-text `parse_street_name` run against `FULLNAME` as a fallback when the structured suffix field is blank.

Output: `tools/offgeo/profile-join-quality.py`, `tools/offgeo/reconcile-sangis-census-streets.py`. Real numbers and both normalization-bug writeups in `tools/offgeo/README.md`.

## Not started — `OFF-104` through `OFF-116`

None of the remaining R1 work items have been started. Listed here (not duplicated from roadmap.md) so this file stays the single place to check R1 status without re-reading the full roadmap:

- [ ] **OFF-104 — Prototype compact representations.** Compare the custom block format against at least one maintained SQLite/PBF-style alternative.
- [ ] **OFF-105 — Implement a benchmark reader.** Exact street/range lookup plus polyline interpolation outside the production UI.
- [ ] **OFF-106 — Run the real-address coverage benchmark.** Needs a geocoder prototype run against the real Group 3 calls-fixture corpus (`tests/offgeo/fixtures/addresses.json`) — note the map-prototype's `build-address-index.py`/`geocoder.js` already did a *much* smaller, feature-scoped version of this for the map UI, not a substitute for the real benchmark.
- [ ] **OFF-107 — Run held-out spatial validation.**
- [ ] **OFF-108 — Benchmark the target device.** Some informal signal already exists (peak RSS/wall time per reader run, recorded in `tools/offgeo/README.md`), but that's this dev host, not a formal reference-device benchmark, and it measures the readers, not decode/import/query latency of an actual compiled pack (which doesn't exist yet).
- [ ] **OFF-109 — Decide format/runtime tools.**
- [ ] **OFF-110 — Review feasibility thresholds.**
- [ ] **OFF-111 — Benchmark integrity paths.**
- [ ] **OFF-112 — Prototype community disambiguation.** Note R0 Group 3's feed-community crosswalk (`tests/offgeo/fixtures/community-crosswalk.json`) is a related but distinct, smaller piece of work — it maps feed `Community` strings to SanGIS `COMMUNITY` values, not the duplicate-street-name-before/after-crosswalk measurement this item asks for.
- [ ] **OFF-113 — Prototype intersection topology.**
- [ ] **OFF-114 — Spike IndexedDB failure modes.**
- [ ] **OFF-115 — Test the static host contract.**
- [ ] **OFF-116 — Measure location uncertainty UX inputs.**

## R1 exit gate — feasible design selected (roadmap.md §5)

Not evaluated yet — every bullet in the roadmap's own R1 exit-gate list depends on work items not yet started (`OFF-104` onward). Revisit once at least a candidate pack format and benchmark reader exist.

## Suggested execution order

1. `OFF-112` (community disambiguation) can reuse Group A/B's readers directly and is comparatively cheap — a reasonable next step before committing to a pack format.
2. `OFF-104` (compact representation prototyping) is the biggest open decision blocking most of the rest of R1 (`OFF-105`–`OFF-111` all depend on a candidate format existing).
3. `OFF-106` (real-address coverage benchmark) needs a geocoder prototype, which needs `OFF-104`/`OFF-105` first (or at minimum a throwaway lookup structure — the map-prototype's `geocoder.js` is *not* that prototype, see the note above).
4. `OFF-108`, `OFF-111`, `OFF-114`, `OFF-115` are host/device/browser feasibility spikes that don't depend on the format decision and could run in parallel with `OFF-104`.
5. `OFF-113` (intersection topology) and `OFF-116` (location UX inputs) are lower-urgency and can trail the rest.
