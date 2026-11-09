import { closeHelp, closeItem, toggleHelp } from "./actions.ts";
import { searchInput } from "./shell.ts";
import { store } from "./store.ts";

export interface KeyboardActions {
  readonly onEscape: () => void;
  readonly onFocusSearch: () => void;
  readonly onToggleHelp: () => void;
}

export function isTypingTarget(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement && (target.isContentEditable || ["INPUT", "SELECT", "TEXTAREA"].includes(target.tagName))
  );
}

// Escape works while typing (it is how you leave the field); `/` and `?` stay typeable in inputs.
export function actionFor(
  event: Pick<KeyboardEvent, "altKey" | "ctrlKey" | "key" | "metaKey" | "target">,
): keyof KeyboardActions | null {
  if (event.ctrlKey || event.metaKey || event.altKey) return null;
  if (event.key === "Escape") return "onEscape";
  if (isTypingTarget(event.target)) return null;
  if (event.key === "/") return "onFocusSearch";
  return event.key === "?" ? "onToggleHelp" : null;
}

// Esc order: the help sheet, then the detail panel, then leave the search box.
export const APP_KEYS: KeyboardActions = {
  onEscape(): void {
    const { helpOpen, url } = store.getState();
    if (helpOpen) closeHelp();
    else if (url.selected === null) searchInput().blur();
    else closeItem();
  },
  onFocusSearch(): void {
    searchInput().focus();
  },
  onToggleHelp: toggleHelp,
};

// The only Esc owner; returns stop().
export function startKeyboard(keys: KeyboardActions = APP_KEYS): () => void {
  function onKeyDown(event: KeyboardEvent): void {
    const action = actionFor(event);
    if (action === null) return;
    event.preventDefault();
    keys[action]();
  }

  globalThis.addEventListener("keydown", onKeyDown);
  return (): void => {
    globalThis.removeEventListener("keydown", onKeyDown);
  };
}
