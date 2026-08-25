import { test, before, after, beforeEach } from "node:test";
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
  // pack-engine.js fetches a relative URL meant for a browser page's (or
  // worker's) own origin -- serve the real pack bytes from disk here
  // instead of standing up an HTTP server for this test.
  globalThis.fetch = async () => ({
    ok: true,
    status: 200,
    arrayBuffer: async () =>
      packBytes.buffer.slice(packBytes.byteOffset, packBytes.byteOffset + packBytes.byteLength),
  });
});
after(() => {
  globalThis.fetch = originalFetch;
});

// This is the exact module pack-worker.js runs inside the real Web
// Worker -- tested directly here since Node has no global `Worker` to
// exercise the worker boundary itself (that's covered by the real
// Chromium E2E run in tests/e2e/run.mjs instead).
const { geocode, getRoadLinesNear, _resetStateForTests } = await import("../../src/offgeo/pack-engine.js");

beforeEach(() => {
  _resetStateForTests();
});

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
  for (const { points, label } of lines.slice(0, 5)) {
    assert.ok(Array.isArray(points));
    assert.ok(points.length >= 2);
    assert.ok(Array.isArray(points[0]) && points[0].length === 2);
    assert.ok(label === null || typeof label === "string");
  }
});

test("getRoadLinesNear labels at most one segment per distinct street name", async () => {
  const bounds = { minLat: 32.70, maxLat: 32.72, minLon: -117.18, maxLon: -117.16 };
  const lines = await getRoadLinesNear(bounds);
  const labels = lines.map((l) => l.label).filter(Boolean);
  assert.ok(labels.length > 0, "expected at least one labeled street");
  assert.equal(labels.length, new Set(labels).size, "labels should be unique -- one per street name, not per segment");
});

test("getRoadLinesNear returns nothing for a bounding box far outside the county", async () => {
  const bounds = { minLat: 0, maxLat: 0.01, minLon: 0, maxLon: 0.01 };
  const lines = await getRoadLinesNear(bounds);
  assert.equal(lines.length, 0);
});

test("getRoadLinesNear stays fast for a world-spanning bounding box (regression)", async () => {
  // Real bug found live: Leaflet's getBounds() at very low (zoomed-out)
  // zoom legitimately spans most of the globe. Without clamping the
  // query to the pack's own known extent first, the grid-cell loop
  // iterated the whole requested range regardless of where the actual
  // data was -- a measured 25+ second stall in the browser. This must
  // stay well under a second.
  const worldBounds = { minLat: -85, maxLat: 85, minLon: -180, maxLon: 180 };
  const t0 = Date.now();
  const lines = await getRoadLinesNear(worldBounds);
  const elapsedMs = Date.now() - t0;
  assert.ok(elapsedMs < 3000, `expected well under 3s, took ${elapsedMs}ms`);
  assert.ok(lines.length > 0, "a world-spanning box should still match San Diego County roads");
  assert.ok(lines.length <= 600, "should still respect the MAX_LINES_PER_QUERY cap");
});
