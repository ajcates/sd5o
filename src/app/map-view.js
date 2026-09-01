import { Component, html } from "../framework/core.js";
import { geocode } from "../offgeo/geocoder.js";
import { ageMinutes } from "./format.js";
import { loadLeaflet } from "./leaflet-loader.js";
import { eventTypeColor, eventTypeCategoryName } from "./event-category.js";

const OPEN_ANIMATION_MS = 340;
const NO_PULSE_AFTER_MINUTES = 120;

function prefersReducedMotion() {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

function mapMotionOptions(options = {}) {
  return { ...options, animate: !prefersReducedMotion() };
}

// OpenStreetMap's tile server, fetched live from the visitor's own
// browser -- a different usage pattern from bulk-mirroring tiles as
// static files (which the earlier custom road-line-only map explicitly
// avoided, see notes/offgeo/map-prototype.md), acceptable at this
// project's low request volume under OSM's tile usage policy
// (https://operations.osmfoundation.org/policies/tiles/). A deliberate
// trade-off, not an oversight: this makes map tiles a live, non-private,
// non-offline-capable dependency (every open of the map panel requests
// tiles from osm.org, and the map can't render at all with the pack's
// own network unavailable) -- accepted in exchange for a real,
// recognizable basemap instead of hand-drawn road lines with no
// context. Attribution below is required by OSM's ODbL license, not
// optional styling.
const OSM_TILE_URL = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
const OSM_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

/** Age -> pulse animation parameters. Newer calls pulse faster, bigger,
 * and more opaquely; the effect fades out and stops entirely once a call
 * is old enough that highlighting it as "fresh" would be misleading. */
function pulseParamsForAge(minutes) {
  const clamped = Math.min(Math.max(minutes, 0), NO_PULSE_AFTER_MINUTES);
  if (clamped >= NO_PULSE_AFTER_MINUTES) return null;
  const t = clamped / NO_PULSE_AFTER_MINUTES; // 0 = brand new, 1 = at the cutoff
  return {
    duration: (0.9 + t * 2.6).toFixed(2), // 0.9s -> 3.5s
    scale: (2.6 - t * 1.1).toFixed(2), // 2.6x -> 1.5x
    opacity: (0.65 - t * 0.35).toFixed(2), // 0.65 -> 0.30
  };
}

/** Owns the slide-down map panel: a Leaflet map on a live OpenStreetMap
 * tile basemap, one marker per geocodable call with an age-scaled
 * pulse, and tap-to-select wired back to the calls table via
 * props.onSelectEvent.
 *
 * Leaflet and the real OffGeo pack (../offgeo/geocoder.js, used only
 * for geocoding here -- road-line/label rendering was removed once a
 * real tile basemap made it redundant) are loaded lazily on first
 * open, not on page load -- most visits won't open the map, and the
 * pack alone is ~10MB gzip.
 *
 * This component deliberately never re-renders after its first mount: a
 * second `render()` call would replace #map-canvas and destroy the live
 * Leaflet instance. Every later state change (open/close, marker updates)
 * is an imperative method that touches the Leaflet map directly, the same
 * pattern CallsList already uses for its own filter/map-expand methods
 * that can't go through a full rebuild either. */
export class MapView extends Component {
  onCreate() {
    this.isOpen = false;
    this.hasInitializedMap = false;
    this.leafletMap = null;
    this.markersLayer = null;
    this.locationLayer = null;
    this.latestEvents = [];
    this.userLocation = null;
    this.selectedEventNumber = null;
    this.markerByEventNumber = new Map();
    this.markersBounds = null;
    this.hasFitInitialMarkers = false;
    this.legendOpen = false;
    this.noticeTimeout = null;

    this.toggleButton = document.createElement("button");
    this.toggleButton.type = "button";
    this.toggleButton.className = "icon-button";
    this.toggleButton.title = "Map view";
    this.toggleButton.setAttribute("aria-label", "Map view");
    this.toggleButton.setAttribute("aria-expanded", "false");
    this.toggleButton.innerHTML = `
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 2C8.14 2 5 5.14 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.86-3.14-7-7-7Zm0 9.5A2.5 2.5 0 1 1 12 6.5a2.5 2.5 0 0 1 0 5Z"/>
      </svg>
    `;
    this.toggleButton.addEventListener("click", () => this.toggle());
    document.getElementById(this.props.buttonsContainerId).appendChild(this.toggleButton);
    this.updateToggleState();
  }

  render() {
    return html`
      <div id="map-canvas"></div>
      <button type="button" class="map-help-button" data-on-click="toggleLegend" aria-label="Show map legend" aria-expanded="false" title="Map legend">?</button>
      <div class="map-legend hidden" role="note">
        <strong>Map symbols</strong>
        <span><i class="legend-call"></i>Fill color shows call type</span>
        <span><i class="legend-open"></i>Red ring means open</span>
        <span><i class="legend-selected"></i>Blue center means selected</span>
        <span><i class="legend-user"></i>Hollow blue ring is you</span>
      </div>
      <div class="map-notice" role="status" aria-live="polite"></div>
    `;
  }

  toggleLegend() {
    this.legendOpen = !this.legendOpen;
    const button = this.root.querySelector(".map-help-button");
    const legend = this.root.querySelector(".map-legend");
    button?.setAttribute("aria-expanded", String(this.legendOpen));
    button?.setAttribute("aria-label", this.legendOpen ? "Hide map legend" : "Show map legend");
    legend?.classList.toggle("hidden", !this.legendOpen);
  }

  showNotice(message) {
    const notice = this.root.querySelector(".map-notice");
    if (!notice) return;
    notice.textContent = message;
    notice.classList.add("visible");
    clearTimeout(this.noticeTimeout);
    this.noticeTimeout = setTimeout(() => notice.classList.remove("visible"), 3200);
  }

  toggle() {
    if (this.isOpen) this.close();
    else this.open();
  }

  open() {
    if (this.isOpen) return;
    this.isOpen = true;
    this.root.classList.add("open");
    this.updateToggleState();

    this.ensureMapInitialized().then(() => {
      setTimeout(() => this.leafletMap.invalidateSize(), OPEN_ANIMATION_MS);
    });
  }

  close() {
    if (!this.isOpen) return;
    this.isOpen = false;
    this.root.classList.remove("open");
    this.updateToggleState();
  }

  updateToggleState() {
    this.toggleButton.classList.toggle("active", this.isOpen);
    this.toggleButton.setAttribute("aria-expanded", String(this.isOpen));
    this.toggleButton.setAttribute("aria-pressed", String(this.isOpen));
    this.toggleButton.title = this.isOpen ? "Close map" : "Map view";
    this.toggleButton.setAttribute("aria-label", this.isOpen ? "Close map" : "Map view");
  }

  /** Called when a calls-table row is tapped (replaces the old per-row
   * Google Maps iframe embed, which made a request to Google on every
   * expand -- see calls-list.js's selectRow). Opens the map if it's
   * closed, waits for Leaflet + the event's marker to exist, then pans/
   * zooms to it. When the list is sorted by distance, the fitted view
   * includes both that call and the user's location instead.
   *
   * Not every call has a marker -- v0's geocoder has no fallback beyond
   * an exact street-name/range match (see pack-engine.js), so some real
   * addresses turn up nothing. Silently leaving the map wherever it was
   * for those taps looked like a bug (reported live: "the call in view
   * is exactly one call away from the one it should be") -- the map
   * wasn't off by one, it just hadn't moved and was still showing
   * whichever call was focused *before*. Resetting to the all-markers
   * overview instead makes the "no location available for this call"
   * case honest rather than silently wrong-looking. */
  async focusEventOnMap(eventNumber, { includeUserLocation = false } = {}) {
    this.setSelectedEvent(eventNumber);
    const wasOpen = this.isOpen;
    this.open();
    await this.ensureMapInitialized();
    if (!wasOpen) {
      // Let the panel's open transition (and invalidateSize inside it)
      // settle before panning -- fitBounds/setView on a still-collapsed
      // container computes the wrong viewport.
      await new Promise((resolve) => setTimeout(resolve, OPEN_ANIMATION_MS));
      this.leafletMap.invalidateSize();
    }
    const marker = this.markerByEventNumber.get(eventNumber);
    if (!marker) {
      if (this.markersBounds) this.leafletMap.fitBounds(this.markersBounds, mapMotionOptions({ padding: [24, 24], maxZoom: 14 }));
      this.showNotice("Map location unavailable for this call.");
      return;
    }
    this.showSelectionPing(marker);
    if (includeUserLocation && this.userLocation) {
      const L = window.L;
      const focusBounds = L.latLngBounds([
        marker.getLatLng(),
        [this.userLocation.latitude, this.userLocation.longitude],
      ]);
      this.leafletMap.fitBounds(focusBounds, mapMotionOptions({ padding: [38, 38], maxZoom: 16 }));
      return;
    }
    this.leafletMap.setView(marker.getLatLng(), 16, mapMotionOptions());
  }

  /** Keep exactly one call marker visibly selected. The state is stored
   * independently from Leaflet's current DOM so it survives a marker
   * refresh and is applied again when new marker elements are built. */
  setSelectedEvent(eventNumber) {
    this.selectedEventNumber = eventNumber;
    for (const [number, marker] of this.markerByEventNumber) {
      marker.getElement()?.querySelector(".call-marker")?.classList.toggle("selected", number === eventNumber);
    }
  }

  showSelectionPing(marker) {
    if (prefersReducedMotion()) return;
    const markerElement = marker.getElement()?.querySelector(".call-marker");
    if (!markerElement) return;
    markerElement.classList.remove("selection-ping");
    void markerElement.offsetWidth;
    markerElement.classList.add("selection-ping");
    setTimeout(() => markerElement.classList.remove("selection-ping"), 650);
  }

  /** Location is acquired by main.js only after the user presses the
   * explained "Use my location" action. MapView receives the in-memory
   * reading for its marker but never requests or persists coordinates. */
  setUserLocation(coords) {
    this.userLocation = coords;
    if (this.locationLayer) this.showUserLocation(coords);
  }

  clearUserLocation() {
    this.userLocation = null;
    this.locationLayer?.clearLayers();
  }

  showUserLocation(coords) {
    if (!this.locationLayer) return;
    const L = window.L;
    this.locationLayer.clearLayers();

    const { latitude, longitude, accuracy } = coords;
    if (accuracy) {
      L.circle([latitude, longitude], {
        radius: accuracy,
        color: "#4d9dff",
        fillColor: "#4d9dff",
        fillOpacity: 0.12,
        weight: 1,
        interactive: false,
      }).addTo(this.locationLayer);
    }
    const icon = L.divIcon({
      className: "",
      html: `<span class="user-location-marker"></span>`,
      iconSize: [22, 22],
      iconAnchor: [11, 11],
    });
    L.marker([latitude, longitude], { icon, title: "Your location", interactive: false, zIndexOffset: 1000 }).addTo(
      this.locationLayer
    );
  }

  async ensureMapInitialized() {
    if (this.hasInitializedMap) return;
    this.hasInitializedMap = true;

    const L = await loadLeaflet();
    const canvas = this.root.querySelector("#map-canvas");
    this.leafletMap = L.map(canvas, { attributionControl: false, zoomAnimation: !prefersReducedMotion() }).setView(
      [32.9, -117.0],
      9,
      mapMotionOptions()
    );
    L.tileLayer(OSM_TILE_URL, { attribution: OSM_ATTRIBUTION, maxZoom: 19 }).addTo(this.leafletMap);
    L.control.attribution({ prefix: "Leaflet" }).addTo(this.leafletMap);
    this.markersLayer = L.layerGroup().addTo(this.leafletMap);
    this.locationLayer = L.layerGroup().addTo(this.leafletMap);
    if (this.userLocation) this.showUserLocation(this.userLocation);

    await this.updateMarkers(this.latestEvents, { fitOverview: true });
  }

  /** Called by main.js whenever CallsList loads a fresh batch of events.
   * Cached even while the panel is closed so opening it doesn't need to
   * wait on a fresh feed fetch. Only the first populated marker set gets
   * an automatic overview; later feed refreshes rebuild markers in place
   * without changing the user's current center or zoom. */
  setEvents(events) {
    this.latestEvents = events;
    if (this.hasInitializedMap) {
      this.updateMarkers(events, { fitOverview: !this.hasFitInitialMarkers });
    }
  }

  async updateMarkers(events, { fitOverview = false } = {}) {
    if (!this.markersLayer) return;
    const L = window.L;
    this.markersLayer.clearLayers();
    this.markerByEventNumber.clear();

    const geocoded = await Promise.all(
      events.map(async (event) => {
        const point = await geocode(event.Address);
        return point ? { event, point } : null;
      })
    );

    const fitBoundsPoints = [];
    for (const item of geocoded) {
      if (!item) continue;
      const { event, point } = item;
      const marker = this.buildMarker(L, event, point);
      marker.addTo(this.markersLayer);
      this.markerByEventNumber.set(event.EventNumber, marker);
      fitBoundsPoints.push([point.lat, point.lon]);
    }
    this.markersBounds = fitBoundsPoints.length ? L.latLngBounds(fitBoundsPoints) : null;
    if (this.markersBounds && fitOverview) {
      this.leafletMap.fitBounds(this.markersBounds, mapMotionOptions({ padding: [24, 24], maxZoom: 14 }));
      this.hasFitInitialMarkers = true;
    }
  }

  /** Marker fill color encodes the call's dispatch category (see
   * event-category.js), matching the same category's left-edge color in
   * the calls table (calls-list.js) so a color means the same thing in
   * both places. Open/closed status, previously the marker's own color,
   * now shows as the ring around it instead so neither signal is lost. */
  buildMarker(L, event, point) {
    const pulse = pulseParamsForAge(ageMinutes(event.DateTime));
    const colorVar = eventTypeColor(event.EventType);
    const pulseStyle = pulse
      ? `--pulse-duration:${pulse.duration}s;--pulse-scale:${pulse.scale};--pulse-opacity:${pulse.opacity}`
      : "";
    const icon = L.divIcon({
      className: "",
      html: `<span class="call-marker${pulse ? " pulsing" : ""}${event.IsOpen ? " open" : ""}${
        event.EventNumber === this.selectedEventNumber ? " selected" : ""
      }" style="--marker-color:${colorVar};${pulseStyle}"></span>`,
      iconSize: [14, 14],
      iconAnchor: [7, 7],
    });
    const marker = L.marker([point.lat, point.lon], {
      icon,
      title: `${eventTypeCategoryName(event.EventType)} · ${event.Address}, ${event.Community}`,
      alt: event.EventType,
    });
    marker.on("click", () => {
      this.setSelectedEvent(event.EventNumber);
      this.showSelectionPing(marker);
      this.props.onSelectEvent?.(event.EventNumber);
    });
    return marker;
  }
}
