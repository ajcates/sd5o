/** Lazily inject the vendored (self-hosted, see vendor/leaflet/README.md)
 * Leaflet CSS + UMD script the first time the map is opened, instead of
 * loading it on every page visit whether or not the map feature is used.
 * Leaflet's dist bundle isn't an ES module, so this is a plain <script>
 * tag rather than a dynamic import(). */

let leafletPromise = null;

export function loadLeaflet() {
  if (leafletPromise) return leafletPromise;

  if (!document.querySelector('link[data-leaflet-css]')) {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = "vendor/leaflet/leaflet.css";
    link.setAttribute("data-leaflet-css", "");
    document.head.appendChild(link);
  }

  leafletPromise = new Promise((resolve, reject) => {
    if (window.L) {
      resolve(window.L);
      return;
    }
    const script = document.createElement("script");
    script.src = "vendor/leaflet/leaflet.js";
    script.onload = () => resolve(window.L);
    script.onerror = () => reject(new Error("Failed to load vendored Leaflet"));
    document.body.appendChild(script);
  });
  return leafletPromise;
}
