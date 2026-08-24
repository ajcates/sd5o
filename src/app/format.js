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
