/**
 * Mini component framework for this app. Deliberately small: a `Component`
 * base class (state -> render -> delegated events), an escaping `html`
 * template tag, and `mount()`. No virtual DOM/diffing -- every `setState`
 * call fully replaces the component root's `innerHTML`, exactly matching
 * what the app's previous hand-written `addTable()`/`buildTable()` already
 * did on every refresh (see notes/offgeo/index-html-audit.md Part B). No
 * build step: loaded as a plain ES module.
 *
 * Event binding is delegated once per event type at the component's root
 * element (mount time), not re-attached on every render -- markup opts in
 * with `data-on-click="methodName"` etc., and the named method is called on
 * the component instance with (event, matchedElement).
 */

const ESCAPE_MAP = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (c) => ESCAPE_MAP[c]);
}

/** Wrap a string that is already safe/trusted HTML so `html` doesn't escape it. */
export class Raw {
  constructor(value) {
    this.value = value;
  }
  toString() {
    return this.value;
  }
}

export function raw(value) {
  return new Raw(value);
}

/**
 * Tagged template: interpolated values are HTML-escaped by default. Arrays
 * are joined (each item escaped/raw per the same rule); `raw()` opts a
 * value out of escaping for pre-built trusted markup (e.g. a list of
 * already-rendered row strings).
 */
export function html(strings, ...values) {
  let out = strings[0];
  for (let i = 0; i < values.length; i++) {
    out += stringifyValue(values[i]);
    out += strings[i + 1];
  }
  return out;
}

function stringifyValue(value) {
  if (value === null || value === undefined || value === false) {
    return "";
  }
  if (Array.isArray(value)) {
    return value.map(stringifyValue).join("");
  }
  if (value instanceof Raw) {
    return value.value;
  }
  return escapeHtml(value);
}

const DELEGATED_EVENT_TYPES = ["click", "input", "change", "keydown", "submit"];

export class Component {
  constructor(root, props = {}) {
    this.root = root;
    this.props = props;
    this.state = {};
    this._destroyed = false;
    if (this.onCreate) this.onCreate();
  }

  setState(partial) {
    const next = typeof partial === "function" ? partial(this.state) : partial;
    this.state = { ...this.state, ...next };
    this.update();
  }

  update() {
    if (this._destroyed) return;
    if (typeof this.rootClass === "function") {
      this.root.className = this.rootClass();
    }
    this.root.innerHTML = this.render();
    if (this.onRender) this.onRender();
  }

  destroy() {
    this._destroyed = true;
    if (this.onDestroy) this.onDestroy();
  }
}

/** Instantiate `ComponentClass` on `root`, wire delegated events, render once. */
export function mount(ComponentClass, root, props) {
  const instance = new ComponentClass(root, props);
  for (const type of DELEGATED_EVENT_TYPES) {
    root.addEventListener(type, (event) => {
      const attr = `data-on-${type}`;
      const target = event.target.closest(`[${attr}]`);
      if (!target || !root.contains(target)) return;
      const methodName = target.getAttribute(attr);
      const method = instance[methodName];
      if (typeof method !== "function") {
        console.warn(`[framework] ${ComponentClass.name} has no method "${methodName}"`);
        return;
      }
      method.call(instance, event, target);
    });
  }
  instance.update();
  return instance;
}
