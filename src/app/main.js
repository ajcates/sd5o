import { mount } from "../framework/core.js";
import { StatusPanel } from "./status-panel.js";
import { CallsList } from "./calls-list.js";
import { SearchToggle } from "./search-toggle.js";
import { MapView } from "./map-view.js";

/** App bootstrap. Replaces the inline <script> previously in index.html
 * (index.html:927-1581, see notes/offgeo/index-html-audit.md). Wires the
 * three components together with plain callback props -- no global store,
 * this app is small enough that explicit wiring here is clearer than
 * adding one. The dead Nearby/geocoder feature (index.html:952-1107) is
 * deliberately not ported; see the audit for why. */
function boot() {
  const statusPanel = mount(StatusPanel, document.getElementById("status-panel"), {});

  const mapView = mount(MapView, document.getElementById("map-panel"), {
    buttonsContainerId: "map-toggle-slot",
    onSelectEvent: (eventNumber) => callsList.focusEvent(eventNumber),
  });

  const callsList = mount(CallsList, document.getElementById("listing"), {
    onLoadingStart: () => statusPanel.setLoading(),
    onLoaded: ({ rawTime, count, events }) => {
      statusPanel.setLive({ rawTime, eventCountText: `${count} call${count === 1 ? "" : "s"}` });
      mapView.setEvents(events);
    },
    onError: (message, hadExistingData) => statusPanel.setError(message, hadExistingData),
    onEventCount: (text) => statusPanel.setEventCount(text),
    onRowTap: (event) => mapView.focusEventOnMap(event.EventNumber),
  });

  mount(SearchToggle, document.getElementById("search-toggle-slot"), {
    searchBarId: "search-bar",
    filterInputId: "filter",
  });

  const filterInput = document.getElementById("filter");
  filterInput.addEventListener("input", () => callsList.setFilter(filterInput.value));
  filterInput.addEventListener("change", () => callsList.setFilter(filterInput.value));

  callsList.load();

  setInterval(() => statusPanel.refreshRelativeTime(), 60000);

  let lastScrollY = window.scrollY;
  window.addEventListener(
    "scroll",
    () => {
      const currentScrollY = window.scrollY;
      if (currentScrollY === 0 && lastScrollY > 0) {
        callsList.refresh();
      }
      lastScrollY = currentScrollY;
    },
    { passive: true }
  );

  observeHeaderHeight();
  registerServiceWorker();
}

/** Keeps --header-height in sync with .app-header's real (sticky, but
 * variable -- the search bar's open/closed state changes it) rendered
 * height, so the sticky .map-panel below it (index.html) can sit flush
 * under the header instead of at a hardcoded offset that would either
 * gap or overlap depending on search-bar state. */
function observeHeaderHeight() {
  const header = document.querySelector(".app-header");
  if (!header || !("ResizeObserver" in window)) return;
  const sync = () => document.documentElement.style.setProperty("--header-height", `${header.offsetHeight}px`);
  new ResizeObserver(sync).observe(header);
  sync();
}

async function registerServiceWorker() {
  if ("serviceWorker" in navigator) {
    try {
      await navigator.serviceWorker.register("serviceworker.js");
    } catch (error) {
      console.log("SW registration failed", error);
    }
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot);
} else {
  boot();
}
