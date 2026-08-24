// LEB128-style unsigned varint + zigzag signed-varint encoding, plain
// ES module, no dependencies. JS port of tools/offgeo/lib/varint.py --
// byte layout is required to match exactly (this and the Python module
// must produce/consume identical bytes for prototype-js/packformat.mjs
// to decode blocks tools/offgeo/prototype-benchmark-reader.py exported).
//
// Deliberately uses plain arithmetic (%, Math.floor, *) instead of
// JS's 32-bit bitwise operators (`&`, `>>>`) -- coordinate values here
// stay well within the 32-bit safe range for this county's data, but
// arithmetic is correct for any magnitude up to Number.MAX_SAFE_INTEGER
// without that assumption, matching Python's arbitrary-precision ints
// more closely than a bit-twiddling port would.

export function writeUvarint(value) {
  if (value < 0) {
    throw new RangeError(`writeUvarint requires a non-negative value, got ${value}`);
  }
  const bytes = [];
  let v = value;
  do {
    let byte = v % 128;
    v = Math.floor(v / 128);
    if (v > 0) byte |= 0x80;
    bytes.push(byte);
  } while (v > 0);
  return Uint8Array.from(bytes);
}

/** Returns [value, newOffset]. */
export function readUvarint(buf, offset) {
  let result = 0;
  let multiplier = 1;
  let o = offset;
  for (;;) {
    const byte = buf[o];
    o += 1;
    result += (byte & 0x7f) * multiplier;
    if ((byte & 0x80) === 0) {
      return [result, o];
    }
    multiplier *= 128;
  }
}

export function zigzagEncode(value) {
  return value >= 0 ? value * 2 : -value * 2 - 1;
}

export function zigzagDecode(value) {
  return value % 2 === 0 ? value / 2 : -(value + 1) / 2;
}

export function writeSvarint(value) {
  return writeUvarint(zigzagEncode(value));
}

/** Returns [value, newOffset]. */
export function readSvarint(buf, offset) {
  const [raw, o] = readUvarint(buf, offset);
  return [zigzagDecode(raw), o];
}
