import { Component, html } from "../framework/core.js";
import { geocode, getRoadLinesNear } from "../offgeo/geocoder.js";
import { ageMinutes } from "./format.js";
import { loadLeaflet } from "./leaflet-loader.js";

const OPEN_ANIMATION_MS = 340;
const NO_PULSE_AFTER_MINUTES = 120;
const ROADS_REFRESH_DEBOUNCE_MS = 350;

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

/** Owns the slide-down map panel: a Leaflet map with no raster basemap
 * (see notes/offgeo/index-html-audit.md's map-prototype section for why --
 * SanGIS road-line geometry is drawn instead), one marker per geocodable
 * call with an age-scaled pulse, and tap-to-select wired back to the calls
 * table via props.onSelectEvent.
 *
 * Leaflet and the real OffGeo pack (../offgeo/geocoder.js -- both
 * geocoding and the road-line backdrop below read from the one pack) are
 * loaded lazily on first open, not on page load -- most visits won't open
 * the map, and the pack alone is ~10MB gzip.
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
    this.roadsLayer = null;
    this.roadsRefreshTimer = null;
    this.roadsRequestSeq = 0;
    this.latestEvents = [];

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
    this.isOpen = !this.isOpen;
    this.root.classList.toggle("open", this.isOpen);
    this.toggleButton.setAttribute("aria-expanded", String(this.isOpen));
    if (!this.isOpen) return;

    this.ensureMapInitialized().then(() => {
      setTimeout(() => this.leafletMap.invalidateSize(), OPEN_ANIMATION_MS);
    });
  }

  async ensureMapInitialized() {
    if (this.hasInitializedMap) return;
    this.hasInitializedMap = true;

    const L = await loadLeaflet();
    const canvas = this.root.querySelector("#map-canvas");
    // preferCanvas: road lines can be a couple thousand polylines at
    // once (see getRoadLinesNear's own cap) -- Leaflet's default SVG
    // renderer gives each one its own DOM node, which is real,
    // measurable jank at that count; canvas draws them all into one
    // element instead.
    this.leafletMap = L.map(canvas, { attributionControl: false, preferCanvas: true }).setView([32.9, -117.0], 9);
    L.control
      .attribution({ prefix: "Leaflet" })
      .addAttribution("Roads: SanGIS")
      .addTo(this.leafletMap);
    this.markersLayer = L.layerGroup().addTo(this.leafletMap);
    this.roadsLayer = L.layerGroup().addTo(this.leafletMap);

    // Road lines follow the current viewport, not a fixed area computed
    // once: only the visible bounds are fetched and redrawn as the map
    // pans/zooms, debounced so a drag gesture doesn't fire a burst of
    // worker requests.
    this.leafletMap.on("moveend", () => this.scheduleRoadsRefresh());

    await this.updateMarkers(this.latestEvents);
    this.scheduleRoadsRefresh();
  }

  scheduleRoadsRefresh() {
    clearTimeout(this.roadsRefreshTimer);
    this.roadsRefreshTimer = setTimeout(() => this.refreshRoadsForViewport(), ROADS_REFRESH_DEBOUNCE_MS);
  }

  /** Road-line visual backdrop for whatever's currently on screen,
   * derived from the same OffGeo pack already loaded for geocoding (no
   * second network fetch, unlike the old prototype's separate
   * roads.json) -- ORDINARY-confidence segments within the live
   * viewport, evenly thinned by getRoadLinesNear itself when a wide
   * viewport would otherwise match tens of thousands at once. A stale
   * in-flight request whose viewport has since changed is dropped
   * rather than drawn. */
  async refreshRoadsForViewport() {
    if (!this.roadsLayer || !this.leafletMap) return;

    const requestId = ++this.roadsRequestSeq;
    const L = window.L;
    const view = this.leafletMap.getBounds().pad(0.2); // a little buffer past the visible edge
    const bounds = {
      minLat: view.getSouth(),
      maxLat: view.getNorth(),
      minLon: view.getWest(),
      maxLon: view.getEast(),
    };
    const lines = await getRoadLinesNear(bounds);
    if (requestId !== this.roadsRequestSeq) return; // viewport moved again before this resolved

    this.roadsLayer.clearLayers();
    // Polylines render in Leaflet's overlayPane (z-index 400) and markers
    // in markerPane (600), so markers already stack above roads without
    // needing an explicit bringToBack() (LayerGroup doesn't have one).
    for (const { points, label } of lines) {
      const line = L.polyline(points, { color: "#5a5a68", weight: 1, opacity: 0.7, interactive: false }).addTo(
        this.roadsLayer
      );
      // getRoadLinesNear labels at most one segment per distinct street
      // name in the result (not one per segment -- a street split into
      // many ROADSEGID pieces would otherwise repeat its own name down
      // its whole length), so this fires once per visible street.
      if (label) {
        line.bindTooltip(label, { permanent: true, direction: "center", className: "road-label" });
      }
    }
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
      fitBoundsPoints.push([point.lat, point.lon]);
    }
    if (fitBoundsPoints.length) {
      // fitBounds' own viewport change fires "moveend", which refreshes
      // the road-line layer for the new view (see scheduleRoadsRefresh) --
      // no separate road-line call needed here.
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
