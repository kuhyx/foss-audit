import { renderHook } from "@testing-library/react";

import { actionFor, isTypingTarget, useKeyboard } from "./use-keyboard.ts";

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

describe("useKeyboard", () => {
  it("dispatches the mapped action and prevents the default", () => {
    const actions = { onEscape: vi.fn(), onFocusSearch: vi.fn(), onToggleHelp: vi.fn() };
    const { unmount } = renderHook(() => {
      useKeyboard(actions);
    });
    const slash = new KeyboardEvent("keydown", { cancelable: true, key: "/" });
    globalThis.dispatchEvent(slash);
    expect(actions.onFocusSearch).toHaveBeenCalledOnce();
    expect(slash.defaultPrevented).toBe(true);

    const other = new KeyboardEvent("keydown", { cancelable: true, key: "x" });
    globalThis.dispatchEvent(other);
    expect(other.defaultPrevented).toBe(false);

    unmount();
    globalThis.dispatchEvent(new KeyboardEvent("keydown", { key: "?" }));
    expect(actions.onToggleHelp).not.toHaveBeenCalled();
  });
});
