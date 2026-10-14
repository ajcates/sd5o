# UX/UI polish backlog — round 2

Status: Implemented and browser-verified 2026-10-14.
Scope: Same CSS/markup/component-sized constraint as [uxpolish.md](uxpolish.md) (that round is fully shipped). Triggered by specific pain points reported this round, confirmed against live screenshots at 390px (mobile) and 1280px (desktop).

## Items

- [x] **UXP2-001 — Separate sort controls from the location/permission button.** `.distance-actions` (index.html:852-858) puts `.sort-control`'s two buttons only 4px from the location/permission button, and both use similar primary-tinted active styling, so they read as one row of three interchangeable buttons. The sort-by-distance button sits disabled right next to "Use my location," inviting a mistap. Fix: widen the gap and/or add a visible divider between the sort group and the location action so they read as two distinct controls, not one row.

- [x] **UXP2-002 — Stop the brand-mark reading as a button.** `.brand-mark` (index.html:416-427) shares its rounded-square tile, gradient background, border, and shadow with `.icon-button` (index.html:534-549), the real action buttons. In the header it looks like the first of three tappable icons even though it's decorative (`aria-hidden`, no handler). Fix: drop the button-like chrome (shadow/border/elevation) from the brand-mark, or otherwise give it a visual language distinct from `.icon-button`, so only real actions look pressable.

- [x] **UXP2-003 — Anchor the external-map icon to something.** `.external-map-link` (index.html:1074-1091) is absolutely centered in the full-height `td.Address` cell, landing in empty space between the address and community lines with nothing visually tying it to either. Fix: anchor it near the top of the cell (next to the address title it acts on) instead of vertically centering it in the whole cell, or move it out of absolute positioning into the grid flow near the time/date.

- [x] **UXP2-004 — Decongest the card's first line.** Status pill, numbered badge, and address title all compete on one line (`.address-content`, index.html:1063-1068). Fix: give the numbered badge its own slot (e.g., overlapping the card's top-left corner as a chip) separate from the inline status pill, or combine them into one compact element.

- [x] **UXP2-005 — Label or hide the idle-distance ring.** The unlabeled grey ring shown when `locationStatus === "idle"` (calls-list.js:416, `.distance-unavailable.idle`) sits alone at the bottom-right of every card with no visible text, reading as a stray mark before the user has ever opted into location. Fix: either suppress it entirely until location has been requested once, or give it a short visible label instead of relying solely on the `aria-label`.

- [x] **UXP2-006 — Make the call-type divider span the full card.** The `border-top` above `td.EventType` (index.html:1425-1433, mobile media query) only runs under the left grid column, not the card's full width, so it looks like a layout bug rather than an intentional rule. Fix: extend the divider across both grid columns.

- [x] **UXP2-007 — Give the search toggle a persistent active state.** `SearchToggle.render()` (src/app/search-toggle.js:26-45) only ever renders a plain `.icon-button`; it never adds `.active` the way `MapView.updateToggleState()` (map-view.js:155-161) does for the adjacent map toggle, even though `.icon-button.active` is already styled (index.html:569-574) and sitting right next to it. `aria-expanded` changes but nothing visible does, so the two buttons in the same row behave inconsistently. Fix: toggle `.active` on the search button the same way the map toggle does.

- [x] **UXP2-008 — Stop the Distance column from being a wall of identical unlabeled circles.** Confirmed on the desktop table: before location is enabled, every row's Distance cell shows the same faint unlabeled "○" (`unavailableDistanceMarkup()`, calls-list.js:414-425), for all rows, with no text anywhere in the column. It reads as a broken or empty column rather than "distance available once you share your location." Related to UXP2-005's mobile-card version of the same glyph, but the desktop manifestation (a whole column of repeated noise) likely wants its own fix — e.g., a one-time inline prompt in the column header instead of repeating the glyph on every row.

## Suggested order

1. UXP2-001, UXP2-002, UXP2-007 — isolated, low-risk CSS/markup-only fixes.
2. UXP2-003, UXP2-006 — mobile card layout fixes, test together since both touch `td.Address`/mobile grid.
3. UXP2-004, UXP2-005, UXP2-008 — card/table content and legibility, slightly more involved (touches markup + JS-rendered labels), test together since 005 and 008 touch the same `unavailableDistanceMarkup()`.

## Completion check for each item

- Verify at 320px, 390px, and desktop widths (desktop table layout is unaffected by UXP2-003/004/005/006, which are mobile-card-only).
- Confirm `.icon-button` vs brand-mark are now visually distinguishable (UXP2-002) without changing real button styling.
- Run `npm run test:unit`, `npm run test:e2e`, and a focused Chromium screenshot diff at 390px.

## Implementation verification

- `npm run test:unit`: 64/64 passing.
- `npm run test:e2e`: live feed loaded, 17 real calls geocoded into markers, no page errors (one raced CORS proxy's expected console error, same as pre-existing behavior).
- Fresh Chromium screenshots at 390px and 1280px confirmed: distance-actions now has a visible 14px gap separating the sort group from the location button; the brand-mark renders as a flat circle clearly distinct from the two real icon-buttons beside it; the search toggle now shows the same `.active` highlight as the map toggle when open; the row-number badge sits pinned at each mobile card's top-left corner instead of competing inline with the status pill; the external-map icon is anchored to the title line instead of floating centered in the cell; the idle-distance glyph is gone entirely (mobile cards and the desktop Distance column are now clean/empty instead of repeating an unlabeled "○"); the call-type divider spans the full mobile card width.
- UXP2-005 and UXP2-008 were resolved by one shared code change (`unavailableDistanceMarkup()` in calls-list.js), since the repeated-glyph problem was identical on mobile cards and the desktop column.
