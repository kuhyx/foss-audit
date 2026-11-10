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
import { hasTrackedDependants, isCacheSource, numberFormat } from "../lib/verdict.ts";
import { buildButton, commandButton } from "../render/command.ts";
import { html } from "../render/dom.ts";
import { effortMark, fitMark, glyph, GLYPH, named, yesNoMark } from "../render/glyph.ts";
import { verdictBadge } from "../render/verdict-badge.ts";

function icon(symbol: string): Child {
  return html("span", { "aria-hidden": "true", class: "icon" }, symbol);
}

function field(ariaLabel: string, icon: Child, value: Child): HTMLElement {
  return html("div", { "aria-label": ariaLabel, class: "field" }, html("dt", {}, icon), html("dd", {}, value));
}

function orDash(value: null | string): string {
  return value === null || value === "" ? "—" : value;
}

function yesNo(isYes: boolean, yes: string): HTMLElement {
  return yesNoMark(isYes, yes);
}

function section(id: string, ariaLabel: string, icon: Child, ...children: readonly Child[]): HTMLElement {
  return html("section", { "aria-labelledby": id, class: "panel-section" }, html("h3", { "aria-label": ariaLabel, id }, icon), ...children);
}

function fields(item: Item): HTMLElement {
  const homepage = item.url === null ? "—" : html("a", { href: item.url, rel: "noreferrer noopener", target: "_blank" }, item.url);
  return html(
    "dl",
    { class: "fields" },
    field("Verdict", icon(GLYPH.verdict), verdictBadge(item.verdict)),
    field("Own code", icon(GLYPH.own), yesNo(item.own, "kuhy's own")),
    field("Untracked file", icon(GLYPH.loose), yesNo(item.loose, "in ~/.local/bin, no repo or package tracks it")),
    field("Dead launcher", icon(GLYPH.dangling), yesNo(item.dangling, "the .desktop file's Exec target no longer exists")),
    field("Evidence", icon("🔎"), orDash(item.reason)),
    field("Licence", icon(GLYPH.license), orDash(item.license)),
    field("Version", icon(GLYPH.version), orDash(item.version)),
    field("Source", icon(GLYPH.source), item.source),
    field("Installed as", icon(GLYPH.kind), named(item.explicit ? "explicit" : "dependency", item.explicit ? "explicit" : "dependency")),
    field("Orphan", icon(GLYPH.orphan), yesNo(item.orphan, "nothing requires it any more")),
    field("Homepage", icon("🌐"), homepage),
    field("ID", icon("#"), html("code", {}, item.id)),
  );
}

function alternativeSection(alt: Alternative): HTMLElement {
  const names =
    alt.names.length === 0
      ? html("p", { "aria-label": "No named alternative in the curated list.", class: "muted" }, icon("—"))
      : html("ol", { class: "alt-names" }, ...alt.names.map((name) => html("li", {}, name)));
  const installed =
    alt.installed.length === 0
      ? null
      : html(
          "p",
          { "aria-label": "Already installed", class: "installed-line" },
          html("span", { class: "badge badge-success" }, icon("📦")),
          " ",
          [...new Set(alt.installed)].join(", "),
        );
  const facts = html(
    "dl",
    { class: "fields" },
    field("Fit", icon(GLYPH.fit), fitMark(alt.fit)),
    field("Build-it effort", icon(GLYPH.effort), alt.effort === null ? "—" : effortMark(alt.effort)),
    field("Why that effort", icon("🧭"), orDash(alt.effortReason)),
    field("Lock-in", icon("🔒"), orDash(alt.lockIn)),
  );
  return section("alt-heading", "FOSS alternative", icon("🌿"), names, installed, facts);
}

// Why `requiredBy` is empty: nothing needs it, no project names it, or not tracked.
function noDependantsText(item: Item): HTMLElement {
  if (isCacheSource(item)) {
    return glyph(GLYPH.empty, "No ~/src lockfile or build file names it: a transitive dependency or a stale cache entry.", "muted");
  }
  return hasTrackedDependants(item)
    ? glyph("—", "Nothing depends on it.", "muted")
    : glyph(`${GLYPH.warning} ?`, `Not tracked: reverse dependencies are only known for pacman and AUR packages, not ${item.source}.`, "muted");
}

function requiredSection(item: Item): HTMLElement {
  const isCached = isCacheSource(item);
  const count = item.requiredBy.length;
  if (count === 0) {
    return section("req-heading", isCached ? "Used by" : "Required by", icon(GLYPH.requiredBy), html("p", { class: "muted" }, noDependantsText(item)));
  }
  const noun = isCached ? "project" : "package";
  const spokenCount = `Required by ${count} ${count === 1 ? noun : noun + "s"}: removing it is not a one-command job.`;
  return section(
    "req-heading",
    isCached ? "Used by" : "Required by",
    icon(GLYPH.requiredBy),
    html("p", { "aria-label": spokenCount, class: "warning-line", role: "img" }, numberFormat.format(count)),
    html("ul", { class: "req-list" }, ...item.requiredBy.map((name) => html("li", {}, html("code", {}, name)))),
  );
}

function promptSection(item: Item): HTMLElement | null {
  if (!isPromptCandidate(item)) return null;
  const button = buildButton(
    async (): Promise<string> => buildItemPrompt(await withRemove(item)),
    `${GLYPH.copy} ${GLYPH.claude}`,
    `Copy Claude prompt: research, suggest and install a FOSS alternative. It never removes ${item.name}.`,
  );
  return section("prompt-heading", "Hand it to Claude", icon(GLYPH.claude), button);
}

function removeBody(fetched: RemoveFetch, id: string): Node[] {
  if (fetched.kind === "loading") {
    return [html("p", { "aria-label": "Loading the remove command…", class: "muted", "data-testid": "remove-loading", role: "img" }, GLYPH.rescan)];
  }
  if (fetched.kind === "error") {
    return [html("p", { "aria-label": `Could not load the remove command: ${fetched.message}`, class: "warning-line", role: "alert" }, GLYPH.remove)];
  }
  const info = fetched.infos.get(id);
  if (info === undefined) {
    return [html("p", { "aria-label": "No remove command", class: "warning-line", role: "alert" }, GLYPH.empty)];
  }
  const button = commandButton(info.removeCommand);
  return info.removeVia === "" ? [button] : [button, html("p", { class: "muted", "data-testid": "remove-via" }, info.removeVia)];
}

export class DetailPanel extends StoreElement {
  #stopRemove: (() => void) | null = null;

  #render(item: Item): void {
    this.teardown();
    const close = html("button", { "aria-label": "Close details (Esc)", class: "btn", type: "button" }, icon("✕"));
    close.addEventListener("click", closeItem);
    const heading = html("h3", { "aria-label": "Remove", id: "remove-heading" }, icon("🗑"));
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
