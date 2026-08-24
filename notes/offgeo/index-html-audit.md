# `index.html` audit — privacy debt and architecture (Group 4)

Status: Done 2026-08-23
Scope: rewritten/expanded Group 4 of [todo.md](./todo.md) — `OFF-010`/`OFF-015` privacy audit, plus a general architecture audit added alongside it per the same group. This is a deliberate scope addition beyond the original `roadmap.md` §4 (`OFF-001`–`OFF-017`) list; it does not remove or weaken the privacy-audit deliverable those items already call for.

Source examined: `index.html` as of commit `970b58b` ("redesign"), cross-checked against `main.js.old` (the pre-PWA-conversion version) and `git log -p -- index.html` for history.

## Part A — Privacy audit (`OFF-010`)

| Item | Location | Status |
| --- | --- | --- |
| Google Geocoding API key (`AIzaSyAhHsSxRyTrAV5cU7bzyXvK1M54S0RVADY`) | `index.html:1152`, inside `getLatLngForAddress` | Shipped in source, **but unreachable** — see finding below |
| `Nearby` class (geocoder call, `localStorage` lat/lng writes) | `index.html:952`–`1107` | Defined but **never instantiated** anywhere in the current file |
| Per-event `localStorage` cache with `nearby` flag | `index.html:1335`–`1366` (read/write), set by `Nearby.addDistanceColumn` at `index.html:1040`–`1044` | The read/write-back of the cache entry itself is live (every table build touches it); only the code path that ever sets `nearby: true` is dead |
| Google Maps iframe embed (row map-expand) | `index.html:1420`–`1442` | **Live.** Clicking any table row embeds `https://maps.google.com/maps?q=<call address>...&output=embed` |

**Key finding — the geocoder path is currently dead code, but was live before.** `grep -n "new Nearby"` across `index.html` returns nothing: the class is defined but nothing constructs it. `git log -p -- index.html` shows the instantiation line has been commented out (`//this.nearby = new Nearby(this.table);`) since before the PWA conversion. However, `main.js.old` — the file this app's script was extracted from — has that same line **active**: `this.nearby = new Nearby(this.table);` (`main.js.old:281`). That means:

- The Google API key is not currently exercised by any live user session, but it is still shipped in page source and callable by anyone who reads it — key revocation/restriction in the Google Cloud console (`OFF-015`) is still required regardless of reachability.
- Real past users of this app, before the PWA-conversion commit, likely did have `localStorage.latitude`/`localStorage.longitude` written, and may carry per-event cache entries with `nearby: true`. **The migration plan cannot assume a clean slate** — `OFF-015`'s test proving unrelated data survives migration must be paired with a positive test that these specific legacy keys, if present from the old code path, get removed.
- The map iframe (separate from the geocoder) discloses which call a visitor is interested in to Google on every row expand — not a coordinate leak, but a distinct minor privacy consideration worth carrying into the `OFF-312`/`OFF-512` replacement design (a non-iframe, non-Google map or an explicit consent gate).

**What OFF-015 needs, now grounded in the real code:**

- `localStorage` keys to remove/migrate: `latitude`, `longitude` (`index.html:981`–`982`); the geocode-address-string cache keys written by `Nearby.geoCodeCache` (`index.html:1089`, `1099`) — these are keyed by the *address string itself*, not a fixed prefix, so the migration must recognize them by the shape of their value (`{lat, lng}` JSON), not by a known key name.
- Per-event records: keyed by `EventNumber` (`index.html:1335`, `1345`, `1353`); strip a `nearby` field if present, keep the rest (the event cache itself, sans `nearby`, is legitimate and still used by the live new/changed-row highlighting).
- Idempotent migration marker: none exists yet; needs a versioned marker key so this runs once per profile.
- Provider-key checklist step: revoke/restrict `AIzaSyAhHsSxRyTrAV5cU7bzyXvK1M54S0RVADY` in Google Cloud Console regardless of current reachability.
- Test: unrelated-origin `localStorage` data survives; **and**, using a profile seeded with `main.js.old`-era keys, they are gone after migration runs once.

## Part B — Architecture audit (new, added alongside the privacy audit)

`index.html` is 1,584 lines: markup, inline `<style>`, and one 635-line inline `<script>` (`index.html:927`–`1562`) holding three classes (`Nearby`, `CallsForService`, `TableFilter`) and seven bare global functions. Findings that motivate a framework decision rather than an incremental patch:

1. **State mutation is interleaved with rendering.** `CallsForService.buildTable` (`index.html:1298`–`1450`) reads/writes the per-event `localStorage` cache *while* constructing DOM nodes in the same loop — there is no way to render without also mutating storage, which makes the render path untestable in isolation and risks double-writes on re-render.
2. **No component boundary between DOM lookup and behavior.** Every class constructor calls `document.getElementById`/`querySelector` directly (`index.html:955`, `1183`–`1190`, `1508`–`1509`); none of the three classes can be instantiated or unit-tested without a live DOM matching the exact current markup.
3. **Three different DOM-construction styles in one file**: imperative `createElement` (most of `buildTable`), `innerHTML` template strings (search-toggle icon `index.html:1209`, loading/error states `index.html:1240`–`1248`, `1282`–`1291`), and direct inline-style mutation (`row.style.backgroundColor = 'rgba(255, 0, 0, 0.5);'` at `index.html:1039` — the trailing `;` is baked into the string value itself, which is invalid as a CSS property value and is silently dropped by the browser; a real, if minor, bug this audit found).
4. **No lifecycle — full teardown/rebuild every refresh.** `addTable()` calls `this.listingElement.replaceChildren(this.table)` (`index.html:1261`) on every poll, discarding and rebuilding the entire table rather than patching it, which is also why an open map row silently vanishes if a refresh lands while it's open.
5. **Global namespace pollution.** `calcCrow`, `toRad`, `toRadians`, `prettyPrintDistance`, `prettyTime`, `fetchJson`, `insertAfter` (`index.html:1112`–`1150`, `1452`–`1500`) are bare top-level functions with no module scoping — any other inline script on the page could collide with or shadow them.
6. **Dead and vestigial code**, beyond the `Nearby` wiring already covered in Part A:
   - A leftover Violentmonkey userscript header (`index.html:928`–`937`, `// ==UserScript== ... @match https://callsforservice.sdsheriff.gov/`) — this file is not a userscript and does not run on that domain; copy-paste residue from wherever this code originated.
   - A commented-out, unrelated `google.maps.Geocoder()` snippet (`index.html:942`–`951`) that predates and duplicates the (also dead) `getLatLngForAddress`.
   - `Nearby.getDistanceInMilesAndFeet` (`index.html:1057`–`1084`) is defined but never called — `addDistanceColumn` uses the top-level `calcCrow` instead, making this a second, unused Haversine implementation.
   - A commented-out reference to a `SortableTable` class that does not exist anywhere in the codebase (`index.html:1053`, `1503`).
7. **Loose equality in change detection.** `CallsForService.buildTable`'s cache-diff loop compares every field with `!=` (`index.html:1344`), not `!==`; harmless for the current all-string feed payload, but a latent bug if any field's type ever changes (e.g. `IsOpen` arriving as a real boolean would compare unreliably against a stringified cached copy).
8. **The change-detection cache diff marks a row "changed" forever after its first "new" poll.** `buildTable`'s cache-diff loop (`index.html:1335`–`1354`) persists the *mutated* event object — including the synthetic `changed`/`new`/`nearby` keys it just set — back into `localStorage`. On the next poll, a freshly fetched event never has those synthetic keys, so `for (var k in oldEvent)` iterating the previous cached copy's keys hits `event['new']` (`undefined`) `!= oldEvent['new']` (`true`) and marks the row `changed` again, unconditionally, on every subsequent poll for the rest of that row's life. Fixed in the rewrite by comparing/persisting only the seven canonical feed fields, never the derived flags.
9. **The service worker doesn't actually serve anything offline.** `serviceworker.js`'s only `fetch` handler is commented out (`serviceworker.js:11`–`19`); `install` caches `["/"]` and nothing ever reads that cache back. The app is a "PWA" only in the sense of having a manifest — airplane-mode behavior (a real roadmap R6 requirement) does not currently exist.

None of this is unique to `index.html` being hand-written rather than framework-based — but the coupling in (1)/(2)/(4) specifically is what makes a from-scratch component layer worth building rather than patching in place: state changes need to flow through one place that both re-renders and is safe to unit-test without a live page.

## Recommendation feeding the framework decision

Build a small custom component/render layer (see `src/framework/core.js`) rather than adopting an external UI library or leaving the current structure as-is. Rationale, weighed against the alternatives:

- **Do nothing / patch in place** — rejected. Findings 1, 2, and 4 above are structural, not local bugs; patching them individually while keeping direct DOM/localStorage coupling in every class would not fix the untestability problem OffGeo's own R1–R6 phases need this app to not have (roadmap.md §2 lists Product UI and PWA/offline as workstreams starting R1/R3).
- **Adopt an existing tiny library (Preact, lit, petite-vue, htm)** — viable, but roadmap.md §3 already commits this project to "ordinary static JavaScript compatible with the current app and deployment" with no required build step; every one of those either needs a build step for JSX/templates or adds a third-party dependency this single-maintainer static site would need to vendor and keep patched. Revisit only if the custom layer proves insufficient once OffGeo's own UI (distance controls, install/update UI) lands in R5.
- **Custom mini framework, native ES modules, no build step** — chosen. Scope is deliberately small: a `Component` base class (state → render → delegated events), one escaping `html` template helper, and a `mount()` entry point. This is sized to what `index.html` actually needs (list rendering, status text, one search input, no routing — it's a single view), not a general-purpose framework.

## Part C — Prototype outcome

Built and verified, not left as a paper design:

- `src/framework/core.js` — `Component` (state → `render()` → `innerHTML`, delegated `data-on-<event>` binding at mount), an escaping `` html`` `` template tag with an explicit `raw()` escape hatch, and `mount()`. ~110 lines.
- `src/app/`: `format.js` (`prettyTime`, `fetchJson`, pulled out of global scope), `status-panel.js`, `calls-list.js`, `search-toggle.js`, `main.js` (bootstrap, replaces the old inline `<script>` wiring). `calls-list.js` also fixes finding 8 above (the "changed forever" bug) as part of reorganizing the cache-diff code, and drops the dead `Nearby` class entirely per the decision above.
- `index.html`'s two inline `<script>` blocks (`index.html:927`–`1581` in the pre-rewrite version) are replaced by one `<script type="module" src="src/app/main.js"></script>`; `#status-panel` and `#listing` are now empty mount points instead of carrying duplicate static skeleton markup, since the components own their own initial render.
- Verified in a real headless Chromium (`playwright-core` against the system browser, per `roadmap.md` §3's sibling `../playwright-termux` harness — no `chromium-cli` was available in this environment, so a small one-off Playwright driver script was used instead) against the live feed: status panel reaches "Live" with the correct call count, the search toggle opens the search bar and the filter narrows visible rows and updates the count text, and clicking a row expands the map iframe with the correct URL and cleanly removes it on collapse (confirmed with a longer wait after the first pass under-waited past the CSS's 260ms transition and read a false negative). Zero console or page errors in any of these interactions.
- The API-key/CORS-proxy call in `calls-list.js` is unchanged from `index.html`'s previous behavior on purpose — fixing that is `OFF-011`'s job (Group 5), not this rewrite's.

## What this audit does not do

Per `todo.md`'s original Group 4 framing, this document plus the prototype in `src/framework/` and `src/app/` are the audit and the migration/replatform vehicle — they do not yet perform the `OFF-015` `localStorage` migration or revoke the Google API key (`OFF-312`/`OFF-512`, R3/R5). The prototype rewrite deliberately does not resurrect the `Nearby`/geocoder feature; that functionality is intentionally left out of the port and is expected to be rebuilt properly on top of OffGeo's own offline geocoder in R5, not carried forward from dead code with known privacy debt.
