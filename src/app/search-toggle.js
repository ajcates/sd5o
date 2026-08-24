import { Component, html } from "../framework/core.js";

/** Search icon button injected into #buttons, toggling the (statically
 * markup'd) #search-bar open and focusing #filter. Ported from
 * CallsForService.addSearchToggleButton/toggleSearch (index.html:1201-1224). */
export class SearchToggle extends Component {
  onCreate() {
    this.searchBar = document.getElementById(this.props.searchBarId);
    this.filterInput = document.getElementById(this.props.filterInputId);
    this.state = { open: false };
  }

  toggleSearch() {
    this.setState({ open: !this.state.open });
  }

  onRender() {
    this.searchBar.classList.toggle("open", this.state.open);
    if (this.state.open) {
      this.filterInput.focus();
    } else {
      this.filterInput.blur();
    }
  }

  render() {
    const expanded = this.state.open ? "true" : "false";
    return html`
      <button
        type="button"
        class="icon-button"
        title="Search calls"
        aria-label="Search calls"
        aria-expanded="${expanded}"
        aria-controls="${this.props.searchBarId}"
        data-on-click="toggleSearch"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path
            d="M9.5 3a6.5 6.5 0 1 0 3.98 11.64L19.85 21 21 19.85l-6.36-6.37A6.5 6.5 0 0 0 9.5 3Zm0 2a4.5 4.5 0 1 1 0 9 4.5 4.5 0 0 1 0-9Z"
          />
        </svg>
      </button>
    `;
  }
}
