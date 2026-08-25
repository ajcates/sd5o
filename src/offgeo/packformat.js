/** Decoder for OffGeo's custom binary pack format. Reads the exact bytes
 * tools/offgeo/compile-pack.py writes to offgeo/packs/v0/sd-06073.ogp0
 * (magic `"OGP0"`, format version 0 -- see that script and
 * tools/offgeo/lib/packformat.py for the encoder/writer side).
 *
 * Decode-only: the browser only ever reads a pack a compiler already
 * produced, never builds one. Varint reads are inlined directly into
 * each loop (no function call, no `[value, offset]` temp-array
 * allocation per read) and each geometry entry decodes into one flat
 * `Float64Array` instead of an array of 2-element arrays -- proven
 * ~1.8-2x faster than the straightforward port in
 * tools/offgeo/prototype-js/packformat-fast.mjs (`OFF-108`), the design
 * this module is promoted from. `points` on a decoded record is
 * therefore `[lat0, lon0, lat1, lon1, ...]`, not an array of pairs. */

export const MAGIC = "OGP0";
export const FORMAT_VERSION = 0;
export const DIRECTION_CODES = [null, "N", "S", "E", "W", "NE", "NW", "SE", "SW"];
export const CONFIDENCE_BY_CODE = { 0: "ORDINARY", 1: "FALLBACK", 2: "EXCLUDED" };
const COORD_SCALE = 1_000_000;

const textDecoder = new TextDecoder("utf-8");

/** buf: Uint8Array (the whole pack file). Returns an array of record
 * objects: {roadsegid, name, pdir, postd, sfx, lLow, lHigh, rLow,
 * rHigh, lMix, rMix, confidence, leftZip, rightZip, points}. */
export function decodeRecords(buf) {
  const magic = textDecoder.decode(buf.subarray(0, 4));
  if (magic !== MAGIC) throw new Error(`bad magic: ${magic}`);
  const version = buf[4];
  if (version !== FORMAT_VERSION) throw new Error(`unsupported version ${version}`);

  let o = 5;
  let stringsLen = 0, geometryLen = 0, recordsLen = 0;
  let byte, mult;

  mult = 1; do { byte = buf[o++]; stringsLen += (byte & 0x7f) * mult; mult *= 128; } while (byte & 0x80);
  mult = 1; do { byte = buf[o++]; geometryLen += (byte & 0x7f) * mult; mult *= 128; } while (byte & 0x80);
  mult = 1; do { byte = buf[o++]; recordsLen += (byte & 0x7f) * mult; mult *= 128; } while (byte & 0x80);

  const stringsStart = o;
  const geometryStart = stringsStart + stringsLen;
  const recordsStart = geometryStart + geometryLen;

  // Strings.
  o = stringsStart;
  let nStrings = 0; mult = 1;
  do { byte = buf[o++]; nStrings += (byte & 0x7f) * mult; mult *= 128; } while (byte & 0x80);
  const strings = new Array(nStrings);
  for (let i = 0; i < nStrings; i++) {
    let slen = 0; mult = 1;
    do { byte = buf[o++]; slen += (byte & 0x7f) * mult; mult *= 128; } while (byte & 0x80);
    strings[i] = textDecoder.decode(buf.subarray(o, o + slen));
    o += slen;
  }

  // Geometry: flat Float64Array per entry.
  o = geometryStart;
  let nGeoms = 0; mult = 1;
  do { byte = buf[o++]; nGeoms += (byte & 0x7f) * mult; mult *= 128; } while (byte & 0x80);
  const geometryTable = new Array(nGeoms);
  for (let i = 0; i < nGeoms; i++) {
    let nPoints = 0; mult = 1;
    do { byte = buf[o++]; nPoints += (byte & 0x7f) * mult; mult *= 128; } while (byte & 0x80);
    const flat = new Float64Array(nPoints * 2);
    let prevLat = 0, prevLon = 0;
    for (let j = 0; j < nPoints; j++) {
      let raw = 0; mult = 1;
      do { byte = buf[o++]; raw += (byte & 0x7f) * mult; mult *= 128; } while (byte & 0x80);
      const dLat = raw % 2 === 0 ? raw / 2 : -(raw + 1) / 2;
      raw = 0; mult = 1;
      do { byte = buf[o++]; raw += (byte & 0x7f) * mult; mult *= 128; } while (byte & 0x80);
      const dLon = raw % 2 === 0 ? raw / 2 : -(raw + 1) / 2;
      prevLat += dLat;
      prevLon += dLon;
      flat[j * 2] = prevLat / COORD_SCALE;
      flat[j * 2 + 1] = prevLon / COORD_SCALE;
    }
    geometryTable[i] = flat;
  }

  // Records.
  o = recordsStart;
  let nRecords = 0; mult = 1;
  do { byte = buf[o++]; nRecords += (byte & 0x7f) * mult; mult *= 128; } while (byte & 0x80);
  const out = new Array(nRecords);
  for (let i = 0; i < nRecords; i++) {
    let roadsegid = 0; mult = 1;
    do { byte = buf[o++]; roadsegid += (byte & 0x7f) * mult; mult *= 128; } while (byte & 0x80);
    let nameIdx = 0; mult = 1;
    do { byte = buf[o++]; nameIdx += (byte & 0x7f) * mult; mult *= 128; } while (byte & 0x80);
    const pdirCode = buf[o++];
    const postdCode = buf[o++];
    let sfxIdx = 0; mult = 1;
    do { byte = buf[o++]; sfxIdx += (byte & 0x7f) * mult; mult *= 128; } while (byte & 0x80);
    let lLow = 0; mult = 1;
    do { byte = buf[o++]; lLow += (byte & 0x7f) * mult; mult *= 128; } while (byte & 0x80);
    let lHigh = 0; mult = 1;
    do { byte = buf[o++]; lHigh += (byte & 0x7f) * mult; mult *= 128; } while (byte & 0x80);
    let rLow = 0; mult = 1;
    do { byte = buf[o++]; rLow += (byte & 0x7f) * mult; mult *= 128; } while (byte & 0x80);
    let rHigh = 0; mult = 1;
    do { byte = buf[o++]; rHigh += (byte & 0x7f) * mult; mult *= 128; } while (byte & 0x80);
    const flags = buf[o++];
    let leftZipIdx = 0; mult = 1;
    do { byte = buf[o++]; leftZipIdx += (byte & 0x7f) * mult; mult *= 128; } while (byte & 0x80);
    let rightZipIdx = 0; mult = 1;
    do { byte = buf[o++]; rightZipIdx += (byte & 0x7f) * mult; mult *= 128; } while (byte & 0x80);
    let geomIdx = 0; mult = 1;
    do { byte = buf[o++]; geomIdx += (byte & 0x7f) * mult; mult *= 128; } while (byte & 0x80);

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
