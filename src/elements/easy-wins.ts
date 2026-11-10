import type { RemoveFetch } from "../client/remove.ts";
/**
 * Easy wins: non-free or partly-free items whose drop-in/good FOSS
 * alternative is already installed (rule in lib/verdict.ts), cleanest
 * removals first: no dependants, then untracked, then still-needed.
 */
import type { AppState } from "../client/store.ts";
import type { Item } from "../lib/schema.ts";

import { openItem } from "../client/actions.ts";
import { watchRemove } from "../client/remove.ts";
import { selectWins } from "../client/selectors.ts";
import { define, hasChanged, StoreElement } from "../client/store-element.ts";
import { FITS } from "../lib/schema.ts";
import { FIT_LABELS, hasTrackedDependants, numberFormat } from "../lib/verdict.ts";
import { commandButton } from "../render/command.ts";
import { html } from "../render/dom.ts";
import { verdictBadge } from "../render/verdict-badge.ts";

function fitRank(item: Item): number {
  return item.alternative === null ? FITS.length : FITS.indexOf(item.alternative.fit);
}

// 0: known to have no dependants; 1: dependants not tracked for this source; 2: still needed.
function dependantRank(item: Item): number {
  if (item.requiredBy.length > 0) return 2;
  return hasTrackedDependants(item) ? 0 : 1;
}

export function orderWins(items: readonly Item[]): Item[] {
  return items.toSorted(
    (a, b) => dependantRank(a) - dependantRank(b) || fitRank(a) - fitRank(b) || a.name.localeCompare(b.name),
  );
}

function removeCell(fetched: RemoveFetch, id: string): HTMLElement {
  if (fetched.kind === "loading") return html("span", { class: "muted" }, "Loading the remove command…");
  if (fetched.kind === "error") return html("span", { "aria-label": `Remove command unavailable: ${fetched.message}`, class: "muted", role: "alert" }, `Remove command unavailable: ${fetched.message}`);
  const info = fetched.infos.get(id);
  return info === undefined ? html("span", { "aria-label": "No remove command", class: "muted", role: "alert" }, "No remove command") : commandButton(info.removeCommand);
}

function card(item: Item): HTMLElement {
  const alt = item.alternative;
  const name = html("button", { class: "link win-name", type: "button" }, item.name);
  name.addEventListener("click", () => {
    openItem(item.id);
  });
  const head = html(
    "div",
    { class: "win-head" },
    name,
    html("span", { class: "muted" }, item.source),
    verdictBadge(item.verdict),
    alt === null ? null : html("span", { class: "muted" }, `fit: ${FIT_LABELS[alt.fit]}`),
  );
  const installed = html(
    "p",
    { class: "win-alt" },
    html("span", { "aria-label": "Already installed", class: "badge badge-success" }, "📦"),
    " ",
    alt?.installed.join(", "),
  );
  const untracked = hasTrackedDependants(item)
    ? null
    : html("p", { class: "muted caption" }, `Dependants are not tracked for ${item.source} items; check before removing.`);
  const needed =
    item.requiredBy.length === 0
      ? null
      : html("p", { class: "warning-line" }, `by ${item.requiredBy.join(", ")}: removing it is not a one-command job.`);
  return html("li", { class: "win card", "data-id": item.id }, head, installed, untracked, needed);
}

function emptyState(): HTMLElement {
  return html(
    "div",
    { class: "table-empty" },
    html(
      "span",
      {
        "aria-label": "No easy wins right now. An easy win is a non-free or partly-free item whose drop-in or good FOSS alternative is already installed.",
        class: "muted large-empty-icon",
      },
      "⚡",
    ),
  );
}

export class EasyWins extends StoreElement {
  #cells = new Map<string, HTMLElement>();
  #stopRemove: (() => void) | null = null;

  #highlight(selected: null | string): void {
    for (const element of this.querySelectorAll<HTMLElement>(".win")) {
      // toggleAttribute cannot carry the value "true".
      // eslint-disable-next-line unicorn/prefer-toggle-attribute
      if (selected !== null && element.dataset.id === selected) element.setAttribute("aria-current", "true");
      else element.removeAttribute("aria-current");
    }
  }

  #render(wins: readonly Item[], selected: null | string): void {
    this.teardown();
    if (wins.length === 0) {
      this.replaceChildren(emptyState());
      return;
    }
    const ordered = orderWins(wins);
    const cards = ordered.map((item) => card(item));
    const caption = html(
      "p",
      { class: "muted caption" },
      `${numberFormat.format(wins.length)} non-free or partly-free items with a drop-in or good FOSS alternative that is already installed. Nothing here is removed for you: copy the command and run it yourself.`,
    );
    this.replaceChildren(html("div", { class: "wins-scroll" }, caption, html("ul", { class: "wins" }, ...cards)));
    this.#highlight(selected);
    this.#stopRemove = watchRemove(
      ordered.map((item) => item.id),
      (fetched) => {
        this.#showRemove(cards, ordered, fetched);
      },
    );
  }

  #showRemove(cards: readonly HTMLElement[], ordered: readonly Item[], fetched: RemoveFetch): void {
    for (const [index, item] of ordered.entries()) {
      const next = removeCell(fetched, item.id);
      const previous = this.#cells.get(item.id);
      if (previous === undefined) cards[index]?.append(next);
      else previous.replaceWith(next);
      this.#cells.set(item.id, next);
    }
  }

  protected override teardown(): void {
    this.#stopRemove?.();
    this.#stopRemove = null;
    this.#cells.clear();
    super.teardown();
  }

  protected override update(state: AppState, previous: AppState | null): void {
    const isActive = (s: AppState): boolean => s.url.view === "wins" && s.scan.kind === "ready";
    if (hasChanged(state, previous, isActive, selectWins)) {
      if (isActive(state)) this.#render(selectWins(state), state.url.selected);
      else this.teardown();
    } else if (isActive(state) && hasChanged(state, previous, (s) => s.url.selected)) {
      this.#highlight(state.url.selected);
    }
  }
}

define("easy-wins", EasyWins);
