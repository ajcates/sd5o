import { test } from "node:test";
import assert from "node:assert/strict";
import { writeUvarint, writeSvarint } from "./varint.mjs";
import { decodeRecords, MAGIC, FORMAT_VERSION } from "./packformat.mjs";

const textEncoder = new TextEncoder();

function concatBytes(chunks) {
  const total = chunks.reduce((sum, c) => sum + c.length, 0);
  const out = new Uint8Array(total);
  let offset = 0;
  for (const c of chunks) {
    out.set(c, offset);
    offset += c.length;
  }
  return out;
}

/** Minimal hand-rolled encoder, independent of tools/offgeo/lib/packformat.py,
 * used only to build a known-good test block so this test doesn't depend
 * on a real Python-exported pack existing on disk. Encodes exactly one
 * record with one string ("MAIN") reused for both name and left ZIP
 * (index 0), one geometry entry (two points), sfx/rightZip absent. */
function buildOneRecordBlock() {
  const strings = ["92101", "MAIN"]; // sorted, matches Python's sorted() string table
  const stringsBlob = concatBytes([
    writeUvarint(strings.length),
    ...strings.flatMap((s) => {
      const enc = textEncoder.encode(s);
      return [writeUvarint(enc.length), enc];
    }),
  ]);

  // One geometry entry: two points, first absolute, second delta.
  const geometryBlob = concatBytes([
    writeUvarint(1), // one geometry entry
    writeUvarint(2), // two points
    writeSvarint(32712250), // lat0 * 1e6 (absolute, delta from 0)
    writeSvarint(-117168570), // lon0 * 1e6
    writeSvarint(750), // dLat to point 1
    writeSvarint(-430), // dLon to point 1
  ]);

  const nameIdx = strings.indexOf("MAIN") + 1;
  const zipIdx = strings.indexOf("92101") + 1;
  const recordsBlob = concatBytes([
    writeUvarint(1), // one record
    writeUvarint(42), // roadsegid
    writeUvarint(nameIdx),
    Uint8Array.from([0]), // pdir code: None
    Uint8Array.from([0]), // postd code: None
    writeUvarint(0), // sfx: absent
    writeUvarint(100), writeUvarint(198), // lLow, lHigh
    writeUvarint(101), writeUvarint(199), // rLow, rHigh
    Uint8Array.from([0b0000]), // flags: no mix, confidence=ORDINARY(0)
    writeUvarint(zipIdx), // leftZip
    writeUvarint(0), // rightZip: absent
    writeUvarint(0), // geometry index
  ]);

  const header = concatBytes([
    textEncoder.encode(MAGIC),
    Uint8Array.from([FORMAT_VERSION]),
    writeUvarint(stringsBlob.length),
    writeUvarint(geometryBlob.length),
    writeUvarint(recordsBlob.length),
  ]);

  return concatBytes([header, stringsBlob, geometryBlob, recordsBlob]);
}

test("decodes a single hand-built record with all fields correct", () => {
  const block = buildOneRecordBlock();
  const records = decodeRecords(block);
  assert.equal(records.length, 1);
  const r = records[0];
  assert.equal(r.roadsegid, 42);
  assert.equal(r.name, "MAIN");
  assert.equal(r.pdir, null);
  assert.equal(r.postd, null);
  assert.equal(r.sfx, null);
  assert.equal(r.lLow, 100);
  assert.equal(r.lHigh, 198);
  assert.equal(r.rLow, 101);
  assert.equal(r.rHigh, 199);
  assert.equal(r.lMix, false);
  assert.equal(r.rMix, false);
  assert.equal(r.confidence, "ORDINARY");
  assert.equal(r.leftZip, "92101");
  assert.equal(r.rightZip, null);
  assert.equal(r.points.length, 2);
  assert.ok(Math.abs(r.points[0][0] - 32.71225) < 1e-6);
  assert.ok(Math.abs(r.points[0][1] - -117.16857) < 1e-6);
  assert.ok(Math.abs(r.points[1][0] - 32.71300) < 1e-6);
  assert.ok(Math.abs(r.points[1][1] - -117.16900) < 1e-6);
});

test("rejects wrong magic", () => {
  const block = buildOneRecordBlock();
  const corrupted = concatBytes([textEncoder.encode("XXXX"), block.subarray(4)]);
  assert.throws(() => decodeRecords(corrupted), /bad magic/);
});

test("rejects unsupported version", () => {
  const block = buildOneRecordBlock();
  const corrupted = Uint8Array.from(block);
  corrupted[4] = 99;
  assert.throws(() => decodeRecords(corrupted), /unsupported version/);
});
