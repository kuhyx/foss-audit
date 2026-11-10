import type { AppState } from "../client/store.ts";

import { dismissBanner } from "../client/actions.ts";
import { selectBannerMessages } from "../client/selectors.ts";
import { define, hasChanged, StoreElement } from "../client/store-element.ts";
import { html } from "../render/dom.ts";
import { glyph, GLYPH } from "../render/glyph.ts";

const RESCAN_FAILED = "Rescan failed: ";

// ⚠ (or ⟳ ⚠ for a failed rescan) then the error itself, which is the backend's diagnostic (kept).
function item(message: string): HTMLElement {
  const isRescan = message.startsWith(RESCAN_FAILED);
  const mark = isRescan ? glyph(`${GLYPH.rescan} ${GLYPH.warning}`, "Rescan failed:") : glyph(GLYPH.warning, "Error:");
  return html("li", {}, mark, " ", isRescan ? message.slice(RESCAN_FAILED.length) : message);
}

// Scanner errors and a failed rescan: a warning above the data, which still shows.
export class ErrorBanner extends StoreElement {
  protected override update(state: AppState, previous: AppState | null): void {
    if (!hasChanged(state, previous, selectBannerMessages)) return;
    const messages = selectBannerMessages(state);
    if (messages.length === 0) {
      this.teardown();
      return;
    }
    const dismiss = html("button", { "aria-label": "Dismiss", class: "btn", type: "button" }, GLYPH.close);
    dismiss.addEventListener("click", dismissBanner);
    const list = html("ul", {}, ...messages.map((message) => item(message)));
    this.replaceChildren(html("div", { class: "banner", role: "alert" }, list, dismiss));
  }
}

define("error-banner", ErrorBanner);
