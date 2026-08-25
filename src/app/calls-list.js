import { Component, html, raw } from "../framework/core.js";
import { fetchJson, prettyTime } from "./format.js";
import { eventTypeColor, eventTypeCategoryName } from "./event-category.js";

// Only these feed fields are compared/persisted for the new/changed-row
// cache diff. The previous version (index.html:1335-1354) stored the whole
// mutated event object -- including the synthetic `changed`/`new`/`nearby`
// flags it had just set -- back into localStorage. Since a freshly fetched
// event never carries those synthetic keys, comparing against a cached copy
// that does meant a row marked "new" the first time would compare
// `undefined !== true` on every later poll and get marked "changed"
// forever. Comparing/storing only the canonical fields fixes that (see
// notes/offgeo/index-html-audit.md Part B).
const CACHE_FIELDS = ["EventNumber", "IsOpen", "DateTime", "Address", "ServiceArea", "Community", "EventType"];

function pickCacheFields(event) {
  const clean = {};
  for (const key of CACHE_FIELDS) clean[key] = event[key];
  return clean;
}

function annotateWithCache(events) {
  return events.map((event) => {
    const clean = pickCacheFields(event);
    const cachedRaw = localStorage.getItem(event.EventNumber);
    let isNew = false;
    let isChanged = false;
    if (cachedRaw) {
      try {
        const cached = JSON.parse(cachedRaw);
        isChanged = CACHE_FIELDS.some((key) => clean[key] !== cached[key]);
      } catch {
        isChanged = true;
      }
    } else {
      isNew = true;
    }
    localStorage.setItem(event.EventNumber, JSON.stringify(clean));
    return { ...event, isNew, isChanged };
  });
}

/** Owns #listing: the loading skeleton, error state, and the calls table
 * itself (address links, relative time, open/new/changed row state, and
 * tap-a-row-to-zoom-the-map selection). Ported from
 * CallsForService.buildTable (index.html:1298-1450). Row selection
 * (selectRow) and text filter (applyFilter) intentionally stay outside
 * the render()/setState() cycle -- they mutate the already-rendered DOM
 * directly, exactly like the code they replace, so a filter keystroke or a
 * row selection is never wiped by an unrelated re-render. Only a data
 * refresh (load()) goes through the full render() rebuild, matching the
 * previous full-teardown-per-refresh behavior 1:1 (see audit finding 4) --
 * that behavior wasn't changed here, only reorganized. */
export class CallsList extends Component {
  onCreate() {
    this.apiUrl = "https://leag-caddata-dev-fa-leag-caddata-dev-fa-blue.azurewebsites.us/api/GetCADEvents";
    this.apiKey = "LrxsShPJ3sVycwPqa_Dk-EajBxZJfQGbDBQK1c5wbBoBAzFu2CxMqA==";
    // Third-party CORS proxy with an embedded function key -- carried over
    // unchanged. OFF-011 (notes/offgeo/todo.md Group 5) already flags this
    // as not meeting the "no secret in shipped source" bar; replacing it is
    // that item's job, not this rewrite's.
    this.proxyUrl = "https://api.cors.syrins.tech/?url=";
    this.filterValue = "";
    this.filterInputEl = document.getElementById("filter");
    this.selectedRowTimeout = null;
    this.state = { phase: "loading", events: [], errorMessage: "" };
  }

  getRequestUrl() {
    const sourceUrl = new URL(this.apiUrl);
    sourceUrl.searchParams.set("code", this.apiKey);
    sourceUrl.searchParams.set("_", Date.now().toString());
    return this.proxyUrl + encodeURIComponent(sourceUrl.toString());
  }

  async load() {
    const hadExistingData = this.state.events.length > 0;
    this.props.onLoadingStart?.();
    if (!hadExistingData) {
      this.setState({ phase: "loading" });
    }
    try {
      const json = await fetchJson(this.getRequestUrl());
      if (!json || !Array.isArray(json.Events)) {
        throw new Error("The calls service returned an unexpected response.");
      }
      const events = annotateWithCache(json.Events);
      this.setState({ phase: "live", events });
      this.props.onLoaded?.({ rawTime: json.LastUpdated, count: events.length, events });
    } catch (error) {
      console.error("Unable to load calls for service:", error);
      this.props.onError?.(error.message, hadExistingData);
      if (!hadExistingData) {
        this.setState({ phase: "error", events: [], errorMessage: error.message });
      }
    }
  }

  refresh() {
    return this.load();
  }

  setFilter(value) {
    this.filterValue = value;
    this.applyFilter();
  }

  applyFilter() {
    const filter = this.filterValue.trim().toLowerCase();
    const rows = this.root.querySelectorAll("tbody tr");
    let visibleCount = 0;
    for (const row of rows) {
      const matches = row.textContent.toLowerCase().includes(filter);
      row.classList.toggle("hidden", !matches);
      if (matches) visibleCount += 1;
    }
    const text = filter ? `${visibleCount} of ${rows.length} calls` : `${rows.length} call${rows.length === 1 ? "" : "s"}`;
    this.props.onEventCount?.(text);
  }

  onRender() {
    if (this.state.phase === "live") {
      this.applyFilter();
    }
  }

  /** Scroll the matching row into view and briefly highlight it -- the
   * MapView marker-tap target (see src/app/map-view.js). Clears an active
   * search filter first if it's hiding the row, since a marker tap is an
   * explicit request to see that specific call. */
  focusEvent(eventNumber) {
    const rows = this.root.querySelectorAll("tbody tr");
    const row = [...rows].find((r) => r.dataset.eventNumber === eventNumber);
    if (!row) return;

    if (row.classList.contains("hidden")) {
      this.filterInputEl.value = "";
      this.setFilter("");
    }
    row.scrollIntoView({ behavior: "smooth", block: "center" });
    row.classList.add("selected");
    clearTimeout(this.selectedRowTimeout);
    this.selectedRowTimeout = setTimeout(() => row.classList.remove("selected"), 2000);
  }

  /** Tapping a row zooms the top map panel to that call's location
   * (opening it first if it's closed) -- replaces the old per-row Google
   * Maps iframe embed, which made a request to Google on every expand.
   * See MapView.focusEventOnMap in map-view.js. */
  selectRow(event, rowEl) {
    if (event.target.closest("a")) return;

    const eventData = this.state.events.find((e) => e.EventNumber === rowEl.dataset.eventNumber);
    if (!eventData) return;

    this.root.querySelectorAll("tbody tr.selected").forEach((r) => r.classList.remove("selected"));
    rowEl.classList.add("selected");
    clearTimeout(this.selectedRowTimeout);
    this.selectedRowTimeout = setTimeout(() => rowEl.classList.remove("selected"), 2000);

    this.props.onRowTap?.(eventData);
  }

  renderRow(event, rowIndex) {
    const classes = [];
    if (event.isChanged) classes.push("changed");
    if (event.isNew) classes.push("new");
    if (event.IsOpen) classes.push("open");
    const address = `${event.Address}, ${event.Community}`;
    const mapsHref = `https://www.google.com/maps/search/?api=1&amp;query=${encodeURIComponent(address)}`;
    const categoryColor = eventTypeColor(event.EventType);
    const categoryName = eventTypeCategoryName(event.EventType);
    // The left-edge color now carries the dispatch category (matching
    // the map marker's fill color, see event-category.js), so "new"/
    // "changed" -- previously shown the same way, by swapping that
    // edge's color -- get their own explicit badge instead of competing
    // for the same visual slot.
    const badge = event.isNew ? `<span class="badge-new">New</span>` : event.isChanged ? `<span class="badge-changed">Updated</span>` : "";
    return html`
      <tr
        class="${classes.join(" ")}"
        style="--row-index: ${rowIndex + 1}; --category-color: ${raw(categoryColor)}"
        data-event-number="${event.EventNumber}"
        data-on-click="selectRow"
        title="${categoryName}"
      >
        <td data-label="Address" class="Address">
          <a href="${raw(mapsHref)}" target="_blank" rel="noopener noreferrer">
            ${raw(badge)}
            <span class="address-primary">${event.Address}</span>
            <span class="community">${event.Community}</span>
          </a>
        </td>
        <td data-label="DateTime" class="DateTime" title="${event.DateTime}">${prettyTime(event.DateTime)}</td>
        <td data-label="EventType" class="EventType">${event.EventType}</td>
      </tr>
    `;
  }

  render() {
    if (this.state.phase === "loading" && this.state.events.length === 0) {
      return html`
        <div class="loading-state" aria-hidden="true">
          <div class="loading-content">
            <p>Loading active calls…</p>
            <div class="loading-bar"></div>
            <div class="loading-bar"></div>
            <div class="loading-bar"></div>
          </div>
        </div>
      `;
    }
    if (this.state.phase === "error" && this.state.events.length === 0) {
      return html`
        <div class="error-state">
          <div>
            <strong>Unable to load calls</strong>
            <span>${this.state.errorMessage}</span>
          </div>
        </div>
      `;
    }
    // The feed's own array order gets visually reversed by this render
    // (newest last in the array ends up first in the table) to match the
    // previous tbody.prepend()-per-row behavior exactly.
    const rows = [...this.state.events].reverse().map((event, i) => this.renderRow(event, i));
    return html`
      <table>
        <thead>
          <tr>
            <th class="Address">Address</th>
            <th class="DateTime">DateTime</th>
            <th class="EventType">EventType</th>
          </tr>
        </thead>
        <tbody>
          ${raw(rows.join(""))}
        </tbody>
      </table>
    `;
  }
}
