import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  normalizeText,
  stripUnitDesignator,
  canonicalizeDirection,
  canonicalizeSuffix,
  canonicalizeStreetCoreName,
  parseBlockNotation,
  splitIntersection,
  parseHighwayRoute,
  parseStreetName,
  parseAddress,
} from "../../src/offgeo/normalize.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const fixturesPath = join(__dirname, "..", "..", "tests", "offgeo", "fixtures", "addresses.json");

test("normalizeText: uppercases, trims, and collapses whitespace", () => {
  assert.equal(normalizeText("  100  n el camino real "), "100 N EL CAMINO REAL");
});

test("normalizeText: strips periods", () => {
  assert.equal(normalizeText("100 N. Main St."), "100 N MAIN ST");
});

test("normalizeText: preserves intersection and fraction punctuation", () => {
  assert.equal(normalizeText("main st/2nd ave"), "MAIN ST/2ND AVE");
  assert.equal(normalizeText("123 1/2 main st"), "123 1/2 MAIN ST");
});

test("stripUnitDesignator: strips trailing apartment/unit/hash forms", () => {
  assert.equal(stripUnitDesignator("123 MAIN ST APT 4"), "123 MAIN ST");
  assert.equal(stripUnitDesignator("123 MAIN ST UNIT B"), "123 MAIN ST");
  assert.equal(stripUnitDesignator("123 MAIN ST #12"), "123 MAIN ST");
  assert.equal(stripUnitDesignator("123 MAIN ST"), "123 MAIN ST");
});

test("canonicalizeDirection / canonicalizeSuffix: abbreviations from both SanGIS tables collapse together", () => {
  assert.equal(canonicalizeDirection("N"), "N");
  assert.equal(canonicalizeDirection("NORTH"), "N");
  assert.equal(canonicalizeDirection("NB"), null); // travel-direction marker, not a street direction
  assert.equal(canonicalizeSuffix("BLVD"), "BOULEVARD");
  assert.equal(canonicalizeSuffix("BL"), "BOULEVARD");
  assert.equal(canonicalizeSuffix("NOTASUFFIX"), null);
});

test("canonicalizeStreetCoreName: strips a leading zero from ordinal street numbers", () => {
  assert.equal(canonicalizeStreetCoreName("01ST"), "1ST");
  assert.equal(canonicalizeStreetCoreName("02ND"), "2ND");
  assert.equal(canonicalizeStreetCoreName("09TH"), "9TH");
  assert.equal(canonicalizeStreetCoreName("21ST"), "21ST"); // already unpadded, untouched
  assert.equal(canonicalizeStreetCoreName("First American"), "FIRST AMERICAN");
});

test("parseBlockNotation: recognizes block-of forms", () => {
  assert.deepEqual(parseBlockNotation("1200 BLOCK OF MAIN ST"), [1200, "MAIN ST"]);
  assert.deepEqual(parseBlockNotation("1200 BLOCK MAIN ST"), [1200, "MAIN ST"]);
  assert.equal(parseBlockNotation("100 MAIN ST"), null);
});

test("splitIntersection: splits unspaced slash, spaced ampersand, and word AT", () => {
  assert.deepEqual(splitIntersection("MAIN ST/ELM ST"), ["MAIN ST", "ELM ST"]);
  assert.deepEqual(splitIntersection("MAIN ST & ELM ST"), ["MAIN ST", "ELM ST"]);
  assert.deepEqual(splitIntersection("MAIN ST AT ELM ST"), ["MAIN ST", "ELM ST"]);
});

test("splitIntersection: a fraction slash is not treated as an intersection", () => {
  assert.equal(splitIntersection("123 1/2 MAIN ST"), null);
});

test("splitIntersection: an ordinary address is not an intersection", () => {
  assert.equal(splitIntersection("100 MAIN ST"), null);
});

test("parseHighwayRoute: recognizes highway/interstate/state-route numbers", () => {
  assert.equal(parseHighwayRoute("INTERSTATE 5"), 5);
  assert.equal(parseHighwayRoute("STATE ROUTE 76"), 76);
  assert.equal(parseHighwayRoute("SR 76"), 76);
  assert.equal(parseHighwayRoute("EL CAMINO REAL"), null); // named highway, no number
});

test("parseStreetName: extracts pdir/suffix/postd, leaves unrecognized words in the name", () => {
  const s = parseStreetName("N MAIN ST");
  assert.equal(s.pdir, "N");
  assert.equal(s.name, "MAIN");
  assert.equal(s.suffix, "STREET");
  const real = parseStreetName("EL CAMINO REAL");
  assert.equal(real.name, "EL CAMINO REAL"); // REAL is not a recognized suffix
});

test("parseStreetName: highway number short-circuits suffix parsing", () => {
  const s = parseStreetName("INTERSTATE 5");
  assert.equal(s.isHighway, true);
  assert.equal(s.routeNumber, 5);
});

test("parseAddress: ordinary numbered address", () => {
  const p = parseAddress("100 N El Camino Real");
  assert.equal(p.houseNumber, 100);
  assert.equal(p.streets[0].pdir, "N");
  assert.equal(p.isIntersection, false);
});

test("parseAddress: slash intersection", () => {
  const p = parseAddress("AMIGOS RD/E OLD JULIAN HWY");
  assert.equal(p.isIntersection, true);
  assert.equal(p.streets.length, 2);
});

test("parseAddress: block notation marks the number approximate", () => {
  const p = parseAddress("1200 BLOCK OF MAIN ST");
  assert.equal(p.houseNumber, 1200);
  assert.equal(p.isBlockApproximate, true);
});

test("parseAddress: street-only text has no house number", () => {
  const p = parseAddress("EL CAMINO REAL");
  assert.equal(p.houseNumber, null);
});

test("real fixture corpus: every real captured address parses without throwing", () => {
  const fixtures = JSON.parse(readFileSync(fixturesPath, "utf-8")).fixtures;
  assert.ok(fixtures.length > 0);
  for (const f of fixtures) {
    assert.doesNotThrow(() => parseAddress(f.address), `threw on ${f.address}`);
  }
});

test("real fixture corpus: ordinary_numbered addresses get a house number", () => {
  const fixtures = JSON.parse(readFileSync(fixturesPath, "utf-8")).fixtures;
  for (const f of fixtures.filter((x) => x.categories.includes("ordinary_numbered"))) {
    const p = parseAddress(f.address);
    assert.notEqual(p.houseNumber, null, `no house number for ${f.address}`);
  }
});

test("real fixture corpus: has_directional addresses get a pdir/postd on at least one street", () => {
  const fixtures = JSON.parse(readFileSync(fixturesPath, "utf-8")).fixtures;
  for (const f of fixtures.filter((x) => x.categories.includes("has_directional"))) {
    const p = parseAddress(f.address);
    const anyDir = p.streets.some((s) => s.pdir || s.postd);
    assert.ok(anyDir, `no direction found for ${f.address}`);
  }
});

test("real fixture corpus: slash intersections are recognized and split in two", () => {
  const fixtures = JSON.parse(readFileSync(fixturesPath, "utf-8")).fixtures;
  for (const f of fixtures.filter((x) => x.categories.includes("slash_intersection_unspaced"))) {
    const p = parseAddress(f.address);
    assert.equal(p.isIntersection, true, `not recognized as intersection: ${f.address}`);
    assert.equal(p.streets.length, 2);
  }
});
