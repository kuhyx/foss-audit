/**
 * Every field of the open item plus its alternative, on a non-modal
 * `<dialog>` beside the table. It opens without taking focus, so ↑↓ keep
 * moving the table row. The remove command is copy-only; `requiredBy` is
 * prominent because a package others need is not a one-command removal.
 */
import type { RemoveFetch } from "../client/remove.ts";
import type { AppState } from "../client/store.ts";
import type { Alternative, Item } from "../lib/schema.ts";
import type { Child } from "../render/dom.ts";

import { closeItem } from "../client/actions.ts";
import { withRemove } from "../client/remove-api.ts";
import { watchRemove } from "../client/remove.ts";
import { selectSelectedItem } from "../client/selectors.ts";
import { define, hasChanged, StoreElement } from "../client/store-element.ts";
import { buildItemPrompt, isPromptCandidate } from "../lib/claude-prompt.ts";
import { EFFORT_LABELS, FIT_LABELS, hasTrackedDependants, isCacheSource } from "../lib/verdict.ts";
import { buildButton, commandButton } from "../render/command.ts";
import { html } from "../render/dom.ts";
import { verdictBadge } from "../render/verdict-badge.ts";

function field(label: string, value: Child): HTMLElement {
  return html("div", { class: "field" }, html("dt", {}, label), html("dd", {}, value));
}

function orDash(value: null | string): string {
  return value === null || value === "" ? "—" : value;
}

function yesNo(isYes: boolean, yes: string): string {
  return isYes ? `yes — ${yes}` : "no";
}

function section(id: string, heading: string, ...children: readonly Child[]): HTMLElement {
  return html("section", { "aria-labelledby": id, class: "panel-section" }, html("h3", { id }, heading), ...children);
}

function fields(item: Item): HTMLElement {
  const homepage = item.url === null ? "—" : html("a", { href: item.url, rel: "noreferrer noopener", target: "_blank" }, item.url);
  return html(
    "dl",
    { class: "fields" },
    field("Verdict", verdictBadge(item.verdict)),
    field("Own code", yesNo(item.own, "kuhy's own")),
    field("Untracked file", yesNo(item.loose, "in ~/.local/bin, no repo or package tracks it")),
    field("Dead launcher", yesNo(item.dangling, "the .desktop file's Exec target no longer exists")),
    field("Evidence", orDash(item.reason)),
    field("Licence", orDash(item.license)),
    field("Version", orDash(item.version)),
    field("Source", item.source),
    field("Installed as", item.explicit ? "explicit" : "dependency"),
    field("Orphan", yesNo(item.orphan, "nothing requires it any more")),
    field("Homepage", homepage),
    field("ID", html("code", {}, item.id)),
  );
}

function alternativeSection(alt: Alternative): HTMLElement {
  const names =
    alt.names.length === 0
      ? html("p", { class: "muted" }, "No named alternative in the curated list.")
      : html("ol", { class: "alt-names" }, ...alt.names.map((name) => html("li", {}, name)));
  const installed =
    alt.installed.length === 0
      ? null
      : html(
          "p",
          { class: "installed-line" },
          html("span", { class: "badge badge-success" }, "Already installed"),
          " ",
          [...new Set(alt.installed)].join(", "),
        );
  const facts = html(
    "dl",
    { class: "fields" },
    field("Fit", FIT_LABELS[alt.fit]),
    field("Build-it effort", alt.effort === null ? "—" : EFFORT_LABELS[alt.effort]),
    field("Why that effort", orDash(alt.effortReason)),
    field("Lock-in", orDash(alt.lockIn)),
  );
  return section("alt-heading", "FOSS alternative", names, installed, facts);
}

// Why `requiredBy` is empty: nothing needs it, no project names it, or not tracked.
function noDependantsText(item: Item): string {
  if (isCacheSource(item)) {
    return "No ~/src lockfile or build file names it: a transitive dependency or a stale cache entry.";
  }
  return hasTrackedDependants(item)
    ? "Nothing depends on it."
    : `Not tracked: reverse dependencies are only known for pacman and AUR packages, not ${item.source}.`;
}

function requiredSection(item: Item): HTMLElement {
  const isCached = isCacheSource(item);
  const count = item.requiredBy.length;
  if (count === 0) {
    return section("req-heading", isCached ? "Used by" : "Required by", html("p", { class: "muted" }, noDependantsText(item)));
  }
  const noun = isCached ? "project" : "package";
  return section(
    "req-heading",
    isCached ? "Used by" : "Required by",
    html("p", { class: "warning-line" }, `by ${count} ${count === 1 ? noun : noun + "s"}:`),
    html("ul", { class: "req-list" }, ...item.requiredBy.map((name) => html("li", {}, html("code", {}, name)))),
  );
}

function promptSection(item: Item): HTMLElement | null {
  if (!isPromptCandidate(item)) return null;
  const button = buildButton(
    async (): Promise<string> => buildItemPrompt(await withRemove(item)),
    "Copy Claude prompt",
    "Copy a Claude prompt for this item",
  );
  const note = html(
    "p",
    { class: "muted" },
    `A prompt to research, suggest and install a FOSS alternative. It never removes ${item.name}.`,
  );
  return section("prompt-heading", "Hand it to Claude", note, button);
}

function removeBody(fetched: RemoveFetch, id: string): Node[] {
  if (fetched.kind === "loading") {
    return [html("p", { class: "muted", "data-testid": "remove-loading" }, "Loading the remove command…")];
  }
  if (fetched.kind === "error") {
    return [html("p", { class: "warning-line", role: "alert" }, `Could not load the remove command: ${fetched.message}`)];
  }
  const info = fetched.infos.get(id);
  const button = commandButton(info?.removeCommand);
  return info === undefined || info.removeVia === "" ? [button] : [button, html("p", { class: "muted", "data-testid": "remove-via" }, info.removeVia)];
}

export class DetailPanel extends StoreElement {
  #stopRemove: (() => void) | null = null;

  #render(item: Item): void {
    this.teardown();
    const close = html("button", { "aria-label": "Close details (Esc)", class: "btn", type: "button" }, "Close");
    close.addEventListener("click", closeItem);
    const heading = html("h3", { id: "remove-heading" }, "Remove");
    const remove = html("section", { "aria-labelledby": "remove-heading", class: "panel-section" }, heading);
    const body = html(
      "div",
      { class: "panel-body" },
      fields(item),
      remove,
      requiredSection(item),
      item.alternative === null ? null : alternativeSection(item.alternative),
      promptSection(item),
    );
    const head = html("div", { class: "panel-head" }, html("h2", { id: "panel-title" }, item.name), close);
    // `open` rather than show(): show() would move focus off the table row.
    const dialog = html("dialog", { "aria-labelledby": "panel-title", class: "panel", open: true }, head, body);
    dialog.addEventListener("cancel", (event) => {
      event.preventDefault();
      closeItem();
    });
    this.replaceChildren(dialog);
    this.#stopRemove = watchRemove([item.id], (fetched) => {
      remove.replaceChildren(heading, ...removeBody(fetched, item.id));
    });
  }

  protected override teardown(): void {
    this.#stopRemove?.();
    this.#stopRemove = null;
    super.teardown();
  }

  protected override update(state: AppState, previous: AppState | null): void {
    const shown = (s: AppState): Item | null =>
      s.url.view === "summary" || s.scan.kind !== "ready" ? null : selectSelectedItem(s);
    if (!hasChanged(state, previous, shown)) return;
    const item = shown(state);
    if (item === null) this.teardown();
    else this.#render(item);
  }
}

define("detail-panel", DetailPanel);
