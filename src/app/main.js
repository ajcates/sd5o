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
  const statusPanel = mount(StatusPanel, document.getElementById("status-panel"), {
    onRefresh: () => callsList.refresh(),
  });
  let locationRequestId = 0;

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
    onFilterChange: (value) => syncSearchControls(value),
    onRowTap: async (event, { sortMode }) => {
      await mapView.focusEventOnMap(event.EventNumber, { includeUserLocation: sortMode === "distance" });
      callsList.focusEvent(event.EventNumber);
    },
    onRequestLocation: requestUserLocation,
    onStopLocation: stopUsingLocation,
  });

  function requestUserLocation() {
    const requestId = ++locationRequestId;
    callsList.setLocationPending();
    if (!("geolocation" in navigator)) {
      callsList.setLocationUnavailable("Location is not supported by this browser.");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        if (requestId !== locationRequestId) return;
        const coords = {
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracy: position.coords.accuracy,
          timestamp: position.timestamp,
        };
        callsList.setUserLocation(coords);
        mapView.setUserLocation(coords);
      },
      (error) => {
        if (requestId !== locationRequestId) return;
        const message =
          error.code === 1
            ? "Location permission was denied. Allow location for this site, then try again."
            : error.code === 3
              ? "Location timed out. Try again where your device has a clearer signal."
              : "Your location is currently unavailable. Please try again.";
        callsList.setLocationUnavailable(message);
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 }
    );
  }

  function stopUsingLocation() {
    locationRequestId += 1;
    callsList.clearUserLocation();
    mapView.clearUserLocation();
  }

  mount(SearchToggle, document.getElementById("search-toggle-slot"), {
    searchBarId: "search-bar",
    filterInputId: "filter",
  });

  const filterInput = document.getElementById("filter");
  const clearFilterButton = document.getElementById("clear-filter");
  function syncSearchControls(value) {
    clearFilterButton.classList.toggle("visible", Boolean(value));
  }
  function applyFilter() {
    callsList.setFilter(filterInput.value);
    syncSearchControls(filterInput.value);
  }
  filterInput.addEventListener("input", applyFilter);
  filterInput.addEventListener("change", applyFilter);
  clearFilterButton.addEventListener("click", () => callsList.clearFilter());

  callsList.load();

  let relativeTimeTimer = null;
  const startRelativeTimeTimer = () => {
    if (relativeTimeTimer || document.hidden) return;
    relativeTimeTimer = setInterval(() => statusPanel.refreshRelativeTime(), 1000);
  };
  const stopRelativeTimeTimer = () => {
    clearInterval(relativeTimeTimer);
    relativeTimeTimer = null;
  };
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stopRelativeTimeTimer();
    else {
      statusPanel.refreshRelativeTime();
      startRelativeTimeTimer();
    }
  });
  startRelativeTimeTimer();

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
