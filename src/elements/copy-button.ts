import { define } from "../client/store-element.ts";
import { html } from "../render/dom.ts";

type CopyStatus = "copied" | "failed" | "idle" | "unavailable" | "working";

const STATUS_TEXT: Readonly<Record<CopyStatus, string>> = {
  copied: "Copied",
  failed: "Copy failed",
  idle: "",
  unavailable: "Could not load the remove commands",
  working: "Preparing…",
};

// `command` attribute (shown unless show-text="false") or an async `build` property; see DOCS-ui-contract.md.
export class CopyButton extends HTMLElement {
  static readonly observedAttributes = ["button-text", "command", "label", "show-text"];

  #status: CopyStatus = "idle";
  #statusElement: HTMLElement | null = null;
  build: (() => Promise<string>) | null = null;

  async #copy(): Promise<void> {
    const command = this.getAttribute("command");
    const build = this.build ?? ((): Promise<string> => Promise.resolve(command ?? ""));
    this.#setStatus("working");
    let text: string;
    try {
      text = await build();
    } catch {
      this.#setStatus("unavailable");
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      this.#setStatus("copied");
    } catch {
      this.#setStatus("failed");
    }
  }

  #render(): void {
    const command = this.getAttribute("command");
    if (command === null && this.build === null) {
      this.replaceChildren(html("span", { class: "muted" }, "No remove command"));
      return;
    }
    const title = this.getAttribute("label") ?? "Copy remove command";
    const button = html("button", { class: "btn", title, type: "button" }, this.getAttribute("button-text") ?? "Copy");
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      void this.#copy();
    });
    this.#statusElement = html("span", { "aria-live": "polite", class: "copy-status" }, STATUS_TEXT[this.#status]);
    const isShowText = command !== null && this.getAttribute("show-text") !== "false";
    const text = isShowText ? html("code", { class: "command" }, command) : null;
    this.replaceChildren(html("span", { class: "copy" }, text, button, this.#statusElement));
  }

  #setStatus(status: CopyStatus): void {
    this.#status = status;
    if (this.#statusElement !== null) this.#statusElement.textContent = STATUS_TEXT[status];
  }

  attributeChangedCallback(): void {
    if (this.isConnected) this.#render();
  }

  connectedCallback(): void {
    this.#render();
  }
}

define("copy-button", CopyButton);
