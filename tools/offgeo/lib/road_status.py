"""SanGIS Roads-All status/confidence inclusion matrix (`OFF-101`, R1 Group A).

`spec.md` section 6.1 (compiler pipeline step 9, quoted in full):

    "SanGIS road status fields require an explicit inclusion matrix.
    Active/constructed addressable roads are eligible for ordinary
    confidence. Inactive, pending, private, unbuilt/of-record, or
    otherwise uncertain segments are excluded or placed in a separately
    scored fallback class only after validation against current address
    points. The compiler must report counts for every status/class rather
    than accepting all Roads - All rows."

This module is that inclusion matrix. The code meanings below are
transcribed verbatim from SanGIS's own field-domain documentation
(`Roads_All.shp.xml`, the FGDC metadata sidecar shipped inside the pinned
`sangis-roads-all` archive itself, `<attrlabl>SEGSTAT/DEDSTAT/PENDING/
FUNCLASS</attrlabl>` `<attrdef>` text) -- not guessed from the field
names or reconstructed from memory.

Deliberately conservative about EXCLUDED vs FALLBACK: spec.md's own
wording gates a real exclude-vs-fallback decision on validating against
current address points, which is `OFF-103` (R1 Group B), not this
reader. Only ABANDONED segments are excluded outright here -- everything
else this module considers uncertain is FALLBACK, not EXCLUDED, because
several of those categories (private streets, undedicated roads on
military/tribal/state land) plausibly carry real mailing addresses that
this reader alone has no basis to discard.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Code meanings, transcribed from Roads_All.shp.xml's <attrdef> text.
SEGSTAT_CODES = {
    "A": "Approved",
    "C": "Constructed",
    "M": "Maintained",
    "R": "Recorded",
    "T": "Tentative",
}
DEDSTAT_CODES = {
    "A": "Abandoned (no longer in use)",
    "D": "Dedicated (for public use, maintained by a Jurisdiction)",
    "L": "Dedicated, but unofficially named Alley",
    "O": "Offer for dedication (street reservation, not yet accepted)",
    "P": "Private street",
    "Q": "Undocumented",
    "U": "Undedicated (public use but no authority to dedicate, e.g. military/tribal/state land)",
}
# Only the FUNCLASS codes that are themselves a status signal, not a road
# *type* signal (most FUNCLASS values -- freeway, collector, local street,
# etc. -- describe use, not construction/legal status, and are out of scope
# for this inclusion matrix).
FUNCLASS_UNCERTAIN_CODES = {
    "7": "Private street",
    "P": "Paper street",
    "Q": "Undocumented",
}

ORDINARY = "ORDINARY"
FALLBACK = "FALLBACK"
EXCLUDED = "EXCLUDED"


@dataclass
class Classification:
    confidence: str
    reasons: list[str] = field(default_factory=list)


def classify_segment(segstat: str, dedstat: str, pending: str, funclass: str) -> Classification:
    """Classify one SanGIS Roads-All row's construction/legal status.
    Inputs are the raw DBF string values (may be blank)."""
    reasons: list[str] = []

    if dedstat == "A":
        return Classification(EXCLUDED, ["dedication status is Abandoned (no longer in use)"])

    if not segstat:
        reasons.append("SEGSTAT is blank -- treated as uncertain, not assumed Constructed")
    elif segstat in ("A", "R", "T"):
        reasons.append(f"SEGSTAT={segstat} ({SEGSTAT_CODES[segstat]}) -- not yet built/of-record")
    elif segstat not in ("C", "M"):
        reasons.append(f"SEGSTAT={segstat} is not a recognized code")

    if not dedstat:
        reasons.append("DEDSTAT is blank -- treated as uncertain, not assumed Dedicated")
    elif dedstat in ("P", "U", "O", "Q", "L"):
        reasons.append(f"DEDSTAT={dedstat} ({DEDSTAT_CODES[dedstat]})")
    elif dedstat != "D":
        reasons.append(f"DEDSTAT={dedstat} is not a recognized code")

    if pending == "Y":
        reasons.append("PENDING=Y -- recording pending, not yet finalized")

    if funclass in FUNCLASS_UNCERTAIN_CODES:
        reasons.append(f"FUNCLASS={funclass} ({FUNCLASS_UNCERTAIN_CODES[funclass]})")

    if reasons:
        return Classification(FALLBACK, reasons)
    return Classification(ORDINARY, ["SEGSTAT Constructed/Maintained, DEDSTAT Dedicated, not pending, ordinary FUNCLASS"])
