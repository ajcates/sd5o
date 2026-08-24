import { test } from "node:test";
import assert from "node:assert/strict";
import { writeUvarint, readUvarint, writeSvarint, readSvarint, zigzagEncode, zigzagDecode } from "./varint.mjs";

test("uvarint round-trips single and multi-byte values", () => {
  for (const v of [0, 1, 127, 128, 300, 16384, 10 ** 9, 2 ** 32 - 1]) {
    const encoded = writeUvarint(v);
    const [decoded, offset] = readUvarint(encoded, 0);
    assert.equal(decoded, v);
    assert.equal(offset, encoded.length);
  }
});

test("writeUvarint rejects a negative value", () => {
  assert.throws(() => writeUvarint(-1), RangeError);
});

test("readUvarint reads from a nonzero offset", () => {
  const buf = new Uint8Array([0xff, ...writeUvarint(300)]);
  const [decoded, offset] = readUvarint(buf, 1);
  assert.equal(decoded, 300);
  assert.equal(offset, buf.length);
});

test("zigzag keeps small-magnitude negatives small", () => {
  assert.equal(zigzagEncode(0), 0);
  assert.equal(zigzagEncode(-1), 1);
  assert.equal(zigzagEncode(1), 2);
  assert.equal(zigzagEncode(-2), 3);
  assert.equal(zigzagEncode(2), 4);
});

test("zigzag round-trips including large magnitudes", () => {
  for (const v of [0, 1, -1, 127, -127, 128, -128, 10 ** 6, -(10 ** 6), 2 ** 31 - 1, -(2 ** 31)]) {
    assert.equal(zigzagDecode(zigzagEncode(v)), v);
  }
});

test("svarint round-trips", () => {
  for (const v of [0, -1, 1, -1000000, 1000000]) {
    const encoded = writeSvarint(v);
    const [decoded, offset] = readSvarint(encoded, 0);
    assert.equal(decoded, v);
    assert.equal(offset, encoded.length);
  }
});
