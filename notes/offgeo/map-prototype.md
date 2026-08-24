# Calls map prototype

Status: Done 2026-08-23 (prototype, not the real R1-R4 geocoder/compiler)
Scope: a further extension of [todo.md](./todo.md) Group 4's replatforming work, built at the user's direction as a slice of what roadmap.md's R5 "Product UI" workstream will eventually need for real (distance/location, `src/offgeo/` geocoder-backed UI). Nothing here is R1-R4 implementation — it deliberately reuses only what R0 already pinned and profiled, plus one new build-time dependency (`proj`/`cs2cs`, noted below).

## What it is

A slide-down map panel (toggle button next to search, `src/app/map-view.js`) built on self-hosted Leaflet (`vendor/leaflet/`, BSD-2-Clause, MIT-adjacent, version 1.9.4) showing:

- **Roads as line geometry, not raster tiles.** Bulk-mirroring the public OpenStreetMap tile server as static files would violate its tile usage policy, and self-rendering raster tiles is a heavier pipeline than this prototype needs. Instead the map draws SanGIS Roads-All centerlines directly (`src/app/data/roads.json`) — a real, already-pinned, already-licensed dataset, and inherently self-hosted.
- **One pulsing marker per geocodable call.** Pulse speed/size/opacity scale continuously with the call's age (`pulseParamsForAge` in `map-view.js`): fast/bright/large near the moment of dispatch, fading to a slow, subtle pulse, and stopping entirely (static dot) past 2 hours old.
- **Tap a marker → the matching table row scrolls into view and highlights** (`CallsList.focusEvent`), clearing an active search filter first if it's hiding that row. No separate "single card" view was built — the existing table is the list, per the chosen interaction model.

## How markers get coordinates (and why most calls still won't have one)

There is no live geocoder in this app (the old Google one was already dead code before this session, see `index-html-audit.md`). Building a real one is R1-R4 work: shared normalization, range interpolation over road geometry, confidence scoring. This prototype does none of that. Instead:

- `tools/offgeo/build-address-index.py` builds a lookup **scoped to only the communities the live calls feed has actually been observed dispatching to** (`tests/offgeo/fixtures/community-crosswalk.json`'s 14 mapped feed communities / 28 raw SanGIS `COMMUNITY` spellings) — not the whole county. Key: a normalized street name (`PDIR NAME POSTD SFX`); value: every known SanGIS address point's (house number, lat, lon) on that street.
- `src/app/geocoder.js` (client-side) splits a call's `Address` into a leading house number and that street key, and looks for an **exact** house-number match, or the **nearest known point on the same street within 300 house numbers**, explicitly labeled `exact` vs. `nearest`. Beyond that delta, or if the street isn't in the scoped index at all (including every intersection — there's no single point for those here), the call gets no marker. This is a bounded, explainable approximation, not an invented result: an exact-match-only first pass measured just 4/43 hits against the Group 3 fixture corpus (SanGIS address points are real parcels, not every integer house number), so nearest-on-street was added to raise real coverage — verified on a live run at 31/46 markers (67%) against the current feed snapshot, not just the fixture corpus.
- Coordinates: SanGIS's native CRS is State Plane NAD83 California Zone 6, US survey feet (EPSG:2230, confirmed from each archive's `.prj` during Group 2). An early hand-rolled Lambert Conformal Conic inverse implementation (`tools/offgeo/lib/coords.py`) had a real bug, caught by checking its output against a known address point (611 W G St, San Diego): it placed the point in the Texas panhandle, about 1,400 km off. Rather than keep debugging the projection algebra, `coords.py` now shells out to PROJ's `cs2cs` (installed via `pkg install proj` — **a new build-time-only system dependency**, not shipped to the browser, and not previously required by any other `tools/offgeo/` script). NAD83 is treated as equivalent to WGS84 at this accuracy budget, same approximation already recorded for the Census source in Group 2.

## What was built to support this

- `tools/offgeo/lib/coords.py` — State Plane (EPSG:2230) → WGS84 via `cs2cs`, batched (~20,000 points/second measured on this device).
- `tools/offgeo/lib/shp.py` — minimal stdlib-only streaming reader for `.shp` PolyLine/PolyLineZ records (SanGIS Roads-All is type 13), same "exploration tooling, not a shapefile library commitment" rationale as `lib/dbf.py`.
- `tools/offgeo/build-address-index.py` → `src/app/data/address-index.json` (197,192 points across 10,061 streets, 6.8 MB / ~1.8 MB gzipped).
- `tools/offgeo/build-roads-geometry.py` → `src/app/data/roads.json` (140,338 line segments kept out of 164,555 by filtering to per-community bounding boxes rather than one whole-county box — the 28 scoped communities are scattered from the coast to the mountains, so their combined envelope is nearly the whole county and wouldn't cut size at all; per-community boxes correctly exclude the large incorporated-city areas between them). Simplified with Douglas-Peucker (35 ft tolerance) before transform. 7.3 MB / ~1.6 MB gzipped.
- Both data files are fetched lazily — only when the map panel is opened for the first time, not on initial page load, since most visits won't open it and together they're several MB.
- `vendor/leaflet/` — self-hosted Leaflet 1.9.4 core (`leaflet.js`, `leaflet.css`, marker/layer icons), also lazy-loaded on first map open (`src/app/leaflet-loader.js`).

Verified in a real headless Chromium against the live feed (same harness as the framework rewrite): map opens, roads render, 31/46 live calls got a marker, 23 were still pulsing, marker tap scrolled to and highlighted the correct row, zero console errors.

## Explicit non-goals / what this is not

- Not the real OffGeo geocoder. No shared normalization library, no range interpolation over geometry, no confidence/reason codes, no fallback to Census. All of that is still R1-R4 as roadmap.md already scopes it.
- Not full-county coverage. Only the 28 already-crosswalked SanGIS community spellings are indexed; the 4 feed communities Group 3 already found unmapped (`PAUMA`, the three `UNINCORPORATED <CITY>` labels) still resolve zero markers, same gap Group 3 already flagged for `OFF-009`.
- Not a tile basemap. No raster imagery, no third-party tile provider account/terms dependency.
- The "nearest within 300" fallback is a real approximation with real error (a marker can visibly land at the wrong end of a long block). It's labeled `exact`/`nearest` internally (`geocoder.js`'s return value) but the UI doesn't yet surface that distinction to the user — worth doing before this becomes more than a prototype.
