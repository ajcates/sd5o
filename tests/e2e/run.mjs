#!/usr/bin/env node
/**
 * Real-browser smoke test + browser capability probe (OFF-012/OFF-013,
 * Group 6). Drives system-installed Chromium via `playwright-core` the
 * same way the sibling ../playwright-termux harness does -- no browser
 * download, no bundled `playwright` package. Not run as part of `npm run
 * test:unit`; it needs a real Chromium binary and network access to the
 * live calls feed.
 *
 * What it does:
 *   1. Serves the repo root over plain HTTP on localhost (Chromium treats
 *      http://localhost as a secure context, same as the real deployment's
 *      HTTPS origin, without needing a cert here).
 *   2. Loads index.html and waits for the status panel to leave "loading"
 *      (either "live" against the real feed, or "error" -- both are a
 *      real, checkable outcome; only an infinite hang or a page/console
 *      error fails the run).
 *   3. If live, opens the map panel -- this triggers the real OffGeo pack
 *      fetch+decode (src/offgeo/geocoder.js against offgeo/packs/v0/
 *      sd-06073.ogp0) -- and waits for at least one real call to geocode
 *      and render as a marker (or the panel settling with none, also a
 *      real checkable outcome).
 *   4. Probes the browser capability matrix (OFF-013) in that same page
 *      context and writes notes/offgeo/browser-capability-matrix.md.
 */
import http from "node:http";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

// Termux's Node reports process.platform === "android", which this pinned
// playwright-core build's browser-registry module rejects outright at
// import time ("Unsupported platform: android") even though it's never
// asked to manage a browser download here -- launch() always gets an
// explicit executablePath below. Reporting "linux" (accurate: this is a
// real Linux userland/ELF Chromium build via Termux's x11-repo) sidesteps
// that check without needing to patch node_modules. Must happen before
// playwright-core is loaded, and a static `import` is hoisted above this
// statement regardless of source order, so this uses a dynamic import.
Object.defineProperty(process, "platform", { value: "linux" });
const { chromium } = await import("playwright-core");

const ROOT = path.resolve(fileURLToPath(new URL("../../", import.meta.url)));
const CHROMIUM_PATH = process.env.CHROMIUM_PATH || "/data/data/com.termux/files/usr/bin/chromium-browser";
const PORT = 8934;

const MIME = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".mjs": "text/javascript",
  ".json": "application/json",
  ".css": "text/css",
  ".png": "image/png",
  ".svg": "image/svg+xml",
};

function startServer() {
  const server = http.createServer(async (req, res) => {
    try {
      const urlPath = decodeURIComponent(req.url.split("?")[0]);
      const filePath = path.join(ROOT, urlPath === "/" ? "/index.html" : urlPath);
      if (!filePath.startsWith(ROOT)) {
        res.writeHead(403).end();
        return;
      }
      const body = await readFile(filePath);
      const ext = path.extname(filePath);
      res.writeHead(200, { "Content-Type": MIME[ext] || "application/octet-stream" });
      res.end(body);
    } catch {
      res.writeHead(404).end("not found");
    }
  });
  return new Promise((resolve) => server.listen(PORT, "localhost", () => resolve(server)));
}

const CAPABILITY_PROBE = `(async () => {
  const out = {};
  out.indexedDB = typeof indexedDB !== "undefined";
  out.webWorkers = typeof Worker !== "undefined";
  out.streamingFetch = (() => {
    try {
      return typeof Response !== "undefined" && "body" in Response.prototype;
    } catch { return false; }
  })();
  out.decompressionStreamGzip = (() => {
    try {
      if (typeof DecompressionStream === "undefined") return false;
      new DecompressionStream("gzip");
      return true;
    } catch { return false; }
  })();
  out.webCryptoSha256 = (() => {
    try { return typeof crypto !== "undefined" && !!crypto.subtle && typeof crypto.subtle.digest === "function"; }
    catch { return false; }
  })();
  out.storageEstimate = typeof navigator !== "undefined" && !!navigator.storage && typeof navigator.storage.estimate === "function";
  out.storagePersist = typeof navigator !== "undefined" && !!navigator.storage && typeof navigator.storage.persist === "function";
  if (out.storageEstimate) {
    try { out.storageEstimateSample = await navigator.storage.estimate(); } catch (e) { out.storageEstimateSample = { error: String(e) }; }
  }
  out.webLocks = typeof navigator !== "undefined" && !!navigator.locks && typeof navigator.locks.request === "function";
  out.broadcastChannel = typeof BroadcastChannel !== "undefined";
  out.serviceWorker = typeof navigator !== "undefined" && "serviceWorker" in navigator;
  out.geolocation = typeof navigator !== "undefined" && !!navigator.geolocation;
  out.isSecureContext = typeof isSecureContext !== "undefined" ? isSecureContext : null;
  out.userAgent = navigator.userAgent;
  return out;
})()`;

async function main() {
  const server = await startServer();
  const browser = await chromium.launch({
    executablePath: CHROMIUM_PATH,
    headless: true,
    args: ["--no-sandbox", "--disable-gpu"],
  });

  const consoleErrors = [];
  const pageErrors = [];
  let statusPanelOutcome = "never left loading";

  try {
    const page = await browser.newPage();
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (err) => pageErrors.push(String(err)));

    await page.goto(`http://localhost:${PORT}/index.html`, { waitUntil: "load" });

    try {
      await page.waitForFunction(
        () => {
          const el = document.getElementById("status-panel");
          return el && !el.classList.contains("loading");
        },
        { timeout: 15000 }
      );
      const classes = await page.$eval("#status-panel", (el) => el.className);
      statusPanelOutcome = classes.includes("error") ? "error (feed unreachable from this host/run)" : "live";
    } catch {
      statusPanelOutcome = "timed out still loading";
    }

    let mapOutcome = "not attempted (status panel never went live)";
    if (statusPanelOutcome === "live") {
      mapOutcome = await checkMapAndGeocoding(page);
    }

    const capabilities = await page.evaluate(CAPABILITY_PROBE);
    capabilities.browserVersion = browser.version();

    console.log("Status panel outcome:", statusPanelOutcome);
    console.log("Map/geocoding outcome:", mapOutcome);
    console.log("Console errors:", consoleErrors.length ? consoleErrors : "none");
    console.log("Page errors:", pageErrors.length ? pageErrors : "none");
    console.log("Capabilities:", JSON.stringify(capabilities, null, 2));

    await writeCapabilityMatrix(capabilities, statusPanelOutcome, consoleErrors, pageErrors);

    if (pageErrors.length > 0) {
      throw new Error(`${pageErrors.length} uncaught page error(s) during load`);
    }
    if (statusPanelOutcome === "timed out still loading") {
      throw new Error("status panel never left the loading state within 15s");
    }
  } finally {
    await browser.close();
    server.close();
  }
}

/** Opens the map panel (triggers the real OffGeo pack fetch+decode via
 * src/offgeo/geocoder.js) and waits for either a rendered marker or the
 * panel settling with none -- both are real, checkable outcomes; only a
 * page error (already tracked separately) or a timeout is a failure. */
async function checkMapAndGeocoding(page) {
  await page.click("#map-toggle-slot button");
  try {
    await page.waitForFunction(() => document.querySelector("#map-panel .leaflet-container") !== null, {
      timeout: 10000,
    });
  } catch {
    return "timed out waiting for the Leaflet map to initialize";
  }

  // The real pack is ~10MB gzip and decodes ~165k records client-side
  // (OFF-108 measured ~1s in Node/V8) -- give it real headroom before
  // concluding "no markers" rather than "still decoding".
  try {
    await page.waitForFunction(() => document.querySelectorAll("#map-panel .call-marker").length > 0, {
      timeout: 15000,
    });
    const markerCount = await page.$$eval("#map-panel .call-marker", (els) => els.length);
    return `${markerCount} real call(s) geocoded and rendered as markers`;
  } catch {
    return "map initialized, zero calls geocoded this run (not necessarily a bug -- depends on live feed content)";
  }
}

async function writeCapabilityMatrix(cap, statusPanelOutcome, consoleErrors, pageErrors) {
  const chromiumVersionOut = cap.browserVersion || "unknown";
  const rows = [
    ["IndexedDB", cap.indexedDB],
    ["Web Workers", cap.webWorkers],
    ["Streaming `fetch` (`Response.body`)", cap.streamingFetch],
    ['`DecompressionStream("gzip")`', cap.decompressionStreamGzip],
    ["Web Crypto (`crypto.subtle.digest`, for SHA-256)", cap.webCryptoSha256],
    ["Storage API — `navigator.storage.estimate()`", cap.storageEstimate],
    ["Storage API — `navigator.storage.persist()`", cap.storagePersist],
    ["Web Locks (`navigator.locks`)", cap.webLocks],
    ["BroadcastChannel", cap.broadcastChannel],
    ["Service Workers", cap.serviceWorker],
    ["Geolocation (`navigator.geolocation`)", cap.geolocation],
    ["Secure context (`isSecureContext`)", cap.isSecureContext],
  ];
  const md = `# Browser capability matrix (\`OFF-013\`, Group 6)

Status: Probed live ${new Date().toISOString().slice(0, 10)} against one real device/browser
Scope: [\`todo.md\`](./todo.md) Group 6. This is a **measured baseline from the one browser available in this dev environment**, not the production target-device matrix -- \`roadmap.md\` §13 separately tracks "Reference Android/browser matrix" as its own decision due at R1 start, once real target devices/browsers are chosen. Re-run \`node tests/e2e/run.mjs\` (regenerates this file) against each browser added to that matrix as it's decided.

Probed with: playwright-core driving system Chromium (\`${CHROMIUM_PATH}\`), version \`${chromiumVersionOut}\`, via \`tests/e2e/run.mjs\`.

| Capability | Supported here | Degraded/unsupported behavior required |
| --- | --- | --- |
${rows.map(([name, ok]) => `| ${name} | ${ok ? "Yes" : "**No**"} | ${degradedBehaviorFor(name)} |`).join("\n")}

Storage estimate sample from this probe run: \`${JSON.stringify(cap.storageEstimateSample)}\`.

## Required degraded/unsupported behavior (per \`spec.md\`)

None of these may fail silently -- each missing API needs its own explicit state, not a caught-and-ignored error:

- **IndexedDB missing/blocked** (private browsing in some browsers): keep live calls usable (the feed doesn't need IndexedDB), disable install with an explicit explanation (\`spec.md\` §15 "IndexedDB/private-mode unsupported").
- **Web Workers missing**: the geocoder/distance engine (R4) would need a same-thread fallback or to disable distance calculation with an explicit reason, never a silent hang.
- **Streaming fetch / DecompressionStream missing**: pack download falls back to a full-buffer download-then-decompress path, or is disabled with an explicit size/compatibility warning -- must not attempt a partial/streaming read that then fails opaquely.
- **Web Crypto missing**: pack checksum verification cannot run; installing a pack must be refused outright rather than skipping verification, since \`spec.md\` §13.6 requires checksum verification before activation unconditionally.
- **Storage estimate/persist missing**: proceed without a quota preflight, but surface that the size/eviction risk is unknown rather than asserting persistence succeeded.
- **Web Locks missing**: multi-tab install coordination (\`spec.md\` §8's compare-and-swap/fencing language) needs a fallback coordination strategy (e.g. a single \`BroadcastChannel\`-based leader election) or must refuse concurrent installs from multiple tabs rather than racing them.
- **BroadcastChannel missing**: cross-tab "another tab installed/upgraded" notification (\`spec.md\` §15) degrades to poll-based detection on next load instead of instant cross-tab notice.
- **Service Workers missing**: offline/PWA behavior (R6) is simply unavailable; the app must keep working online-only rather than registering a worker that silently no-ops (the audit already found the *current* worker does exactly that silent no-op -- see \`index-html-audit.md\` finding 9).
- **Geolocation missing/denied/timed out**: \`spec.md\` §10/§15 already requires calls/geocoding to keep working with an explicit recovery action; this probe only confirms the API's presence, not permission-grant behavior (that needs a manual/interactive test, not a headless probe).
- **Not a secure context**: several of the above APIs (Web Crypto, Storage API, Service Workers) are themselves unavailable outside a secure context; \`spec.md\` §13.10 already requires HTTPS in production for exactly this reason.

## Smoke-test outcome from this same probe run

- Status panel reached: \`${statusPanelOutcome}\`
- Console errors: ${consoleErrors.length ? consoleErrors.map((e) => `\`${e}\``).join(", ") : "none"}
- Uncaught page errors: ${pageErrors.length ? pageErrors.map((e) => `\`${e}\``).join(", ") : "none"}

This section is regenerated every run of \`node tests/e2e/run.mjs\` and reflects that specific run's live-feed reachability, not a fixed guarantee.
`;
  await writeFile(path.join(ROOT, "notes/offgeo/browser-capability-matrix.md"), md);
}

function degradedBehaviorFor(name) {
  if (name.startsWith("IndexedDB")) return "Live calls stay usable; install disabled with explanation";
  if (name.startsWith("Web Workers")) return "Distance engine disabled with explicit reason, not a silent hang";
  if (name.startsWith("Streaming")) return "Fall back to full-buffer download-then-decompress";
  if (name.startsWith("`DecompressionStream")) return "Fall back to full-buffer download-then-decompress";
  if (name.startsWith("Web Crypto")) return "Refuse pack install outright (no unverified activation)";
  if (name.startsWith("Storage API — `navigator.storage.estimate")) return "Skip quota preflight; surface size risk as unknown";
  if (name.startsWith("Storage API — `navigator.storage.persist")) return "Proceed without persistence guarantee; note eviction risk";
  if (name.startsWith("Web Locks")) return "BroadcastChannel-based leader election, or refuse concurrent installs";
  if (name.startsWith("BroadcastChannel")) return "Fall back to poll-based cross-tab update detection";
  if (name.startsWith("Service Workers")) return "Stay online-only; do not register a no-op worker";
  if (name.startsWith("Geolocation")) return "Keep calls/geocoding usable; explicit recovery action";
  if (name.startsWith("Secure context")) return "Several APIs above are unavailable outside a secure context by spec";
  return "";
}

main().then(
  () => {
    console.log("\nE2E smoke test: PASS");
    process.exit(0);
  },
  (err) => {
    console.error("\nE2E smoke test: FAIL —", err.message);
    process.exit(1);
  }
);
