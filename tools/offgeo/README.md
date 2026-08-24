# OffGeo build tooling

Build-time tooling for the OffGeo offline geocoder. See [`../../notes/offgeo/roadmap.md`](../../notes/offgeo/roadmap.md) for the phase plan and [`../../notes/offgeo/spec.md`](../../notes/offgeo/spec.md) for the product/format requirements. Phase R0 (source pinning/profiling/fixtures/audits, `OFF-001`–`OFF-017`) is done — see [`../../notes/offgeo/todo.md`](../../notes/offgeo/todo.md) for the closed checklist. Phase R1 is underway — see [`../../notes/offgeo/r1-todo.md`](../../notes/offgeo/r1-todo.md) for status/checklist (Group A/B done, `OFF-104` onward not started) and the sections below for real numbers and run commands.

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

`tools/offgeo/compile-sangis-address-points.py` is `OFF-101`'s second reader. Per `spec.md` §6.1 line 79 ("do not ship APN, parcel ID, unit, or other unused property identifiers"), it reads `APN`/`PARCELID`/`ADDRAPNID`/`ADDRUNIT` explicitly so their exclusion is recorded, then never writes them to output (`excludedFieldsNeverEmitted` in the report, so a future reader can't silently reintroduce them unnoticed). Unlike the roads reader, it never touches `.shp` geometry at all — `Address_Points.dbf` already carries `X_COORD`/`Y_COORD` as attribute fields, so there's no need to add Point/PointZ support to `tools/offgeo/lib/shp.py` (which only reads PolyLine/PolyLineZ today) just to duplicate coordinates already in the table. `ORIG_OID` was checked directly against the full retained archive and confirmed 100% unique across all 1,222,722 rows before being trusted as the sort/join key, same rigor as `ROADSEGID`. Deliberately reads every county-wide row, unlike the map-prototype's `build-address-index.py`, which scopes to only the communities the live calls feed has hit so far — that scoping is a feature-prototype shortcut, not appropriate for a compiler-grade source reader.

**Real run against the full retained archive** (2026-08-24, same host):

- 1,222,722 source rows; every one had a parsable `ADDRNMBR` (0 skipped for that reason). 71,688 rows (5.9%) hit the zero-coordinate sentinel and were dropped before transform. 1,151,034 points transformed in 12.0s (~95,600 pts/sec); **zero** implausible after transform.
- 413,262 of the 1,151,034 kept rows (35.9%) carry the `ROADSEGID=0` unjoined sentinel — in the same range as Group 2 profiling's earlier 33.8% (measured against a slightly different row set: all 1,222,722 rows there vs. the coordinate-filtered 1,151,034 here), not a new finding but a consistent re-confirmation from an independent full pass.
- 114 distinct raw `COMMUNITY` values seen (Group 2 profiling found 115 across the unfiltered table — the coordinate-sentinel-dropped rows account for the one-value difference).
- Peak RSS 3,417.7 MiB, wall time 84.4s. Output is one JSONL record per `ORIG_OID`, gitignored under `build/offgeo-sources/`, reproducible the same way as the roads output.

`tools/offgeo/compile-census-addrfeat.py` is `OFF-101`'s third reader. Its source CRS is geographic NAD83 (EPSG:4269, degrees), not SanGIS's projected State Plane feet, confirmed from the archive's own `.prj`. This turned up a real finding: `cs2cs EPSG:4269 EPSG:4326` (the naive way to invoke this transform) uses PROJ's default-ranked operation for that CRS pair, which is a **"Ballpark geographic offset from NAD83 to WGS 84"** — literally `+proj=noop`, a zero-shift relabel with "unknown accuracy" — confirmed directly with `projinfo -s EPSG:4269 -t EPSG:4326 --hide-ballpark` returning **zero** candidate operations until a real grid is fetched. That is exactly the failure mode `spec.md` §6.1 warns against ("do not merely relabel NAD83 or State Plane coordinates as WGS84"), and it would have passed unnoticed since the output still looks like a plausible coordinate. The fix, now in `tools/offgeo/lib/coords.py`'s `batch_nad83_geographic_to_wgs84`: fetch the NOAA `us_noaa_cshpgn.tif` Southern-California HARN/NADCON grid once (`projsync --file us_noaa_cshpgn.tif`, ~6.8 KB, EPSG operation 1750, 2.0 m accuracy), and invoke it through PROJ's `cct` tool with an explicit pipeline (not `cs2cs` with a bare CRS pair, which can't be told to prefer the grid over the ballpark default). Measured against the same downtown-San-Diego control point used for the State Plane landmarks: the ballpark no-op returns the input completely unchanged; the real grid shifts it by about 0.135 m in latitude and negligibly in longitude — small, but real and sourced rather than a silent identity. Five new tests cover this in `test_coords.py::Nad83TransformTests`, including one that asserts the grid-based result is *not* bit-identical to the ballpark no-op (so a future regression back to the no-op fails loudly) and one confirming a missing grid raises rather than silently falling back.

ADDRFEAT also has no field that's unique on its own — `TLID` legitimately repeats once per extra address-range row on the same street segment (Group 2's already-known 5,718 duplicate-TLID groups). A ten-field composite key (`TLID`, `ARIDL`, `ARIDR`, `LFROMHN`, `LTOHN`, `RFROMHN`, `RTOHN`, `ZIPL`, `ZIPR`, `FULLNAME`) was checked directly against the full retained archive and found unique across all 111,770 rows — used as the deterministic sort key.

**Real run against the full retained ADDRFEAT archive** (2026-08-24, same host):

- 111,770 records, 894,330 vertices transformed via `cct` in 10.8s (~83,000 pts/sec). Zero implausible after transform.
- **103,965 distinct TLIDs, 5,718 duplicate-TLID groups, 7,805 extra rows** — an exact match against Group 2's independently-computed profiling numbers, confirming both measurements agree.
- **214 non-digit house-number field values** (55 `LFROMHN` + 55 `LTOHN` + 52 `RFROMHN` + 52 `RTOHN`) — again an exact match against Group 2 profiling.
- **31,137 one-sided ranges (27.9%)**, counting a row as one-sided when exactly one side (left or right) has any range data at all. This corrects a misreading of the earlier Group 2 note in `notes/offgeo/todo.md`/this file's Group 2 section, which quoted "~13.9%" — that figure was actually just one side's individual blank rate (`RFROMHN` blank in 13.87% of rows, `LFROMHN` blank in 13.99%, confirmed by rerunning `profile-sources.py` fresh against this checkout). The two populations are close to disjoint, so the true combined one-sided rate is closer to their sum, ~27.9% — a real, if unsurprising, correction: TIGER's one-sided-frontage pattern is about twice as common as the earlier note implied.
- Peak RSS only 849 MiB (vs. ~3.4–3.9 GiB for the two SanGIS readers) — ADDRFEAT is a much smaller dataset (111,770 vs. 164,555/1,222,722 rows) and its transform (`cct`, not `cs2cs`) turned out cheaper too.

`tools/offgeo/compile-census-featnames.py` is `OFF-101`'s fourth and last reader. FEATNAMES has no `.shp` member at all (confirmed directly — it's a pure attribute alias/name table, no geometry to transform), and joins to `ADDRFEAT` by `TLID`. Neither `TLID` (repeats once per alias) nor `LINEARID` (repeats across every `TLID` sharing one physical named feature) is unique; the full 18-field row tuple was checked and found unique across all 183,865 rows, used as the sort key. This reader reads `ADDRFEAT`'s `TLID`s directly from the retained archive (not from `compile-census-addrfeat.py`'s own output file) so it stays independently runnable and doesn't quietly trust another script's derived output as ground truth for its own join-coverage number.

**Real run against the full retained FEATNAMES archive:**

- 183,865 records, 171,683 distinct TLIDs, `PAFLAG` split 171,683 primary (`P`) / 12,182 alias (`A`) — exact match against Group 2 profiling.
- **110,003/183,865 rows (59.8%) join to a TLID present in the retained ADDRFEAT extract** — exact match against Group 2's earlier finding, now reproduced end-to-end through the real reader rather than ad hoc profiling code.
- Peak RSS 411 MiB, 12.7s total (no coordinate transform needed).

All four `OFF-101` thin source readers now exist and run cleanly against the real retained archives.

## Phase R1, Group B — range and join-quality profiling (`OFF-103`, mostly done)

```sh
python3 tools/offgeo/profile-join-quality.py   # requires the roads + address-points readers' output first
```

`tools/offgeo/profile-join-quality.py` runs against `compile-sangis-roads.py`/`compile-sangis-address-points.py`'s real JSONL output (not raw source bytes the way Group 2's `profile-sources.py` did), so it measures what a downstream compiler stage would actually see. Five passes: road range-side classification (absent/ascending/descending/malformed-one-bound-zero per side, plus an extreme-span flag), address-point join quality (sentinel/joined/dangling by `ROADSEGID`, joined-by-road-confidence cross-tab, and a coarse numeric range-containment check for joined points), `LMIXADDR`/`RMIXADDR` mix-flag distributions, duplicate road geometry, and ZIP consistency between joined address points and their road's `L_ZIP`/`R_ZIP`.

**Real run** (2026-08-24, against the roads/address-points output committed above):

- **Roads (164,555 records):** 28.1% both-sides-absent (no address range at all) — matches Group 2's raw-source figure of 28.3% closely (small difference expected: Group 2 profiled all 164,555 raw rows directly, this profiles the reader's parsed output, same population, different code path). 5 left-side and 5 right-side rows are malformed (`one_bound_zero`: exactly one of low/high present, not both) — a new finding, not previously counted. Exactly **1 descending range** (right side) — an exact match against Group 2's "only one descending-range row" finding, reproduced independently through the real reader. At Group 2's own 100,000-unit "implausibly wide" threshold, this pass found **2** such rows, not Group 2's reported 1 — close but not an exact match; not investigated further here (small enough either way to be a data curiosity, not a systemic problem), flagged for whoever next touches range-repair logic.
- **Address points (1,151,034 records) joined to the real roads output:** 35.9% unjoined (`ROADSEGID=0` sentinel, expected — condo/unit sub-records), **64.1% joined**, and only **40 dangling** (0.0035% — a `ROADSEGID` that doesn't resolve to any road in this reader's own output; Group 2's raw-source figure was 207/1,222,722 rows against the full unfiltered table, so this smaller number over the smaller coordinate-filtered population is consistent, not a new problem).
- **New finding, not measurable before both readers existed:** of the 737,732 joined address points, 634,382 (86.0%) join to an `ORDINARY`-confidence road, 103,332 (14.0%) to `FALLBACK`, and only 18 to `EXCLUDED` — i.e. address points overwhelmingly attach to roads this project's own status classification already trusts, a good sign for `road_status.py`'s conservative fallback-not-excluded design.
- **New finding — range containment:** among joined address points with a usable (non-all-zero) range on their road, **98.3% (725,382) have a house number that falls within the road's own combined low/high bounds**; 12,103 (1.6%) fall outside; 247 joined points had no usable range to check against at all. This is a coarse min/max check, not real side/parity-aware interpolation (that's R4's job) — the 12,103 outside-range points are a real, now-measured population worth carrying into R2's range-repair design, not proof any individual one is a data error (SanGIS ranges are revised over time and a point can predate a range edit).
- **Mix flags:** `LMIXADDR`/`RMIXADDR` are `N` (no mixed parity) for 99.8% of roads, `Y` for only ~0.16%, blank for ~0.02% — mixed-parity ranges are a real but small population, not a dominant case R4's scorer needs to specially optimize for.
- **Duplicate geometry:** only 3 groups (6 total segments) out of 164,555 share an exactly identical vertex sequence with another `ROADSEGID` — negligible; SanGIS's own geometry is clean enough that de-duplication (spec.md 6.3) will barely change the byte count.
- **ZIP consistency:** checked over the full 737,732 joined points (independent of range containment — an earlier version of this script accidentally skipped the ZIP check for the 247 no-range points by coupling it to the range check's early exit; fixed so this count is complete). 733,423 (99.4%) have an `ADDRZIP` matching one side of their road's `L_ZIP`/`R_ZIP`; **4,309 (0.6%) don't**, and 0 were unchecked for a missing ZIP on either side. A real, small locality/ZIP-gap population, plausible near ZIP boundaries that don't line up exactly with road-segment boundaries, not investigated further here.

`OFF-103`'s scope is now essentially complete except the SanGIS<->Census address-range *conflict* check (see the reconciliation section below — that still needs a geometry-based segment join, deliberately not attempted here).

## Phase R1, Group B — SanGIS<->Census street reconciliation (`OFF-004` cross-source half, `OFF-103` continued)

```sh
python3 tools/offgeo/reconcile-sangis-census-streets.py   # requires all four OFF-101 readers' output
```

`tools/offgeo/reconcile-sangis-census-streets.py` answers the question Group 2 profiling explicitly deferred: "how many roads does Census add that SanGIS lacks, and where do the two overlap." Method: build one canonical street-name key per source (`predirCode, coreName, postdirCode, suffixCode`, via `lib/normalize.py`) from each reader's already-structurally-split fields, then compare the two key sets. Census's key set is restricted to `FEATNAMES` rows (primary + alias) whose `TLID` actually carries a usable address range in `ADDRFEAT` — a name-only `TLID` with no range data isn't real fallback coverage, per `spec.md` 6.1's warning not to claim a benefit that can't be measured. This is name-level reconciliation only; it does not attempt a geometry-based segment match or compare address ranges for streets matched by name in both sources (real future work, not done here).

Building this turned up two real, sourced normalization-library gaps, both fixed in `lib/normalize.py` directly since they're `OFF-102` shared-library correctness bugs, not just artifacts of this one script:

- **Leading-zero ordinal streets.** SanGIS zero-pads single-digit numbered streets (`01ST`, `02ND`, ..., `09TH` — 2,018 SanGIS road segments, including downtown San Diego's 1st through 9th Avenue) while Census spells the same streets `1ST`, `2ND`, etc. Every one of those streets would have silently failed to cross-reference between the two sources. Fixed with `canonicalize_street_core_name`, scoped narrowly (digits immediately followed by `ST`/`ND`/`RD`/`TH`) so it can never touch an actual house number. Four new tests in `test_normalize.py::StreetCoreNameCanonicalizationTests`.
- **Missing Census suffix vocabulary.** `SUFFIX_CANON` was built entirely from SanGIS's own two domain tables; checking every real `FEATNAMES` `SUFTYPABRV` value that failed to canonicalize found 38 distinct tokens covering 6,328 of 126,976 non-blank rows (~5%) — `CRK`/Creek, `RIV`/River, `RDG`/Ridge, `VIS`/Vista, `HTS`/Heights, `CYN`/Canyon, and so on, plus `TRUCK TRL` mapped onto the same `TRUCKTRAIL` canonical form SanGIS's own `TKTL`/`TT` already use. Unlike the SanGIS-sourced half of the table, these are this project's own best-effort standard-abbreviation mapping (same standard already used for `build-address-index.py`'s `FEED_SUFFIX_ALIASES`), not a transcription from an official field-domain document — disclosed as such in the code comment. Two tokens (`TRANS LN`, `JEEP TRL`, 107 rows) were deliberately left unmapped rather than guessed.

**Known remaining gap, not fixed:** some `FEATNAMES` rows carry their suffix embedded directly in the `NAME`/`FULLNAME` field with `SUFTYPABRV` left blank (e.g. `NAME="Adelaide Gln"`, `SUFTYPABRV=""`, found by spot-checking a Census-only example against a same-named SanGIS street that turned out to share the base name `ADELAIDE`). This reconciliation's key construction only reads the structured suffix field, so rows like this contribute a real but uncounted number of false census-only entries. A fix would need `lib/normalize.py`'s free-text `parse_street_name` run against `FULLNAME` as a fallback when `SUFTYPABRV` is blank — not done here, flagged for whoever next improves this script's accuracy.

**Real run against the full retained archives, after both normalization fixes above:**

- SanGIS: 34,357 distinct street keys across 164,555 road segments.
- Census (restricted to range-bearing TLIDs): 30,685 distinct street keys, out of 33,264 total (some Census streets carry only alias/unrange-backed names).
- **Matched: 25,998 keys (75.7% of SanGIS's street keys have a same-named Census counterpart).**
- **SanGIS-only: 8,359 keys** — SanGIS names Roads-All has that this key scheme didn't find a Census match for (some of this is real SanGIS-only coverage; some is certainly further normalization gaps like the two found above, not yet all found).
- **Census-only (range-bearing): 4,687 keys, covering 15,076 distinct TLIDs** — this is the real, measured answer to "what does Census's fallback data add." A seeded random sample (not alphabetically-first, which was tried and rejected during development — digit-leading route-number keys sort first and are under 1% of the real population, so an alphabetical sample badly overrepresented them) shows mostly ordinary named residential streets (`ANNA LIE`, `SIERRA RIDGE`, `SAN FELIPE VALLEY ROAD`, ...), not exotic edge cases — real evidence that Census fallback coverage is a genuine, non-trivial addition, not just federal-only route codes or misc. features.

This is real progress on `OFF-004`'s cross-source half, but not the complete picture `spec.md` 6.1 originally asked for: conflicts (both sources naming the same physical street with different/incompatible address ranges) and the community-mapping/locality-ZIP-gap counts `OFF-103`'s full scope also asks for are still open, and require the geometry-based segment match this pass deliberately didn't attempt.
