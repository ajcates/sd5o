// SQLite-in-the-browser feasibility check (OFF-108/OFF-115, remaining
// half). Loads the real r1-pack.sqlite (OFF-104's SQLite candidate)
// through sql.js -- a WASM build of SQLite, the standard way to run
// SQLite in a browser since there's no native binding -- and queries it
// with the *exact same* 2000-key seeded sample
// prototype-benchmark-reader.py and prototype-js/benchmark.mjs both
// used, for a genuine three-way same-data comparison across Python
// native SQLite, JS custom-format decode, and JS SQLite-via-WASM.
//
// sql.js is a devDependency (never shipped to the app) per this
// project's existing playwright-core pattern -- see package.json's own
// description field.
//
// Usage: node tools/offgeo/prototype-js/sqljs-benchmark.mjs
//   (requires build/offgeo-sources/r1-pack.sqlite from
//    prototype-pack-formats.py, and build/offgeo-sources/
//    r1-pack-manifest.json from prototype-benchmark-reader.py)

import { readFileSync, writeFileSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import initSqlJs from "sql.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(__dirname, "..", "..", "..");
const dbPath = join(repoRoot, "build/offgeo-sources/r1-pack.sqlite");
const manifestPath = join(repoRoot, "build/offgeo-sources/r1-pack-manifest.json");
const reportPath = join(repoRoot, "build/offgeo-sources/r1-sqljs-benchmark-report.json");
const wasmPath = join(repoRoot, "node_modules/sql.js/dist/sql-wasm.wasm");
const jsGluePath = join(repoRoot, "node_modules/sql.js/dist/sql-wasm.js");

function main() {
  const jsGlueBytes = statSync(jsGluePath).size;
  const wasmBytes = statSync(wasmPath).size;
  console.log(`sql.js production build: ${jsGlueBytes.toLocaleString()} bytes JS + ${wasmBytes.toLocaleString()} bytes WASM = ${(jsGlueBytes + wasmBytes).toLocaleString()} bytes raw`);

  console.log("\nInitializing sql.js (WASM compile + instantiate)...");
  const tInit0 = performance.now();
  return initSqlJs({ locateFile: () => wasmPath }).then((SQL) => {
    const initMs = performance.now() - tInit0;
    console.log(`  ${initMs.toFixed(1)} ms`);

    const dbBytes = readFileSync(dbPath);
    console.log(`\nLoading r1-pack.sqlite (${dbBytes.length.toLocaleString()} bytes) into sql.js...`);
    const tLoad0 = performance.now();
    const db = new SQL.Database(dbBytes);
    const loadMs = performance.now() - tLoad0;
    console.log(`  ${loadMs.toFixed(1)} ms (whole file loaded into WASM memory -- sql.js has no partial/streaming read by default)`);

    const manifest = JSON.parse(readFileSync(manifestPath, "utf-8"));
    const sampleKeys = manifest.sampleKeys.map((joined) => {
      const [pdir, name, postd, sfx] = joined.split("\x1f");
      // prototype-benchmark-reader.py's street_key() uses "" for an
      // absent component; the SQLite candidate's own schema (built in
      // prototype-pack-formats.py) stores Python None -> SQL NULL for
      // the same case. Convert so "IS ?" matches correctly.
      return [pdir || null, name, postd || null, sfx || null];
    });

    const stmt = db.prepare(
      `SELECT segments.roadsegid FROM segments
       JOIN streets ON streets.id = segments.street_id
       WHERE streets.pdir IS :pdir AND streets.name = :name AND streets.postd IS :postd AND streets.sfx IS :sfx`
    );

    console.log(`\nRunning ${sampleKeys.length} queries (same seeded sample as the Python/JS custom-format benchmarks)...`);
    const perQueryUs = [];
    let matched = 0;
    const t0 = performance.now();
    for (const [pdir, name, postd, sfx] of sampleKeys) {
      const tStart = performance.now();
      stmt.bind({ ":pdir": pdir, ":name": name, ":postd": postd, ":sfx": sfx });
      let rows = 0;
      while (stmt.step()) {
        stmt.getAsObject();
        rows++;
      }
      stmt.reset();
      const tEnd = performance.now();
      perQueryUs.push((tEnd - tStart) * 1000);
      if (rows > 0) matched++;
    }
    const totalMs = performance.now() - t0;
    stmt.free();
    db.close();

    perQueryUs.sort((a, b) => a - b);
    const n = perQueryUs.length;
    const mean = perQueryUs.reduce((a, b) => a + b, 0) / n;
    const median = perQueryUs[Math.floor(n / 2)];
    const p95 = perQueryUs[Math.floor(n * 0.95)];

    const report = {
      generatedAt: new Date().toISOString(),
      engine: `node ${process.version} (V8) + sql.js (WASM SQLite)`,
      bundleBytes: { jsGlue: jsGlueBytes, wasm: wasmBytes, totalRaw: jsGlueBytes + wasmBytes },
      wasmInitMilliseconds: Math.round(initMs * 10) / 10,
      dbLoadMilliseconds: Math.round(loadMs * 10) / 10,
      dbFileBytes: dbBytes.length,
      sampleSize: n,
      matchedKeys: matched,
      totalMilliseconds: Math.round(totalMs),
      microsecondsPerQueryMean: Math.round(mean * 100) / 100,
      microsecondsPerQueryMedian: Math.round(median * 100) / 100,
      microsecondsPerQueryP95: Math.round(p95 * 100) / 100,
      note: "Same 2000-key seeded sample as prototype-benchmark-reader.py (Python custom format) and prototype-js/benchmark.mjs (JS custom format) used. dbLoadMilliseconds loads the WHOLE 77 MB file into WASM memory upfront -- sql.js has no partial-read/streaming mode by default, unlike the block-partitioned custom format's per-query decode. A real integration would need OPFS-backed VFS or similar to avoid that, not evaluated here.",
    };
    writeFileSync(reportPath, JSON.stringify(report, null, 2));

    console.log(`\nMean:   ${report.microsecondsPerQueryMean.toFixed(2)} us/query`);
    console.log(`Median: ${report.microsecondsPerQueryMedian.toFixed(2)} us/query`);
    console.log(`P95:    ${report.microsecondsPerQueryP95.toFixed(2)} us/query`);
    console.log(`Matched: ${matched}/${n}`);
    console.log(`\nReport: ${reportPath}`);
  });
}

main();
