import type { AppState } from "../client/store.ts";

import { dismissBanner } from "../client/actions.ts";
import { selectBannerMessages } from "../client/selectors.ts";
import { define, hasChanged, StoreElement } from "../client/store-element.ts";
import { html } from "../render/dom.ts";

// Scanner errors and a failed rescan: a warning above the data, which still shows.
export class ErrorBanner extends StoreElement {
  protected override update(state: AppState, previous: AppState | null): void {
    if (!hasChanged(state, previous, selectBannerMessages)) return;
    const messages = selectBannerMessages(state);
    if (messages.length === 0) {
      this.teardown();
      return;
    }
    const dismiss = html("button", { class: "btn", type: "button" }, "Dismiss");
    dismiss.addEventListener("click", dismissBanner);
    const list = html("ul", {}, ...messages.map((message) => html("li", {}, message)));
    this.replaceChildren(html("div", { class: "banner", role: "alert" }, list, dismiss));
  }
}

define("error-banner", ErrorBanner);
