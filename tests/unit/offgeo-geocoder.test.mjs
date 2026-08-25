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
const { geocode, _resetStateForTests } = await import("../../src/offgeo/pack-engine.js");

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

