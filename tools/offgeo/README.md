# OffGeo build tooling

Build-time tooling for the OffGeo offline geocoder. See [`../../notes/offgeo/roadmap.md`](../../notes/offgeo/roadmap.md) for the phase plan and [`../../notes/offgeo/spec.md`](../../notes/offgeo/spec.md) for the product/format requirements. Phase R0 (source pinning/profiling/fixtures/audits, `OFF-001`–`OFF-017`) is done — see [`../../notes/offgeo/todo.md`](../../notes/offgeo/todo.md) for the closed checklist. This directory now also carries the start of **Phase R1, Group A** (`OFF-101`/`OFF-102`, thin source readers and shared normalization) — see the section near the bottom of this file.

## Fetching and pinning sources

```sh
python3 tools/offgeo/fetch-sources.py            # fetch/verify all locked sources
python3 tools/offgeo/fetch-sources.py --only sangis-roads-all   # just one
python3 tools/offgeo/fetch-sources.py --force     # re-download even if already retained
```

`tools/offgeo/config/sources.lock.json` is the single authority for source URL, adapter name, vintage, license, and (once fetched) checksum. The script:

1. **Preflights** disk space via `HEAD` requests before downloading anything, requiring 3x the declared total free.
2. **Fetches** only from an explicit host allowlist (`geo.sandag.org`, `www2.census.gov`); a redirect to any other host aborts the run.
3. **Hashes while streaming** (bounded memory, 300 MiB hard cap per archive) and only writes the file once complete.
4. **Refuses silent drift**: if the lock file already has a `sha256` for a source and a re-fetch produces a different one, the run aborts with an explicit error instead of updating the lock. A first-time fetch pins the observed checksum.
5. **Inspects the zip** without extracting: rejects absolute paths / `..` traversal in entry names, more than 2000 entries, or an uncompressed:compressed expansion ratio above 25x.
6. **Content-addresses** the retained file as `build/offgeo-sources/<sha256><ext>` (gitignored — see `OFF-016`). Re-running detects local corruption (retained bytes no longer match the recorded hash) and fails loudly rather than silently re-trusting a damaged file.
7. Writes `build/offgeo-sources/fetch-report.json` (per-source bytes, checksum, zip entry count/uncompressed size) and updates the lock file's `sha256`/`byteLength`/`retrievedAt`/`retainedPath` fields.

All four safeguards above (host allowlist, checksum-drift rejection, local-corruption detection, zip-safety inspection) have been exercised against the live sources, including a deliberate corruption test (truncate a retained file, confirm the script refuses to trust it, delete, re-fetch, confirm it heals).

## Pinned sources (as of 2026-08-23)

| id | publisher | dataset | bytes | sha256 |
| --- | --- | --- | --- | --- |
| `sangis-roads-all` | SanGIS | Roads - All | 103,374,275 | `c432371b4011572ae8e2c135087d359c9f62b65e36e33c89fc675b9e78356694` |
| `sangis-address-points` | SanGIS | Address Points to APN | 76,627,495 | `a792711074d4d07543826e2228c42d56fb9c375261295efbd551334c825853b0` |
| `census-addrfeat-06073` | U.S. Census Bureau | TIGER/Line ADDRFEAT (06073) | 15,102,855 | `750f9eaf9d00d11bfbd8eb4ab030d386c27fbe03fe510a67ec14789842161a8b` |
| `census-featnames-06073` | U.S. Census Bureau | TIGER/Line FEATNAMES (06073) | 3,418,066 | `454d8bb0c4e187c48d6f11d0c8709af4db69f118d6545b63407835b02393d045` |

Full metadata (documentation URL, license, publisher-displayed vintage, retrieval timestamp) lives in `config/sources.lock.json`, which is the authoritative record. The `census-addrfeat-06073` checksum matches the value already recorded in `spec.md` §4.2, confirming that documentation is accurate against the live source as of this fetch.

Publisher-displayed vintage: both SanGIS datasets show "Updated Aug 10, 2026" on their `data.sandiego.gov` landing pages. Both are licensed under the Open Data Commons Public Domain Dedication and Licence (ODC-PDDL) 1.0. Census TIGER/Line 2025 data is a U.S. Government work (not copyright-protected under 17 U.S.C. §105); the Census Bureau requests citation and a derived-product notice, which is captured in each entry's `attribution` field for later use in the pack manifest and download UI (`OFF-709`).

### Archive contents

Confirmed by listing (not extracting) each zip:

- `sangis-roads-all` — full shapefile bundle: `.shp` (238.6 MB), `.dbf` (136.1 MB), `.shx`, `.sbn`, `.sbx`, `.prj`, `.cpg`, FGDC `.shp.xml` metadata. 8 entries, 377.9 MB uncompressed.
- `sangis-address-points` — full shapefile bundle, dominated by a 560 MB `.dbf` (situs/APN attribute table) against a 34.2 MB `.shp`. 8 entries, 614.4 MB uncompressed.
- `census-addrfeat-06073` — standard TIGER/Line shapefile bundle plus ISO/FGDC metadata XML. 7 entries, 53.0 MB uncompressed.
- `census-featnames-06073` — **DBF-only relationship table, no geometry** (`.dbf`, `.cpg`, two ISO metadata XML files). This matches the TIGER/Line spec: FEATNAMES links `TLID` to alternate/official names and carries no shape of its own. 4 entries, 76.0 MB uncompressed.

### CRS control points (`OFF-014`)

Read directly from each archive's `.prj` (not yet transformed — this is a recorded observation for the R1 transform step, not a completed transform):

- **Both SanGIS sources**: `NAD_1983_StatePlane_California_VI_FIPS_0406_Feet` — NAD83, Lambert Conformal Conic, central meridian -116.25°, standard parallels 32°47'/33°53', US Survey Feet. This is EPSG:2230 (NAD83 / California zone 6, US survey feet) by parameter match; confirm against EPSG's authoritative definition before relying on it in the compiler. **This is not WGS84 and not in degrees** — it must go through an explicit State-Plane-feet → NAD83-geographic → WGS84 pipeline. Mislabeling these coordinates as already-WGS84, or treating the false easting/northing as meters, would silently misplace every road/address point.
- **Census `census-addrfeat-06073`**: `GCS_North_American_1983` — geographic (longitude/latitude in degrees), NAD83 datum. Close to WGS84 for this application's accuracy budget, but the datum difference should still be an explicit, versioned transform per `spec.md` §6.1 rather than an implicit relabel.
- `census-featnames-06073` carries no geometry, so no CRS applies.

Known-coordinate control-point validation against the *production* R1 transform is still open — that transform doesn't exist yet, and is tracked as part of `OFF-109`/`OFF-205`, not finished by this note alone. Ahead of that, the map-prototype work's own transform (`tools/offgeo/lib/coords.py`, State Plane EPSG:2230 → WGS84 via PROJ `cs2cs`) now has three real control points checked in `tests/offgeo/unit/test_coords.py`, geographically spread to catch a gross axis-swap/unit error rather than just one lucky match:

| Landmark | Real SanGIS address point | State Plane (ft) | Transformed WGS84 | Independently plausible? |
| --- | --- | --- | --- | --- |
| Downtown San Diego | 611 W G St | 6279119.9, 1840176.1 | 32.71225, -117.16857 | Yes — matches the known downtown block |
| Balboa Park (central Prado) | 1500 El Prado | 6285018.6415, 1847261.2475 | 32.73187, -117.14959 | Yes — matches the well-known Prado/museum row location |
| La Jolla Village | 7600 Girard Ave | 6247331.5175, 1887762.38825 | 32.84222, -117.27342 | Yes — matches the well-known La Jolla village core |

These are prototype-transform control points, not a substitute for `OFF-109`/`OFF-205`'s eventual validation of whatever R1 actually ships — but they already catch the class of error this item exists to catch (wrong axis order, wrong State Plane zone/units, NAD83-as-WGS84 mislabeling), since any of those would move at least one of these three points by tens to thousands of kilometers, not fractions of a degree.

## Build-host resource budget (`OFF-017`)

Measured on this Termux host during the full four-source fetch:

- Combined declared download size: 198,522,691 bytes (~189 MiB).
- Disk free before: ~7.04 GiB; after: ~6.81 GiB; consumed: ~230 MiB (matches the download total plus the JSON report/lock overhead — no extraction occurred, so no expanded-size spike yet).
- This host is otherwise at 94% disk utilization (only ~6.5 GiB free of 105 GiB) — tight enough that R1/R2 work extracting and holding the ~1 GiB combined uncompressed shapefile data, plus compiler intermediates, **must** stream rather than fully expand-then-process, and should re-check free space immediately before any extraction step, not just before download.
- The fetch script's own scratch usage is bounded: it streams to a `.tmp-<id>` file and never holds a full archive in memory (1 MiB chunks, hashed incrementally).
- Retained archives live at `build/offgeo-sources/` (gitignored). Total retained: ~189 MiB across 4 files. This directory is safe to delete and fully reproducible by re-running `fetch-sources.py`, since it is re-verified against the lock file's checksums.

Not yet measured (deferred to R1 when extraction/parsing exists): peak RAM during shapefile parsing, peak disk during expanded intermediate storage, and end-to-end compile-time resource use. Those numbers depend on the R1 compiler implementation, which doesn't exist yet.

## Group 2 — Schema profiling (`OFF-002`–`OFF-005`, `OFF-014` follow-up)

```sh
python3 tools/offgeo/dump-schema.py [source-id ...]     # field list + sample rows, exploration only
python3 tools/offgeo/profile-sources.py                 # full profiling run -> build/offgeo-sources/profile-report.json
```

`tools/offgeo/lib/dbf.py` is a small stdlib-only, forward-only reader for the classic `.dbf` format ESRI shapefiles use for attributes. It's deliberately dependency-free (no `pyshp`/`gdal`/`fiona`, none of which are installed here) because `OFF-012`'s module/toolchain decision hasn't been made yet, and profiling shouldn't presuppose it. It streams records rather than loading them, which matters: `Address_Points.dbf` is ~560 MB uncompressed. The full four-source profiling run reads 164,555 + 1,222,722 + 111,770 + 183,865 records in about 75 seconds on this device.

Full field lists, null rates, and distributions are in `build/offgeo-sources/profile-report.json` (gitignored — reproducible by re-running the script against the retained archives). Headline findings:

**SanGIS Roads - All** (164,555 records, 62 fields) — `ROADSEGID` is 100% unique with zero duplicate rows, so it's a safe join key. 28.3% of segments have a zero left-*and*-right address range (`LLOWADDR`/`LHIGHADDR`/`RLOWADDR`/`RHIGHADDR` all 0) — these are real segments (ramps, trails, unaddressed connectors) that must be excluded from numbered interpolation but kept for street/intersection fallback, exactly as `spec.md` §6.3 anticipates. Only one descending-range and one implausibly-wide-range row exist — this is a clean field, not a systemic problem. `LJURISDIC`/`RJURISDIC` show 15+ jurisdiction codes (`SD`, `CN`, `CV`, `OC`, ... — city/unincorporated-county codes), confirming roads alone don't carry a `COMMUNITY` value; that has to come from the address-point join, as `spec.md` §4.3 already assumes. **Anomaly worth carrying into `OFF-014`:** the coordinate-bounds scan found `FRXCOORD`/`FRYCOORD` minimums of exactly `0.0`, which is not a plausible San Diego County State Plane coordinate (real values run ~6.2–6.6 million ft / ~1.8–2.1 million ft per the sample rows above) — a small number of rows carry a literal zero-coordinate sentinel that any bounds/control-point check must reject rather than silently accept as "north of null island."

**SanGIS Address Points** (1,222,722 records, 22 fields) — confirms `APN` (99.4% populated), `PARCELID`, `ADDRAPNID`, and `ADDRUNIT` (18.6% populated) are present exactly as `spec.md` §4.1 warns, and none of the four may reach a derived output. `ROADSEGID` join to Roads: 66.2% joined, 33.8% carry the `0` sentinel (no linked segment — largely condo/unit sub-records sharing a parent building's frontage), and only 207 rows (0.02%) point at a `ROADSEGID` that doesn't exist in Roads at all, which is small enough to treat as a data-entry anomaly rather than a systemic join problem. **Data-quality finding for the future crosswalk (`OFF-009`):** `COMMUNITY` is *not* case-normalized at the source — `"San Diego"` (360,440 rows), `"SAN DIEGO"` (67,136 rows), and mixed-case duplicates of other names all appear as distinct values among the 115 raw distinct strings. The crosswalk must case-fold before treating this as a lookup key, or it will silently miss two-thirds of San Diego proper. Same zero-coordinate anomaly as Roads appears in `X_COORD`/`Y_COORD`.

**Census `ADDRFEAT` 06073** (111,770 records, 25 fields) — record count and the non-digit house-number count (55 + 52 = 107 across the `*FROMHN`/`*TOHN` fields) match `spec.md` §4.2's audited figures exactly, confirming the spec was written against this same vintage. 103,965 distinct `TLID`s across 111,770 rows (5,718 roads carry more than one range row, 7,805 "extra" rows total) — the duplicate-geometry-per-`TLID` behavior `spec.md` §6.3 already calls out. About 13.9% of rows are one-sided (missing the right- or left-side range entirely, reported as the `ARIDR`/`RFROMHN`/etc. blank-rate cluster), which is a normal TIGER pattern for one-sided-frontage segments, not a data error.

**Census `FEATNAMES` 06073** (183,865 records, 18 fields, no geometry) — 171,683 distinct `TLID`s, up to 7 alias rows per `TLID`, `PAFLAG` split 171,683 primary / 12,182 alias. Only 59.8% of `FEATNAMES` rows have a `TLID` that also appears in the county `ADDRFEAT` extract — expected, since `FEATNAMES` carries names for edge types (rail, water, etc.) that `ADDRFEAT` doesn't include, not a join defect; the alias table only needs to be consulted for `TLID`s that already resolved through `ADDRFEAT`.

### `OFF-004` — source precedence and value: what R0 can and can't prove yet

The within-source measurements above (join cardinality, range validity, duplicate rates) are complete. What R0 profiling **cannot** honestly measure yet is cross-source coverage gain/conflict — SanGIS `ROADSEGID` and Census `TLID` are unrelated identifier spaces from two different agencies; there is no shared key to join on. Determining "how many roads does Census add that SanGIS lacks" or "where do the two disagree" requires the shared street-name normalization pipeline (`spec.md` §6.2), which is explicitly R1 scope (`OFF-101`–`OFF-106`, in particular the real-address coverage benchmark `OFF-106`). Building an ad hoc name-matcher just for this profiling step would duplicate that work with a lower-quality throwaway version. This is a scoping decision, not a skipped task: `OFF-004`'s cross-source half is deferred to R1 with its dependency now explicit, while the within-source half (this document) is done.

### `OFF-005` — source precedence rules

Already fully specified in `spec.md` §4.3 (SanGIS wins on a validated join; Census supplies fallback/alias/gap-detection; provenance and alternate names are preserved, never averaged; every conflict is reported; unresolved conflicts are downgraded, never silently promoted). Grounding that abstract rule in the concrete fields found here: the merge/scoring step will read SanGIS `LMIXADDR`/`RMIXADDR` and Census `LFROMTYP`/`LTOTYP`/`RFROMTYP`/`RTOTYP` as the actual mix/imputation signals `spec.md` §6.3 requires, and `ROADSEGID` vs. `TLID` are confirmed to need name/geometry-based reconciliation rather than a direct key join.

## Group 3 — Fixtures and community crosswalk (`OFF-008`, `OFF-009`)

```sh
python3 tools/offgeo/capture-calls-snapshot.py       # append one read-only feed snapshot
python3 tools/offgeo/build-address-fixtures.py       # -> tests/offgeo/fixtures/addresses.json
python3 tools/offgeo/build-community-crosswalk.py    # -> tests/offgeo/fixtures/community-crosswalk.json
```

`capture-calls-snapshot.py` calls the same Azure Function `index.html` already calls in every visitor's browser (`GetCADEvents`), directly rather than through the third-party CORS proxy the current app routes through — a server-side script has no same-origin restriction to work around, so routing a credentialed request through an uncontrolled third party would add risk for no benefit. This is itself supporting evidence for the `OFF-011`/`OFF-515` finding that the proxy hop is unnecessary. The credential used is the same function key already shipped in `index.html`'s client-side source today; this script is temporary research tooling, not the production feed path (that's `OFF-011`). Each run appends one timestamped, gitignored snapshot to `build/offgeo-sources/calls-snapshots/`.

**Feed refresh cadence, observed directly:** three captures taken ~10–25 minutes apart during this session returned an unchanged `LastUpdated` for the middle and last pair, and a changed one only across the ~10-minute gap between the first two — i.e. the feed does not refresh on every request, and captures taken minutes apart within the same refresh window are exact duplicates (they were deleted rather than kept as padding). Meaningful diversity requires captures spread over hours/days, not a burst in one sitting. As of this note, `tests/offgeo/fixtures/` reflects **2 distinct feed moments, 50 unique events, 50 unique address strings** — a real but small window. Both scripts are idempotent and rebuild from whatever snapshots exist on disk, so the corpus and crosswalk report are meant to be regenerated as more snapshots accumulate over subsequent days before R1 leans on them as representative.

### `OFF-008` — address fixture corpus

`build-address-fixtures.py` classifies each distinct captured address string into the syntax categories `todo.md` asks for (a string can match more than one), and writes `tests/offgeo/fixtures/addresses.json` plus a category-count report. Every one of the 50 captured addresses hit at least one category — none fell through to the `malformed` catch-all, so 100% of this sample is accounted for. What real captures show:

- `ordinary_numbered` (43) and `has_directional` (7, e.g. `100 N EL CAMINO REAL`) dominate.
- `slash_intersection_unspaced` (7, e.g. `AMIGOS RD/E OLD JULIAN HWY`) confirms `spec.md` §6.2's note that the live feed uses no-space slash intersections — not yet seen: a *spaced* slash intersection, or an `&`/`@`/`AT` form.
- `highway` (4, e.g. `SANTA FE DR/NB INTERSTATE 5`, `STATE ROUTE 76/EL SENDERO DR`) appears only inside intersections in this sample, never as a bare numbered highway address.
- **Not yet observed in real captures:** `hundred_block`, `numbered_street`, `street_only`, `missing_locality`, `malformed`, `non_address_text`. This dispatch feed appears to emit consistently well-formed `NUMBER STREET` or `STREET/STREET` strings; categories like malformed/non-address text may simply not occur in this source (worth confirming, not assuming, once more snapshots accumulate), and `alias` cannot be detected from a single feed string at all — it needs the alias table cross-reference that is explicit R1 parser-fixture scope (`spec.md` §6.2/§17), not something OFF-008 profiling alone can produce.

The corpus intentionally drops `EventNumber`, `DateTime`, `EventType`, and `IsOpen` from the feed payload — none carry parsing signal, and `EventType` is the closest thing in this payload to incident-sensitive detail. Only `Address` (the string under test) and the `Community` values it was seen under survive into the fixture file.

### `OFF-009` — feed-community crosswalk

`build-community-crosswalk.py` streams the full distinct `COMMUNITY` value set directly from the retained `sangis-address-points` archive (not the top-20 subset `profile-sources.py` reports), case-folds both sides, and matches each feed `Community` value against it by exact case-folded string equality — deliberately not fuzzy/substring matching, so every non-match is a reviewable, explicit finding rather than a silent guess. Output: `tests/offgeo/fixtures/community-crosswalk.json`.

From the current 50-event sample (18 distinct feed communities, 7 service areas):

- **14 of 18 feed `Community` values match a SanGIS `COMMUNITY` string exactly under case-folding** (e.g. `ENCINITAS` → SanGIS `"Encinitas"`/`"ENCINITAS"`, 20,779 combined records).
- **4 unmapped, all genuine, not typos:** `PAUMA` (SanGIS only has `"Pauma Valley"`/`"PAUMA VALLEY"` — needs an explicit alias, not a fuzzy match), and `UNINCORPORATED EL CAJON` / `UNINCORPORATED LA MESA` / `UNINCORPORATED VISTA` — the feed prefixes unincorporated county pockets adjacent to a city with `UNINCORPORATED `, a compound label that does not exist as a literal SanGIS `COMMUNITY` string at all. Resolving these needs a human-authored alias table (mapping the compound feed label onto the correct SanGIS community and/or jurisdiction-code fallback), not a string-matching improvement — recorded here as the concrete input to that future work, per `spec.md` §4.3/§6.3's community-crosswalk requirement.
- **One community-spans-multiple-service-areas case:** `UNINCORPORATED EL CAJON` appeared under both `RANCHO SAN DIEGO / LEMON GROVE` and `SANTEE / LAKESIDE / ALPINE` (3 occurrences total) — plausible for a county pocket near a patrol-area boundary, but the sample is too small (3 events) to treat as confirmed; re-check once the corpus grows. No other community showed this in the current sample.

R0 is closed — all six groups done (`OFF-004`'s cross-source half and one Census exit-gate bullet are the only genuinely-R1-blocked leftovers, tracked in `notes/offgeo/todo.md`). Group 4 (privacy/architecture audit, mini framework, map prototype), Group 5 (feed adapter contract), and Group 6 (tooling decision, browser capability matrix) all landed after this section was first written; see [`../../notes/offgeo/index-html-audit.md`](../../notes/offgeo/index-html-audit.md), [`../../notes/offgeo/feed-adapter-contract.md`](../../notes/offgeo/feed-adapter-contract.md), [`../../notes/offgeo/tooling-decision.md`](../../notes/offgeo/tooling-decision.md), and [`../../notes/offgeo/browser-capability-matrix.md`](../../notes/offgeo/browser-capability-matrix.md).

## Phase R1, Group A — thin source readers (`OFF-101`, `OFF-102`, part of `OFF-103`)

```sh
python3 tools/offgeo/compile-sangis-roads.py   # -> build/offgeo-sources/r1-sangis-roads.jsonl + -report.json
```

`tools/offgeo/lib/normalize.py` is the shared canonical-form module (`OFF-102`): direction/suffix canonicalization (both SanGIS's and USPS's abbreviation tables collapse to the same token), highway/route recognition, block notation, unit stripping, and a full free-text `parse_street_name`/intersection splitter, versioned via `NORMALIZE_VERSION` so compiler and runtime can prove they agree later. `tools/offgeo/lib/road_status.py` is the SanGIS `SEGSTAT`/`DEDSTAT`/`PENDING`/`FUNCLASS` inclusion matrix required by `spec.md` §6.1 step 9 (code meanings transcribed verbatim from the archive's own `Roads_All.shp.xml` FGDC metadata, not guessed) — deliberately conservative, classifying private/undedicated/pending roads as `FALLBACK` rather than `EXCLUDED` since several of those categories plausibly carry real mailing addresses. Both have full unit coverage in `tests/offgeo/unit/test_normalize.py` and `test_road_status.py`.

`compile-sangis-roads.py` is `OFF-101`'s first reader (Roads-All only; Address Points and the two Census sources are follow-on work, same pattern). It reads the retained `.dbf`/`.shp` directly (no `pyshp`/`gdal`), batches every vertex through one `cs2cs` subprocess call (`state-plane-2230-feet-to-wgs84-cs2cs-v1`, the same transform validated against three real landmarks in `test_coords.py`), applies the road-status inclusion matrix per row, and writes deterministic sorted-by-`ROADSEGID` JSONL plus a report. Requires PROJ's `cs2cs` (`apt install proj-bin` / `pkg install proj`); `test_coords.py`'s three transform tests and this script both skip/fail cleanly without it rather than silently using an unvalidated fallback.

**Real run against the full retained archive** (2026-08-24, this host — 29 GiB RAM, `cs2cs` 9.6.0):

- 164,555 records, 7,004,428 vertices transformed in 79.1s (~88,500 pts/sec).
- Confidence: **106,346 ORDINARY** (64.6%), **58,189 FALLBACK** (35.4%), **20 EXCLUDED** (0.01%, all `DEDSTAT=A` Abandoned).
- Largest single fallback drivers: `DEDSTAT=P` Private street (45,292) and `FUNCLASS=7` Private street (39,754, overlapping with the former on most rows), then `DEDSTAT=U` Undedicated public/military/tribal/state land (5,077) and blank `DEDSTAT`/`SEGSTAT` (2,045 / 5,979) — full breakdown in the report's `fallbackExcludedReasonCounts`.
- 9 rows carry the zero-coordinate sentinel found in Group 2 profiling; **zero** rows are implausible after transform (`is_plausible_san_diego_point` on every vertex), i.e. the sentinel is caught before it could look like a real point, and no axis-swap/zone/unit error slipped through on this full run.
- Peak RSS 3,878.6 MiB, wall time 149.2s. Output is 284,910,428 bytes of uncompressed JSONL — a useful, if generous, upper bound before any of R1's compact-representation work (`OFF-104`) touches it. Both output files are gitignored under `build/offgeo-sources/`, reproducible by re-running the fetch (`fetch-sources.py`) then the compiler.
- This host's earlier 94%-disk-utilization flag (`OFF-017`) no longer applies to this checkout — it now measures ~196 GiB free — but the peak-RSS number above is the first real data point for R1's own memory budget (`OFF-108`), previously "not yet measured" in the Group 1 section above; worth watching as Address Points (1.2M rows) and the two Census readers are added, and before this batch-everything-in-one-process approach is assumed to scale to a from-scratch multi-source compile.

Not yet built: the Address Points reader, the two Census (`ADDRFEAT`/`FEATNAMES`) readers, and `OFF-103`'s full range/join-quality profiling pass (this script's `zeroCoordSentinelCount`/`implausibleAfterTransformCount` are early signal toward that, not the full profiling item).
