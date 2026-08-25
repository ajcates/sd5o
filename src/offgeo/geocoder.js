/** The real OffGeo geocoder: fetches and decodes the compiled pack
 * (offgeo/manifest.json / offgeo/packs/v0/sd-06073.ogp0, built by
 * tools/offgeo/compile-pack.py), builds an in-memory street-key index,
 * and resolves a free-text call address to a coordinate via real
 * address-range interpolation over the road's own geometry --
 * replacing the small nearest-known-point map-prototype this app
 * shipped before.
 *
 * v0 scope, matching notes/offgeo/r1-todo.md's own framing: SanGIS
 * Roads-All only (no Census fallback merge), exact address-range
 * containment only (no fuzzy/nearest fallback -- an address that
 * doesn't fall inside any segment's range on a known street simply
 * isn't geocoded, same "never invent a result" stance the old
 * prototype had), and no route-based lookup for bare highway addresses
 * or intersections (both are correctly *parsed* by normalize.js but
 * have no lookup path here yet).
 *
 * Faithfully ports the real logic tools/offgeo/prototype-benchmark-reader.py
 * (`OFF-105`) already proved end-to-end in Python (100% matched, 35.8m
 * median / 215.5m p95 error against 2,000 real ground-truth address
 * points): parse address -> build street key -> find candidate
 * segment(s) -> keep those whose range contains the house number ->
 * side-select (documented simplification below) -> interpolate.
 */

import { decodeRecords } from "./packformat.js";
import { parseAddress, canonicalizeStreetCoreName } from "./normalize.js";
import { rangeFraction, interpolateAlongPolyline } from "./interpolate.js";

const PACK_URL = "offgeo/packs/v0/sd-06073.ogp0";

let statePromise = null;

function buildKey(pdir, name, postd, sfx) {
  const canonicalName = name ? canonicalizeStreetCoreName(name) : "";
  return [pdir || "", canonicalName, postd || "", sfx || ""].join("\x1f");
}

function loadState() {
  if (!statePromise) {
    statePromise = fetch(PACK_URL)
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

/** Pick a side (L/R) whose range contains houseNumber, compute the
 * fraction along that range, and interpolate along the segment's own
 * geometry. Returns [lat, lon] or null if neither side contains the
 * number.
 *
 * Side-selection simplification, disclosed (same one
 * prototype-benchmark-reader.py already used and measured): SanGIS
 * carries no direct odd/even parity flag per side the way Census does
 * -- when both sides' ranges contain the number, this arbitrarily
 * prefers the left side rather than guess at parity. Real future work,
 * not a claim of correctness for that rare both-contain case. */
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
export async function geocode(address) {
  const parsed = parseAddress(address || "");
  if (parsed.isIntersection) return null; // no intersection lookup in v0
  const street = parsed.streets[0];
  if (!street || street.isHighway) return null; // no route-based lookup in v0
  if (parsed.houseNumber === null) return null; // street-only text, no point to return

  const { byKey } = await loadState();
  const key = buildKey(street.pdir, street.name, street.postd, street.suffix);
  const candidates = byKey.get(key);
  if (!candidates || candidates.length === 0) return null;

  const matching = [];
  for (const record of candidates) {
    const point = resolveCoordinate(record, parsed.houseNumber);
    if (point) matching.push({ record, point });
  }
  if (matching.length === 0) return null;

  // Deterministic tie-break among multiple matching segments (rare --
  // overlapping ranges on the same named street): lowest ROADSEGID,
  // same simplification prototype-benchmark-reader.py used.
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

/** ORDINARY-confidence road-line geometry whose bounding box overlaps
 * `bounds` (`{minLat, maxLat, minLon, maxLon}`), for the map's visual
 * road backdrop. Reuses the already-loaded pack -- no second network
 * fetch, unlike the old prototype's separate roads.json. Returns an
 * array of `[lat, lon]`-pair arrays (Leaflet's own polyline point
 * shape). */
export async function getRoadLinesNear(bounds) {
  const { records } = await loadState();
  const lines = [];
  for (const record of records) {
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
    const overlaps =
      minLat <= bounds.maxLat && maxLat >= bounds.minLat && minLon <= bounds.maxLon && maxLon >= bounds.minLon;
    if (!overlaps) continue;
    const pairs = [];
    for (let i = 0; i < points.length; i += 2) pairs.push([points[i], points[i + 1]]);
    lines.push(pairs);
  }
  return lines;
}
