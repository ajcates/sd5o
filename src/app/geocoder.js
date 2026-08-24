/** Client-side half of the map prototype's address lookup (see
 * tools/offgeo/build-address-index.py for how src/app/data/address-index.json
 * is built, and why). This is deliberately not the real OffGeo geocoder --
 * no normalization library, no confidence scoring, no range interpolation
 * over road geometry. It does exactly two things: split a leading house
 * number off an address string, and look it up (exact, or nearest-known
 * point on the same street within a bounded delta) in the prebuilt index.
 * Intersections (containing "/") are never looked up -- there is no
 * single point for those in this prototype, consistent with "never invent
 * a result" rather than guessing a midpoint. */

const MAX_NEAREST_DELTA = 300;
const INDEX_URL = "src/app/data/address-index.json";

let indexPromise = null;

function loadIndex() {
  if (!indexPromise) {
    indexPromise = fetch(INDEX_URL)
      .then((response) => {
        if (!response.ok) throw new Error(`address-index fetch failed: HTTP ${response.status}`);
        return response.json();
      })
      .catch((error) => {
        indexPromise = null; // allow retry on next call
        throw error;
      });
  }
  return indexPromise;
}

/** @returns {Promise<{lat:number, lon:number, method:'exact'|'nearest'}|null>} */
export async function geocode(address) {
  const trimmed = (address || "").trim().toUpperCase();
  if (!trimmed || trimmed.includes("/")) return null;

  const spaceIndex = trimmed.indexOf(" ");
  if (spaceIndex === -1) return null;
  const head = trimmed.slice(0, spaceIndex);
  if (!/^\d+$/.test(head)) return null;
  const number = Number(head);
  const streetKey = trimmed.slice(spaceIndex + 1);

  const index = await loadIndex();
  const points = index[streetKey];
  if (!points || points.length === 0) return null;

  let exact = null;
  let nearest = null;
  let nearestDelta = Infinity;
  for (const [pointNumber, lat, lon] of points) {
    if (pointNumber === number) {
      exact = { lat, lon };
      break;
    }
    const delta = Math.abs(pointNumber - number);
    if (delta < nearestDelta) {
      nearestDelta = delta;
      nearest = { lat, lon };
    }
  }

  if (exact) return { ...exact, method: "exact" };
  if (nearest && nearestDelta <= MAX_NEAREST_DELTA) return { ...nearest, method: "nearest" };
  return null;
}
