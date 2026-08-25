/** Web Worker entry point: runs pack-engine.js's real fetch/decode/
 * geocode logic off the main thread. Decoding all 164,555 records
 * takes roughly a second even in a JIT-warmed V8 -- doing that inline
 * on the main thread froze the page for that whole time (confirmed
 * live: this was the real cause of a reported "the map is really
 * slow" bug). geocoder.js on the main thread is a thin postMessage RPC
 * wrapper talking to this worker; pack-engine.js holds the actual
 * logic and is also imported directly by tests (no real `Worker`
 * needed there). */

import { geocode, getRoadLinesNear, DEFAULT_PACK_URL } from "./pack-engine.js";

// Resolved relative to this worker module's own URL, not the page that
// created it -- a worker's fetch()/import base is its own script location.
const PACK_URL = new URL(`../../${DEFAULT_PACK_URL}`, import.meta.url);

self.onmessage = async (event) => {
  const { id, method, args } = event.data;
  try {
    let result;
    if (method === "geocode") result = await geocode(args[0], PACK_URL);
    else if (method === "getRoadLinesNear") result = await getRoadLinesNear(args[0], PACK_URL);
    else throw new Error(`unknown worker method: ${method}`);
    self.postMessage({ id, result });
  } catch (error) {
    self.postMessage({ id, error: String((error && error.message) || error) });
  }
};
