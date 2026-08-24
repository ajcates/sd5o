// Decoder for the custom binary block format (OFF-104/OFF-105/OFF-108),
// plain ES module, no dependencies. JS port of the decode half of
// tools/offgeo/lib/packformat.py -- must produce byte-identical
// semantics for blocks that Python module encodes, since the whole
// point of this module is measuring decode speed in a real JS engine
// against the *same* bytes the Python benchmark measured.
//
// Decode-only: this prototype never needs to build packs client-side,
// only read ones a compiler already produced, so encodeRecords isn't
// ported here.

import { readUvarint, readSvarint } from "./varint.mjs";

export const MAGIC = "OGP0";
export const FORMAT_VERSION = 0;
export const DIRECTION_CODES = [null, "N", "S", "E", "W", "NE", "NW", "SE", "SW"];
export const CONFIDENCE_BY_CODE = { 0: "ORDINARY", 1: "FALLBACK", 2: "EXCLUDED" };
const COORD_SCALE = 1_000_000;

const textDecoder = new TextDecoder("utf-8");

/** buf: Uint8Array. Returns an array of record objects, same shape as
 * the Python decoder's output (field names match 1:1). */
export function decodeRecords(buf) {
  const magic = textDecoder.decode(buf.subarray(0, 4));
  if (magic !== MAGIC) {
    throw new Error(`bad magic: ${magic}`);
  }
  const version = buf[4];
  if (version !== FORMAT_VERSION) {
    throw new Error(`unsupported version ${version}`);
  }

  let offset = 5;
  let stringsLen, geometryLen, recordsLen;
  [stringsLen, offset] = readUvarint(buf, offset);
  [geometryLen, offset] = readUvarint(buf, offset);
  [recordsLen, offset] = readUvarint(buf, offset);

  const stringsStart = offset;
  const geometryStart = stringsStart + stringsLen;
  const recordsStart = geometryStart + geometryLen;

  // Decode strings.
  let o = stringsStart;
  let nStrings;
  [nStrings, o] = readUvarint(buf, o);
  const strings = new Array(nStrings);
  for (let i = 0; i < nStrings; i++) {
    let slen;
    [slen, o] = readUvarint(buf, o);
    strings[i] = textDecoder.decode(buf.subarray(o, o + slen));
    o += slen;
  }

  // Decode geometry.
  o = geometryStart;
  let nGeoms;
  [nGeoms, o] = readUvarint(buf, o);
  const geometryTable = new Array(nGeoms);
  for (let i = 0; i < nGeoms; i++) {
    let nPoints;
    [nPoints, o] = readUvarint(buf, o);
    const points = new Array(nPoints);
    let prevLat = 0;
    let prevLon = 0;
    for (let j = 0; j < nPoints; j++) {
      let dLat, dLon;
      [dLat, o] = readSvarint(buf, o);
      [dLon, o] = readSvarint(buf, o);
      prevLat += dLat;
      prevLon += dLon;
      points[j] = [prevLat / COORD_SCALE, prevLon / COORD_SCALE];
    }
    geometryTable[i] = points;
  }

  // Decode records.
  o = recordsStart;
  let nRecords;
  [nRecords, o] = readUvarint(buf, o);
  const out = new Array(nRecords);
  for (let i = 0; i < nRecords; i++) {
    let roadsegid, nameIdx, sfxIdx, lLow, lHigh, rLow, rHigh, leftZipIdx, rightZipIdx, geomIdx;
    [roadsegid, o] = readUvarint(buf, o);
    [nameIdx, o] = readUvarint(buf, o);
    const pdirCode = buf[o]; o += 1;
    const postdCode = buf[o]; o += 1;
    [sfxIdx, o] = readUvarint(buf, o);
    [lLow, o] = readUvarint(buf, o);
    [lHigh, o] = readUvarint(buf, o);
    [rLow, o] = readUvarint(buf, o);
    [rHigh, o] = readUvarint(buf, o);
    const flags = buf[o]; o += 1;
    [leftZipIdx, o] = readUvarint(buf, o);
    [rightZipIdx, o] = readUvarint(buf, o);
    [geomIdx, o] = readUvarint(buf, o);

    out[i] = {
      roadsegid,
      name: nameIdx ? strings[nameIdx - 1] : "",
      pdir: DIRECTION_CODES[pdirCode],
      postd: DIRECTION_CODES[postdCode],
      sfx: sfxIdx ? strings[sfxIdx - 1] : null,
      lLow, lHigh, rLow, rHigh,
      lMix: (flags & 1) !== 0,
      rMix: (flags & 2) !== 0,
      confidence: CONFIDENCE_BY_CODE[flags >> 2],
      leftZip: leftZipIdx ? strings[leftZipIdx - 1] : null,
      rightZip: rightZipIdx ? strings[rightZipIdx - 1] : null,
      points: geometryTable[geomIdx],
    };
  }
  return out;
}
