import { screen } from "@testing-library/dom";
import userEvent from "@testing-library/user-event";

import "./help-overlay.ts";
import { store } from "../client/store.ts";
import { mount, resetDocument, showScan, stubDialog } from "../test/elements.ts";
import { paintedWords } from "../test/table-setup.ts";

function scrim(): HTMLDialogElement | null {
  return document.querySelector("dialog.scrim");
}

beforeEach(() => {
  resetDocument();
  stubDialog();
  showScan("table");
});

describe("help-overlay", () => {
  it("renders nothing until help is opened", () => {
    expect(mount("help-overlay")).toBeEmptyDOMElement();
  });

  it("opens a modal <dialog> with every shortcut and focuses Close", () => {
    mount("help-overlay");
    store.set({ helpOpen: true });
    expect(scrim()).toHaveAttribute("open");
    expect(document.querySelector(".scrim > .help")).not.toBeNull();
    expect(screen.getByRole("dialog", { name: "Keyboard shortcuts" })).toBe(scrim());
    expect(screen.getByRole("img", { name: "focus search" })).toHaveTextContent("⌕");
    expect(screen.getByLabelText("PgUp PgDn")).toHaveTextContent("⇞ ⇟");
    expect(paintedWords(scrim()!)).toEqual([]);
    expect(screen.getAllByRole("term")).toHaveLength(6);
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Close" }));
  });

  it("stays shut while the scan is not on screen", () => {
    store.set({ helpOpen: true, scan: { kind: "error", message: "HTTP 502 from /api/scan" } });
    expect(mount("help-overlay")).toBeEmptyDOMElement();
  });

  it("closes from the button and the scrim, not from inside the sheet", async () => {
    const user = userEvent.setup();
    const element = mount("help-overlay");
    store.set({ helpOpen: true });
    await user.click(document.querySelector(".help")!);
    expect(store.getState().helpOpen).toBe(true);
    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(store.getState().helpOpen).toBe(false);
    expect(element).toBeEmptyDOMElement();
    store.set({ helpOpen: true });
    await user.click(scrim()!);
    expect(store.getState().helpOpen).toBe(false);
  });

  it("turns the dialog's own cancel (Esc) into closeHelp", () => {
    const element = mount("help-overlay");
    store.set({ helpOpen: true });
    const cancel = new Event("cancel", { cancelable: true });
    scrim()?.dispatchEvent(cancel);
    expect(cancel.defaultPrevented).toBe(true);
    expect(store.getState().helpOpen).toBe(false);
    expect(element).toBeEmptyDOMElement();
  });

  it("closes the dialog when the element leaves the page", () => {
    const element = mount("help-overlay");
    store.set({ helpOpen: true });
    const dialog = scrim()!;
    element.remove();
    expect(dialog).not.toHaveAttribute("open");
  });
});
