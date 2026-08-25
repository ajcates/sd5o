/** Maps a raw EventType string (a mix of CA penal/vehicle code numbers
 * and free text -- e.g. "242 BATTERY", "5150 MENTAL HEALTH EVALUATION",
 * "WELFARE CHECK") to one of a small set of dispatch categories, each
 * with its own color. Used to color both the map markers
 * (map-view.js's buildMarker) and the calls list's left-edge indicator
 * (calls-list.js's renderRow) consistently, so a color means the same
 * thing in both places.
 *
 * Keyword-matched against the free text rather than a numeric code
 * prefix alone, since not every real value has one (e.g. "WELFARE
 * CHECK", "ASSIST OTHER AGENCY"). Order matters -- more specific
 * keywords are listed before broader ones they'd otherwise be caught
 * by (e.g. "domestic violence" before the generic "assault"/"battery"
 * bucket, "grand theft" before generic "theft"). Coverage is drawn from
 * real values seen in the live feed plus common CA penal/vehicle code
 * dispatch types; anything unmatched falls back to a neutral color
 * rather than guessing. */

const CATEGORIES = [
  {
    name: "Violent/weapons",
    color: "#ff5470",
    keywords: [
      "HOMICIDE", "MURDER", "SHOOTING", "SHOTS FIRED", "STABBING", "ASSAULT WITH A DEADLY WEAPON",
      "DOMESTIC VIOLENCE", "BATTERY", "ASSAULT", "ROBBERY", "KIDNAP", "RAPE", "SEXUAL ASSAULT",
      "MOLEST", "WEAPON", "FIREARM", "417",
    ],
  },
  {
    name: "Welfare/medical",
    color: "#4dd9a0",
    keywords: [
      "WELFARE CHECK", "5150", "MENTAL HEALTH", "SUICIDE", "OVERDOSE", "MEDICAL AID", "DEAD BODY",
      "MISSING PERSON",
    ],
  },
  {
    name: "Property crime",
    color: "#ff9f4d",
    keywords: [
      "BURGLARY", "459", "GRAND THEFT", "PETTY THEFT", "SHOPLIFT", "THEFT", "STOLEN VEHICLE",
      "10851", "VANDALISM", "594", "ARSON", "TRESPASS", "PROWLER",
    ],
  },
  {
    name: "Drugs/alcohol",
    color: "#ff6ec7",
    keywords: ["UNDER THE INFLUENCE", "647F", "NARCOTIC", "DRUG", "ALCOHOL", "11550", "DUI", "23152"],
  },
  {
    name: "Traffic/vehicle",
    color: "#b48cff",
    keywords: [
      "TRAFFIC", "COLLISION", "ACCIDENT", "HIT AND RUN", "HIT-AND-RUN", "RECKLESS DRIVING",
      "MOVING VEHICLE", "23110", "VEHICLE", "PARKING", "ROAD RAGE",
    ],
  },
  {
    name: "Disturbance/suspicious",
    color: "#f2c94d",
    keywords: [
      "DISTURBANCE", "415", "ARGUMENT", "FIGHT", "SUSPICIOUS", "NOISE", "THREATS", "HARASSMENT",
    ],
  },
  {
    name: "Alarm",
    color: "#4dc3ff",
    keywords: ["ALARM"],
  },
  {
    name: "Assist/admin",
    color: "#8f9bb3",
    keywords: ["ASSIST OTHER AGENCY", "ASSIST", "CIVIL", "CITIZEN CONTACT", "PATROL CHECK", "SECURITY CHECK"],
  },
];

const FALLBACK_COLOR = "#9a9aa8"; // matches --on-surface-variant

/** @returns {string} a hex color for this event type -- always returns
 * something, falling back to a neutral gray for unmatched/unknown text. */
export function eventTypeColor(eventType) {
  const text = (eventType || "").toUpperCase();
  for (const category of CATEGORIES) {
    if (category.keywords.some((keyword) => text.includes(keyword))) return category.color;
  }
  return FALLBACK_COLOR;
}

/** @returns {string} a human-readable category name, for tooltips/titles. */
export function eventTypeCategoryName(eventType) {
  const text = (eventType || "").toUpperCase();
  for (const category of CATEGORIES) {
    if (category.keywords.some((keyword) => text.includes(keyword))) return category.name;
  }
  return "Other";
}
