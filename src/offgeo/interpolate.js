/** Polyline-length, polyline-interpolation, and great-circle distance
 * helpers. Port of tools/offgeo/lib/interpolate.py -- see that module
 * for the design notes (this is the first JS port of it; the R1
 * prototyping work stayed on the Python side).
 *
 * `haversineMeters` is the accurate distance function. `planarMeters`
 * is a fast equirectangular approximation used internally by the
 * length/interpolation walk, which only ever operates over a single
 * road segment's own extent (tens to a few hundred meters) -- accurate
 * to well under 0.1% error at that scale. */

const EARTH_RADIUS_M = 6371000.0;

export function haversineMeters(lat1, lon1, lat2, lon2) {
  const phi1 = (lat1 * Math.PI) / 180;
  const phi2 = (lat2 * Math.PI) / 180;
  const dPhi = ((lat2 - lat1) * Math.PI) / 180;
  const dLambda = ((lon2 - lon1) * Math.PI) / 180;
  const a = Math.sin(dPhi / 2) ** 2 + Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLambda / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1.0, Math.sqrt(a)));
}

function planarMeters(lat1, lon1, lat2, lon2) {
  const latAvg = ((lat1 + lat2) / 2) * (Math.PI / 180);
  const dx = ((lon2 - lon1) * Math.PI) / 180 * Math.cos(latAvg) * EARTH_RADIUS_M;
  const dy = ((lat2 - lat1) * Math.PI) / 180 * EARTH_RADIUS_M;
  return Math.hypot(dx, dy);
}

/** points: flat Float64Array [lat0, lon0, lat1, lon1, ...] (the shape
 * packformat.js's decoded `points` field already uses). */
export function polylineLengthMeters(points) {
  let total = 0;
  const n = points.length / 2;
  for (let i = 0; i < n - 1; i++) {
    total += planarMeters(points[i * 2], points[i * 2 + 1], points[(i + 1) * 2], points[(i + 1) * 2 + 1]);
  }
  return total;
}

/** Walk `points` (flat [lat,lon,...] array) from the first vertex toward
 * the last, returning [lat, lon] at `fraction` (clamped to [0, 1]) of
 * the total polyline length. A single-vertex polyline always returns
 * that vertex; a zero-length polyline (all vertices coincide) returns
 * the first vertex rather than dividing by zero. */
export function interpolateAlongPolyline(points, fraction) {
  const f = Math.max(0, Math.min(1, fraction));
  const n = points.length / 2;
  if (n === 1) return [points[0], points[1]];

  const total = polylineLengthMeters(points);
  if (total === 0) return [points[0], points[1]];

  const target = f * total;
  let covered = 0;
  for (let i = 0; i < n - 1; i++) {
    const lat1 = points[i * 2], lon1 = points[i * 2 + 1];
    const lat2 = points[(i + 1) * 2], lon2 = points[(i + 1) * 2 + 1];
    const segLen = planarMeters(lat1, lon1, lat2, lon2);
    if (covered + segLen >= target || i === n - 2) {
      const remaining = target - covered;
      const t = segLen === 0 ? 0 : Math.min(1, remaining / segLen);
      return [lat1 + (lat2 - lat1) * t, lon1 + (lon2 - lon1) * t];
    }
    covered += segLen;
  }
  return [points[(n - 1) * 2], points[(n - 1) * 2 + 1]];
}

/** Where `houseNumber` falls between `low` and `high` as a 0..1
 * fraction. Direction-agnostic: works whether `low < high` (ascending,
 * the common case) or `low > high` (descending -- one real segment
 * OFF-103 profiling found), since `(v - low) / (high - low)` is
 * algebraically symmetric either way. Returns null only for a
 * degenerate zero-width range (`low === high`). */
export function rangeFraction(houseNumber, low, high) {
  if (high === low) return null;
  return (houseNumber - low) / (high - low);
}
