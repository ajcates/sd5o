# Legacy geocoder/location storage migration — test plan

Status: Test plan written 2026-08-23 — plan only, migration code not yet written
Scope: closes the R0 exit-gate bullet "the existing geocoder/location storage leaks have a precise removal/migration test plan" ([`todo.md`](./todo.md)). Builds on, does not replace, [`index-html-audit.md`](./index-html-audit.md) Part A (`OFF-010`) and its `OFF-015` safety contract, which already named the keys and shapes in general terms. This document pins down literal seed/expected values and concrete test cases so `OFF-312`/`OFF-512` (R3/R5, still out of scope here) has an unambiguous target to implement against and test-drive, rather than re-deriving the exact legacy shapes from `main.js.old` a second time.

## Why this needs to be precise, not general

The migration cannot assume a clean slate. `main.js.old` (the pre-PWA-conversion source this app's script was extracted from — see `index-html-audit.md`'s finding) was live in real users' browsers, and its exact, sometimes buggy, write patterns determine exactly what a real profile can contain today. Three of those patterns are easy to get wrong if re-derived from memory instead of the actual old source:

1. `latitude`/`longitude` are written as **raw, non-JSON values** (`main.js.old:56-57`: `localStorage.setItem('longitude', position.coords.longitude)`), so `localStorage.getItem('latitude')` on an affected profile returns a bare numeric string like `"32.715738"`, not `'{"lat":32.715738}'` or similar. A migration that tries `JSON.parse` on these two specific keys before removing them must not throw or treat a parse failure as "not present."
2. The geocode address-string cache key is not a clean address string. `main.js.old:102`: `` let address = row.querySelector('td.Address').innerText + ' ' + row.querySelector('td.Commuinty') + ' California'; `` — `td.Commuinty` is a typo that never matches any real cell (the real class the table ever assigned was `Community`, and even that was never applied to a `Community` cell — `buildTable`'s `headers` array is only `["Address", "DateTime", "EventType"]`, so a `Community`-classed cell never existed either). `querySelector` therefore always returns `null`, and string-concatenating `null` coerces to the literal text `"null"`. **Every real cache key this code ever wrote has the exact literal shape** `"<address text> null California"` — e.g. `"400 HARDELL LN null California"` — not `"400 HARDELL LN, UNINCORPORATED VISTA California"` as a naive re-reading of the code might assume. A migration that pattern-matches "an address-shaped key" using the community name will miss every real instance.
3. The value at that key is `JSON.stringify(coords)` where `coords` came straight from the Google Geocoding API's `results[0].geometry.location` (`main.js.old:238`) — a plain `{"lat": <number>, "lng": <number>}` object, no wrapper, no extra fields. This is the shape-detection signature (`OFF-015` already named this; this plan pins the exact key set: an object with exactly `lat` and `lng` numeric keys and no others).
4. The per-event cache (`main.js.old:322-341`) writes the *entire* event object back to `localStorage[event.EventNumber]`. Tracing the exact write order: for a brand-new event, `nearby`/`new`/`changed` are never present in what's saved (they're set on the in-memory object *after* the save call). For an event that was already cached with `nearby: true` (set later by `Nearby.addDistanceColumn`, `main.js.old:118-119`), that `nearby: true` **does** carry forward into the next cached write if any other field changes (`main.js.old:327-329` copies `oldEvent.nearby` onto the live `event` before the save at line 333). So real affected profiles can have per-event entries with `nearby: true` sitting alongside perfectly ordinary fields — this is the only synthetic flag that can appear in a saved entry from the old code, matching what `index-html-audit.md` already found by static reading; this plan adds the concrete write-order trace confirming it.

## Exact fixture: what a "dirty" test profile contains

A migration test must seed **all** of these before running the migration, in one profile, because a real long-lived user profile would have accumulated all of them together:

```js
localStorage.setItem('latitude', '32.715738');                 // raw, not JSON
localStorage.setItem('longitude', '-117.161087');               // raw, not JSON
localStorage.setItem(
  '400 HARDELL LN null California',                             // literal, see finding 2 above
  JSON.stringify({ lat: 33.1959, lng: -117.2504 })
);
localStorage.setItem(
  'E8375208',
  JSON.stringify({
    EventNumber: 'E8375208',
    IsOpen: true,
    DateTime: '08-23-2026 06:44:00',
    Address: '400 HARDELL LN',
    ServiceArea: 'VISTA / FALLBROOK',
    Community: 'UNINCORPORATED VISTA',
    EventType: '11-7 PROWLER',
    nearby: true,                                                // the one synthetic flag that persists
  })
);
localStorage.setItem(
  'E9999999',                                                    // a second, unaffected per-event entry
  JSON.stringify({
    EventNumber: 'E9999999',
    IsOpen: false,
    DateTime: '08-23-2026 05:10:00',
    Address: '100 MAIN ST',
    ServiceArea: 'CENTRAL',
    Community: 'SAN DIEGO',
    EventType: 'TRAFFIC STOP',
  })
);
localStorage.setItem('unrelated-app-setting', 'keep-me');         // must survive untouched
localStorage.setItem('theme', 'dark');                            // must survive untouched
```

## Required migration behavior (test assertions)

Given the profile above, after the migration runs once:

| Assertion | Key | Expected |
| --- | --- | --- |
| Removed | `latitude` | `localStorage.getItem('latitude') === null` |
| Removed | `longitude` | `localStorage.getItem('longitude') === null` |
| Removed | `'400 HARDELL LN null California'` | `=== null` |
| Migrated, not removed | `'E8375208'` | still present; parses to an object with **no** `nearby` key; every other field (`EventNumber`, `IsOpen`, `DateTime`, `Address`, `ServiceArea`, `Community`, `EventType`) unchanged |
| Untouched | `'E9999999'` | byte-identical to its seeded value (no `nearby` key to strip, must not be rewritten at all — a real implementation should skip a `JSON.stringify` round-trip on rows that don't need one, so this is also a "don't touch what you don't have to" check, not just a correctness check) |
| Preserved | `'unrelated-app-setting'`, `'theme'` | byte-identical to seeded values |
| Marker set | migration version key (see "Open interface question" below) | present, non-sensitive value (a version number/string, never a coordinate or address) |

Additional cases beyond the one combined fixture above:

- **Detection by value shape, not key name, for the geocode cache.** Seed a second geocode-style entry under a *different* address string (e.g. `"100 MAIN ST null California"` → `{"lat":32.7,"lng":-117.1}`) to prove the migration finds these by scanning for the `{lat, lng}`-only value shape across all keys, not by hardcoding the one example key from the fixture above.
- **False-positive guard.** Seed a key whose value also happens to parse as JSON with `lat`/`lng` fields but represents something legitimate and unrelated (e.g. `localStorage.setItem('map-center', '{"lat":32.8,"lng":-117.2,"zoom":10}')` — note the extra `zoom` field). This must **survive** — the shape match must require *exactly* `{lat, lng}` with no extra keys, or the migration will delete data it doesn't own.
- **Idempotency.** Run the migration twice in the same profile. The second run must be a true no-op: no error, no change to any remaining key, marker key unchanged (not re-written with a new timestamp if versioned by more than a bare version number).
- **Clean-profile no-op.** Run the migration against a profile containing only ordinary current-app keys (e.g. just `'E9999999'` and `'theme'` from above, none of the legacy ones). Migration must complete without error and still set the marker key — a clean profile is not an error case.
- **Runs before anything else reads the affected keys.** This is an ordering requirement, not a unit-testable pure-function assertion: the migration must execute before `CallsList.onCreate`'s `annotateWithCache` (`src/app/calls-list.js:21-40`) does its first read of any `EventNumber`-keyed entry, otherwise a `nearby: true` leftover could be read and rendered (as a CSS class, currently unused post-rewrite, but still a live read of migrated-away data) before cleanup happens. The test for this is an integration-level check: seed the dirty profile, load the real app (not a mocked one), and assert the *first* render of the calls list never reflects `nearby` state for `E8375208` — not just that the storage ends up clean eventually.

## Recommended test harness

Use the real-Chromium E2E harness already built for `OFF-012` ([`tooling-decision.md`](./tooling-decision.md), `tests/e2e/run.mjs`'s `playwright-core` setup), not a Node unit test. Reasons:

- `localStorage` is a genuine per-origin browser API; Node has no built-in equivalent (confirmed: a bare `node -e "localStorage.setItem(...)"` throws `Cannot read properties of undefined` on the Node version this project uses — there is no global `localStorage` without an experimental flag whose semantics aren't guaranteed to match a real browser).
- The ordering requirement above (migration-before-first-render) can only be checked meaningfully against the real boot sequence in `index.html`/`src/app/main.js`, which only exists in a real page load.

Concretely: `page.evaluate()` to seed the fixture into `localStorage` **before** navigating to `index.html` (Playwright allows adding init scripts via `page.addInitScript()` specifically so seeded storage exists before the page's own scripts run), navigate, then `page.evaluate()` again to read back every key in the assertions table above. This fits directly into `tests/e2e/run.mjs`'s existing pattern once the migration function exists.

## Open interface question this plan surfaces (for whoever implements `OFF-312`/`OFF-512`)

This plan deliberately stops short of naming the migration's module path, exact marker key name/value, or call site in `src/app/main.js` — pinning those down is implementation, which stays out of scope here per the same R3/R5 boundary `todo.md` Group 4 already drew around this work. What it does require, so the future implementation isn't invented from scratch either: a single idempotent function taking a `Storage`-like object (so it's testable against a real `localStorage` without needing DOM/network) and returning a small report of what it removed/migrated, callable exactly once at app boot before any other component's first `localStorage` read.
