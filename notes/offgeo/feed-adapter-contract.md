# Calls-feed adapter contract (`OFF-011`, Group 5)

Status: Contract written 2026-08-23 — design only, not yet implemented in `src/app/`
Scope: [`todo.md`](./todo.md) Group 5. Grounded in [`spec.md`](./spec.md) §13 (security), §15 (failure/recovery), §16.500 area, and the current live implementation in [`src/app/calls-list.js`](../../src/app/calls-list.js) / [`src/app/format.js`](../../src/app/format.js).

This is a written contract per Group 5's framing — it does not change `src/app/` code. It records the current behavior, where it already meets `spec.md`, where it doesn't, and the one open finding (the third-party CORS proxy) that needs a decision before it can be called production-safe.

## 0. Ground truth checked live before writing this

The feed endpoint does not send CORS headers, even when asked:

```
curl -D - -o /dev/null "https://leag-caddata-dev-fa-leag-caddata-dev-fa-blue.azurewebsites.us/api/GetCADEvents?code=<key>" -H "Origin: https://sd50.surge.sh"
HTTP/1.1 200 OK
Content-Type: text/plain; charset=utf-8
(no Access-Control-Allow-Origin header at all)
```

So a relay of some kind between the browser and this Azure Function is not a design choice this project can engineer away — a plain browser `fetch` to that URL from `sd50.surge.sh` (or any origin) is blocked by the browser regardless of what the relay does with the credential. This confirms the user's framing directly: **a proxy is structurally required.** The finding below is about what the proxy does with the secret, not about whether a proxy exists at all.

Also confirmed: `CNAME` pins this site to `sd50.surge.sh` — Surge is a pure static host with no server-side execution. A literal *same-origin* serverless function (the phrasing `spec.md`/`OFF-011` use) is not available without adding a separate service or changing hosts. That distinction matters for §4 below.

## 1. Error taxonomy

Feed errors and pack errors (the offline geodata artifact, R1+) must never share a code space or a UI message — a live-feed outage must never be mistaken for, or reported alongside, broken offline data (`spec.md` §13.14, §15 row "Calls feed returns 401/CORS/schema error"). Within the feed itself, `getRequestUrl`/`load()` in `calls-list.js` currently collapse everything into one `catch` with a string message. The adapter must instead classify into these categories, each carrying enough detail to render a distinct message and to log distinctly without ever including the credential:

| Category | How it's detected | Example |
| --- | --- | --- |
| `network` | `fetch()` itself rejects (thrown `TypeError`) — true CORS rejection, DNS failure, offline, mixed content | Proxy host unreachable, device offline |
| `timeout` | No response within a bounded budget (not currently enforced — `fetchJson` has no `AbortController`) | Proxy or upstream hangs |
| `proxy_error` | Proxy responds, but with its own non-2xx status distinct from the upstream feed's status (e.g. proxy quota, proxy 5xx) | `api.cors.syrins.tech` itself down or rate-limiting |
| `upstream_auth` | Upstream (Azure Function) responds 401/403, whether surfaced directly or wrapped by the proxy | Function key revoked/rotated |
| `invalid_json` | Body isn't parseable JSON (`format.js:38-45` already does this) | Feed returns an HTML error page through the proxy |
| `schema_mismatch` | Body parses but doesn't match the expected shape (`calls-list.js:83-85` already does this for the top-level `Events` array) | Feed changes its payload shape |

`fetchJson`'s current double-`JSON.parse` (`format.js:39-41`) is a real, observed quirk (the feed/proxy sometimes returns a JSON string containing JSON text) — the adapter must keep handling it, and it is not itself an error category; it's normalized away before validation.

Every one of these must resolve to "keep showing the last good snapshot, staleness-labeled" per `spec.md` §15 — none of them may blank the list if a prior snapshot exists. This already matches `calls-list.js`'s `hadExistingData` branch; the gap is only that today all six categories produce the same undifferentiated message.

## 2. Schema validation rules

Top level, required to accept the payload at all (failure here is `schema_mismatch`, fatal to the whole poll):

- `Events` — array. Anything else (missing, object, string) rejects the whole payload.
- `LastUpdated` — string. Used as the source timestamp (§3). Its absence doesn't invalidate the batch — it degrades to "source timestamp unknown, only local fetch time known" rather than failing closed, since the local timestamp is still meaningful on its own.

Per-event, evaluated after the top level passes. An individual malformed event is dropped and counted, not fatal to the batch — one bad row from an upstream ops system (already observed to have quirks like the double-JSON-encoding) should not take the whole board down:

- `EventNumber` — non-empty string. This is the cache/identity key (`calls-list.js:24,37`, `CACHE_FIELDS`); an event without one can't be cached, deduped, or targeted by `focusEvent`, so it's dropped.
- `Address`, `Community`, `EventType`, `ServiceArea` — strings (may be empty; downstream display already tolerates that).
- `DateTime` — string parseable by `parseFeedDate` (`format.js:5-8`); if `Date` parsing produces `Invalid Date`, drop the event rather than rendering `prettyTime`'s output as `Invalid Date`.
- `IsOpen` — present in some string/boolean form; only used for a CSS class today (`calls-list.js:203`), so a missing value degrades to "not open" rather than dropping the event.

Report a count of dropped events alongside the accepted ones (e.g. "42 calls (3 skipped — malformed)") rather than silently shrinking the list, so a real upstream data-quality problem is visible instead of looking like a quiet drop in call volume.

## 3. One-snapshot caching, timestamps, and stale/hide/purge

`spec.md` §12.431 already specifies this precisely; this section is that spec applied to the concrete fields this feed adapter has:

- **Two timestamps, both kept**: the feed's own `LastUpdated` (source timestamp) and the device's local time at the moment of a *successful* fetch (local timestamp). Only a successful, schema-valid response replaces the stored snapshot — a failed poll leaves both timestamps untouched.
- **One snapshot, replaced transactionally.** No history of prior payloads is kept (matches the current design: `this.setState({ events })` replaces the whole array on every successful `load()`; there is no accumulation).
- **Stale labeling**: immediately after any failed refresh (any category in §1), the currently-displayed snapshot must be visibly labeled non-live/stale — per `spec.md` §11.3, "when offline, show cached calls with their last-fetched timestamp and a prominent stale indicator." `calls-list.js` today calls `this.props.onError?.(error.message, hadExistingData)` but nothing currently renders a stale badge from that signal — this is a real gap between the contract and current code, to close when this ticket is implemented.
- **Hide window**: `spec.md` §12.432 and §19.550 propose 6 hours — past that, the snapshot is hidden behind an explicit "Show old snapshot" action rather than shown as if current.
- **Purge window**: proposed 24 hours — past that, the cached snapshot is deleted outright, not just hidden. These two numbers are marked "proposed... to validate" in `spec.md` and are formally an R5-start decision (`roadmap.md` §13, "Calls snapshot safety/retention windows"); this contract adopts them as the working default for R0/R1 design purposes, not as a final approved value.
- **Per-event cache purge (a real defect found here, not in `spec.md`)**: `annotateWithCache` (`calls-list.js:21-40`) writes one `localStorage` key per `EventNumber` ever seen and never deletes any of them — a browser profile that stays open across many polls accumulates one permanent key per historical call, unbounded. The one-snapshot rule in `spec.md` §12.431 ("replace the single snapshot transactionally; do not accumulate an event history") already forbids this. The fix belongs with the eventual localStorage migration work (`OFF-312`/`OFF-512`, already tracked in [`index-html-audit.md`](./index-html-audit.md)): on every successful poll, delete any cached per-event key whose `EventNumber` is not present in the fresh payload.

## 4. Production-safe credential and CORS design

**Current state** (`calls-list.js:55-72`): the Azure Function key (`this.apiKey`) is a literal in shipped source, appended as a `code` query parameter to the upstream URL, which is itself then URL-encoded as a query parameter to a third-party proxy (`https://api.cors.syrins.tech/?url=...`) that this project does not control, has no SLA with, and cannot audit the logs of.

**Finding, restated precisely**: the problem is not that a proxy exists — §0 already established that's structurally required. The problem is that this specific proxy is (a) a third party outside this project's control, and (b) doesn't hide the key from anyone or anything — it's visible in the page's shipped source to any reader, visible in the browser's own Network tab on every request, and visible to `api.cors.syrins.tech`'s own operators and any logging they do. URL-encoding a secret through a proxy changes its transport encoding, not its confidentiality — `spec.md` §13's own wording ("Encoding, minifying, or routing a secret through a third-party CORS proxy does not protect it") applies exactly here.

**Recommendation**: replace the third-party proxy with a small relay under this project's own control that holds the key server-side:

- A minimal serverless function (e.g. a Cloudflare Worker, free tier) on a domain/subdomain this project owns and can rotate/monitor independently of Surge. `spec.md`/`OFF-011`'s wording says "same-origin," but the actual bar in the R0 exit gate is narrower and is the one that matters: *"no secret recoverable from browser source, URLs, caches, or diagnostics."* A cross-origin relay that never ships the key to the client, and that sets `Access-Control-Allow-Origin` scoped to this project's real origin(s), satisfies that bar even though it isn't literally same-origin — same-origin was one sufficient way to get there, not the only one, and it isn't available on Surge's static-only hosting without a bigger hosting change.
- The Worker holds the Azure Function key as a server-side secret binding (never sent to or readable by the client), fetches the upstream feed, and returns the JSON body with permissive-but-scoped CORS headers.
- The relay should apply its own short server-side cache (on the order of the ~10-minute feed refresh cadence already observed in Group 3's snapshot capture) so it isn't hammering the upstream feed on every client poll and so the key is exercised less frequently than 1:1 with client requests.
- This relay is a new, separate piece of infrastructure this project would need to provision and maintain (an account with a serverless provider, a secret to rotate) — building it is out of scope for this contract and for Group 5 (which is written-contract-only per its own framing) and isn't currently ticketed anywhere in `roadmap.md`. It should get its own work item before it's built; this section records the design so that item has something concrete to implement against.
- Until that relay exists, the current third-party-proxy arrangement remains a known, explicitly-tracked gap — not a silent one. It should not be described as "production-safe" in any release checklist until it's replaced.

## 5. What this closes and what it doesn't

Against `todo.md`'s R0 exit gate:

- "Feed authentication failure, pack failure, storage failure, and permission failure have distinct contracts" — closed by §1 above.
- "The feed path has a production-safe credential/CORS design; no secret recoverable from browser source, URLs, caches, or diagnostics" — the *design* is recorded in §4; the actual relay is **not built**, so the current shipped app still leaks the key today. The exit-gate bullet asks for a design at R0, which this satisfies, but it should not be read as "the leak is fixed."

Not touched here, and not this ticket's job: implementing §1's error classes or §4's relay in `src/app/calls-list.js`, or the per-event cache purge in §3 (all future work, some already tracked under `OFF-312`/`OFF-512`).
