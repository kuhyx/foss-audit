/**
Small shared pieces of the all-items table element: its mode, parts and event-target helpers.
*/
import type { ArrowKey } from "../lib/virtual.ts";

export type Mode = "empty" | "none" | "table";

export interface Table {
  readonly body: HTMLElement;
  readonly header: HTMLElement;
  readonly headerBox: HTMLInputElement;
  readonly observer: ResizeObserver;
  readonly scroller: HTMLElement;
}

export function rowOf(target: EventTarget | null): HTMLElement | null {
  return target instanceof Element ? target.closest<HTMLElement>(".tr.row") : null;
}

export function isArrow(key: string): key is ArrowKey {
  return key === "ArrowDown" || key === "ArrowUp";
}
