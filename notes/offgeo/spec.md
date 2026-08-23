# OffGeo San Diego County Specification

Status: Draft for implementation

Last updated: 2026-08-22

Working name: OffGeo

Target application: SD50 calls-to-service web app

## 1. Product summary

OffGeo is a versioned, downloadable San Diego County address-range dataset and an in-browser geocoder. After a one-time countywide pack download, the app can estimate a call address's latitude and longitude without sending that lookup or the user's location to a geocoding service. The app then calculates straight-line distance between that estimated call location and the user's current coordinates.

The pack is compiled by this project from public open-government source data. It is not a proxy or cache of a commercial geocoder.

### Fixed product decisions

- Coverage: all of San Diego County, California (state/county FIPS `06/073`).
- Model: street-centerline segments with left/right address ranges and interpolation.
- Distribution: one countywide downloadable pack.
- Compressed transfer target: 10–30 MiB; 30 MiB is a hard release ceiling.
- Update check and candidate build: every four months.
- Storage: IndexedDB, installed only after an explicit user action.
- Imperfect input: return the best defensible nearby address-range result with a confidence and reason, never a silent arbitrary match.
- Distance: straight-line distance, displayed in feet or miles.
- User coordinates: device-local, memory-only, never persisted, logged, placed in a URL, or transmitted.
- UI scope: pack download/update/delete, storage status, location permission, distance display, nearest sorting, and failure recovery.

## 2. Accuracy contract

“Every address” is the coverage goal, not a claim that the source data is perfect. Version 1 attempts every parsable San Diego County street number whose normalized street can be associated with an official source address range. It does **not** mean that the pack enumerates every physical delivery point or knows every rooftop/entrance coordinate. Census potential ranges can include numbers that do not exist and suppress some single-address ranges; local records can lag new construction or contain gaps. The compiler must measure those gaps against SanGIS address points and the calls fixture rather than claiming absolute completeness.

Street interpolation estimates a point along a road centerline. Results may be displaced from a building, parcel entrance, apartment, private road, new development, or call location. The UI must use words such as **estimated**, **approximately**, and **street-range match**. It must not label an interpolated point as an exact address location.

Accuracy classes:

| Confidence | Meaning | User presentation |
| --- | --- | --- |
| High | Exact normalized street, locality agrees, number is inside a compatible side/range, and parity agrees when known | Distance with an approximate marker; detail says “street-range estimate” |
| Medium | Exact street but locality is absent/ambiguous, parity is unavailable, intersection matched, or the number is just outside the nearest range | Distance with an approximate marker; detail explains the fallback |
| Low | Conservative alias/fuzzy street match or street midpoint/endpoint fallback | Distance shown only with a clear low-confidence label |
| Unmatched | No candidate passes the minimum score | “Distance unavailable” and a reason; no fabricated coordinate |

The user's location must never influence which address candidate wins. Candidate selection uses the event address, locality/ZIP/service-area hints, range fit, and source quality. Using proximity to the user would create incorrect, biased matches.

## 3. Goals and non-goals

### Goals

1. Resolve normal numbered addresses, hundred-block addresses, and intersections found in calls-to-service records.
2. Work after installation with no geocoder network request.
3. Keep the UI responsive on a representative mid-range Android phone.
4. Make data provenance, version, age, integrity, and match confidence inspectable.
5. Install updates without destroying the last known-good pack.
6. Make the compiler deterministic and reproducible from pinned public source files.

### Non-goals for version 1

- Rooftop, parcel-centroid, entrance, unit, apartment, suite, or indoor positioning.
- Driving distance, route time, traffic, road-network routing, or turn-by-turn directions.
- Reverse geocoding the user's location.
- Searching outside San Diego County.
- Background or continuous location tracking.
- Uploading location or address telemetry.
- Claiming that every number inside a government address range corresponds to an occupied or deliverable address.

## 4. Public-government source plan

### 4.1 Required local production sources

Use these downloadable, countywide SanGIS datasets as the production primary:

- [SanGIS Roads - All](https://data.sandiego.gov/datasets/gis-roads-all/) supplies road geometry, stable `ROADSEGID`, from/to nodes, left/right low/high address ranges, mix flags, ZIP/jurisdiction fields, status/classification, and official name components.
- [SanGIS Address Points to APN](https://data.sandiego.gov/datasets/gis-address-points-apn/) supplies situs address components, `ROADSEGID`, `COMMUNITY`, placement/type information, and point coordinates.

Both are public government downloads updated weekly. The raw inputs are intentionally much larger than the browser pack: the audited CSV endpoints were approximately 79 MB for roads and 209 MB for address points. That is a build-system concern, not a client download. The compiler must fetch them outside the browser and retain only the fields needed for lookup.

The address-point source is primarily a compiler-side join and validation set. Join `COMMUNITY` and observed address coverage to roads by `ROADSEGID`; do not ship APN, parcel ID, unit, or other unused property identifiers. A point may repair or subdivide a segment range only under a documented deterministic rule with outlier and conflict checks. Version 1 still returns a segment-interpolated centerline point, not the source address point.

Use a full Roads - All geometry download, not the simplified public basemap service or CSV alone. The CSV proves the required attributes exist but contains only selected from/mid/to coordinate columns; it cannot preserve curved-road interpolation. Every source adapter must schema-check actual fields, coordinate reference system, record counts, null rates, and join rates on each build.

### 4.2 Required federal fallback and cross-check

Use the current U.S. Census Bureau TIGER/Line® Address Range Feature (`ADDRFEAT`) county shapefile for San Diego County (`06073`) as a reproducible fallback and independent cross-check:

- Current candidate: [2025 San Diego County ADDRFEAT ZIP](https://www2.census.gov/geo/tiger/TIGER2025/ADDRFEAT/tl_2025_06073_addrfeat.zip)
- Directory listing: [2025 ADDRFEAT files](https://www2.census.gov/geo/tiger/TIGER2025/ADDRFEAT/)
- Format and field definitions: [2025 TIGER/Line technical documentation](https://www2.census.gov/geo/pdfs/maps-data/data/tiger/tgrshp2025/TGRSHP2025_TechDoc.pdf)

The audited 2025 San Diego archive is 15,102,855 bytes with SHA-256 `750f9eaf9d00d11bfbd8eb4ab030d386c27fbe03fe510a67ec14789842161a8b`. It contains 111,770 address-range records, 31,114 nonempty unique full names, and 894,330 polyline points in NAD83 geographic coordinates. Its house-number columns are strings, not integers; 107 audited side ranges contain non-digit forms such as hyphenated or alphabetic values. The adapter must model or explicitly reject these forms with counts.

Evaluate the approximately 3.3 MB [San Diego County Feature Names relationship file](https://www2.census.gov/geo/tiger/TIGER2025/FEATNAMES/tl_2025_06073_featnames.zip) for official aliases. Do not ship the roughly 30 MB county `EDGES` archive wholesale. If address-range geometry cannot resolve enough intersections, derive only the minimum named-road node topology needed from `EDGES` and keep it under the pack size gate.

U.S. government works are not copyright-protected under 17 U.S.C. §105. The Census documentation requests source citation and a conspicuous repackaging notice. Every published pack and the download UI must therefore identify the Census Bureau as a source, link the documentation, include the source vintage, and state that the pack is a derived product not endorsed by the Census Bureau.

### 4.3 Source precedence and conflict handling

SanGIS is primary, while Census supplies fallback ranges, aliases, gap detection, and an independent regression signal. They are merged by explicit rules:

1. Preserve original source IDs and provenance on every merged segment.
2. Prefer a valid local jurisdiction-maintained SanGIS range/name over Census when its segment and address-point joins pass validation.
3. Retain alternate official names as aliases rather than overwriting them.
4. Never average conflicting address ranges.
5. Emit every conflict to a build report with selected value, rejected value, rule, and source IDs.
6. A segment with an unresolved source conflict is downgraded or excluded; it is never silently promoted to high confidence.
7. Fail the candidate release if the conflict rate, unmatched source join rate, or county coverage crosses its approved threshold.

### 4.4 Required source manifest

Each build stores a machine-readable source manifest containing:

```json
{
  "packVersion": "2026.08.0",
  "formatVersion": 1,
  "countyFips": "06073",
  "compilerCommit": "...",
  "sources": [
    {
      "publisher": "SanGIS",
      "dataset": "Roads - All",
      "vintage": "2026-08-10",
      "url": "https://geo.sandag.org/server/rest/directories/downloads/Roads_All_shapefile.zip",
      "sha256": "...",
      "licenseOrReuseStatement": "...",
      "retrievedAt": "..."
    }
  ]
}
```

The pack-internal manifest contains only deterministic values from the source lock and compiler. Nondeterministic `builtAt`/deployment timestamps belong in the detached release manifest. Because weekly government endpoints can replace bytes at the same URL, reproducibility requires a content-addressed retained copy of every exact source archive outside Git, not only its URL/hash. A clean build reads the retained bytes and verifies the lock before compiling. A source changing at the public URL produces a new checksum and requires a reviewed source-lock update and candidate build.

## 5. System architecture

```text
public government files
        |
        v
source adapters -> normalize/merge -> validate -> compact pack + reports
                                                    |
                                                    v
                                          same-origin static hosting
                                                    |
                      explicit download/update -----+
                                                    v
calls feed -> address parser -> Web Worker -> IndexedDB pack -> estimated call point
                                                                     |
one-shot browser geolocation ----------------------------------------+
                                                                     v
                                                    local Haversine distance + UI
```

The compiler is a build-time/offline tool. Runtime geocoding must not depend on a server API. Pack parsing, integrity verification, indexing, and lookup run in a Web Worker so download/import work cannot freeze the calls UI.

## 6. Compiler requirements

### 6.1 Deterministic pipeline

For identical source bytes, compiler version, and options, the output pack checksum must be identical. Build timestamps belong in a detached release manifest or must be normalized so they do not make the binary nondeterministic.

Pipeline stages:

1. Fetch pinned source URLs and calculate SHA-256 before extraction.
2. Reject unexpected archive entries, absolute paths, path traversal, excessive expanded size, or unexpected file counts.
3. Read geometry and required attributes in the declared source coordinate reference system; fail if it is missing or unexpected.
4. Transform to WGS84 longitude/latitude with an explicit, versioned datum/CRS pipeline. Do not merely relabel NAD83 or State Plane coordinates as WGS84. Record the transform and validate control points.
5. Restrict records to San Diego County and usable road/address-range feature classes.
6. Normalize names and ranges while retaining raw source values for build diagnostics.
7. Join SanGIS address-point communities and observed ranges to roads by `ROADSEGID`; report unmatched and one-to-many anomalies.
8. Merge Census fallback/aliases using deterministic precedence rules.
9. Separate geometry from address-range rows and store one verified geometry per stable segment/edge ID. Address-range sources can repeat the same geometry for multiple ranges; duplicating it would waste the pack budget.
10. Quantize coordinates, encode geometry, dictionary-encode strings, and partition lookup blocks.
11. Build exact, alias, locality, and bounded fuzzy-candidate indexes and serialize the pack.
12. Re-open the produced pack with the runtime reader and run all release validation.
13. Write size, coverage, join, conflict, accuracy, performance, license, and checksum reports.

SanGIS road status fields require an explicit inclusion matrix. Active/constructed addressable roads are eligible for ordinary confidence. Inactive, pending, private, unbuilt/of-record, or otherwise uncertain segments are excluded or placed in a separately scored fallback class only after validation against current address points. The compiler must report counts for every status/class rather than accepting all Roads - All rows.

### 6.2 Address normalization

The compiler and runtime parser must share one versioned normalization library and fixture suite. It must:

- Unicode-normalize, uppercase, trim, collapse whitespace, and remove non-semantic punctuation.
- Remove unit designators and unit numbers from matching input.
- Canonicalize directional prefixes/suffixes (`N`, `NORTH`, etc.).
- Canonicalize common suffixes (`STREET`/`ST`, `AVENUE`/`AVE`, etc.) without collapsing semantically different names.
- Normalize highway and route forms conservatively.
- Preserve numbered street ordinals and alphabetic house-number suffixes where supported.
- Recognize block notation such as `1200 BLOCK OF MAIN ST` and mark its number as approximate.
- Recognize intersections separated by `/`, `&`, `@`, `AT`, or equivalent feed conventions, with or without surrounding spaces. Current calls samples contain slash-separated intersections without spaces and street-only locations without a house number; both require fixtures.
- Keep official alternate names and explicitly reviewed local aliases in a separate alias table.

Normalization changes are pack-format behavior changes. They require fixtures and either a compatible version marker or a format-version increment.

### 6.3 Address-range cleanup

- Treat source house numbers as structured strings. Support normal integers first, preserve a separately modeled suffix/fraction when unambiguous, and explicitly classify hyphenated/alphabetic source forms as supported or rejected. Never coerce `145-100`, `BL01`, or similar values with `parseInt`.
- Support ascending and descending ranges.
- Retain the source left/right side, parity/mix flags, imputation/type flags, and offset flags needed for scoring. Do not confuse Census `LFROMTYP`/`LTOTYP` with a house-number suffix.
- Reject zero, malformed, implausibly broad, or missing ranges from numbered interpolation while keeping eligible geometry for intersection/street fallback.
- Do not invent missing ranges from adjacent segments in version 1.
- Store range records separately from geometry. De-duplicate geometry by stable `ROADSEGID`/`TLID` only after proving repeated geometry is byte- or tolerance-equivalent; retain distinct ranges and names that reference it.
- Derive a segment's locality/community set from address-point joins and explicit jurisdiction crosswalks. A missing/ambiguous community join lowers confidence and is reported.

### 6.4 Geometry encoding

- Interpolation follows cumulative length over the entire polyline, not a straight chord between endpoints.
- Coordinates are transformed to WGS84 and quantized to `1e-5` degrees or a benchmarked precision no worse than roughly one meter locally. Datum-transform error is included in the benchmark.
- Polyline coordinates use delta plus ZigZag/varint encoding.
- Geometry simplification is permitted only if validation shows it does not materially alter interpolated positions or intersections.
- Street, locality, ZIP, source, and reason strings are dictionary encoded.

## 7. County pack format

The distributed artifact will be one logical county pack. `.offgeo`/`OFG1` below is the leading candidate, not a frozen decision: R1 must compare it with at least one maintained binary/SQLite-or-PBF-style alternative before R2 freezes the format. The selected format must support independently compressed/verified internal blocks and IndexedDB storage without requiring a framework or server runtime.

### 7.1 Container layout

```text
magic "OFG1"
format version
header/directory length
manifest and dictionaries
street-key index
alias index
block directory: block id, offset, compressed bytes, raw bytes, SHA-256
individually compressed segment/geometry blocks
whole-file SHA-256 stored in the detached release manifest
```

The directory allows the installer and worker to validate blocks without retaining a second fully expanded copy. Partitioning should use a deterministic street-key hash or prefix scheme, selected by benchmark rather than assumption. Version 1 should prefer gzip blocks because browser-native `DecompressionStream("gzip")` is broadly available in workers; the runtime still needs a capability probe and a tested fallback/unsupported-browser state.

Web Crypto `crypto.subtle.digest()` is not streaming and would require buffering the entire pack. The installer must therefore benchmark and choose one of two explicit integrity paths: an incremental audited SHA-256 implementation over the response stream, or bounded block-by-block Web Crypto verification plus a final whole-file check whose peak memory remains inside the approved device budget. It must not accidentally buffer compressed bytes, decompressed bytes, and IndexedDB copies simultaneously.

### 7.2 Pack limits

| Limit | Requirement |
| --- | --- |
| Download size | Preferred ≤20 MiB; hard failure above 30 MiB |
| Installed IndexedDB footprint | Target ≤45 MiB including indexes and metadata; report actual browser estimate |
| Update peak footprint | Preflight active + staged + working overhead; target ≤95 MiB and report measured peak |
| County count | Exactly one: `06073` |
| Maximum decompressed bytes | Declared in the header and enforced before allocation |
| Integrity | Whole-file and per-block SHA-256 |
| Compatibility | Unknown mandatory fields or unsupported format versions fail closed |

The pack endpoint should be same-origin and support `Content-Length`, immutable versioned URLs, and ordinary HTTP caching. Progress uses the release-manifest-declared byte length rather than trusting a missing or rewritten response header. Byte-range requests are optional optimization only; cancellation/retry must work by restarting when the host/CDN does not support ranges. Do not apply HTTP `Content-Encoding` to an already internally compressed pack unless deployment testing proves the browser receives the intended container bytes. The small release manifest points to the active version and contains its URL, byte length, checksum, schema version, source vintage, and minimum/maximum compatible app version.

Checksums detect corruption, truncation, and mismatched artifacts; because the app and manifest share an origin, they do not independently authenticate a compromised host. HTTPS plus controlled deployment/rollback is the version 1 authenticity boundary. Do not describe checksum verification as a digital signature.

## 8. IndexedDB design

Database name: `sd50-offgeo`

Initial schema version: `1`

Object stores:

| Store | Key | Purpose |
| --- | --- | --- |
| `meta` | name | Active version pointer, pending version, source metadata, byte counts, state, install/update timestamps |
| `packs` | `[version, blockId]` | Verified compressed block blobs and their hashes |
| `streetIndex` | `[version, streetKey]` | Candidate block/segment descriptors for an exact normalized name |
| `aliases` | `[version, aliasKey]` | Reviewed alias to canonical street keys |
| `installState` | version | Progress/checkpoint data for resumable or safely restartable installation |
| `eventCache` | feed key | Last successful source calls response and fetched time; never user coordinates, distance, resolved points, or legacy `nearby` flags |

### 8.1 Installation transaction

1. User presses **Download offline address data**.
2. App fetches the release manifest and checks app/format compatibility.
3. App capability-tests IndexedDB, workers, decompression, Web Crypto/incremental hashing, and the Storage API. Private/ephemeral or unsupported storage gets a specific non-installable state.
4. App uses `navigator.storage.estimate()` to compare the **estimated** origin quota/usage with the declared worst-case requirement. Estimates are advisory and privacy-padded; the actual write and `QuotaExceededError` remain authoritative.
5. App calls `navigator.storage.persist()` when available. This occurs inside the user-initiated install flow before the large write; automatic denial/absence is non-fatal but is disclosed.
6. App acquires the origin-wide installer lock. Use Web Locks when available and an IndexedDB lease with owner token, expiry, heartbeat, and fencing generation as the fallback. Other tabs observe progress instead of starting a competing install.
7. App downloads to a staging version while showing bytes, percentage, and a cancel control.
8. A worker verifies hashes and bounds, then writes each bounded block in a short transaction. Never hold an IndexedDB transaction open across `fetch`, decompression, hashing, or unrelated `await` work because transactions can become inactive at the next event-loop turn.
9. Runtime smoke queries and metadata checks run against the staged version.
10. One short transaction changes `activeVersion` to the new version.
11. Keep the previous version during a grace period and while any open tab has pinned it. Delete it only under the installer lock after no reader lease references it; never delete immediately beneath an old tab.

An interrupted or corrupt install never changes `activeVersion`. On restart, the app may resume a verified checkpoint or delete only the incomplete staged version and restart. Update preflight includes the active version, full staged version, indexes, and bounded working overhead; it must not assume the old pack can be deleted first. If that peak will not fit, keep the active version and postpone the update. A `QuotaExceededError` must lead to a useful recovery message and must not damage the active pack. Installation state transitions use compare-and-swap/fencing values so a stale tab cannot activate or clean up another tab's work.

Every connection handles `versionchange` by closing promptly; the opener handles `blocked` and tells the user which tab/action is preventing an upgrade. BroadcastChannel may synchronize progress and reload notices, but correctness must not depend on message delivery. IndexedDB storage is best-effort unless persistence is granted and may still be cleared by the browser/user. The UI must always be able to detect a missing pack, reinstall it, and explain the state. See [MDN IndexedDB](https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API/Using_IndexedDB), [storage quotas and eviction](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria), [Web Locks](https://developer.mozilla.org/en-US/docs/Web/API/Web_Locks_API), and [persistent storage](https://developer.mozilla.org/en-US/docs/Web/API/StorageManager/persist).

## 9. Runtime geocoder

### 9.1 Input

```ts
type OffGeoQuery = {
  rawAddress: string;
  locality?: string;
  postalCode?: string;
  serviceArea?: string;
};
```

No user coordinates are part of the geocoder query.

### 9.2 Matching sequence

1. Parse numbered address, hundred block, intersection, or unsupported form.
2. Normalize the street name with the shared normalization version.
3. Retrieve exact canonical and reviewed alias candidates.
4. Narrow by the SanGIS `COMMUNITY`/jurisdiction mapping and the feed's `Community`/`ServiceArea`; use ZIP only when actually present or deterministically derived. A same-named street in multiple communities remains ambiguous if the crosswalk cannot separate it.
5. For a numbered address, score segments by inclusive range containment, parity, number gap, locality agreement, and source precedence.
6. For an intersection, find shared or spatially coincident endpoints of the two exact street candidate sets. Use the compact named-road topology only if address-range geometry alone misses the approved intersection coverage gate.
7. If no containing range exists, consider the nearest numeric range on the exact street within the compatible locality only when its absolute/relative number gap is below benchmark-approved hard limits.
8. Only then consider a conservative fuzzy street-name match. Use a bounded candidate index, require a benchmarked threshold and a clear margin over the runner-up, and never scan/decode the entire county pack per query.
9. If no candidate passes the minimum score, return unmatched.

Ties that cannot be resolved without guessing must return `AMBIGUOUS`, not whichever record appears first.

### 9.3 Interpolation

For the winning address range:

1. Orient the numeric range without changing the stored geometry direction.
2. Calculate `t = (number - from) / (to - from)` and invert it when required by range/geometry orientation.
3. Clamp `t` to `[0, 1]` only for an explicitly allowed nearest-range fallback.
4. Walk the decoded polyline by cumulative geodesic length until the `t` fraction is reached.
5. Return the centerline coordinate. Version 1 does not offset toward the left/right curb because source side/orientation quality varies.

If `from === to`, use the polyline midpoint and downgrade confidence. Block addresses use the block's representative number or matched range midpoint and are always marked approximate.

### 9.4 Result contract

```ts
type OffGeoResult = {
  status: "matched" | "fallback" | "unmatched";
  latitude?: number;
  longitude?: number;
  method?:
    | "range-interpolation"
    | "range-endpoint"
    | "intersection"
    | "street-midpoint";
  confidence?: "high" | "medium" | "low";
  reasonCode:
    | "RANGE_PARITY_MATCH"
    | "RANGE_MATCH_PARITY_UNKNOWN"
    | "BLOCK_ESTIMATE"
    | "INTERSECTION_MATCH"
    | "OUTSIDE_RANGE_NEAREST"
    | "STREET_FUZZY_MATCH"
    | "STREET_ONLY_FALLBACK"
    | "NONSTANDARD_HOUSE_NUMBER"
    | "LOCALITY_NOT_MAPPED"
    | "AMBIGUOUS"
    | "ADDRESS_UNSUPPORTED"
    | "STREET_NOT_FOUND"
    | "PACK_UNAVAILABLE"
    | "RUNTIME_UNSUPPORTED";
  normalizedAddress?: string;
  segmentId?: string;
  sourceIds?: string[];
  packVersion: string;
};
```

Debug/source IDs stay local and are shown only in an optional detail panel. Production analytics must not contain raw event addresses, matches, source IDs tied to addresses, or coordinates.

## 10. User location and distance

Location access is a separate explicit action from installing the pack. The browser permission prompt must never appear on initial page load.

Flow:

1. Explain: “Your location stays on this device and is used only to calculate straight-line distance.”
2. User presses **Use my location**.
3. Call `navigator.geolocation.getCurrentPosition` from the secure origin with an explicit bounded timeout and maximum age. Start with normal accuracy to reduce latency/power; offer a deliberate higher-accuracy retry when the returned accuracy is poor. `enableHighAccuracy` is only a hint and may be ignored.
4. Keep latitude, longitude, `accuracy`, and reading timestamp only in main-page controller memory. The geocoder worker never receives user coordinates; it returns the estimated call point and the page calculates distance.
5. Calculate distance locally using the Haversine formula and mean Earth radius.
6. Clear coordinates on reload, when the user presses **Stop using location**, or when the page is hidden long enough to require a fresh reading.

Display rules:

- Under 0.1 mile: feet, rounded no more finely than the combined geocoder/location uncertainty supports.
- 0.1 mile and above: miles; one decimal under 10 miles and an appropriate coarser precision above it.
- Prefix or visually mark all interpolated distances as approximate.
- Include an accessible label such as “Approximately 1.2 miles straight-line distance.”
- Never imply driving time or road distance.
- Use `coords.accuracy` (a 95%-confidence radius in meters) to warn on a poor location fix. Do not show a fine-grained distance or use it for a tight radius filter when the uncertainty is comparable to the displayed distance.

Permission denied, unavailable, timeout, and insecure-context states must have separate messages. Location failure must not block the calls feed or offline geocoding.

**Stop using location** clears the app's in-memory reading and distances. It cannot revoke a permission retained by the browser; the denied/permission help text must explain how to change browser site permissions without claiming the app can do so.

## 11. User interface states

### 11.1 Offline data card

The settings/data card displays:

- Not installed, downloading, verifying, installing, ready, update available, stale, failed, and storage-evicted states.
- Pack size before download, source vintage, build version, and last update check.
- **Download**, **Cancel**, **Retry**, **Update**, and **Delete offline data** actions as applicable.
- Byte and percentage progress plus the current stage; progress must not be animation-only.
- Whether persistent storage was granted or the browser may evict the data.
- Data sources/attribution and an expandable accuracy explanation.

Deleting data must require confirmation, delete only OffGeo versioned pack/index records, leave unrelated site data alone, clear the active pointer, and report completion.

### 11.2 Location card

- An explanation appears before **Use my location**.
- Active state shows reading age and **Refresh** / **Stop using location**.
- Denied state links to concise browser-permission recovery guidance.
- Coordinates are never displayed unless a future explicit diagnostic feature is approved.

### 11.3 Calls list

- Each resolved call gets an approximate distance chip and accessible text.
- A detail affordance exposes match method/confidence without overwhelming the primary list.
- Users can sort by nearest and optionally filter within a selected radius.
- Unmatched calls remain visible and sort after known distances.
- Sorting is stable for equal/unknown distances and never mutates the source feed ordering permanently.
- New/updated calls are geocoded in a worker and update progressively without layout jumps.
- When offline, show cached calls with their last-fetched timestamp and a prominent stale indicator.
- A map link is a separately labeled **Open in external map** action. Do not load a Google Maps iframe from an ordinary row click. Explain that the external action sends the call address to that provider and requires connectivity; it is not part of offline geocoding.

Animations should be subtle and short: progress transitions, card state changes, and distance-chip entry may use opacity/transform. Honor `prefers-reduced-motion`; never animate list positions in a way that obscures an emergency call.

## 12. Offline behavior

- The app shell is cached by the service worker separately from the address pack.
- The address pack belongs in IndexedDB, not the service-worker Cache API.
- The last schema-valid calls payload is cached with its source `LastUpdated` and local fetch timestamp so the most recent known calls can still be displayed offline. Replace the single snapshot transactionally; do not accumulate an event history.
- The UI must clearly distinguish live calls from cached/stale calls. Any payload shown after a failed/no network refresh is not labeled live. A snapshot older than the approved safety window is hidden behind an explicit **Show old snapshot** action and is purged at the retention limit; proposed values to validate are 6 hours and 24 hours respectively.
- After app shell, pack, and at least one calls response are cached, airplane-mode reload must support list display, geocoding, location permission where the platform permits it, distance calculation, sorting, and filtering without a network request.
- Going offline during a first-time pack download leaves no active partial pack.
- Update checks and new calls naturally require connectivity.

## 13. Security and privacy requirements

1. No runtime geocoder network calls.
2. No request URL, body, header, log, crash report, analytics event, worker message, or service-worker message may contain user latitude/longitude.
3. Raw event addresses and resolved coordinates must not be added to analytics.
4. User coordinates must not enter IndexedDB, Cache API, local/session storage, cookies, service-worker messages retained after calculation, or URL/history state.
5. Validate declared sizes/counts before allocation and enforce hard decompression limits.
6. Verify pack checksum and format before activation.
7. Reject unknown incompatible formats rather than partially interpreting them.
8. Parse source archives without path traversal or archive bombs.
9. Escape all source strings when rendered; pack content is untrusted input.
10. Keep the site on HTTPS because geolocation and persistent storage are secure-context features.
11. Before enabling OffGeo, remove the legacy Google geocoder and exposed browser key, coordinate-bearing console logs/URLs, and all writes of `latitude`, `longitude`, or geocoded points to `localStorage`. Revoke/restrict the exposed Google key in its provider console.
12. Run a one-time, idempotent migration that removes the known legacy coordinate keys, only cache entries whose values match the old `{lat,lng}` geocode shape, and old per-event entries whose parsed `EventNumber` equals their storage key. Those event records can contain the location-derived `nearby` flag and must not be retained indefinitely. Preserve unrelated origin storage, then record a non-sensitive migration version.
13. Existing Google map links/iframes are not part of OffGeo. Replace implicit iframe loading with the explicit external-map disclosure described above.
14. Treat calls-feed authentication/CORS and OffGeo pack failures as separate states. No source credential belongs in an OffGeo manifest, cache record, worker message, or diagnostic report.

If the calls feed requires a secret, a static browser app cannot keep it secret. The production feed path must use a source-approved public-client credential or a controlled same-origin server/serverless proxy that applies the secret after receiving a bounded request. Encoding, minifying, or routing a secret through a third-party CORS proxy does not protect it. This feed deployment decision is separate from the fully static OffGeo lookup path but is required before claiming the overall site is production-safe.

A test must instrument `fetch`, `XMLHttpRequest`, `sendBeacon`, service-worker fetches, and storage APIs to prove that using location and geocoding calls emits no coordinates and persists none.

## 14. Performance and quality targets

Targets are release gates after they are confirmed against the first feasibility prototype:

| Measure | Version 1 target |
| --- | --- |
| Pack transfer | 10–30 MiB; fail above 30 MiB |
| Installed footprint | ≤45 MiB target on Chromium; actual values reported |
| Warm single-address query | p50 ≤20 ms, p95 ≤75 ms in worker |
| Cold query including block read | p95 ≤250 ms |
| Batch of 100 calls | ≤2 seconds, progressive results, no main-thread freeze |
| Main-thread responsiveness | No import/query long task over 50 ms attributable to OffGeo |
| Install | ≤60 seconds on the agreed reference Android device/network after bytes arrive |
| Determinism | Same inputs/options/compiler produce identical SHA-256 |
| County isolation | 100% decoded points and records inside approved county buffer or explicitly reported exceptions |
| Result explainability | 100% of queries return status, reason code, and pack version |

Coverage gates use a versioned, sanitized fixture derived from real calls plus hand-authored edge cases:

- At least 95% of supported fixture inputs produce a matched or documented fallback result.
- At least 85% use a range/intersection method rather than street-only fallback.
- Zero known cross-locality ambiguous matches are silently selected.
- All expected unmatched/ambiguous fixtures remain unmatched.
- No release may regress high-confidence resolution by more than 1 percentage point without a reviewed explanation.

Accuracy is evaluated against a held-out public-government address-point sample when available. Initial provisional targets are median error ≤75 m and 95th percentile ≤300 m for range-interpolation results. The feasibility phase must measure and approve or revise these thresholds before implementation promotion; the UI wording remains approximate regardless.

## 15. Failure and recovery behavior

| Failure | Required behavior |
| --- | --- |
| Manifest unavailable | Keep using active pack; show last successful check |
| Download interrupted | Keep active pack; allow retry/restart of staged version |
| Checksum or block failure | Reject candidate, remove only staged records, retain active pack |
| Unsupported format/app version | Do not install; request app refresh/update |
| Quota insufficient | Explain required/available estimate and offer safe retry/delete actions |
| IndexedDB/private-mode unsupported | Keep live calls usable, disable install with an explicit browser/storage explanation |
| Browser evicts data | Detect missing active blocks, clear invalid pointer, offer reinstall |
| Another tab installs/upgrades | Observe the existing installer, close on `versionchange`, and never race activation/deletion |
| Worker crashes | Keep calls UI usable, restart once, then show distance unavailable |
| Address ambiguous/unmatched | Keep call visible and show reason; never invent a result |
| Location denied/timed out | Keep geocoder/calls usable; show recovery/refresh action |
| Calls feed returns 401/CORS/schema error | Keep a valid cached snapshot with stale labeling; report feed failure separately from pack health |
| New release performs poorly | Manifest rollback to prior immutable pack; clients retain old pack until a valid replacement installs |

## 16. Release and maintenance contract

Every four months, automation checks all source endpoints and checksums. Because Census releases may be annual while local data can update more often, a check with unchanged inputs records “checked, no new pack” instead of publishing a byte-identical release.

A candidate pack may be promoted only when:

1. Source manifest, licenses/reuse notices, and attribution are complete.
2. Compiler output is deterministic.
3. All schema/integrity/security tests pass.
4. Size, coverage, accuracy, and performance reports pass approved thresholds.
5. A browser install/update/rollback test passes on desktop Chromium and the reference Android browser.
6. Airplane-mode end-to-end behavior passes.
7. Privacy instrumentation finds no coordinate transmission or persistence.
8. Legacy coordinate/geocoder migration passes on a profile containing old site data.
9. Multi-tab install/update/upgrade tests pass.
10. A human reviews source diffs, join/conflict reports, regressions, and release notes.

Published pack URLs are immutable. The small active manifest may move forward or roll back. Keep at least the active and immediately previous versions available until telemetry-free/manual release confidence is established.

## 17. Acceptance scenarios

The feature is complete only when automated or recorded manual evidence covers:

1. Fresh user installs the county pack, grants location, sees approximate distances, sorts nearest, reloads offline, and still sees cached calls/distances.
2. Permission-denied user can use the calls list and offline address matches without distance.
3. A failed update leaves the prior pack usable.
4. A storage-evicted pack is detected and recoverable.
5. Exact, reversed, odd/even, block, intersection, alias, duplicate-street, ambiguous, out-of-range, malformed, and out-of-county address fixtures return expected reason codes.
6. No location coordinates appear in persistent storage or captured network traffic.
7. Reduced-motion users receive no nonessential movement.
8. Pack credits expose publisher, source, vintage, retrieval date, and derived-product notice.
9. Two tabs cannot race an install, block an upgrade indefinitely without explanation, or delete a version still in use.
10. Upgrade from the existing live app removes legacy saved coordinates/geocode cache and the Google geocoder/key without deleting unrelated data.
11. Feed 401/CORS/invalid-schema failures show the last valid snapshot as stale and do not report the address pack as broken.
12. Clicking a call row does not contact an external map provider; only the labeled external-map action does.

## 18. Decisions to confirm during feasibility

These do not block writing the prototype but must be fixed before the format is frozen:

- Final SanGIS-to-Census field precedence and the allowed address-point-to-range repair rules.
- Compression algorithm supported by target browsers and static hosting.
- Block partition count and whether the street index is stored expanded or as an indexed block.
- Custom `OFG1` versus a maintained SQLite/PBF-style format after equivalent size/runtime benchmarks.
- Final installed-size, coverage, and accuracy thresholds after measurements.
- Reference Android device/browser used for release performance evidence.
- Stale-pack warning threshold; proposed: warn at six months, remain functional.
- Cached-call stale/hide/purge windows; proposed: immediate stale after failed refresh, hide at 6 hours, purge at 24 hours.
- Whether a low-confidence street-only distance should be shown by default or require expanding details.

## 19. Pre-implementation risk register

This review converts the likely failure points into required design controls:

| Risk discovered | Preventive decision | Proof before release |
| --- | --- | --- |
| Census cannot substantiate “every address” because it contains potential ranges and suppresses some single-address ranges | Make SanGIS roads/address points primary; use Census as fallback/cross-check; publish measured coverage rather than an absolute claim | Address-point join, calls fixture, gap, and unmatched reports |
| Duplicate street names cannot be resolved from Census ZIP fields when the feed supplies sheriff communities | Join SanGIS `COMMUNITY` to `ROADSEGID` and maintain a versioned feed-community crosswalk | Duplicate-name fixtures in every affected community; unmatched crosswalk count gate |
| Current feed uses slash intersections without spaces and sometimes street-only locations | Parser recognizes no-space separators and street-only type; intersection topology has its own measured gate | Rolling sanitized calls corpus plus explicit parser fixtures |
| Full TIGER `EDGES` or raw SanGIS inputs could exceed the client budget | Raw data stays build-time; geometry is de-duplicated; ship only minimal named-road topology if it improves measured intersection coverage | Per-component pack-size report; hard 30 MiB gate |
| Weekly source URLs overwrite prior bytes, so URL + checksum alone is not reproducible | Retain exact inputs in content-addressed build storage outside Git and verify them against the source lock | Clean rebuild from retained archives after the public URL changes |
| Large road/address inputs and expanded geometry can exhaust a Termux build device | Disk/memory preflight, streaming stages, ignored content-addressed cache, bounded scratch directory, and measured cleanup | Build-host peak disk/RAM report and low-space failure test |
| House-number fields are strings with hyphenated/alphabetic values | Structured house-number parser and explicit unsupported reason; no `parseInt` coercion | Source profile and golden nonstandard-number fixtures |
| NAD83/State Plane source coordinates can be silently mislabeled as WGS84 | Explicit CRS/datum transform and control-point validation | Transform metadata and spatial control report |
| Whole-file Web Crypto hashing is not streaming | Incremental hash or bounded-memory block verification selected by device benchmark | Peak-memory trace and corrupt-block/whole-file tests |
| IndexedDB transactions can auto-close across asynchronous gaps | Short per-block transactions; no fetch/decompression inside a live transaction | Forced-yield install test with no `TransactionInactiveError` |
| Two tabs can race installs, upgrades, activation, or cleanup | Web Lock plus lease/fencing fallback, reader version pins, `blocked`/`versionchange` handling | Multi-tab install/update/old-tab E2E suite |
| Quota estimates are not guarantees and private storage may be ephemeral | Capability test, advisory preflight, authoritative write errors, persistence status, reinstall path | Private-mode/denied-persistence/quota/eviction tests |
| The existing app violates the new location boundary | Remove old Google geocoder/key, localStorage coordinates, coordinate logs, and implicit map iframe; run an idempotent migration | Network/storage capture on an upgraded profile |
| Current service worker does not intercept fetches and caches only `/` under an unversioned name | Replace it with a versioned app-shell strategy and test actual offline reload; keep pack in IndexedDB | Public-origin install followed by airplane-mode reload |
| Cached active calls can become dangerously stale | Keep only one snapshot, mark non-live immediately after refresh failure, hide/purge at approved windows | Clock/network failure E2E and cache-retention test |
| Calls-feed 401/CORS failures can be mistaken for pack failures | Separate feed, pack, storage, worker, and permission state machines/error codes | Fault-injection UI tests for each subsystem |
| The current static page embeds a calls-service credential and sends it through a CORS proxy | Use an approved public-client credential or controlled same-origin proxy; keep all secrets out of browser source, URLs, caches, and reports | Production network/source inspection plus 401/rotation test |
| A custom format can create unnecessary maintenance and compatibility risk | Compare `OFG1` against maintained alternatives before freezing; retain golden/corrupt fixtures if selected | R1 format decision with measured size, memory, speed, and support matrix |
