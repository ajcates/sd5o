import { test } from "node:test";
import assert from "node:assert/strict";
import { distanceMiles, formatAccuracyMeters, formatDistanceMiles } from "../../src/app/distance.js";

test("distanceMiles() calculates straight-line great-circle distance", () => {
  const sanDiego = { latitude: 32.7157, longitude: -117.1611 };
  const laJolla = { latitude: 32.8328, longitude: -117.2713 };
  const miles = distanceMiles(sanDiego, laJolla);
  assert.ok(Math.abs(miles - 10.3) < 0.2, `expected about 10.3 miles, got ${miles}`);
});

test("distanceMiles() validates inputs and returns zero for the same point", () => {
  const point = { latitude: 32.8, longitude: -117.1 };
  assert.equal(distanceMiles(point, point), 0);
  assert.equal(distanceMiles(point, { latitude: 91, longitude: 0 }), null);
  assert.equal(distanceMiles(null, point), null);
});

test("formatDistanceMiles() uses approximate feet nearby and miles farther away", () => {
  assert.deepEqual(formatDistanceMiles(0.05), {
    visible: "≈300 ft",
    accessible: "Approximately 300 feet straight-line distance",
  });
  assert.equal(formatDistanceMiles(1.24).visible, "≈1.2 mi");
  assert.equal(formatDistanceMiles(12.7).visible, "≈13 mi");
  assert.equal(formatDistanceMiles(null), null);
});

test("formatAccuracyMeters() avoids false precision", () => {
  assert.equal(formatAccuracyMeters(30), "Location accuracy ±100 ft.");
  assert.equal(formatAccuracyMeters(1000), "Location accuracy ±0.6 mi.");
});
