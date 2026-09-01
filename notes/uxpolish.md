# UX/UI polish backlog

Status: Implemented and browser-verified 2026-09-01
Scope: The current calls list, status/search controls, compact distance toolbar, and Leaflet map. These items should remain CSS/markup/component-sized changes; larger data, offline, geocoder, and pack-management work stays in the OffGeo roadmap.

## Highest-value quick wins

- [x] **UXP-001 — Make the whole call card select the call.** The address currently acts as a large external Google Maps link while the rest of the card selects the call, so two visually similar taps do different things. Make card tap consistently select the call and move external maps to a small, labeled launch icon. **Done when:** tapping address text and call type selects the same event; only the launch icon opens an external map.

- [x] **UXP-002 — Make call rows keyboard-selectable.** Add an appropriate interactive role, `tabindex="0"`, and Enter/Space handling. The existing `:focus-visible` style then becomes reachable instead of dead CSS. **Done when:** every visible row can be selected without a pointer and its external-map action remains separately reachable.

- [x] **UXP-003 — Keep the selected list card subtly selected.** The map's blue center dot persists, but the row highlight disappears after two seconds. Keep a low-intensity selected state until another call is selected; retain the brighter two-second flash for initial confirmation. **Done when:** list and map always identify the same selected event.

- [x] **UXP-004 — Increase closed-call readability.** Closed rows are faded even though they already have a Closed badge and map-ring treatment, making text unnecessarily dim on the black theme. Raise their opacity while keeping a smaller visual distinction from open calls. **Done when:** closed address, time, and call type meet normal-text contrast without being confused with open calls.

- [x] **UXP-005 — Show a real no-search-results state.** A filter with zero matches currently leaves an empty area and only changes the count. Render a compact message such as “No calls match this search” with a Clear search action. **Done when:** zero matches never look like a loading or feed failure.

- [x] **UXP-006 — Explain calls with no map point.** Selecting an unmatched address currently resets to the overview without explaining why. Show a short non-blocking message: “Map location unavailable for this call.” **Done when:** the overview reset cannot be mistaken for the wrong marker being selected.

- [x] **UXP-007 — Preserve the compact toolbar while enlarging touch targets.** The 44 px distance row is appropriately compact, but its 30 px icon buttons are small for touch. Use 36–40 px hit regions with tightly sized glyphs and spacing, without increasing the toolbar beyond one row. **Done when:** the bar stays one line at 320 px width and each action has a comfortable touch target.

- [x] **UXP-008 — Surface compact location errors on touch devices.** The toolbar currently relies on `title` text for the full denied/timeout/unavailable explanation, which is not discoverable on most phones. Let tapping the Unavailable state reveal the reason and retry guidance. **Done when:** permission denial and timeout recovery are understandable without hover.

## Useful visual and interaction polish

- [x] **UXP-009 — Add an explicit refresh glyph to the feed status.** The incident-feed status is tappable but resembles passive status text. Add a small refresh icon and pressed/loading treatment without making the card taller. **Done when:** first-time users can identify it as an action before tapping.

- [x] **UXP-010 — Give the map toggle a persistent active state.** In addition to `aria-expanded`, visually distinguish the map button while the panel is open and change its tooltip to “Close map.” **Done when:** the toggle's visual and accessible states agree.

- [x] **UXP-011 — Rename technical table headings.** On desktop, change `DateTime` to `Time` and `EventType` to `Call type`. **Done when:** headings use reader-facing language while data fields remain unchanged internally.

- [x] **UXP-012 — Suppress the first-load wall of New badges.** A fresh profile can mark every current call as New, which dilutes the signal. Establish the initial snapshot silently and show New only for calls first observed after that baseline. **Done when:** New reliably means added since the visitor's initial successful load.

- [x] **UXP-013 — Distinguish unmatched distance from inactive location.** The same em dash covers an unmatched call, location not enabled, and distance still calculating. Use accessible state-specific labels and optionally a tiny muted status glyph. **Done when:** assistive text describes the actual reason for every missing distance.

- [x] **UXP-014 — Announce sort changes.** Update a polite live region with “Sorted by nearest” or “Sorted by newest,” especially because the compact icon toolbar has no persistent text labels. **Done when:** keyboard and screen-reader users receive confirmation without moving focus.

- [x] **UXP-015 — Honor reduced motion in Leaflet operations.** CSS animations already respect `prefers-reduced-motion`, but Leaflet `setView`/`fitBounds` calls still request animation. Disable animated pan/zoom when reduced motion is requested. **Done when:** opening or selecting a call produces no animated map movement under the preference.

- [x] **UXP-016 — Make selected markers clearer without changing category color.** Retain the requested tiny blue center dot, but add a very subtle one-time halo or scale bump on selection so it can be found among dense nearby markers. **Done when:** selection is noticeable in a crowded cluster and settles back to the normal marker size quickly.

## Optional finishing touches

- [x] **UXP-017 — Add a compact map legend/help button.** Explain marker fill = call category, ring = open/closed, blue center = selected, and hollow blue ring = user. Keep it collapsed by default. **Done when:** marker encodings are understandable without adding permanent map clutter.

- [x] **UXP-018 — Use a viewport-relative map height on short phones.** Replace the fixed 360 px mobile height with a bounded `vh`/`dvh` value so the selected card still has useful space below it. **Done when:** 320×568 and landscape layouts show both usable map controls and at least part of one call card.

- [x] **UXP-019 — Add a visible clear-search control.** Do not rely only on the browser's native search-field clear affordance, which varies by platform. **Done when:** clearing search is consistent in installed PWA and browser modes.

- [x] **UXP-020 — Pause the one-second refresh-age repaint while hidden.** The counter does not need to re-render every second in a background tab. Resume and immediately reconcile when the page becomes visible. **Done when:** the displayed age stays correct while background work is reduced.

## Additional improvement found while implementing

- [x] **UXP-021 — Remove accidental scroll-to-top feed refreshes.** The previous scroll listener treated any return to the top of the page—including programmatic selection scrolling—as a refresh gesture, which could create duplicate requests and reset feedback unexpectedly. Feed refresh is now limited to the explicit, labeled incident-feed action. **Done when:** normal scrolling and call-selection scrolling never issue a feed request.

## Implementation verification

- `npm run test:unit`: 64/64 passing.
- `npm run test:e2e`: live feed loaded, 12 live calls geocoded into markers, with no console or page errors.
- Focused Chromium checks at 390 px and 320×568 covered first-load New suppression, search/no-results/clear, keyboard and persistent selection, external-map isolation, missing-map messaging, the active map toggle, the legend, 36 px toolbar hit targets in a 44 px row, nearest sorting, user-plus-call map fitting, viewport preservation across feed refresh, reduced motion, and selected-row positioning below the sticky map.

## Suggested implementation order

1. UXP-001, UXP-002, UXP-004, UXP-005, UXP-006
2. UXP-007, UXP-008, UXP-009, UXP-010, UXP-014
3. UXP-003, UXP-011, UXP-012, UXP-013, UXP-015
4. UXP-016 through UXP-020 as optional finishing work

## Completion check for each item

- Verify at 320 px, 390 px, and desktop widths.
- Exercise pointer and keyboard behavior where applicable.
- Check accessible names, focus visibility, and live announcements.
- Run `git diff --check`, `npm run test:unit`, and the focused Chromium interaction path affected by the change.
- Keep the live feed, location, sorting, selected-marker, and map-refresh behavior unchanged unless the item explicitly modifies it.
