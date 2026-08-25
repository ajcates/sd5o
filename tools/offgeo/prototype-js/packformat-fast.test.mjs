import { test } from "node:test";
import assert from "node:assert/strict";
import { writeUvarint, writeSvarint } from "./varint.mjs";
import { MAGIC, FORMAT_VERSION } from "./packformat.mjs";
import { decodeRecords as decodeRecordsFast } from "./packformat-fast.mjs";
import { decodeRecords as decodeRecordsBaseline } from "./packformat.mjs";

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

// Same hand-built block as packformat.test.mjs -- kept independent
// (not imported from there) so this test doesn't silently depend on
// that file's internals changing underneath it.
function buildOneRecordBlock() {
  const strings = ["92101", "MAIN"];
  const stringsBlob = concatBytes([
    writeUvarint(strings.length),
    ...strings.flatMap((s) => {
      const enc = textEncoder.encode(s);
      return [writeUvarint(enc.length), enc];
    }),
  ]);
  const geometryBlob = concatBytes([
    writeUvarint(1),
    writeUvarint(2),
    writeSvarint(32712250),
    writeSvarint(-117168570),
    writeSvarint(750),
    writeSvarint(-430),
  ]);
  const nameIdx = strings.indexOf("MAIN") + 1;
  const zipIdx = strings.indexOf("92101") + 1;
  const recordsBlob = concatBytes([
    writeUvarint(1),
    writeUvarint(42),
    writeUvarint(nameIdx),
    Uint8Array.from([0]),
    Uint8Array.from([0]),
    writeUvarint(0),
    writeUvarint(100), writeUvarint(198),
    writeUvarint(101), writeUvarint(199),
    Uint8Array.from([0b0000]),
    writeUvarint(zipIdx),
    writeUvarint(0),
    writeUvarint(0),
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

test("fast decoder matches the baseline decoder on every non-geometry field", () => {
  const block = buildOneRecordBlock();
  const baseline = decodeRecordsBaseline(block)[0];
  const fast = decodeRecordsFast(block)[0];
  for (const field of ["roadsegid", "name", "pdir", "postd", "sfx", "lLow", "lHigh", "rLow", "rHigh", "lMix", "rMix", "confidence", "leftZip", "rightZip"]) {
    assert.equal(fast[field], baseline[field], `field ${field} differs`);
  }
});

test("fast decoder's flat Float64Array geometry matches the baseline's array-of-pairs, reshaped", () => {
  const block = buildOneRecordBlock();
  const baseline = decodeRecordsBaseline(block)[0];
  const fast = decodeRecordsFast(block)[0];
  assert.equal(fast.points.length, baseline.points.length * 2);
  for (let i = 0; i < baseline.points.length; i++) {
    assert.ok(Math.abs(fast.points[i * 2] - baseline.points[i][0]) < 1e-9);
    assert.ok(Math.abs(fast.points[i * 2 + 1] - baseline.points[i][1]) < 1e-9);
  }
});

test("rejects wrong magic and unsupported version the same way as the baseline", () => {
  const block = buildOneRecordBlock();
  const wrongMagic = concatBytes([textEncoder.encode("XXXX"), block.subarray(4)]);
  assert.throws(() => decodeRecordsFast(wrongMagic), /bad magic/);

  const wrongVersion = Uint8Array.from(block);
  wrongVersion[4] = 99;
  assert.throws(() => decodeRecordsFast(wrongVersion), /unsupported version/);
});
