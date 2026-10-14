# Material Expressive pass

Status: Implemented and browser-verified 2026-10-14.
Direction: Full expressive push — springy/bouncy motion replacing flat easing, shape-morphing on key interactive elements, bolder surface shapes — while deliberately leaving legibility-critical, data-dense elements (table/card rows) alone. This is a public-safety data feed; playfulness goes on chrome and feedback, not on the calls themselves.
Scope: CSS/markup-level only, same constraint as the uxpolish rounds. Touches index.html (CSS), map-view.js (legend reveal), calls-list.js (location-detail-panel reveal).

## Motion tokens (foundation for everything below)

- [x] **ME-001 — Add expressive easing tokens.** Replace `--ease-emphasized` (used only by the map-panel/search-bar height transitions) with two purpose-built tokens: `--ease-bounce: cubic-bezier(0.34, 1.56, 0.64, 1)` for small interactive feedback (button press/release, selection), and `--ease-spring: cubic-bezier(0.175, 0.885, 0.32, 1.4)` for larger surface entrances/exits (panels, cards). `--ease-standard` stays for color/background swaps, where overshoot would look like a rendering glitch rather than a bounce.

## Taps & selection

- [x] **ME-002 — Shape-morph the primary location FAB.** `.distance-tool-button.primary` goes from a circle (idle) to a rounded-square (`.busy`, while locating) with an animated `border-radius` transition — a direct nod to Material Expressive's FAB shape-morph pattern, and a free signal ("something is actively happening") beyond the existing spin.
- [x] **ME-003 — Bouncier press feedback everywhere a button exists.** `.icon-button`, `.map-help-button`, `.sort-control button`, `.distance-tool-button`, and `.feed-summary` currently either have flat `ease-standard` transforms or (for the sort/distance-tool buttons) no press feedback at all. Give all of them a `transform` transition on `--ease-bounce` and an explicit `:active` scale-down, so every tap visibly squishes and springs back.
- [x] **ME-007 — Bigger, springier selection feedback.** `selected-marker-ping` and `selected-row-flash` currently use `--ease-standard`; switch both to `--ease-bounce` and deepen the peak (marker scale 1.32→1.42, row-flash peak opacity 0.26→0.32) so selecting a call is more felt, not just technically visible.

## Panel transitions

- [x] **ME-004 — Animate the map-legend and location-detail-panel reveals.** Both currently hard-toggle via the generic `.hidden` (`display:none`, no transition possible). Give each its own pop-in keyframe (`opacity`/`translateY`/`scale`) on `--ease-spring`, re-triggered on each open the same way `MapView.showSelectionPing` already re-triggers `.selection-ping` (remove class, force reflow, re-add) since `.map-legend` is a long-lived DOM node that never re-renders.
- [x] **ME-005 — Springier, bigger panel surfaces.** Switch the map-panel/search-bar height transitions from the old `--ease-emphasized` to `--ease-spring`. Bump `.map-panel`/`.leaflet-container` corner radius 14px→20px to match Expressive's bolder large-surface shape scale.

## Loading & status

- [x] **ME-008 — Give the loading state and status dot more personality.** The three loading skeleton bars currently just shimmer in place with no entrance; add a staggered bounce-in pop (`scaleX` 0.4→1) on `--ease-bounce`, ~70ms apart, so they visibly cascade in rather than appearing instantly. Switch the status-dot's loading pulse ring from `--ease-standard` to `--ease-bounce`, and add a subtle breathing scale to the dot itself during loading.

## Shape language

- [x] **ME-006 — Bouncier entrance choreography.** `app-bar-enter`, `surface-enter` (status-panel, #listing), and `row-enter` currently animate in on flat `--ease-standard`. Switch to `--ease-spring` (surfaces) / `--ease-bounce` (rows), and widen the per-row stagger slightly (16ms→22ms step, 220ms→260ms cap) so the list's cascade-in reads more clearly.
- [x] **ME-009 — Selective shape accents on framing surfaces, not data rows.** Bump `#listing`/`.status-panel` corner radius 14px→18px (these are single large surfaces, not repeated dense rows). Make `.map-help-button` fully circular (50%) to match the already-circular brand-mark and location FAB, reinforcing "small round accent = helper/identity element" as a consistent shape language. Mobile call cards and the desktop table explicitly keep their current radius/shape — legibility of a public-safety feed takes priority over playfulness there.

## Completion check

- Verify `@media (prefers-reduced-motion: reduce)` still collapses every new animation/transition to ~1ms (the existing blanket rule already covers any `animation`/`transition` property, so no new motion should need its own reduced-motion override).
- Run `npm run test:unit` and `npm run test:e2e`.
- Re-screenshot mobile (390px) and desktop (1280px): header buttons, distance-controls/FAB morph, loading state, a triggered selection (row + marker), and the map legend/location-detail reveal.

## Implementation verification

- `npm run test:unit`: 64/64 passing.
- `npm run test:e2e`: live feed loaded, real calls geocoded into markers, no page errors.
- Fresh Chromium screenshots at 390px confirmed: the location FAB visibly morphs from a circle (idle) to a rounded square (`.busy`); `.map-panel`/`#listing`/`.status-panel` render with the bigger 18-20px radii; row selection, the distance toolbar, and the auto-open-map-on-row-tap behavior all still work correctly with the new motion/shape CSS in place.
- The legend/location-detail pop-in (ME-004) and the various press/selection bounce effects (ME-003/ME-007) are motion-only and don't show up in a static screenshot; verified by code review instead -- the re-trigger pattern for `.map-legend` mirrors `MapView.showSelectionPing`'s already-proven remove/reflow/re-add approach, and all new transitions/animations fall under the existing blanket `prefers-reduced-motion` override.
