import { test } from "node:test";
import assert from "node:assert/strict";
import {
  haversineMeters,
  polylineLengthMeters,
  interpolateAlongPolyline,
  rangeFraction,
} from "../../src/offgeo/interpolate.js";

test("haversineMeters: same point is zero distance", () => {
  assert.ok(Math.abs(haversineMeters(32.71225, -117.16857, 32.71225, -117.16857)) < 1e-9);
});

test("haversineMeters: known short distance is plausible", () => {
  // 611 W G St and 1500 El Prado (Balboa Park), real SanGIS control points -- ~2.3-2.8km apart.
  const d = haversineMeters(32.71225, -117.16857, 32.73187, -117.14959);
  assert.ok(d > 2000 && d < 3000, `expected ~2-3km, got ${d}`);
});

test("polylineLengthMeters: two-point line matches haversine", () => {
  const points = Float64Array.from([32.0, -117.0, 32.001, -117.001]);
  const length = polylineLengthMeters(points);
  const expected = haversineMeters(32.0, -117.0, 32.001, -117.001);
  assert.ok(Math.abs(length - expected) < expected * 0.01);
});

test("polylineLengthMeters: single point has zero length", () => {
  assert.equal(polylineLengthMeters(Float64Array.from([32.0, -117.0])), 0);
});

test("polylineLengthMeters: multi-vertex length is the sum of segments", () => {
  const points = Float64Array.from([32.0, -117.0, 32.001, -117.0, 32.001, -117.001]);
  const total = polylineLengthMeters(points);
  const a = polylineLengthMeters(points.subarray(0, 4));
  const b = polylineLengthMeters(points.subarray(2, 6));
  assert.ok(Math.abs(total - (a + b)) < 0.01);
});

test("interpolateAlongPolyline: fraction 0 returns the first vertex", () => {
  const points = Float64Array.from([32.0, -117.0, 32.01, -117.01]);
  const [lat, lon] = interpolateAlongPolyline(points, 0);
  assert.equal(lat, 32.0);
  assert.equal(lon, -117.0);
});

test("interpolateAlongPolyline: fraction 1 returns the last vertex", () => {
  const points = Float64Array.from([32.0, -117.0, 32.01, -117.01]);
  const [lat, lon] = interpolateAlongPolyline(points, 1);
  assert.ok(Math.abs(lat - 32.01) < 1e-6);
  assert.ok(Math.abs(lon - -117.01) < 1e-6);
});

test("interpolateAlongPolyline: fraction 0.5 on a straight line is the midpoint", () => {
  const points = Float64Array.from([32.0, -117.0, 32.01, -117.0]); // due north, constant longitude
  const [lat, lon] = interpolateAlongPolyline(points, 0.5);
  assert.ok(Math.abs(lat - 32.005) < 1e-4);
  assert.ok(Math.abs(lon - -117.0) < 1e-6);
});

test("interpolateAlongPolyline: fraction is clamped to [0, 1]", () => {
  const points = Float64Array.from([32.0, -117.0, 32.01, -117.01]);
  assert.deepEqual(interpolateAlongPolyline(points, -0.5), interpolateAlongPolyline(points, 0));
  assert.deepEqual(interpolateAlongPolyline(points, 1.5), interpolateAlongPolyline(points, 1));
});

test("interpolateAlongPolyline: zero-length polyline returns the first vertex without throwing", () => {
  const points = Float64Array.from([32.0, -117.0, 32.0, -117.0, 32.0, -117.0]);
  const [lat, lon] = interpolateAlongPolyline(points, 0.7);
  assert.equal(lat, 32.0);
  assert.equal(lon, -117.0);
});

test("interpolateAlongPolyline: single-vertex polyline always returns that vertex", () => {
  const points = Float64Array.from([32.0, -117.0]);
  const [lat, lon] = interpolateAlongPolyline(points, 0.3);
  assert.equal(lat, 32.0);
  assert.equal(lon, -117.0);
});

test("interpolateAlongPolyline: multi-vertex walk lands in the correct segment", () => {
  const points = Float64Array.from([32.0, -117.0, 32.001, -117.0, 32.002, -117.0, 32.003, -117.0]);
  const [lat] = interpolateAlongPolyline(points, 0.5);
  assert.ok(lat > 32.001 && lat < 32.002);
});

test("rangeFraction: low end is zero, high end is one, midpoint is half", () => {
  assert.equal(rangeFraction(100, 100, 200), 0);
  assert.equal(rangeFraction(200, 100, 200), 1);
  assert.equal(rangeFraction(150, 100, 200), 0.5);
});

test("rangeFraction: descending range still produces a sensible fraction", () => {
  assert.equal(rangeFraction(75, 100, 50), 0.5);
  // (100-100)/(50-100) is -0 in JS, not 0 -- numerically identical
  // (-0 === 0 is true), just not Object.is-equal, which assert.equal
  // (strict mode) checks. Use === here rather than assert the exact
  // signed-zero bit pattern, which isn't the thing under test.
  assert.ok(rangeFraction(100, 100, 50) === 0);
  assert.equal(rangeFraction(50, 100, 50), 1);
});

test("rangeFraction: zero-width range returns null", () => {
  assert.equal(rangeFraction(100, 100, 100), null);
});
