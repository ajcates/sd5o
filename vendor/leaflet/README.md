# Vendored Leaflet

Version: 1.9.4
Source: `https://unpkg.com/leaflet@1.9.4/dist/` (`leaflet.js`, `leaflet.css`, `images/*`)
License: BSD-2-Clause (see https://github.com/Leaflet/Leaflet/blob/main/LICENSE)
Retrieved: 2026-08-23

Self-hosted so the app has no runtime dependency on a CDN. This is the
library only -- no map tile imagery is vendored or fetched from any tile
server (see `notes/offgeo/index-html-audit.md` / the map prototype notes
for why: bulk-mirroring a public raster tile server would violate its
usage policy). The map view draws SanGIS road-line geometry instead of a
tile basemap.

To update: re-download the three files above at a newer version tag and
update this note's version/date.
