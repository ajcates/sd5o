import { Component, html } from "../framework/core.js";
import { geocode } from "../offgeo/geocoder.js";
import { ageMinutes } from "./format.js";
import { loadLeaflet } from "./leaflet-loader.js";

const OPEN_ANIMATION_MS = 340;
const NO_PULSE_AFTER_MINUTES = 120;

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
    this.markerByEventNumber = new Map();

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
  }

  render() {
    return html`<div id="map-canvas"></div>`;
  }

  toggle() {
    if (this.isOpen) this.close();
    else this.open();
  }

  open() {
    if (this.isOpen) return;
    this.isOpen = true;
    this.root.classList.add("open");
    this.toggleButton.setAttribute("aria-expanded", "true");

    this.ensureMapInitialized().then(() => {
      setTimeout(() => this.leafletMap.invalidateSize(), OPEN_ANIMATION_MS);
      this.requestUserLocation();
    });
  }

  close() {
    if (!this.isOpen) return;
    this.isOpen = false;
    this.root.classList.remove("open");
    this.toggleButton.setAttribute("aria-expanded", "false");
  }

  /** Called when a calls-table row is tapped (replaces the old per-row
   * Google Maps iframe embed, which made a request to Google on every
   * expand -- see calls-list.js's selectRow). Opens the map if it's
   * closed, waits for Leaflet + the event's marker to exist, then pans/
   * zooms to it. */
  async focusEventOnMap(eventNumber) {
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
    if (!marker) return;
    this.leafletMap.setView(marker.getLatLng(), 16, { animate: true });
  }

  /** Prompts for geolocation permission on map open (never on page
   * load) and, if granted, drops a "you are here" marker + accuracy
   * circle. Denial/timeout/unsupported all fail silently -- location is
   * a nice-to-have overlay here, never something that blocks the map or
   * the calls list, matching this project's own stated location-UX
   * principle (see notes/offgeo/spec.md's location-state requirements).
   * The browser only ever prompts once; later calls just resolve
   * immediately against the stored permission decision, so it's safe to
   * call this on every open, not just the first. */
  requestUserLocation() {
    if (!("geolocation" in navigator)) return;
    navigator.geolocation.getCurrentPosition(
      (position) => this.showUserLocation(position.coords),
      (error) => {
        console.log("[map-view] geolocation unavailable:", error.message);
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 }
    );
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
      iconSize: [16, 16],
      iconAnchor: [8, 8],
    });
    L.marker([latitude, longitude], { icon, title: "Your location", interactive: false }).addTo(this.locationLayer);
  }

  async ensureMapInitialized() {
    if (this.hasInitializedMap) return;
    this.hasInitializedMap = true;

    const L = await loadLeaflet();
    const canvas = this.root.querySelector("#map-canvas");
    this.leafletMap = L.map(canvas, { attributionControl: false }).setView([32.9, -117.0], 9);
    L.tileLayer(OSM_TILE_URL, { attribution: OSM_ATTRIBUTION, maxZoom: 19 }).addTo(this.leafletMap);
    L.control.attribution({ prefix: "Leaflet" }).addTo(this.leafletMap);
    this.markersLayer = L.layerGroup().addTo(this.leafletMap);
    this.locationLayer = L.layerGroup().addTo(this.leafletMap);

    await this.updateMarkers(this.latestEvents);
  }

  /** Called by main.js whenever CallsList loads a fresh batch of events.
   * Cached even while the panel is closed so opening it doesn't need to
   * wait on a fresh feed fetch. */
  setEvents(events) {
    this.latestEvents = events;
    if (this.hasInitializedMap) {
      this.updateMarkers(events);
    }
  }

  async updateMarkers(events) {
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
    if (fitBoundsPoints.length) {
      this.leafletMap.fitBounds(fitBoundsPoints, { padding: [24, 24], maxZoom: 14 });
    }
  }

  buildMarker(L, event, point) {
    const pulse = pulseParamsForAge(ageMinutes(event.DateTime));
    const colorVar = event.IsOpen ? "var(--secondary)" : "var(--primary)";
    const pulseStyle = pulse
      ? `--pulse-duration:${pulse.duration}s;--pulse-scale:${pulse.scale};--pulse-opacity:${pulse.opacity}`
      : "";
    const icon = L.divIcon({
      className: "",
      html: `<span class="call-marker${pulse ? " pulsing" : ""}" style="--marker-color:${colorVar};${pulseStyle}"></span>`,
      iconSize: [14, 14],
      iconAnchor: [7, 7],
    });
    const marker = L.marker([point.lat, point.lon], {
      icon,
      title: `${event.Address}, ${event.Community}`,
      alt: event.EventType,
    });
    marker.on("click", () => this.props.onSelectEvent?.(event.EventNumber));
    return marker;
  }
}
