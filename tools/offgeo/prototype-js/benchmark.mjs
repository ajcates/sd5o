// Decode-speed benchmark for the custom block format, run in real V8
// (plain `node`, no browser needed for a raw decode-throughput number --
// see this file's own note below on why that's a fair proxy here).
// Reads the *exact same bytes* tools/offgeo/prototype-benchmark-reader.py
// exported (r1-pack-blocks.bin + r1-pack-manifest.json), decodes the
// same 2000-key seeded sample that script benchmarked in Python, and
// reports the same statistic (microseconds/lookup, cold: fresh block
// decode every query, no cache) for a direct language comparison on
// identical input.
//
// Node's V8 is not literally a browser, but it's the same JS engine
// Chromium uses, JIT behavior included -- a fair proxy for whether the
// custom format's ~2,300x-slower-than-SQLite result (OFF-105, measured
// in pure Python) is a Python-interpreter artifact or a real property
// of this byte layout. Confirming in actual Chromium (via the existing
// playwright-core E2E harness) is the next step if this number looks
// promising; not done in this script.
//
// Runs two decoders back-to-back on the identical sample: `packformat.mjs`
// (the direct, unoptimized port) and `packformat-fast.mjs` (inlined
// varint decode, flat-Float64Array geometry -- see that file's own
// docstring for what changed and why, and packformat-fast.test.mjs /
// the real-data cross-check for why it's trusted to decode correctly).
//
// Usage: node tools/offgeo/prototype-js/benchmark.mjs
//   (requires build/offgeo-sources/r1-pack-blocks.bin and
//    r1-pack-manifest.json -- run prototype-benchmark-reader.py first)

import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { decodeRecords as decodeBaseline } from "./packformat.mjs";
import { decodeRecords as decodeFast } from "./packformat-fast.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(__dirname, "..", "..", "..");
const blocksPath = join(repoRoot, "build/offgeo-sources/r1-pack-blocks.bin");
const manifestPath = join(repoRoot, "build/offgeo-sources/r1-pack-manifest.json");
const reportPath = join(repoRoot, "build/offgeo-sources/r1-js-decode-benchmark-report.json");

function streetKeyFromJoined(joined) {
  return joined.split("\x1f");
}

function runBenchmark(label, decodeRecords, blocksBuf, manifest, sampleKeys) {
  function lookupSegments(joinedKey) {
    const blockIds = manifest.index[joinedKey];
    if (!blockIds || blockIds.length === 0) return [];
    const wantKey = streetKeyFromJoined(joinedKey).join("\x1f");
    const out = [];
    for (const blockId of blockIds) {
      const { offset, length } = manifest.blockOffsets[blockId];
      const blockBytes = blocksBuf.subarray(offset, offset + length);
      const records = decodeRecords(blockBytes);
      for (const r of records) {
        const gotKey = [r.pdir ?? "", r.name, r.postd ?? "", r.sfx ?? ""].join("\x1f");
        if (gotKey === wantKey) out.push(r);
      }
    }
    return out;
  }

  console.log(`\nRunning ${sampleKeys.length} cold lookups with ${label} (fresh block decode every query, no cache)...`);
  const perLookupUs = [];
  let totalMatched = 0;
  for (const key of sampleKeys) {
    const tStart = performance.now();
    const segments = lookupSegments(key);
    const tEnd = performance.now();
    perLookupUs.push((tEnd - tStart) * 1000);
    if (segments.length > 0) totalMatched += 1;
  }

  perLookupUs.sort((a, b) => a - b);
  const n = perLookupUs.length;
  const mean = perLookupUs.reduce((a, b) => a + b, 0) / n;
  const median = perLookupUs[Math.floor(n / 2)];
  const p95 = perLookupUs[Math.floor(n * 0.95)];

  const result = {
    sampleSize: n,
    matchedKeys: totalMatched,
    microsecondsPerLookupMean: Math.round(mean * 100) / 100,
    microsecondsPerLookupMedian: Math.round(median * 100) / 100,
    microsecondsPerLookupP95: Math.round(p95 * 100) / 100,
  };
  console.log(`  Mean:   ${result.microsecondsPerLookupMean.toFixed(2)} us/lookup`);
  console.log(`  Median: ${result.microsecondsPerLookupMedian.toFixed(2)} us/lookup`);
  console.log(`  P95:    ${result.microsecondsPerLookupP95.toFixed(2)} us/lookup`);
  console.log(`  Matched: ${totalMatched}/${n}`);
  return result;
}

function main() {
  console.log("Loading exported blocks + manifest...");
  const blocksBuf = new Uint8Array(readFileSync(blocksPath));
  const manifest = JSON.parse(readFileSync(manifestPath, "utf-8"));
  console.log(`  ${blocksBuf.length.toLocaleString()} bytes, ${manifest.blockOffsets.length} blocks, ${Object.keys(manifest.index).length} indexed keys`);

  const sampleKeys = manifest.sampleKeys;

  const baseline = runBenchmark("packformat.mjs (baseline)", decodeBaseline, blocksBuf, manifest, sampleKeys);
  const fast = runBenchmark("packformat-fast.mjs (optimized)", decodeFast, blocksBuf, manifest, sampleKeys);

  const report = {
    generatedAt: new Date().toISOString(),
    engine: `node ${process.version} (V8)`,
    note: "Same 2000-key seeded sample and same exported block bytes prototype-benchmark-reader.py's Python benchmark used -- a fair same-data, cross-engine, cross-implementation comparison.",
    baseline,
    optimized: fast,
    speedupFactor: Math.round((baseline.microsecondsPerLookupMean / fast.microsecondsPerLookupMean) * 100) / 100,
  };
  writeFileSync(reportPath, JSON.stringify(report, null, 2));

  console.log(`\nOptimized is ${report.speedupFactor}x faster than the baseline port (mean).`);
  console.log(`\nReport: ${reportPath}`);
}

main();
