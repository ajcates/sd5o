"""Shared address/street-name normalization library (`OFF-102`, R1 Group A).

`spec.md` section 6.2 requires "one versioned normalization library and
fixture suite" shared by the compiler and the runtime parser -- this is
that library. Nothing here is compiler- or runtime-specific; both the
future R1 source readers (`OFF-101`) and the eventual browser-side address
parser (R4) import from this one module so their notion of "canonical
street name" can never drift apart.

Canonical forms chosen here, and why:

- **Suffix canonical form is the full spelled-out word** (`"BOULEVARD"`,
  not `"BLVD"` or `"BL"`). SanGIS alone uses *two different* abbreviation
  systems for the same concept -- compare its 30-character `RD30SFX`
  table (up to 4 letters, e.g. `BLVD`) with its 20-character `RD20SFX`
  table (always 2 letters, e.g. `BL`) -- and the live calls feed uses yet
  a third convention (`tools/offgeo/build-address-index.py`'s
  `FEED_SUFFIX_ALIASES` already found `"BLVD"` vs `"BL"` for the same
  real street). The full word is the only form all three abbreviation
  systems can be collapsed into without picking one source's convention
  as privileged over another.
- **Direction canonical form is the short code** (`"N"`, not `"NORTH"`),
  because that already matches how every source in this project
  represents directions natively (SanGIS `RD30PRED`/`RD20PRED`/`ADDRPDIR`,
  Census `LFROMTYP`-adjacent direction fields) -- there is no "the sources
  disagree" problem to resolve here the way there is for suffixes.

Both tables are transcribed from SanGIS's own official field-domain
documentation (`Roads_All.shp.xml`, the FGDC metadata sidecar shipped
inside the pinned `sangis-roads-all` archive itself -- see
`RD30SFX`/`RD20SFX`/`RD30PRED`'s `<attrdef>` text), not reconstructed from
memory or guessed from abbreviation conventions in general.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

NORMALIZE_VERSION = 1

# --- Direction canonicalization ---------------------------------------------
# Canonical form: the short code, matching every source's own native
# representation (SanGIS RD30PRED/RD20PRED/ADDRPDIR; RD20PRED further folds
# NE/NW into N and SE/SW into S at the 20-char level, but this library keeps
# the full 8-point compass since RD30PRED and the live feed both use it).
DIRECTION_CANON: dict[str, str] = {}
for _code, _word in [
    ("N", "NORTH"),
    ("S", "SOUTH"),
    ("E", "EAST"),
    ("W", "WEST"),
    ("NE", "NORTHEAST"),
    ("NW", "NORTHWEST"),
    ("SE", "SOUTHEAST"),
    ("SW", "SOUTHWEST"),
]:
    DIRECTION_CANON[_code] = _code
    DIRECTION_CANON[_word] = _code

# Travel-direction prefixes seen on real numbered-route intersections in the
# live feed (e.g. "NB INTERSTATE 5") are a genuinely different concept from a
# street pre/post directional -- "northbound" describes a direction of
# travel on a route, not a component of the route's own name the way "N Main
# St" and "Main St N" differ. Deliberately NOT folded into DIRECTION_CANON:
# collapsing "NB Interstate 5" and "N Interstate 5" together would assert an
# equivalence this library has no evidence for. Recognized only so callers
# can tell "this token is a known travel-direction marker" from "this token
# is unrecognized," never silently canonicalized into a street direction.
TRAVEL_DIRECTION_MARKERS = {"NB", "SB", "EB", "WB"}

# --- Suffix canonicalization -------------------------------------------------
# Canonical form: the full spelled-out word. Sourced from SanGIS's own
# RD30SFX ("SanGIS standards manual", up to 4 letters) and RD20SFX (always 2
# letters) field-domain tables in Roads_All.shp.xml, merged since both name
# the same set of street types under two different abbreviation lengths.
_SUFFIX_ABBREVIATIONS: dict[str, str] = {
    # RD30SFX (4-letter) table
    "ALY": "ALLEY", "ARC": "ARCADE", "AVE": "AVENUE", "BP": "BIKEPATH",
    "BLVD": "BOULEVARD", "BRG": "BRIDGE", "BYP": "BYPASS", "CSWY": "CAUSEWAY",
    "CIR": "CIRCLE", "CP": "CAPE", "CTE": "CORTE", "CT": "COURT", "CV": "COVE",
    "CRES": "CRESCENT", "XING": "CROSSING", "DR": "DRIVE", "DRWY": "DRIVEWAY",
    "EXPY": "EXPRESSWAY", "EXT": "EXTENSION", "FRY": "FERRY", "FWY": "FREEWAY",
    "GLEN": "GLEN", "HWY": "HIGHWAY", "INTR": "INTERCHANGE", "LN": "LANE",
    "LOOP": "LOOP", "MALL": "MALL", "PKY": "PARKWAY", "PASS": "PASS",
    "PATH": "PATH", "PL": "PLACE", "PLZ": "PLAZA", "PT": "POINT",
    "PTE": "POINTE", "RAMP": "RAMP", "RD": "ROAD", "ROW": "ROW", "SQ": "SQUARE",
    "ST": "STREET", "TER": "TERRACE", "TRL": "TRAIL", "TKTL": "TRUCKTRAIL",
    "WALK": "WALK", "WAY": "WAY",
    # RD20SFX (2-letter) table -- same concepts, shorter codes. Only entries
    # that differ from the RD30SFX spellings above are added; duplicates
    # (DR, LN, PL, PT, RD, ST) are already covered.
    "AL": "ALLEY", "AR": "ARCADE", "AV": "AVENUE", "BL": "BOULEVARD",
    "BR": "BRIDGE", "BY": "BYPASS", "CE": "CORTE", "CG": "CROSSING",
    "CR": "CIRCLE", "CS": "CRESCENT", "CY": "CAUSEWAY", "DY": "DRIVEWAY",
    "EX": "EXTENSION", "EY": "EXPRESSWAY", "FR": "FERRY", "FY": "FREEWAY",
    "HY": "HIGHWAY", "IN": "INTERCHANGE", "LP": "LOOP", "ML": "MALL",
    "PA": "PATH", "PE": "POINTE", "PS": "PASS", "PY": "PARKWAY", "PZ": "PLAZA",
    "RA": "RAMP", "RW": "ROW", "TL": "TRAIL", "TR": "TERRACE",
    "TT": "TRUCKTRAIL", "WK": "WALK", "WY": "WAY",
    # Common USPS-style long forms and other spellings observed in the real
    # calls-feed fixture corpus (tests/offgeo/fixtures/addresses.json) that
    # aren't literal SanGIS domain codes but must still collapse to the same
    # canonical word.
    "STREET": "STREET", "AVENUE": "AVENUE", "BOULEVARD": "BOULEVARD",
    "DRIVE": "DRIVE", "LANE": "LANE", "ROAD": "ROAD", "COURT": "COURT",
    "PLACE": "PLACE", "CIRCLE": "CIRCLE", "TERRACE": "TERRACE",
    "PARKWAY": "PARKWAY", "HIGHWAY": "HIGHWAY", "TRAIL": "TRAIL",
    "FREEWAY": "FREEWAY", "EXPRESSWAY": "EXPRESSWAY", "SQUARE": "SQUARE",
    "PLAZA": "PLAZA", "CROSSING": "CROSSING", "POINT": "POINT",
    "PKWY": "PARKWAY",
}

# Census TIGER/Line FEATNAMES abbreviations (its own `SUFTYPABRV` field)
# not covered by SanGIS's two domain tables above -- found by running
# tools/offgeo/reconcile-sangis-census-streets.py against the real
# retained archive and checking every `SUFTYPABRV` value that failed to
# canonicalize (38 distinct tokens, 6,328 of 126,976 non-blank rows,
# ~5%). These are standard geographic-feature-suffix abbreviations, not
# SanGIS-domain-table entries, so unlike the block above they are this
# library's own best-effort spellings rather than a transcription from
# an official field-domain document -- same standard this project
# already applied to `FEED_SUFFIX_ALIASES` in
# tools/offgeo/build-address-index.py (real evidence, human-mapped,
# explicitly disclosed as such). "TRUCK TRL" maps to the same
# "TRUCKTRAIL" canonical form SanGIS's own TKTL/TT already use, so a
# truck trail named in both sources still collapses to one key.
# Deliberately does NOT include "TRANS LN" or "JEEP TRL" (104 and 3
# rows) -- their expansions aren't obvious enough to guess confidently;
# they stay unmapped (canonicalize_suffix returns None) rather than risk
# asserting a wrong equivalence.
_CENSUS_SUFFIX_ABBREVIATIONS: dict[str, str] = {
    "CRK": "CREEK", "RLWY": "RAILWAY", "TRUCK TRL": "TRUCKTRAIL", "RIV": "RIVER",
    "AQUEDUCT": "AQUEDUCT", "VIS": "VISTA", "WASH": "WASH", "RTE": "ROUTE",
    "TROLLEY": "TROLLEY", "RDG": "RIDGE", "STRM": "STREAM", "CNL": "CANAL",
    "VW": "VIEW", "DRIVEWAY": "DRIVEWAY", "CRST": "CREST", "BOUNDARY": "BOUNDARY",
    "HTS": "HEIGHTS", "ESTS": "ESTATES", "FRK": "FORK", "CHNNL": "CHANNEL",
    "LNDG": "LANDING", "GRADE": "GRADE", "POINTE": "POINTE", "CYN": "CANYON",
    "STRIP": "STRIP", "LAGOON": "LAGOON", "PROMENADE": "PROMENADE", "BLF": "BLUFF",
    "PIER": "PIER", "DITCH": "DITCH", "LK": "LAKE", "PSGE": "PASSAGE",
    "ESPLANADE": "ESPLANADE", "CUTOFF": "CUTOFF", "WALKWAY": "WALKWAY", "TRCE": "TRACE",
}
SUFFIX_CANON: dict[str, str] = {**_SUFFIX_ABBREVIATIONS, **_CENSUS_SUFFIX_ABBREVIATIONS}


def normalize_text(text: str) -> str:
    """Unicode-normalize, uppercase, trim, and collapse whitespace, per
    spec.md 6.2's first bullet. Deliberately preserves `/`, `&`, `@`, and
    hyphens: those are semantically load-bearing (intersection separators;
    hyphenated house-number forms like "145-100" that spec.md 6.3 forbids
    coercing with parseInt) and must survive to the later parsing stages,
    not be stripped as "non-semantic punctuation" here."""
    text = unicodedata.normalize("NFKC", text)
    text = text.upper().strip()
    text = text.replace(".", "")  # "ST." / "N." -> "ST" / "N"
    text = re.sub(r"\s+", " ", text)
    return text


_UNIT_RE = re.compile(
    r"\s+(?:APT|APARTMENT|UNIT|STE|SUITE|BLDG|BUILDING|SPC|SPACE|LOT|RM|ROOM|#)\s*\S+$"
)


def strip_unit_designator(text: str) -> str:
    """Remove a trailing unit designator and its value, per spec.md 6.2's
    "remove unit designators and unit numbers from matching input." Only
    strips from the end -- a unit designator embedded mid-string would be
    unusual and safer to leave for a human/fixture to classify than to
    guess at."""
    return _UNIT_RE.sub("", text).strip()


def canonicalize_direction(token: str) -> str | None:
    """Return the canonical short direction code for `token`, or None if
    `token` isn't a recognized direction (including travel-direction
    markers like "NB" -- see TRAVEL_DIRECTION_MARKERS above)."""
    return DIRECTION_CANON.get(token)


def canonicalize_suffix(token: str) -> str | None:
    """Return the canonical full-word suffix for `token`, or None if
    `token` isn't a recognized street-type suffix."""
    return SUFFIX_CANON.get(token)


# Found via tools/offgeo/reconcile-sangis-census-streets.py's real
# cross-source street-key comparison, not guessed in advance: SanGIS
# zero-pads single-digit ordinal street numbers ("01ST", "02ND", ...,
# "09TH" -- 2,018 SanGIS road segments use this form, e.g. downtown San
# Diego's 1st through 9th Avenue), while Census TIGER/Line spells the
# same streets "1ST", "2ND", etc. Without stripping this, every one of
# those streets would silently fail to cross-reference between the two
# sources -- not a rare edge case, since numbered downtown streets are
# common addresses. Scoped narrowly (only digits immediately followed by
# ST/ND/RD/TH) so it can never touch an actual house number, which lives
# in a separate field/token everywhere this library is used.
_LEADING_ZERO_ORDINAL_RE = re.compile(r"^0+(\d+(?:ST|ND|RD|TH))$")


def canonicalize_street_core_name(name: str) -> str:
    """Canonicalize the core (non-direction, non-suffix) portion of a
    street name for cross-source/cross-component matching. Callers that
    already have raw text should pass it through `normalize_text` first
    or rely on this function's own internal call -- either is safe since
    `normalize_text` is idempotent."""
    text = normalize_text(name)
    m = _LEADING_ZERO_ORDINAL_RE.match(text)
    return m.group(1) if m else text


_BLOCK_RE = re.compile(r"^(\d+)\s+BLOCK(?:\s+OF)?\s+(.+)$")


def parse_block_notation(text: str) -> tuple[int, str] | None:
    """Recognize "1200 BLOCK OF MAIN ST" / "1200 BLOCK MAIN ST" per
    spec.md 6.2. Returns (approximate_number, remainder) or None. The
    caller is responsible for marking the returned number as approximate
    -- this function only recognizes the shape, it doesn't know how the
    caller will score confidence."""
    m = _BLOCK_RE.match(text)
    if not m:
        return None
    return int(m.group(1)), m.group(2)


# A '/' between two runs of digits (e.g. "123 1/2 MAIN ST") is very likely a
# fractional house-number suffix, not an intersection separator -- guard
# against splitting those. No such case exists in the current fixture
# corpus, but the ambiguity is real and worth guarding rather than assuming
# away.
_FRACTION_SLASH_RE = re.compile(r"\d\s*/\s*\d")
_INTERSECTION_RE = re.compile(r"\s*(?:/|&|@|\bAT\b)\s*")


def split_intersection(text: str) -> tuple[str, str] | None:
    """Recognize intersections separated by `/`, `&`, `@`, or `AT`, with or
    without surrounding spaces, per spec.md 6.2. Returns (left, right) or
    None if `text` doesn't look like an intersection. Only splits on the
    first separator found -- a text with more than one separator is
    unusual enough to leave to a human/fixture rather than guess a
    three-way split."""
    if _FRACTION_SLASH_RE.search(text):
        return None
    parts = _INTERSECTION_RE.split(text, maxsplit=1)
    if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
        return None
    return parts[0].strip(), parts[1].strip()


# Numbered routes: "HIGHWAY 80", "INTERSTATE 5", "STATE ROUTE 76", "SR 76",
# "US HIGHWAY 80". Deliberately conservative per spec.md 6.2 ("normalize
# highway and route forms conservatively") -- this only tags a route
# number's presence; it does not attempt to rewrite "STATE ROUTE 76" and
# "SR 76" into one one canonical spelling, since collapsing those without
# more real examples risks conflating distinct route-naming conventions.
_HIGHWAY_RE = re.compile(
    r"\b(?:(?:US\s+)?(?:HWY|HIGHWAY)|INTERSTATE|FREEWAY|STATE\s+ROUTE|SR)\s*-?\s*(\d+)\b"
)


def parse_highway_route(text: str) -> int | None:
    """Return the route number if `text` contains a recognizable numbered
    highway/route reference, else None. A leading travel-direction marker
    (e.g. "NB INTERSTATE 5") is left in place in the caller's raw text --
    this function only extracts the number, it doesn't rewrite the
    string."""
    m = _HIGHWAY_RE.search(text)
    return int(m.group(1)) if m else None


@dataclass
class StreetName:
    raw: str
    pdir: str | None = None
    name: str = ""
    suffix: str | None = None
    postd: str | None = None
    is_highway: bool = False
    route_number: int | None = None

    def canonical_key(self) -> str:
        """The normalized "PDIR NAME SUFFIX POSTD" key used to join across
        sources / look up in an index, matching the convention already
        established by tools/offgeo/build-address-index.py's street_key()."""
        parts = [self.pdir, self.name, self.suffix, self.postd]
        return " ".join(p for p in parts if p)


def parse_street_name(text: str) -> StreetName:
    """Parse a single street name (no house number, no intersection --
    callers split those first) into pre-direction / name / suffix /
    post-direction components. Conservative: a trailing/leading token is
    only pulled out as a direction or suffix if it's an exact known match;
    anything else is left inside `name` untouched (e.g. "EL CAMINO REAL"
    keeps "REAL" as part of the name -- it is not a recognized suffix, and
    guessing would risk mangling a real proper name)."""
    text = normalize_text(text)
    route_number = parse_highway_route(text)
    if route_number is not None:
        return StreetName(raw=text, name=text, is_highway=True, route_number=route_number)

    tokens = text.split(" ")
    pdir = None
    if tokens and canonicalize_direction(tokens[0]):
        pdir = canonicalize_direction(tokens[0])
        tokens = tokens[1:]

    postd = None
    if len(tokens) > 1 and canonicalize_direction(tokens[-1]):
        postd = canonicalize_direction(tokens[-1])
        tokens = tokens[:-1]

    suffix = None
    if len(tokens) > 1 and canonicalize_suffix(tokens[-1]):
        suffix = canonicalize_suffix(tokens[-1])
        tokens = tokens[:-1]

    return StreetName(raw=text, pdir=pdir, name=" ".join(tokens), suffix=suffix, postd=postd)


_HOUSE_NUMBER_RE = re.compile(r"^(\d+)\s+(.+)$")


@dataclass
class ParsedAddress:
    raw: str
    house_number: int | None = None
    is_block_approximate: bool = False
    is_intersection: bool = False
    streets: list[StreetName] = field(default_factory=list)


def parse_address(text: str) -> ParsedAddress:
    """Top-level entry point tying the pieces above together for a single
    free-text calls-feed-style address. This is the shared function the
    future R4 runtime parser and any R1 compiler-side fixture validation
    both call, per spec.md 6.2's "one versioned normalization library"
    requirement."""
    text = strip_unit_designator(normalize_text(text))

    intersection = split_intersection(text)
    if intersection:
        left, right = intersection
        return ParsedAddress(
            raw=text,
            is_intersection=True,
            streets=[parse_street_name(left), parse_street_name(right)],
        )

    block = parse_block_notation(text)
    if block:
        number, remainder = block
        return ParsedAddress(
            raw=text,
            house_number=number,
            is_block_approximate=True,
            streets=[parse_street_name(remainder)],
        )

    m = _HOUSE_NUMBER_RE.match(text)
    if m:
        return ParsedAddress(
            raw=text,
            house_number=int(m.group(1)),
            streets=[parse_street_name(m.group(2))],
        )

    # Street-only location, no house number (e.g. a named location with no
    # address component). Not an error -- spec.md 6.2 explicitly lists
    # "street-only locations" as a required fixture category.
    return ParsedAddress(raw=text, streets=[parse_street_name(text)])
