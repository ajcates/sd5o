/** Main-thread entry point for the real OffGeo geocoder. Thin
 * postMessage RPC wrapper around pack-worker.js, which does the actual
 * pack fetch/decode/geocode work in a Web Worker -- decoding all
 * 164,555 records takes roughly a second even in a JIT-warmed V8, and
 * doing that inline on the main thread froze the page for that whole
 * time (found live against the real deployment). Same public API as
 * before this fix (`geocode(address)`, `getRoadLinesNear(bounds)`), so
 * map-view.js didn't need to change.
 *
 * v0 scope, unchanged from before: SanGIS Roads-All only (no Census
 * fallback merge), exact address-range containment only (no fuzzy/
 * nearest fallback), no route-based lookup for bare highway addresses
 * or intersections. See pack-worker.js for the real geocoding logic
 * (faithfully porting tools/offgeo/prototype-benchmark-reader.py's
 * proven-in-Python approach). */

let worker = null;
let nextId = 1;
const pending = new Map();

function getWorker() {
  if (!worker) {
    worker = new Worker(new URL("./pack-worker.js", import.meta.url), { type: "module" });
    worker.onmessage = (event) => {
      const { id, result, error } = event.data;
      const entry = pending.get(id);
      if (!entry) return;
      pending.delete(id);
      if (error) entry.reject(new Error(error));
      else entry.resolve(result);
    };
    worker.onerror = (event) => {
      const message = event.message || "offgeo worker error";
      for (const entry of pending.values()) entry.reject(new Error(message));
      pending.clear();
    };
  }
  return worker;
}

function call(method, args) {
  return new Promise((resolve, reject) => {
    const id = nextId++;
    pending.set(id, { resolve, reject });
    getWorker().postMessage({ id, method, args });
  });
}

/** Resolve a real calls-feed address string to a coordinate.
 * @returns {Promise<{lat:number, lon:number, confidence:'ORDINARY'|'FALLBACK'|'EXCLUDED', reason:string}|null>} */
export function geocode(address) {
  return call("geocode", [address]);
}

/** ORDINARY-confidence road-line geometry whose bounding box overlaps
 * `bounds` (`{minLat, maxLat, minLon, maxLon}`), for the map's visual
 * road backdrop. Returns an array of `[lat, lon]`-pair arrays. */
export function getRoadLinesNear(bounds) {
  return call("getRoadLinesNear", [bounds]);
}
