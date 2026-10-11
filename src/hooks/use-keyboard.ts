/**
 * Global keyboard shortcuts: `/` search, `?` help, `Esc` close.
 *
 * Kept as a pure mapping plus a thin effect, as in awesome-mcp-explorer, so the
 * key table is testable without mounting anything.
 */
import { useEffect } from "react";

export interface KeyboardActions {
  readonly onEscape: () => void;
  readonly onFocusSearch: () => void;
  readonly onToggleHelp: () => void;
}

/**
 * True when the event target is a field that should swallow the keystroke.
 */
export function isTypingTarget(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable ||
      ["INPUT", "SELECT", "TEXTAREA"].includes(target.tagName))
  );
}

/**
 * Maps a keydown to an action, or null if it should pass through.
 *
 * Escape works while typing (it is how you leave the field); `/` and `?` are
 * suppressed inside inputs so they can be typed into the search box.
 */
export function actionFor(
  event: Pick<KeyboardEvent, "altKey" | "ctrlKey" | "key" | "metaKey" | "target">,
): keyof KeyboardActions | null {
  if (event.ctrlKey || event.metaKey || event.altKey) return null;
  if (event.key === "Escape") return "onEscape";
  if (isTypingTarget(event.target)) return null;
  if (event.key === "/") return "onFocusSearch";
  return event.key === "?" ? "onToggleHelp" : null;
}

export function useKeyboard(actions: KeyboardActions): void {
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent): void {
      const action = actionFor(event);
      if (action === null) return;
      event.preventDefault();
      actions[action]();
    }

    globalThis.addEventListener("keydown", onKeyDown);
    return (): void => {
      globalThis.removeEventListener("keydown", onKeyDown);
    };
  }, [actions]);
}
