# Attribution and derived-product notice draft

Status: Drafted 2026-08-23 — content only, no pack/UI exists yet to place it in
Scope: closes the R0 deliverable "attribution and derived-product notice draft" and the exit-gate bullet "source notices are ready to place in the pack manifest and UI" ([`todo.md`](./todo.md), [`roadmap.md`](./roadmap.md) §4). Every fact below is copied from [`tools/offgeo/config/sources.lock.json`](../../tools/offgeo/config/sources.lock.json) — the sole authority for these strings per `OFF-006` — not re-worded from memory. Where `spec.md` mandates specific required language (Census citation/repackaging notice, derived-product status), that requirement is quoted and satisfied verbatim, not paraphrased.

This is a draft of **content**, not a wired feature: there is no pack yet (R2, `notices/<version>.txt` per `roadmap.md` §3's layout), and no offline-data-card UI yet (R5, `OFF-501`). Both future pieces of work should copy from this file rather than re-deriving the required legal language from the sources fresh.

## Requirement this satisfies (quoted, not paraphrased)

- `spec.md` §4: "U.S. government works are not copyright-protected under 17 U.S.C. §105. The Census documentation requests source citation and a conspicuous repackaging notice. Every published pack and the download UI must therefore identify the Census Bureau as a source, link the documentation, include the source vintage, and state that the pack is a derived product not endorsed by the Census Bureau."
- `spec.md` §17 (acceptance scenario 8): "Pack credits expose publisher, source, vintage, retrieval date, and derived-product notice."
- `roadmap.md` `OFF-709` (R7): "Include every government publisher, vintage, source link, derived-product notice, and Census citation/repackaging language."

## Draft: `notices/<version>.txt` (full pack notice)

This is the literal draft content for the file `roadmap.md` §3's repository layout places at `offgeo/notices/<version>.txt`, generated once R2's `OFF-210` produces real release artifacts. `<version>` and `<retrieval date>` are placeholders until an actual release exists; every other line is final, sourced word-for-word from the lock file.

```text
OffGeo San Diego County (06073) — Data Sources and Notices
Pack version: <version>
Generated: <build timestamp>

This pack is a derived product built from the following public government
sources. It is not endorsed by, and does not represent, any of the
publishers below.

1. SanGIS/SANDAG — Roads - All
   Source: SanGIS/SANDAG, Roads - All. Public domain (ODC-PDDL).
   License: Open Data Commons Public Domain Dedication and Licence (ODC-PDDL) 1.0
     https://opendefinition.org/licenses/odc-pddl/
   Documentation: https://data.sandiego.gov/datasets/gis-roads-all/
   Publisher-displayed vintage: 2026-08-10
   Retrieved: 2026-08-23 (SHA-256 c432371b4011572ae8e2c135087d359c9f62b65e36e33c89fc675b9e78356694)

2. SanGIS/SANDAG — Address Points to APN
   Source: SanGIS/SANDAG, Address Points to APN. Public domain (ODC-PDDL).
     APN/parcel/unit fields are excluded from any derived output.
   License: Open Data Commons Public Domain Dedication and Licence (ODC-PDDL) 1.0
     https://opendefinition.org/licenses/odc-pddl/
   Documentation: https://data.sandiego.gov/datasets/gis-address-points-apn/
   Publisher-displayed vintage: 2026-08-10
   Retrieved: 2026-08-23 (SHA-256 a792711074d4d07543826e2228c42d56fb9c375261295efbd551334c825853b0)

3. U.S. Census Bureau — TIGER/Line ADDRFEAT (San Diego County, 06073)
   Source: U.S. Census Bureau, TIGER/Line Shapefiles 2025, ADDRFEAT.
     This is a derived product, not endorsed by the Census Bureau.
   License: U.S. Government work, not copyright-protected (17 U.S.C. §105);
     Census Bureau requests citation.
   Documentation: https://www2.census.gov/geo/pdfs/maps-data/data/tiger/tgrshp2025/TGRSHP2025_TechDoc.pdf
   Publisher-displayed vintage: TIGER2025
   Retrieved: 2026-08-23 (SHA-256 750f9eaf9d00d11bfbd8eb4ab030d386c27fbe03fe510a67ec14789842161a8b)

4. U.S. Census Bureau — TIGER/Line FEATNAMES (San Diego County, 06073)
   Source: U.S. Census Bureau, TIGER/Line Shapefiles 2025, FEATNAMES.
     This is a derived product, not endorsed by the Census Bureau.
   License: U.S. Government work, not copyright-protected (17 U.S.C. §105);
     Census Bureau requests citation.
   Documentation: https://www2.census.gov/geo/pdfs/maps-data/data/tiger/tgrshp2025/TGRSHP2025_TechDoc.pdf
   Publisher-displayed vintage: TIGER2025
   Retrieved: 2026-08-23 (SHA-256 454d8bb0c4e187c48d6f11d0c8709af4db69f118d6545b63407835b02393d045)

Address ranges, road geometry, and community names in this pack are
estimates derived by combining the sources above; they are not authoritative
addresses and must not be used for emergency dispatch, legal, or survey
purposes. See the accompanying pack manifest for the exact build/compiler
version that produced this file.
```

## Draft: offline-data-card UI copy (short form)

For `spec.md` §11.1's "Data sources/attribution and an expandable accuracy explanation" (built at R5, `OFF-501`). Two layers: a one-line always-visible summary, and the expandable detail using the same source list as above.

**Always-visible summary line:**

> Address data from SanGIS/SANDAG and the U.S. Census Bureau (TIGER/Line). Public domain / U.S. government works — this app's estimates are not officially endorsed.

**Expandable detail** (same four entries as the full notice above, condensed per-source to: publisher, dataset name, vintage, one-line license, documentation link):

```text
SanGIS/SANDAG — Roads - All
  Public domain (ODC-PDDL) · vintage 2026-08-10 · data.sandiego.gov/datasets/gis-roads-all

SanGIS/SANDAG — Address Points to APN
  Public domain (ODC-PDDL) · vintage 2026-08-10 · data.sandiego.gov/datasets/gis-address-points-apn
  (parcel/APN/unit fields excluded from this app)

U.S. Census Bureau — TIGER/Line ADDRFEAT, San Diego County
  U.S. government work, not copyright-protected · TIGER2025
  Derived product — not endorsed by the Census Bureau

U.S. Census Bureau — TIGER/Line FEATNAMES, San Diego County
  U.S. government work, not copyright-protected · TIGER2025
  Derived product — not endorsed by the Census Bureau
```

**Accuracy explanation** (the other half of the same UI element, per `spec.md` §11.1 — drafted now since it belongs next to the notices above, though it depends on numbers R1/R2 haven't produced yet):

> Locations are estimated by matching addresses to road segments and interpolating along them — not measured at the actual building. Accuracy varies by street; some addresses may not match at all. [Placeholder: link to the R1/R2 accuracy/coverage report once it exists — `roadmap.md` §13 "Final quality thresholds," due R1 exit.]

## What's still open, deliberately not drafted here

- The exact build timestamp / pack version placeholders above can't be filled until a real pack exists (R2, `OFF-210`).
- The accuracy explanation's specific numbers depend on the R1 feasibility benchmark (`roadmap.md` §5) and R1's "Final quality thresholds" decision (`roadmap.md` §13) — neither exists yet.
- Where this text actually gets wired into `notices/<version>.txt` generation and the offline-data-card component is `OFF-210`/`OFF-701` (R2) and `OFF-501` (R5) respectively — this document is copy-ready content for both, not the implementation of either.
