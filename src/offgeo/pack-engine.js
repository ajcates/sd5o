/** The real OffGeo pack fetch/decode/geocode logic, independent of
 * *where* it runs. `pack-worker.js` (a Web Worker, so this work stays
 * off the main thread -- decoding all 164,555 records takes roughly a
 * second even in a JIT-warmed V8) is a thin `self.onmessage` wrapper
 * around this module; tests import it directly (with `fetch` mocked)
 * so the real logic is covered without needing an actual `Worker`,
 * which Node doesn't provide as a global.
 *
 * v0 scope: SanGIS Roads-All only (no Census fallback merge), exact
 * address-range containment only (no fuzzy/nearest fallback), no
 * route-based lookup for bare highway addresses or intersections.
 * Faithfully ports tools/offgeo/prototype-benchmark-reader.py's
 * real, proven-in-Python approach (100% matched, 35.8m median / 215.5m
 * p95 error against 2,000 real ground-truth address points).
 *
 * This module used to also serve road-line/label geometry for the
 * map's visual backdrop (a whole spatial-grid-indexed getRoadLinesNear
 * function, since removed). Once src/app/map-view.js switched to a
 * real OpenStreetMap tile basemap, hand-drawn road lines became
 * redundant -- the tiles already show roads, labels, and everything
 * else a basemap needs -- so that code (and the class of viewport-
 * query performance bugs that came with it) was deleted rather than
 * kept around unused. This module's only remaining job is geocoding. */

import { decodeRecords } from "./packformat.js";
import { parseAddress, canonicalizeStreetCoreName } from "./normalize.js";
import { rangeFraction, interpolateAlongPolyline } from "./interpolate.js";

export const DEFAULT_PACK_URL = "offgeo/packs/v0/sd-06073.ogp0";

let statePromise = null;

function buildKey(pdir, name, postd, sfx) {
  const canonicalName = name ? canonicalizeStreetCoreName(name) : "";
  return [pdir || "", canonicalName, postd || "", sfx || ""].join("\x1f");
}

function loadState(packUrl) {
  if (!statePromise) {
    statePromise = fetch(packUrl)
      .then((response) => {
        if (!response.ok) throw new Error(`offgeo pack fetch failed: HTTP ${response.status}`);
        return response.arrayBuffer();
      })
      .then((buffer) => {
        const records = decodeRecords(new Uint8Array(buffer));
        const byKey = new Map();
        for (const record of records) {
          const key = buildKey(record.pdir, record.name, record.postd, record.sfx);
          let list = byKey.get(key);
          if (!list) {
            list = [];
            byKey.set(key, list);
          }
          list.push(record);
        }
        return { records, byKey };
      })
      .catch((error) => {
        statePromise = null; // allow retry on next call
        throw error;
      });
  }
  return statePromise;
}

/** Test-only escape hatch: force a fresh fetch+decode on the next call
 * (each test otherwise shares the same cached pack across the whole
 * process, which is what production wants but not what an isolated
 * test does). Not used by pack-worker.js. */
export function _resetStateForTests() {
  statePromise = null;
}

/** Pick a side (L/R) whose range contains houseNumber, compute the
 * fraction along that range, and interpolate along the segment's own
 * geometry. Returns [lat, lon] or null if neither side contains the
 * number.
 *
 * Side-selection simplification, disclosed (same one
 * prototype-benchmark-reader.py already used and measured): SanGIS
 * carries no direct odd/even parity flag per side the way Census does
 * -- when both sides' ranges contain the number, this arbitrarily
 * prefers the left side rather than guess at parity. */
function resolveCoordinate(record, houseNumber) {
  const sides = [];
  if (!(record.lLow === 0 && record.lHigh === 0)) {
    const lo = Math.min(record.lLow, record.lHigh);
    const hi = Math.max(record.lLow, record.lHigh);
    if (lo <= houseNumber && houseNumber <= hi) sides.push([record.lLow, record.lHigh]);
  }
  if (!(record.rLow === 0 && record.rHigh === 0)) {
    const lo = Math.min(record.rLow, record.rHigh);
    const hi = Math.max(record.rLow, record.rHigh);
    if (lo <= houseNumber && houseNumber <= hi) sides.push([record.rLow, record.rHigh]);
  }
  if (sides.length === 0) return null;

  const [low, high] = sides[0];
  let fraction = rangeFraction(houseNumber, low, high);
  if (fraction === null) fraction = 0.5; // degenerate zero-width range -- segment midpoint
  return interpolateAlongPolyline(record.points, fraction);
}

/** Resolve a real calls-feed address string to a coordinate.
 * @returns {Promise<{lat:number, lon:number, confidence:'ORDINARY'|'FALLBACK'|'EXCLUDED', reason:string}|null>} */
export async function geocode(address, packUrl = DEFAULT_PACK_URL) {
  const parsed = parseAddress(address || "");
  if (parsed.isIntersection) return null; // no intersection lookup in v0
  const street = parsed.streets[0];
  if (!street || street.isHighway) return null; // no route-based lookup in v0
  if (parsed.houseNumber === null) return null; // street-only text, no point to return

  const { byKey } = await loadState(packUrl);
  const key = buildKey(street.pdir, street.name, street.postd, street.suffix);
  const candidates = byKey.get(key);
  if (!candidates || candidates.length === 0) return null;

  const matching = [];
  for (const record of candidates) {
    const point = resolveCoordinate(record, parsed.houseNumber);
    if (point) matching.push({ record, point });
  }
  if (matching.length === 0) return null;

  matching.sort((a, b) => a.record.roadsegid - b.record.roadsegid);
  const { record, point } = matching[0];
  const [lat, lon] = point;
  return {
    lat,
    lon,
    confidence: record.confidence,
    reason: parsed.isBlockApproximate ? "block-approximate" : "exact-range",
  };
}
