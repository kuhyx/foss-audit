import type { AppState } from "../client/store.ts";
import type { ScanProgress as Progress, RunningSource } from "../lib/schema.ts";

import { define, hasChanged, StoreElement } from "../client/store-element.ts";
import { formatAge } from "../lib/age.ts";
import { html } from "../render/dom.ts";
import { GLYPH } from "../render/glyph.ts";

function runningLabel({ done, source, total }: RunningSource): string {
  return total === null ? `${source} ${done}` : `${source} ${done}/${total}`;
}

// A source that has counted nothing yet reads "npm-cache 0": noise, so it waits.
function visibleRunning(progress: Progress): readonly RunningSource[] {
  return progress.running.filter(({ done, total }) => done > 0 || total !== null);
}

function bar(progress: Progress): HTMLElement {
  const { sourcesDone, sourcesTotal } = progress;
  const fill = html("span");
  fill.style.width = `${sourcesTotal > 0 ? Math.min(100, (sourcesDone / sourcesTotal) * 100) : 0}%`;
  return html(
    "div",
    {
      "aria-label": "Sources scanned",
      "aria-valuemax": sourcesTotal,
      "aria-valuemin": 0,
      "aria-valuenow": sourcesDone,
      class: "scan-bar",
      role: "progressbar",
    },
    fill,
  );
}

function loadingView(progress: Progress): HTMLElement {
  return html(
    "div",
    { class: "scan-live-loading" },
    bar(progress),
    html(
      "p",
      { class: "scan-nums" },
      html("span", {}, `${progress.sourcesDone}/${progress.sourcesTotal}`),
      html("span", { "aria-label": `${progress.itemsFound} items` }, `${GLYPH.total} ${progress.itemsFound}`),
    ),
    html("ul", { class: "scan-running" }, ...visibleRunning(progress).map((source) => html("li", {}, runningLabel(source)))),
  );
}

function headerView(progress: null | Progress, age: HTMLElement | null): HTMLElement {
  if (progress === null) return html("p", { class: "scan-live" }, age);
  const steps = [`${progress.sourcesDone}/${progress.sourcesTotal}`, ...visibleRunning(progress).map((source) => runningLabel(source))];
  const text = html("span", { "aria-label": "Rescan progress", class: "scan-live-text" }, steps.join(" · "));
  return html("p", { class: "scan-live" }, bar(progress), text, age);
}

// variant="loading": the first scan's progress; variant="header": a rescan's progress and the shown scan's age.
export class ScanProgress extends StoreElement {
  #clock: ReturnType<typeof setInterval> | undefined;

  #renderHeader(state: AppState, generatedAt: string): void {
    clearInterval(this.#clock);
    this.#clock = undefined;
    const text = formatAge(generatedAt, Date.now());
    const age = text === "" ? null : html("span", { "aria-label": "Scan age" }, text);
    this.replaceChildren(headerView(state.progress, age));
    if (age === null) return;
    this.#clock = setInterval(() => {
      age.textContent = formatAge(generatedAt, Date.now());
    }, 1000);
  }

  protected override teardown(): void {
    clearInterval(this.#clock);
    this.#clock = undefined;
    super.teardown();
  }

  protected override update(state: AppState, previous: AppState | null): void {
    if (!hasChanged(state, previous, (s) => s.scan, (s) => s.progress)) return;
    const { scan } = state;
    if (this.getAttribute("variant") === "header") {
      if (scan.kind === "ready" && scan.refreshing) this.#renderHeader(state, scan.scan.generatedAt);
      else this.teardown();
    } else if (scan.kind === "loading" && state.progress !== null) {
      this.replaceChildren(loadingView(state.progress));
    } else {
      this.teardown();
    }
  }
}

define("scan-progress", ScanProgress);
