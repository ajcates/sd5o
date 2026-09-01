/** Small formatting helpers shared by app components. Pulled out of the old
 * inline <script> global scope (see notes/offgeo/index-html-audit.md Part B
 * finding 5) so they're each independently testable/importable. */

function parseFeedDate(datestring) {
  const normalizedDate = String(datestring).replace(/^(\d{2})-(\d{2})-(\d{4})/, "$1/$2/$3");
  return new Date(normalizedDate);
}

/** Minutes since a feed DateTime string (negative if it's in the future --
 * shouldn't normally happen, but not guarded against here since callers
 * treat "older" vs. "newer" relatively, not as a hard invariant). */
export function ageMinutes(datestring) {
  return Math.round((new Date() - parseFeedDate(datestring)) / 60000);
}

export function prettyTime(datestring) {
  const diff = parseFeedDate(datestring) - new Date();
  const minutes = Math.round(diff / 60000);

  const formatter = new Intl.RelativeTimeFormat("en-US", { numeric: "auto" });

  if (Math.abs(minutes) < 60) {
    return formatter.format(minutes, "minute");
  }
  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 24) {
    return formatter.format(hours, "hour");
  }
  return formatter.format(Math.round(hours / 24), "day");
}

/** Compact elapsed time for the feed status line: 10s ago, 1m20s ago. */
export function compactElapsedTime(datestring) {
  const elapsedSeconds = Math.max(0, Math.floor((new Date() - parseFeedDate(datestring)) / 1000));
  if (elapsedSeconds < 60) return `${elapsedSeconds}s ago`;
  if (elapsedSeconds < 3600) {
    const minutes = Math.floor(elapsedSeconds / 60);
    return `${minutes}m${elapsedSeconds % 60}s ago`;
  }
  if (elapsedSeconds < 86400) {
    const hours = Math.floor(elapsedSeconds / 3600);
    const minutes = Math.floor((elapsedSeconds % 3600) / 60);
    return `${hours}h${minutes}m ago`;
  }
  const days = Math.floor(elapsedSeconds / 86400);
  const hours = Math.floor((elapsedSeconds % 86400) / 3600);
  return `${days}d${hours}h ago`;
}

export async function fetchJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  const responseText = await response.text();
  let data;

  try {
    data = JSON.parse(responseText);
    if (typeof data === "string") {
      data = JSON.parse(data);
    }
  } catch (error) {
    throw new Error(`Calls service returned invalid JSON (HTTP ${response.status}).`);
  }

  if (!response.ok) {
    const message = data.message || data.error || response.statusText || "Request failed";
    throw new Error(`${message} (HTTP ${response.status}).`);
  }

  return data;
}
