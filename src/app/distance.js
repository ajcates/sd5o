const EARTH_RADIUS_METERS = 6_371_008.8;
const METERS_PER_MILE = 1609.344;

function toRadians(degrees) {
  return (degrees * Math.PI) / 180;
}

function validCoordinate(point) {
  return (
    point &&
    Number.isFinite(point.latitude) &&
    Number.isFinite(point.longitude) &&
    point.latitude >= -90 &&
    point.latitude <= 90 &&
    point.longitude >= -180 &&
    point.longitude <= 180
  );
}

/** Straight-line great-circle distance. Coordinates never leave the page. */
export function distanceMiles(from, to) {
  if (!validCoordinate(from) || !validCoordinate(to)) return null;

  const lat1 = toRadians(from.latitude);
  const lat2 = toRadians(to.latitude);
  const deltaLat = lat2 - lat1;
  const deltaLon = toRadians(to.longitude - from.longitude);
  const sinLat = Math.sin(deltaLat / 2);
  const sinLon = Math.sin(deltaLon / 2);
  const a = sinLat * sinLat + Math.cos(lat1) * Math.cos(lat2) * sinLon * sinLon;
  const meters = 2 * EARTH_RADIUS_METERS * Math.asin(Math.min(1, Math.sqrt(a)));
  return meters / METERS_PER_MILE;
}

export function formatDistanceMiles(miles) {
  if (!Number.isFinite(miles) || miles < 0) return null;
  if (miles < 0.1) {
    const feet = Math.max(100, Math.round((miles * 5280) / 100) * 100);
    return {
      visible: `≈${feet.toLocaleString("en-US")} ft`,
      accessible: `Approximately ${feet.toLocaleString("en-US")} feet straight-line distance`,
    };
  }
  const rounded = miles < 10 ? Math.round(miles * 10) / 10 : Math.round(miles);
  return {
    visible: `≈${rounded.toLocaleString("en-US", { maximumFractionDigits: 1 })} mi`,
    accessible: `Approximately ${rounded.toLocaleString("en-US", {
      maximumFractionDigits: 1,
    })} ${rounded === 1 ? "mile" : "miles"} straight-line distance`,
  };
}

export function formatAccuracyMeters(meters) {
  if (!Number.isFinite(meters) || meters <= 0) return "";
  const feet = meters * 3.28084;
  if (feet < 1000) return `Location accuracy ±${Math.max(10, Math.round(feet / 10) * 10)} ft.`;
  return `Location accuracy ±${(feet / 5280).toFixed(1)} mi.`;
}
