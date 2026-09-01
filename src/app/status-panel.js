import { Component, html, raw } from "../framework/core.js";
import { compactElapsedTime } from "./format.js";

/** Owns #status-panel's inner markup: the compact "Incident feed refreshed
 * 1m20s ago" summary and the connecting/live/error status text + call count. Previously this
 * was a handful of scattered classList/textContent calls spread across
 * CallsForService.addTable (index.html:1234-1295) -- see
 * notes/offgeo/index-html-audit.md Part B finding 2. */
export class StatusPanel extends Component {
  onCreate() {
    this.state = {
      phase: "loading", // 'loading' | 'live' | 'error'
      rawTime: null,
      statusText: "Connecting",
      eventCountText: "Fetching calls",
    };
  }

  rootClass() {
    const classes = ["status-panel"];
    if (this.state.phase === "loading") classes.push("loading");
    if (this.state.phase === "error") classes.push("error");
    return classes.join(" ");
  }

  setLoading(statusText = "Updating") {
    this.setState({ phase: "loading", statusText });
  }

  setLive({ eventCountText }) {
    this.setState({ phase: "live", rawTime: new Date(), statusText: "Live", eventCountText });
  }

  /** @param {boolean} hadExistingData - if true, this is a background
   * refresh failure: keep the last known time/count, only flag the error. */
  setError(message, hadExistingData) {
    if (hadExistingData) {
      this.setState({ phase: "error", statusText: message });
    } else {
      this.setState({
        phase: "error",
        rawTime: null,
        statusText: message,
        eventCountText: "No data",
      });
    }
  }

  setEventCount(eventCountText) {
    this.setState({ eventCountText });
  }

  /** Re-render just to recompute the "X minutes ago" text against the
   * clock, without changing any stored data. Called on a 60s tick. */
  refreshRelativeTime() {
    if (this.state.rawTime) {
      this.update();
    }
  }

  refreshFeed() {
    if (this.state.phase !== "loading") this.props.onRefresh?.();
  }

  render() {
    const { phase, rawTime, statusText, eventCountText } = this.state;
    const updateText =
      phase === "loading"
        ? "Incident feed refreshing…"
        : rawTime
          ? `Incident feed refreshed ${compactElapsedTime(rawTime)}`
          : phase === "error"
            ? "Incident feed unavailable"
            : "Incident feed refreshing…";
    return html`
      <button
        type="button"
        class="feed-summary"
        data-on-click="refreshFeed"
        aria-label="Refresh incident feed"
        title="Refresh incident feed"
        ${raw(phase === "loading" ? "disabled" : "")}
      >
        <span class="status-dot" aria-hidden="true"></span>
        <div>
          <p class="update-line" data-time="${rawTime || ""}" id="update">${updateText}</p>
        </div>
      </button>
      <div class="status-meta">
        <span id="calls-status" role="status" aria-live="polite" class="${phase === "error" ? "error" : ""}"
          >${statusText}</span
        >
        <span id="event-count">${eventCountText}</span>
      </div>
    `;
  }
}
