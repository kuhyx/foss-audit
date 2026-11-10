import { define } from "../client/store-element.ts";
import { html } from "../render/dom.ts";

type CopyStatus = "copied" | "failed" | "idle" | "unavailable" | "working";

const STATUS_TEXT: Readonly<Record<CopyStatus, string>> = {
  copied: "✓",
  failed: "✕",
  idle: "",
  unavailable: "⚠",
  working: "⟳",
};

const STATUS_LABELS: Readonly<Record<CopyStatus, string>> = {
  copied: "Copied",
  failed: "Copy failed",
  idle: "",
  unavailable: "Could not load the remove commands",
  working: "Loading…",
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
      this.#announce("Could not load the remove commands", "alert");
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      this.#setStatus("copied");
      this.#announce("Copied", "status");
    } catch {
      this.#setStatus("failed");
      this.#announce("Copy failed", "alert");
    }
  }

  #announce(message: string, role: "alert" | "status"): void {
    const announcer = html("span", { "aria-live": role === "status" ? "polite" : "assertive", class: "sr-only", role }, message);
    document.body.append(announcer);
    setTimeout(() => { announcer.remove(); }, 1000);
  }

  #render(): void {
    const command = this.getAttribute("command");
    if (command === null && this.build === null) {
      this.replaceChildren(html("span", { "aria-label": "No remove command", class: "muted" }, "–"));
      return;
    }
    const title = this.getAttribute("label") ?? "Copy remove command";
    const button = html("button", { "aria-label": title, class: "btn", type: "button" }, this.getAttribute("button-text") ?? "⧉");
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      void this.#copy();
    });
    this.#statusElement = html("span", { "aria-label": STATUS_LABELS[this.#status], "aria-live": "polite", class: "copy-status" }, STATUS_TEXT[this.#status]);
    const isShowText = command !== null && this.getAttribute("show-text") !== "false";
    const text = isShowText ? html("code", { class: "command" }, command) : null;
    this.replaceChildren(html("span", { class: "copy" }, text, button, this.#statusElement));
  }

  #setStatus(status: CopyStatus): void {
    this.#status = status;
    if (this.#statusElement === null) {
      return;
    }

    this.#statusElement.textContent = STATUS_TEXT[status];
    this.#statusElement.setAttribute("aria-label", STATUS_LABELS[status]);
  }

  attributeChangedCallback(): void {
    if (this.isConnected) this.#render();
  }

  connectedCallback(): void {
    this.#render();
  }
}

define("copy-button", CopyButton);
