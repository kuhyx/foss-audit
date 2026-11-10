/**
 * The `?` shortcut sheet: a modal `<dialog>` that is itself the scrim, so a
 * click on it outside `.help` closes it. Esc is keyboard.ts's.
 */
import type { AppState } from "../client/store.ts";

import { closeHelp } from "../client/actions.ts";
import { define, hasChanged, StoreElement } from "../client/store-element.ts";
import { SHORTCUTS } from "../lib/views.ts";
import { html } from "../render/dom.ts";

function sheet(): HTMLElement {
  const close = html("button", { "aria-label": "Close", autofocus: true, class: "btn", type: "button" }, "✕");
  close.addEventListener("click", closeHelp);
  const rows = SHORTCUTS.map(([key, what]) =>
    html("div", { class: "help-row" }, html("dt", {}, html("kbd", {}, key)), html("dd", {}, what)),
  );
  return html(
    "div",
    { class: "help" },
    html("h2", {}, html("span", { "aria-label": "Keyboard shortcuts" }, "⌨")),
    html("dl", {}, ...rows),
    html(
      "p",
      { "aria-label": "Every filter, the sort and the open row live in the URL, so the address bar is always a shareable link.", class: "muted" },
      "⧉",
    ),
    close,
  );
}

export class HelpOverlay extends StoreElement {
  #dialog: HTMLDialogElement | null = null;

  #open(): void {
    const dialog = html("dialog", { "aria-label": "Keyboard shortcuts", class: "scrim" }, sheet());
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) closeHelp();
    });
    dialog.addEventListener("cancel", (event) => {
      event.preventDefault();
      closeHelp();
    });
    this.replaceChildren(dialog);
    this.#dialog = dialog;
    dialog.showModal();
    dialog.querySelector<HTMLElement>("[autofocus]")?.focus();
  }

  protected override teardown(): void {
    this.#dialog?.close();
    this.#dialog = null;
    super.teardown();
  }

  protected override update(state: AppState, previous: AppState | null): void {
    // Only over the app: a modal on the hidden app would make the error screen inert.
    const isOpen = (s: AppState): boolean => s.helpOpen && s.scan.kind === "ready";
    if (!hasChanged(state, previous, isOpen)) return;
    if (isOpen(state)) this.#open();
    else this.teardown();
  }
}

define("help-overlay", HelpOverlay);
