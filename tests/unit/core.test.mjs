import { test } from "node:test";
import assert from "node:assert/strict";
import { html, raw } from "../../src/framework/core.js";

test("html() escapes interpolated values by default", () => {
  const name = `<script>alert("x")</script>`;
  const out = html`<span>${name}</span>`;
  assert.equal(out, "<span>&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;</span>");
});

test("html() drops null/undefined/false without printing them", () => {
  const out = html`<a>${null}${undefined}${false}</a>`;
  assert.equal(out, "<a></a>");
});

test("html() joins arrays, escaping each item", () => {
  const items = ["<a>", "b"];
  const out = html`<ul>${items}</ul>`;
  assert.equal(out, "<ul>&lt;a&gt;b</ul>");
});

test("raw() opts a value out of escaping", () => {
  const out = html`<div>${raw("<b>bold</b>")}</div>`;
  assert.equal(out, "<div><b>bold</b></div>");
});

test("raw() inside an array is still unescaped per-item", () => {
  const out = html`${[raw("<i>1</i>"), "<i>2</i>"]}`;
  assert.equal(out, "<i>1</i>&lt;i&gt;2&lt;/i&gt;");
});
