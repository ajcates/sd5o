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
 * p95 error against 2,000 real ground-truth address points). */

import { decodeRecords } from "./packformat.js";
import { parseAddress, canonicalizeStreetCoreName } from "./normalize.js";
import { rangeFraction, interpolateAlongPolyline } from "./interpolate.js";

export const DEFAULT_PACK_URL = "offgeo/packs/v0/sd-06073.ogp0";

let statePromise = null;

function buildKey(pdir, name, postd, sfx) {
  const canonicalName = name ? canonicalizeStreetCoreName(name) : "";
  return [pdir || "", canonicalName, postd || "", sfx || ""].join("\x1f");
}

// getRoadLinesNear was originally a plain linear scan over all 164,555
// records per call. Fine once, but the viewport-following design (a
// fresh query on every pan/zoom, debounced but still frequent) turned
// that into a real, measured bottleneck: a wide (zoomed-out) query
// scans everything and takes ~2s, and rapid zoom/pan can queue up
// several such scans back to back in the worker's single-threaded event
// loop, backing up badly enough to make the map feel stuck. A coarse
// grid built once at load time (below) turns a query into "check the
// handful of cells the viewport overlaps," not "check every record in
// the county" -- the standard fix for exactly this access pattern.
const GRID_CELL_DEG = 0.05; // ~5.5km lat / ~4.6km lon at this latitude

// San Diego County's real extent with a little margin -- the same
// bounds tools/offgeo/lib/coords.py's is_plausible_san_diego_point uses
// for its own sanity check. Used below to clamp an arbitrarily large
// query viewport before it's turned into a grid cell range.
const PACK_BOUNDS = { minLat: 32.5, maxLat: 33.55, minLon: -117.65, maxLon: -116.0 };

function gridCellKey(latIdx, lonIdx) {
  return `${latIdx},${lonIdx}`;
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
        const roadGrid = new Map(); // grid cell -> ORDINARY records whose bbox overlaps it
        for (const record of records) {
          const key = buildKey(record.pdir, record.name, record.postd, record.sfx);
          let list = byKey.get(key);
          if (!list) {
            list = [];
            byKey.set(key, list);
          }
          list.push(record);

          if (record.confidence !== "ORDINARY") continue;
          const points = record.points;
          let minLat = Infinity, maxLat = -Infinity, minLon = Infinity, maxLon = -Infinity;
          for (let i = 0; i < points.length; i += 2) {
            const lat = points[i], lon = points[i + 1];
            if (lat < minLat) minLat = lat;
            if (lat > maxLat) maxLat = lat;
            if (lon < minLon) minLon = lon;
            if (lon > maxLon) maxLon = lon;
          }
          // Cached once here rather than recomputed by every future
          // query -- the whole point of building this index up front.
          record._bbox = { minLat, maxLat, minLon, maxLon };

          const minLatIdx = Math.floor(minLat / GRID_CELL_DEG);
          const maxLatIdx = Math.floor(maxLat / GRID_CELL_DEG);
          const minLonIdx = Math.floor(minLon / GRID_CELL_DEG);
          const maxLonIdx = Math.floor(maxLon / GRID_CELL_DEG);
          for (let la = minLatIdx; la <= maxLatIdx; la++) {
            for (let lo = minLonIdx; lo <= maxLonIdx; lo++) {
              const cellKey = gridCellKey(la, lo);
              let cellList = roadGrid.get(cellKey);
              if (!cellList) {
                cellList = [];
                roadGrid.set(cellKey, cellList);
              }
              cellList.push(record);
            }
          }
        }
        return { records, byKey, roadGrid };
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
  if (fraction === null) fraction = 0.5;
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

// Rendering ~100k Leaflet polylines at once (measured: a county-wide
// viewport matches all 106,346 ORDINARY segments) is real, visible
// clutter and slow to paint, not usable "context" -- but there's no
// need for a hardcoded zoom-level gate to avoid it. A small viewport
// (zoomed in) naturally matches far fewer roads than this cap and every
// one renders at full detail; a huge viewport (zoomed out) matches far
// more and gets evenly thinned instead. That's the "less detail zoomed
// out, more detail zoomed in" effect, driven by the real relationship
// between viewport size and match count rather than an arbitrary
// threshold that has to be re-tuned for every call distribution.
//
// 600, not a rounder/larger number: measured live that repeated
// zoom/pan cycles each doing a full clearLayers()+rebuild of a couple
// thousand canvas polylines (plus their tooltip DOM nodes) compounds
// into serious, real browser slowdown after several cycles -- lowering
// the per-refresh batch size directly reduces both the per-cycle
// render cost and the cumulative pressure from repeated rebuilds.
const MAX_LINES_PER_QUERY = 600;

function formatStreetLabel(record) {
  return [record.pdir, record.name, record.sfx, record.postd].filter(Boolean).join(" ");
}

/** ORDINARY-confidence road-line geometry whose bounding box overlaps
 * `bounds` (`{minLat, maxLat, minLon, maxLon}`), evenly thinned to at
 * most `MAX_LINES_PER_QUERY` lines when the match count is larger.
 * Returns an array of `{points, label}` (`points`: `[lat, lon]`-pair
 * array, Leaflet's own polyline point shape; `label`: a display string
 * on at most one segment per distinct street name in the result, or
 * `null` on the rest -- a street split into many `ROADSEGID` pieces
 * would otherwise repeat its own name down its whole length, one label
 * per visible pixel of road rather than one per visible street). */
export async function getRoadLinesNear(bounds, packUrl = DEFAULT_PACK_URL) {
  const { roadGrid } = await loadState(packUrl);

  // Real bug found live: at very low zoom (zoomed out to a world view),
  // Leaflet's getBounds() legitimately spans most of the globe. Without
  // this clamp, the grid loop below iterates every cell in that
  // enormous range -- ~25 million Map lookups, a real measured 25+
  // second stall -- regardless of how little (or none) of the actual
  // pack data is anywhere near it. Clamping to the pack's own known
  // extent bounds the search to what could possibly match (at most a
  // few hundred cells) and also correctly yields nothing once the
  // viewport no longer overlaps the county at all.
  const clamped = {
    minLat: Math.max(bounds.minLat, PACK_BOUNDS.minLat),
    maxLat: Math.min(bounds.maxLat, PACK_BOUNDS.maxLat),
    minLon: Math.max(bounds.minLon, PACK_BOUNDS.minLon),
    maxLon: Math.min(bounds.maxLon, PACK_BOUNDS.maxLon),
  };
  if (clamped.minLat > clamped.maxLat || clamped.minLon > clamped.maxLon) return [];

  const minLatIdx = Math.floor(clamped.minLat / GRID_CELL_DEG);
  const maxLatIdx = Math.floor(clamped.maxLat / GRID_CELL_DEG);
  const minLonIdx = Math.floor(clamped.minLon / GRID_CELL_DEG);
  const maxLonIdx = Math.floor(clamped.maxLon / GRID_CELL_DEG);

  const seen = new Set(); // a record can span multiple cells; roadsegid dedups it
  const matches = [];
  for (let la = minLatIdx; la <= maxLatIdx; la++) {
    for (let lo = minLonIdx; lo <= maxLonIdx; lo++) {
      const cellList = roadGrid.get(gridCellKey(la, lo));
      if (!cellList) continue;
      for (const record of cellList) {
        if (seen.has(record.roadsegid)) continue;
        seen.add(record.roadsegid);
        const bbox = record._bbox;
        const overlaps =
          bbox.minLat <= bounds.maxLat &&
          bbox.maxLat >= bounds.minLat &&
          bbox.minLon <= bounds.maxLon &&
          bbox.maxLon >= bounds.minLon;
        if (overlaps) matches.push(record);
      }
    }
  }

  const stride = Math.max(1, Math.ceil(matches.length / MAX_LINES_PER_QUERY));

  // Real bug found live: capping to "one label per distinct street name
  // in the result" alone still produced up to ~900 overlapping,
  // unreadable tooltips on a wide viewport (hundreds of distinct
  // streets fit inside a county-wide box). Space labels out in
  // proportion to the viewport itself -- degrees-per-label scales with
  // `bounds`' own width/height, so a zoomed-out (huge) viewport and a
  // zoomed-in (small) one both end up with roughly the same *visual*
  // label density instead of the raw count exploding at low zoom.
  const minSpacingLat = (bounds.maxLat - bounds.minLat) / 12;
  const minSpacingLon = (bounds.maxLon - bounds.minLon) / 12;
  const labeledStreetKeys = new Set();
  const labelPositions = []; // [lat, lon] anchor of each already-placed label

  const lines = [];
  for (let i = 0; i < matches.length; i += stride) {
    const record = matches[i];
    const points = record.points;
    const pairs = [];
    for (let j = 0; j < points.length; j += 2) pairs.push([points[j], points[j + 1]]);

    let label = null;
    if (record.name) {
      const streetKey = [record.pdir || "", record.name, record.sfx || "", record.postd || ""].join("\x1f");
      if (!labeledStreetKeys.has(streetKey)) {
        const anchorLat = points[0];
        const anchorLon = points[1];
        const tooClose = labelPositions.some(
          ([lat, lon]) => Math.abs(lat - anchorLat) < minSpacingLat && Math.abs(lon - anchorLon) < minSpacingLon
        );
        if (!tooClose) {
          labeledStreetKeys.add(streetKey);
          labelPositions.push([anchorLat, anchorLon]);
          label = formatStreetLabel(record);
        }
      }
    }
    lines.push({ points: pairs, label });
  }
  return lines;
}
