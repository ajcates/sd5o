import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { decodeRecords, MAGIC, FORMAT_VERSION, DIRECTION_CODES, CONFIDENCE_BY_CODE } from "../../src/offgeo/packformat.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const packPath = join(__dirname, "..", "..", "offgeo", "packs", "v0", "sd-06073.ogp0");
const packBuf = new Uint8Array(readFileSync(packPath));

test("decodes the real v0 pack into a real, non-trivial record set", () => {
  const records = decodeRecords(packBuf);
  assert.equal(records.length, 164555, "record count should match compile-pack.py's manifest");
});

test("every decoded record has structurally valid fields", () => {
  const records = decodeRecords(packBuf);
  const validConfidence = new Set(Object.values(CONFIDENCE_BY_CODE));
  const seenRoadsegids = new Set();
  for (const r of records) {
    assert.equal(typeof r.roadsegid, "number");
    assert.ok(!seenRoadsegids.has(r.roadsegid), `duplicate roadsegid ${r.roadsegid}`);
    seenRoadsegids.add(r.roadsegid);
    assert.equal(typeof r.name, "string");
    assert.ok(r.pdir === null || DIRECTION_CODES.includes(r.pdir));
    assert.ok(r.postd === null || DIRECTION_CODES.includes(r.postd));
    assert.ok(validConfidence.has(r.confidence));
    assert.ok(r.points instanceof Float64Array);
    assert.ok(r.points.length >= 2 && r.points.length % 2 === 0, "points must be a non-empty even-length flat array");
  }
});

test("a known real record decodes to the expected values (cross-checked against the Python source)", () => {
  const records = decodeRecords(packBuf);
  const abelia = records.find((r) => r.roadsegid === 3);
  assert.ok(abelia, "ROADSEGID 3 should exist in the real pack");
  assert.equal(abelia.name, "ABELIA");
  assert.equal(abelia.sfx, "COURT");
  assert.equal(abelia.leftZip, "92106");
  assert.equal(abelia.rightZip, "92106");
  assert.ok(Math.abs(abelia.points[0] - 32.706407) < 1e-5);
  assert.ok(Math.abs(abelia.points[1] - -117.24285) < 1e-4);
});

test("rejects a pack with the wrong magic", () => {
  const corrupted = Uint8Array.from(packBuf);
  corrupted.set([0x58, 0x58, 0x58, 0x58], 0); // "XXXX"
  assert.throws(() => decodeRecords(corrupted), /bad magic/);
});

test("rejects a pack with an unsupported format version", () => {
  const corrupted = Uint8Array.from(packBuf.subarray(0, 64));
  corrupted[4] = 99;
  assert.throws(() => decodeRecords(corrupted), /unsupported version/);
});

test("MAGIC and FORMAT_VERSION match compile-pack.py's manifest", () => {
  const manifestPath = join(__dirname, "..", "..", "offgeo", "manifest.json");
  const manifest = JSON.parse(readFileSync(manifestPath, "utf-8"));
  assert.equal(MAGIC, manifest.format.magic);
  assert.equal(FORMAT_VERSION, manifest.format.formatVersion);
});
