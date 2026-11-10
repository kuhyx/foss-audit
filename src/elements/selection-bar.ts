import type { AppState } from "../client/store.ts";
import type { RemovableItem } from "../lib/schema.ts";
import type { CopyButton } from "./copy-button.ts";

import { clearSelection } from "../client/actions.ts";
import { withRemoves } from "../client/remove-api.ts";
import { selectCheckedItems } from "../client/selectors.ts";
import { define, hasChanged, StoreElement } from "../client/store-element.ts";
import { store } from "../client/store.ts";
import { buildRemoveScript } from "../lib/remove-script.ts";
import { buildSelectionPrompt } from "../lib/selection-prompt.ts";
import { numberFormat } from "../lib/verdict.ts";
import { html } from "../render/dom.ts";
import "./copy-button.ts";

const PROMPT_LABEL = "Copy one Claude prompt per selected item";
const SCRIPT_LABEL = "Copy a shell script of remove commands for every selected item (not run)";

interface Bar {
  readonly count: Text;
  readonly prompt: CopyButton;
  readonly script: CopyButton;
}

function checkedWithRemoves(): Promise<RemovableItem[]> {
  return withRemoves(selectCheckedItems(store.getState()));
}

// The commands are fetched when a copy button is used, for whatever is checked at that moment; nothing is ever run.
function copyButton(label: string, build: () => Promise<string>): CopyButton {
  const button = document.createElement("copy-button") as CopyButton;
  button.setAttribute("label", label);
  button.build = build;
  return button;
}

export class SelectionBar extends StoreElement {
  #bar: Bar | null = null;

  #build(): Bar {
    const count = document.createTextNode("");
    const clear = html("button", { "aria-label": "Clear", class: "link", type: "button" }, "✕");
    clear.addEventListener("click", () => {
      clearSelection();
    });
    const prompt = copyButton(PROMPT_LABEL, async () => buildSelectionPrompt(await checkedWithRemoves()));
    const script = copyButton(SCRIPT_LABEL, async () => buildRemoveScript(await checkedWithRemoves()));
    this.replaceChildren(
      html("section", { "aria-label": "Selection", class: "selection-bar" }, html("span", { class: "selection-count" }, count), clear, prompt, script),
    );
    return { count, prompt, script };
  }

  protected override teardown(): void {
    this.#bar = null;
    super.teardown();
  }

  protected override update(state: AppState, previous: AppState | null): void {
    const checked = state.url.view === "table" ? selectCheckedItems(state) : [];
    if (checked.length === 0) {
      if (this.#bar !== null) this.teardown();
      return;
    }
    if (this.#bar !== null && !hasChanged(state, previous, selectCheckedItems)) return;
    const bar = this.#bar ?? this.#build();
    this.#bar = bar;
    const count = numberFormat.format(checked.length);
    bar.count.data = count;
    bar.prompt.setAttribute("button-text", `Copy Claude prompt (${count})`);
    bar.script.setAttribute("button-text", `Copy remove commands (${count})`);
  }
}

define("selection-bar", SelectionBar);
