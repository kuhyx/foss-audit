import { actionFor, APP_KEYS, isTypingTarget, startKeyboard } from "./keyboard.ts";
import { resetStore, store } from "./store.ts";

function event(key: string, target: EventTarget | null = document.body, modifiers = {}) {
  return { altKey: false, ctrlKey: false, key, metaKey: false, target, ...modifiers };
}

describe("actionFor", () => {
  it("maps / ? and Escape", () => {
    expect(actionFor(event("/"))).toBe("onFocusSearch");
    expect(actionFor(event("?"))).toBe("onToggleHelp");
    expect(actionFor(event("Escape"))).toBe("onEscape");
    expect(actionFor(event("a"))).toBeNull();
  });

  it("ignores chords", () => {
    expect(actionFor(event("/", document.body, { ctrlKey: true }))).toBeNull();
    expect(actionFor(event("/", document.body, { metaKey: true }))).toBeNull();
    expect(actionFor(event("/", document.body, { altKey: true }))).toBeNull();
  });

  it("lets / and ? be typed into fields but still honours Escape", () => {
    const input = document.createElement("input");
    expect(actionFor(event("/", input))).toBeNull();
    expect(actionFor(event("?", input))).toBeNull();
    expect(actionFor(event("Escape", input))).toBe("onEscape");
  });
});

describe("isTypingTarget", () => {
  it("recognises inputs, selects, textareas and contenteditable", () => {
    for (const tag of ["input", "select", "textarea"]) {
      expect(isTypingTarget(document.createElement(tag))).toBe(true);
    }
    const div = document.createElement("div");
    expect(isTypingTarget(div)).toBe(false);
    Object.defineProperty(div, "isContentEditable", { value: true });
    expect(isTypingTarget(div)).toBe(true);
    expect(isTypingTarget(null)).toBe(false);
  });
});

describe("startKeyboard", () => {
  it("dispatches the mapped action, prevents the default and stops when told", () => {
    const keys = { onEscape: vi.fn(), onFocusSearch: vi.fn(), onToggleHelp: vi.fn() };
    const stop = startKeyboard(keys);
    const slash = new KeyboardEvent("keydown", { cancelable: true, key: "/" });
    globalThis.dispatchEvent(slash);
    expect(keys.onFocusSearch).toHaveBeenCalledOnce();
    expect(slash.defaultPrevented).toBe(true);

    const other = new KeyboardEvent("keydown", { cancelable: true, key: "x" });
    globalThis.dispatchEvent(other);
    expect(other.defaultPrevented).toBe(false);

    stop();
    globalThis.dispatchEvent(new KeyboardEvent("keydown", { key: "?" }));
    expect(keys.onToggleHelp).not.toHaveBeenCalled();
  });
});

describe("APP_KEYS", () => {
  beforeEach(() => {
    resetStore();
    const input = document.createElement("input");
    input.setAttribute("aria-label", "Search name or id");
    document.body.replaceChildren(input);
  });

  it("closes the help sheet first, then the panel, then leaves the search box", () => {
    const input = document.querySelector("input");
    store.set({ helpOpen: true, url: { ...store.getState().url, selected: "pacman:bash" } });
    APP_KEYS.onEscape();
    expect(store.getState().helpOpen).toBe(false);
    expect(store.getState().url.selected).toBe("pacman:bash");
    APP_KEYS.onEscape();
    expect(store.getState().url.selected).toBeNull();
    input?.focus();
    expect(document.activeElement).toBe(input);
    APP_KEYS.onEscape();
    expect(document.activeElement).not.toBe(input);
  });

  it("focuses the search box and toggles help", () => {
    APP_KEYS.onFocusSearch();
    expect(document.activeElement).toBe(document.querySelector("input"));
    APP_KEYS.onToggleHelp();
    expect(store.getState().helpOpen).toBe(true);
  });
});
