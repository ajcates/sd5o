/** Shared address/street-name normalization library. Port of
 * tools/offgeo/lib/normalize.py -- the exact same canonicalization
 * rules and tables, so the compiler (Python) and this runtime (JS)
 * never drift apart on what "canonical street name" means. See that
 * module's own docstring for why suffixes canonicalize to the full
 * spelled word and directions to the short code, and where each table
 * came from (SanGIS's own field-domain docs, plus a human-mapped
 * Census-suffix addition found via tools/offgeo/reconcile-sangis-census-streets.py). */

export const NORMALIZE_VERSION = 1;

const DIRECTION_PAIRS = [
  ["N", "NORTH"], ["S", "SOUTH"], ["E", "EAST"], ["W", "WEST"],
  ["NE", "NORTHEAST"], ["NW", "NORTHWEST"], ["SE", "SOUTHEAST"], ["SW", "SOUTHWEST"],
];
export const DIRECTION_CANON = {};
for (const [code, word] of DIRECTION_PAIRS) {
  DIRECTION_CANON[code] = code;
  DIRECTION_CANON[word] = code;
}

export const TRAVEL_DIRECTION_MARKERS = new Set(["NB", "SB", "EB", "WB"]);

const SUFFIX_ABBREVIATIONS = {
  ALY: "ALLEY", ARC: "ARCADE", AVE: "AVENUE", BP: "BIKEPATH",
  BLVD: "BOULEVARD", BRG: "BRIDGE", BYP: "BYPASS", CSWY: "CAUSEWAY",
  CIR: "CIRCLE", CP: "CAPE", CTE: "CORTE", CT: "COURT", CV: "COVE",
  CRES: "CRESCENT", XING: "CROSSING", DR: "DRIVE", DRWY: "DRIVEWAY",
  EXPY: "EXPRESSWAY", EXT: "EXTENSION", FRY: "FERRY", FWY: "FREEWAY",
  GLEN: "GLEN", HWY: "HIGHWAY", INTR: "INTERCHANGE", LN: "LANE",
  LOOP: "LOOP", MALL: "MALL", PKY: "PARKWAY", PASS: "PASS",
  PATH: "PATH", PL: "PLACE", PLZ: "PLAZA", PT: "POINT",
  PTE: "POINTE", RAMP: "RAMP", RD: "ROAD", ROW: "ROW", SQ: "SQUARE",
  ST: "STREET", TER: "TERRACE", TRL: "TRAIL", TKTL: "TRUCKTRAIL",
  WALK: "WALK", WAY: "WAY",
  AL: "ALLEY", AR: "ARCADE", AV: "AVENUE", BL: "BOULEVARD",
  BR: "BRIDGE", BY: "BYPASS", CE: "CORTE", CG: "CROSSING",
  CR: "CIRCLE", CS: "CRESCENT", CY: "CAUSEWAY", DY: "DRIVEWAY",
  EX: "EXTENSION", EY: "EXPRESSWAY", FR: "FERRY", FY: "FREEWAY",
  HY: "HIGHWAY", IN: "INTERCHANGE", LP: "LOOP", ML: "MALL",
  PA: "PATH", PE: "POINTE", PS: "PASS", PY: "PARKWAY", PZ: "PLAZA",
  RA: "RAMP", RW: "ROW", TL: "TRAIL", TR: "TERRACE",
  TT: "TRUCKTRAIL", WK: "WALK", WY: "WAY",
  STREET: "STREET", AVENUE: "AVENUE", BOULEVARD: "BOULEVARD",
  DRIVE: "DRIVE", LANE: "LANE", ROAD: "ROAD", COURT: "COURT",
  PLACE: "PLACE", CIRCLE: "CIRCLE", TERRACE: "TERRACE",
  PARKWAY: "PARKWAY", HIGHWAY: "HIGHWAY", TRAIL: "TRAIL",
  FREEWAY: "FREEWAY", EXPRESSWAY: "EXPRESSWAY", SQUARE: "SQUARE",
  PLAZA: "PLAZA", CROSSING: "CROSSING", POINT: "POINT",
  PKWY: "PARKWAY",
};

const CENSUS_SUFFIX_ABBREVIATIONS = {
  CRK: "CREEK", RLWY: "RAILWAY", "TRUCK TRL": "TRUCKTRAIL", RIV: "RIVER",
  AQUEDUCT: "AQUEDUCT", VIS: "VISTA", WASH: "WASH", RTE: "ROUTE",
  TROLLEY: "TROLLEY", RDG: "RIDGE", STRM: "STREAM", CNL: "CANAL",
  VW: "VIEW", DRIVEWAY: "DRIVEWAY", CRST: "CREST", BOUNDARY: "BOUNDARY",
  HTS: "HEIGHTS", ESTS: "ESTATES", FRK: "FORK", CHNNL: "CHANNEL",
  LNDG: "LANDING", GRADE: "GRADE", POINTE: "POINTE", CYN: "CANYON",
  STRIP: "STRIP", LAGOON: "LAGOON", PROMENADE: "PROMENADE", BLF: "BLUFF",
  PIER: "PIER", DITCH: "DITCH", LK: "LAKE", PSGE: "PASSAGE",
  ESPLANADE: "ESPLANADE", CUTOFF: "CUTOFF", WALKWAY: "WALKWAY", TRCE: "TRACE",
};

export const SUFFIX_CANON = { ...SUFFIX_ABBREVIATIONS, ...CENSUS_SUFFIX_ABBREVIATIONS };

/** Unicode-normalize, uppercase, trim, and collapse whitespace, per
 * spec.md 6.2's first bullet. Deliberately preserves `/`, `&`, `@`, and
 * hyphens -- semantically load-bearing (intersection separators;
 * hyphenated house-number forms) that must survive to later parsing. */
export function normalizeText(text) {
  let t = text.normalize("NFKC");
  t = t.toUpperCase().trim();
  t = t.replace(/\./g, ""); // "ST." / "N." -> "ST" / "N"
  t = t.replace(/\s+/g, " ");
  return t;
}

const UNIT_RE = /\s+(?:APT|APARTMENT|UNIT|STE|SUITE|BLDG|BUILDING|SPC|SPACE|LOT|RM|ROOM|#)\s*\S+$/;

export function stripUnitDesignator(text) {
  return text.replace(UNIT_RE, "").trim();
}

export function canonicalizeDirection(token) {
  return DIRECTION_CANON[token] ?? null;
}

export function canonicalizeSuffix(token) {
  return SUFFIX_CANON[token] ?? null;
}

// SanGIS zero-pads single-digit ordinal street numbers ("01ST", "02ND",
// ..., "09TH"), Census does not ("1ST", "2ND"). Scoped narrowly (digits
// immediately followed by ST/ND/RD/TH) so it can never touch a house number.
const LEADING_ZERO_ORDINAL_RE = /^0+(\d+(?:ST|ND|RD|TH))$/;

export function canonicalizeStreetCoreName(name) {
  const text = normalizeText(name);
  const m = LEADING_ZERO_ORDINAL_RE.exec(text);
  return m ? m[1] : text;
}

const BLOCK_RE = /^(\d+)\s+BLOCK(?:\s+OF)?\s+(.+)$/;

/** Recognize "1200 BLOCK OF MAIN ST" / "1200 BLOCK MAIN ST". Returns
 * [approximateNumber, remainder] or null. The caller marks the number
 * as approximate -- this only recognizes the shape. */
export function parseBlockNotation(text) {
  const m = BLOCK_RE.exec(text);
  if (!m) return null;
  return [Number(m[1]), m[2]];
}

// A '/' between two runs of digits (e.g. "123 1/2 MAIN ST") is very
// likely a fractional house-number suffix, not an intersection separator.
const FRACTION_SLASH_RE = /\d\s*\/\s*\d/;
const INTERSECTION_RE = /\s*(?:\/|&|@|\bAT\b)\s*/;

/** Recognize intersections separated by `/`, `&`, `@`, or `AT`, with or
 * without surrounding spaces. Returns [left, right] or null. Only
 * splits on the first separator found. */
export function splitIntersection(text) {
  if (FRACTION_SLASH_RE.test(text)) return null;
  const m = INTERSECTION_RE.exec(text);
  if (!m) return null;
  const left = text.slice(0, m.index).trim();
  const right = text.slice(m.index + m[0].length).trim();
  if (!left || !right) return null;
  return [left, right];
}

// Numbered routes: "HIGHWAY 80", "INTERSTATE 5", "STATE ROUTE 76", "SR 76",
// "US HIGHWAY 80". Deliberately conservative -- only tags a route
// number's presence, doesn't rewrite the spelling.
const HIGHWAY_RE = /\b(?:(?:US\s+)?(?:HWY|HIGHWAY)|INTERSTATE|FREEWAY|STATE\s+ROUTE|SR)\s*-?\s*(\d+)\b/;

/** Returns the route number if `text` contains a recognizable numbered
 * highway/route reference, else null. */
export function parseHighwayRoute(text) {
  const m = HIGHWAY_RE.exec(text);
  return m ? Number(m[1]) : null;
}

export class StreetName {
  constructor({ raw, pdir = null, name = "", suffix = null, postd = null, isHighway = false, routeNumber = null }) {
    this.raw = raw;
    this.pdir = pdir;
    this.name = name;
    this.suffix = suffix;
    this.postd = postd;
    this.isHighway = isHighway;
    this.routeNumber = routeNumber;
  }

  /** The normalized "PDIR NAME SUFFIX POSTD" key used to join across
   * sources / look up in an index. */
  canonicalKey() {
    return [this.pdir, this.name, this.suffix, this.postd].filter(Boolean).join(" ");
  }
}

/** Parse a single street name (no house number, no intersection --
 * callers split those first) into pre-direction / name / suffix /
 * post-direction components. Conservative: a trailing/leading token is
 * only pulled out as a direction or suffix if it's an exact known
 * match; anything else stays inside `name` untouched. */
export function parseStreetName(text) {
  const normalized = normalizeText(text);
  const routeNumber = parseHighwayRoute(normalized);
  if (routeNumber !== null) {
    return new StreetName({ raw: normalized, name: normalized, isHighway: true, routeNumber });
  }

  let tokens = normalized.split(" ");
  let pdir = null;
  if (tokens.length && canonicalizeDirection(tokens[0])) {
    pdir = canonicalizeDirection(tokens[0]);
    tokens = tokens.slice(1);
  }

  let postd = null;
  if (tokens.length > 1 && canonicalizeDirection(tokens[tokens.length - 1])) {
    postd = canonicalizeDirection(tokens[tokens.length - 1]);
    tokens = tokens.slice(0, -1);
  }

  let suffix = null;
  if (tokens.length > 1 && canonicalizeSuffix(tokens[tokens.length - 1])) {
    suffix = canonicalizeSuffix(tokens[tokens.length - 1]);
    tokens = tokens.slice(0, -1);
  }

  return new StreetName({ raw: normalized, pdir, name: tokens.join(" "), suffix, postd });
}

const HOUSE_NUMBER_RE = /^(\d+)\s+(.+)$/;

export class ParsedAddress {
  constructor({ raw, houseNumber = null, isBlockApproximate = false, isIntersection = false, streets = [] }) {
    this.raw = raw;
    this.houseNumber = houseNumber;
    this.isBlockApproximate = isBlockApproximate;
    this.isIntersection = isIntersection;
    this.streets = streets;
  }
}

/** Top-level entry point: parse a single free-text calls-feed-style
 * address. Shared by the compiler (Python side) and this runtime, per
 * spec.md 6.2's "one versioned normalization library" requirement. */
export function parseAddress(text) {
  const normalized = stripUnitDesignator(normalizeText(text));

  const intersection = splitIntersection(normalized);
  if (intersection) {
    const [left, right] = intersection;
    return new ParsedAddress({
      raw: normalized,
      isIntersection: true,
      streets: [parseStreetName(left), parseStreetName(right)],
    });
  }

  const block = parseBlockNotation(normalized);
  if (block) {
    const [number, remainder] = block;
    return new ParsedAddress({
      raw: normalized,
      houseNumber: number,
      isBlockApproximate: true,
      streets: [parseStreetName(remainder)],
    });
  }

  const m = HOUSE_NUMBER_RE.exec(normalized);
  if (m) {
    return new ParsedAddress({
      raw: normalized,
      houseNumber: Number(m[1]),
      streets: [parseStreetName(m[2])],
    });
  }

  // Street-only location, no house number.
  return new ParsedAddress({ raw: normalized, streets: [parseStreetName(normalized)] });
}
