import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const packPath = join(__dirname, "..", "..", "offgeo", "packs", "v0", "sd-06073.ogp0");
const packBytes = readFileSync(packPath);

let originalFetch;
before(() => {
  originalFetch = globalThis.fetch;
  // geocoder.js fetches a relative URL ("offgeo/packs/v0/sd-06073.ogp0")
  // meant for a browser page's own origin -- serve the real pack bytes
  // from disk here instead of standing up an HTTP server for this test.
  globalThis.fetch = async (url) => {
    if (String(url).includes("sd-06073.ogp0")) {
      return {
        ok: true,
        status: 200,
        arrayBuffer: async () => packBytes.buffer.slice(packBytes.byteOffset, packBytes.byteOffset + packBytes.byteLength),
      };
    }
    throw new Error(`unexpected fetch: ${url}`);
  };
});
after(() => {
  globalThis.fetch = originalFetch;
});

// Import after the fetch mock is installed isn't required here since
// geocoder.js only calls fetch() lazily inside geocode()/getRoadLinesNear(),
// not at module-load time -- a top-level dynamic import is fine.
const { geocode, getRoadLinesNear } = await import("../../src/offgeo/geocoder.js");

test("geocodes a real known landmark within a plausible distance of its real coordinate", async () => {
  // 611 W G St, downtown San Diego -- one of the three real SanGIS
  // control points already used in tools/offgeo/tests for CRS validation.
  const result = await geocode("611 W G ST");
  assert.ok(result, "expected a match");
  assert.ok(result.lat > 32.5 && result.lat < 33.5, "latitude should be in San Diego County");
  assert.ok(result.lon > -117.7 && result.lon < -116.0, "longitude should be in San Diego County");
  // R1's own benchmark found 35.8m median / 215.5m p95 error against
  // real ground truth -- 1km is a generous plausibility bound, not a
  // precision claim.
  const R = 6371000;
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(result.lat - 32.71225);
  const dLon = toRad(result.lon - -117.16857);
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(32.71225)) * Math.cos(toRad(result.lat)) * Math.sin(dLon / 2) ** 2;
  const distanceMeters = 2 * R * Math.asin(Math.sqrt(a));
  assert.ok(distanceMeters < 1000, `expected within 1km of the real address, got ${distanceMeters.toFixed(0)}m`);
});

test("returns a confidence and reason on a successful match", async () => {
  const result = await geocode("611 W G ST");
  assert.ok(["ORDINARY", "FALLBACK", "EXCLUDED"].includes(result.confidence));
  assert.equal(result.reason, "exact-range");
});

test("returns null for an intersection (not supported in v0)", async () => {
  const result = await geocode("MAIN ST/ELM ST");
  assert.equal(result, null);
});

test("returns null for a bare highway address (no route-based lookup in v0)", async () => {
  const result = await geocode("INTERSTATE 5");
  assert.equal(result, null);
});

test("returns null for an unparseable/empty address rather than throwing", async () => {
  assert.equal(await geocode(""), null);
  assert.equal(await geocode(null), null);
});

test("returns null for a street that doesn't exist in the pack", async () => {
  const result = await geocode("100 NOT A REAL STREET NAME XYZ");
  assert.equal(result, null);
});

test("getRoadLinesNear returns ORDINARY-confidence lines within the given bounds", async () => {
  const bounds = { minLat: 32.70, maxLat: 32.72, minLon: -117.18, maxLon: -117.16 };
  const lines = await getRoadLinesNear(bounds);
  assert.ok(lines.length > 0, "expected at least one road line near downtown San Diego");
  for (const line of lines.slice(0, 5)) {
    assert.ok(Array.isArray(line));
    assert.ok(line.length >= 2);
    assert.ok(Array.isArray(line[0]) && line[0].length === 2);
  }
});

test("getRoadLinesNear returns nothing for a bounding box far outside the county", async () => {
  const bounds = { minLat: 0, maxLat: 0.01, minLon: 0, maxLon: 0.01 };
  const lines = await getRoadLinesNear(bounds);
  assert.equal(lines.length, 0);
});
