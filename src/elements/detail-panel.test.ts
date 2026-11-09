import { screen } from "@testing-library/dom";
import userEvent from "@testing-library/user-event";

import type { Item } from "../lib/schema.ts";

import "./detail-panel.ts";
import { store } from "../client/store.ts";
import { mount, resetDocument, showScan } from "../test/elements.ts";
import { CHROME, DEAD_LAUNCHER, makeAlternative, makeScan, MYSTERY, OWN_SCRIPT, STEAM_GAME, UNRAR } from "../test/fixtures.ts";
import { postedIds, stubRemove } from "../test/remove-stub.ts";

const VIA = { ...CHROME, id: "aur:via", removeVia: "~/src/sufler via torch" };

// Mounts the panel in the table view with `item` open.
function open(item: Item, extra: readonly Item[] = []): HTMLElement {
  showScan("table", makeScan({ items: [item, ...extra] }), item.id);
  return mount("detail-panel");
}

function dialog(): HTMLDialogElement | null {
  return document.querySelector("dialog.panel");
}

beforeEach(() => {
  resetDocument();
  stubRemove([CHROME, UNRAR, STEAM_GAME, OWN_SCRIPT, MYSTERY, DEAD_LAUNCHER, VIA]);
});

describe("detail-panel", () => {
  it("is an open, non-modal <dialog> with every field, the alternative and the remove command", async () => {
    open(CHROME);
    expect(dialog()).toHaveAttribute("open");
    expect(screen.getByRole("heading", { name: "google-chrome" })).toBeInTheDocument();
    expect(screen.getByText("Non-free")).toBeInTheDocument();
    expect(screen.getAllByText("custom:chrome")).toHaveLength(2);
    expect(screen.getByRole("link", { name: "https://www.google.com/chrome" })).toHaveAttribute("target", "_blank");
    expect(screen.getByText("aur:google-chrome")).toBeInTheDocument();
    expect(screen.getByText("Nothing depends on it.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "FOSS alternative" })).toBeInTheDocument();
    expect(screen.getByText("Chromium")).toBeInTheDocument();
    expect(screen.getByText("Already installed")).toBeInTheDocument();
    expect(screen.getByText("ungoogled-chromium-bin")).toBeInTheDocument();
    expect(screen.getByText("Drop-in")).toBeInTheDocument();
    expect(screen.getByText("XL · infeasible")).toBeInTheDocument();
    expect(screen.getByText("Google Sync")).toBeInTheDocument();
    expect(await screen.findByText("sudo pacman -Rns google-chrome")).toBeInTheDocument();
    expect(document.querySelector(".panel copy-button")).not.toBeNull();
  });

  it("does not take focus when it opens", () => {
    const row = document.createElement("button");
    document.body.append(row);
    row.focus();
    open(CHROME);
    expect(document.activeElement).toBe(row);
  });

  it("renders nothing without a selection, on the summary view, or for an unknown id", () => {
    showScan("table", makeScan({ items: [CHROME] }));
    const element = mount("detail-panel");
    expect(element).toBeEmptyDOMElement();
    showScan("summary", makeScan({ items: [CHROME] }), CHROME.id);
    expect(element).toBeEmptyDOMElement();
    showScan("table", makeScan({ items: [CHROME] }), "aur:gone");
    expect(element).toBeEmptyDOMElement();
    showScan("wins", makeScan({ items: [CHROME] }), CHROME.id);
    expect(dialog()).not.toBeNull();
  });

  it("closes when the selection is cleared", () => {
    const element = open(CHROME);
    store.set({ url: { ...store.getState().url, selected: null } });
    expect(element).toBeEmptyDOMElement();
  });

  it("fetches the remove command of its one item only, with a placeholder meanwhile", async () => {
    const mock = stubRemove([CHROME]);
    open(CHROME);
    expect(screen.getByTestId("remove-loading")).toBeInTheDocument();
    await screen.findByText("sudo pacman -Rns google-chrome");
    expect(screen.queryByTestId("remove-loading")).toBeNull();
    expect(postedIds(mock)).toEqual([[CHROME.id]]);
  });

  it("keeps the same dialog and does not refetch on an unrelated update", async () => {
    const mock = stubRemove([CHROME]);
    open(CHROME);
    await screen.findByText("sudo pacman -Rns google-chrome");
    const before = dialog();
    store.set({ helpOpen: true });
    expect(dialog()).toBe(before);
    expect(mock).toHaveBeenCalledOnce();
  });

  it("shows an error line when the remove command cannot be loaded", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockRejectedValue(new Error("backend down")));
    open(CHROME);
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load the remove command: backend down");
    expect(screen.queryByRole("button", { name: "Copy" })).toBeNull();
  });

  it("says there is no command when the backend no longer knows the item", async () => {
    stubRemove([]);
    open(CHROME);
    expect(await screen.findByText("No remove command")).toBeInTheDocument();
  });

  it("fetches again for the next item and shows loading, not the old command", async () => {
    open(CHROME, [UNRAR]);
    await screen.findByText("sudo pacman -Rns google-chrome");
    store.set({ url: { ...store.getState().url, selected: UNRAR.id } });
    expect(screen.queryByText("sudo pacman -Rns google-chrome")).toBeNull();
    expect(await screen.findByText("sudo pacman -Rns unrar")).toBeInTheDocument();
  });

  it("copies a Claude prompt for a non-FOSS item", async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
    open(CHROME);
    await user.click(screen.getByRole("button", { name: "Copy Claude prompt" }));
    await screen.findByText("Copied");
    const prompt = String(writeText.mock.calls[0]?.[0]);
    expect(prompt).toMatch(/^Replace google-chrome with a FOSS alternative\n/u);
    expect(prompt).toContain("`sudo pacman -Rns google-chrome` (do not run it)");
  });

  it("offers no Claude prompt for FOSS items", () => {
    open(OWN_SCRIPT);
    expect(screen.queryByRole("button", { name: "Copy Claude prompt" })).toBeNull();
  });

  it("warns when other packages still need it", () => {
    open(UNRAR);
    expect(screen.getByText(/by 1 package:/u)).toBeInTheDocument();
    expect(screen.getByText("file-roller")).toBeInTheDocument();
    expect(screen.getByText(/dependency/u)).toBeInTheDocument();
  });

  it("pluralises the dependant count", () => {
    open({ ...UNRAR, requiredBy: ["a", "b"] });
    expect(screen.getByText(/by 2 packages:/u)).toBeInTheDocument();
  });

  it("lists the projects that use a cached package", () => {
    open({ ...UNRAR, id: "pub-cache:unrar", requiredBy: ["~/src/todo"], source: "pub-cache" });
    expect(screen.getByRole("heading", { name: "Used by" })).toBeInTheDocument();
    expect(screen.getByText(/by 1 project:/u)).toBeInTheDocument();
  });

  it("says a cached package no project names may be transitive", () => {
    open({ ...UNRAR, id: "maven-cache:unrar", requiredBy: [], source: "maven-cache" });
    expect(screen.getByText(/No ~\/src lockfile or build file names it/u)).toBeInTheDocument();
  });

  it("says dependants are untracked outside pacman/AUR", () => {
    open(STEAM_GAME);
    expect(screen.getByText(/Not tracked: .* not steam\./u)).toBeInTheDocument();
  });

  it("handles absent values: no alternative, url, version, licence or command", async () => {
    open({ ...OWN_SCRIPT, license: "", orphan: true, version: null });
    expect(screen.queryByRole("heading", { name: "FOSS alternative" })).toBeNull();
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(3);
    expect(screen.getByText(/yes — nothing requires it/u)).toBeInTheDocument();
    expect(await screen.findByText("No remove command")).toBeInTheDocument();
  });

  it("explains the remove command's shape under it when removeVia is set", async () => {
    open(VIA, [CHROME]);
    expect(await screen.findByTestId("remove-via")).toHaveTextContent("~/src/sufler via torch");
    store.set({ url: { ...store.getState().url, selected: CHROME.id } });
    await screen.findByText("sudo pacman -Rns google-chrome");
    expect(screen.queryByTestId("remove-via")).toBeNull();
  });

  it("flags own code, untracked files and dead launchers", () => {
    open(OWN_SCRIPT, [MYSTERY, DEAD_LAUNCHER]);
    expect(screen.getByText("yes — kuhy's own")).toBeInTheDocument();
    store.set({ url: { ...store.getState().url, selected: MYSTERY.id } });
    expect(screen.getByText(/yes — in ~\/\.local\/bin/u)).toBeInTheDocument();
    store.set({ url: { ...store.getState().url, selected: DEAD_LAUNCHER.id } });
    expect(screen.getByText(/yes — the \.desktop file's Exec target no longer exists/u)).toBeInTheDocument();
  });

  it("explains an alternative with no names and nothing installed", () => {
    open({ ...CHROME, alternative: makeAlternative({ names: [] }) });
    expect(screen.getByText("No named alternative in the curated list.")).toBeInTheDocument();
    expect(screen.queryByText("Already installed")).toBeNull();
  });

  it("closes from its button: clears sel in the store and the URL", async () => {
    const user = userEvent.setup();
    const element = open(CHROME);
    await user.click(screen.getByRole("button", { name: "Close details (Esc)" }));
    expect(store.getState().url.selected).toBeNull();
    expect(globalThis.location.search).not.toContain("sel=");
    expect(element).toBeEmptyDOMElement();
  });

  it("turns the dialog's own cancel (Esc) into the close action", () => {
    open(CHROME);
    const cancel = new Event("cancel", { cancelable: true });
    dialog()?.dispatchEvent(cancel);
    expect(cancel.defaultPrevented).toBe(true);
    expect(store.getState().url.selected).toBeNull();
  });
});
