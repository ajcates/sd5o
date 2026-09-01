import { test, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import { ageMinutes, compactElapsedTime, prettyTime, fetchJson } from "../../src/app/format.js";

function feedDateString(date) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())}-${date.getFullYear()} ${pad(date.getHours())}:${pad(
    date.getMinutes()
  )}:${pad(date.getSeconds())}`;
}

test("ageMinutes() reads the feed's MM-DD-YYYY format and returns elapsed minutes", () => {
  const fiveMinutesAgo = new Date(Date.now() - 5 * 60_000);
  const minutes = ageMinutes(feedDateString(fiveMinutesAgo));
  assert.ok(Math.abs(minutes - 5) <= 1, `expected ~5, got ${minutes}`);
});

test("prettyTime() renders a relative-time string for a recent timestamp", () => {
  const tenMinutesAgo = new Date(Date.now() - 10 * 60_000);
  const text = prettyTime(feedDateString(tenMinutesAgo));
  assert.match(text, /ago|minute/i);
});

test("compactElapsedTime() renders the compact feed refresh age", () => {
  assert.match(compactElapsedTime(new Date(Date.now() - 10_000)), /^(9|10)s ago$/);
  assert.match(compactElapsedTime(new Date(Date.now() - 80_000)), /^1m(19|20)s ago$/);
  assert.match(compactElapsedTime(new Date(Date.now() - (2 * 60 + 5) * 60_000)), /^2h(4|5)m ago$/);
});

let originalFetch;
beforeEach(() => {
  originalFetch = globalThis.fetch;
});
afterEach(() => {
  globalThis.fetch = originalFetch;
});

test("fetchJson() parses an ordinary JSON body", async () => {
  globalThis.fetch = async () => new Response(JSON.stringify({ Events: [] }), { status: 200 });
  const data = await fetchJson("https://example.invalid/feed");
  assert.deepEqual(data, { Events: [] });
});

test("fetchJson() unwraps a double-JSON-encoded body (observed feed/proxy quirk)", async () => {
  const doubleEncoded = JSON.stringify(JSON.stringify({ Events: [1, 2] }));
  globalThis.fetch = async () => new Response(doubleEncoded, { status: 200 });
  const data = await fetchJson("https://example.invalid/feed");
  assert.deepEqual(data, { Events: [1, 2] });
});

test("fetchJson() throws with the HTTP status when the body isn't JSON", async () => {
  globalThis.fetch = async () => new Response("<html>not json</html>", { status: 502 });
  await assert.rejects(() => fetchJson("https://example.invalid/feed"), /HTTP 502/);
});

test("fetchJson() throws using the body's message when the response is a non-ok JSON error", async () => {
  globalThis.fetch = async () =>
    new Response(JSON.stringify({ message: "key revoked" }), { status: 401, statusText: "Unauthorized" });
  await assert.rejects(() => fetchJson("https://example.invalid/feed"), /key revoked \(HTTP 401\)/);
});
