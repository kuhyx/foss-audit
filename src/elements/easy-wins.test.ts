import { screen, within } from "@testing-library/dom";
import userEvent from "@testing-library/user-event";

import { selectWins } from "../client/selectors.ts";
import { store } from "../client/store.ts";
import { mount, resetDocument, showScan } from "../test/elements.ts";
import { CHROME, ITEMS, makeAlternative, makeItem, makeScan, STEAM_GAME, UNRAR } from "../test/fixtures.ts";
import { stubRemove } from "../test/remove-stub.ts";
import { orderWins } from "./easy-wins.ts";

const WINS = makeScan({ items: [UNRAR, STEAM_GAME, CHROME, makeItem()] });

function cards(): HTMLElement[] {
  return [...document.querySelectorAll<HTMLElement>(".wins .win")];
}

beforeEach(() => {
  resetDocument();
});

describe("orderWins", () => {
  it("puts known-clean removals first, then untracked, then still-needed", () => {
    expect(orderWins([UNRAR, STEAM_GAME, CHROME]).map((item) => item.name)).toEqual([
      "google-chrome",
      "Some Game",
      "unrar",
    ]);
  });

  it("breaks ties by fit, then name", () => {
    const good = makeItem({ alternative: makeAlternative({ fit: "good" }), name: "a" });
    const dropIn = makeItem({ alternative: makeAlternative({ fit: "drop-in" }), name: "z" });
    const none = makeItem({ name: "m" });
    const alsoDropIn = makeItem({ alternative: makeAlternative(), name: "b" });
    expect(orderWins([good, none, dropIn, alsoDropIn]).map((item) => item.name)).toEqual(["b", "z", "a", "m"]);
  });
});

describe("easy-wins", () => {
  it("shows an explained empty state", () => {
    showScan("wins", makeScan({ items: [makeItem()] }));
    mount("easy-wins");
    expect(screen.getByLabelText("No easy wins right now. An easy win is a non-free or partly-free item whose drop-in or good FOSS alternative is already installed.")).toBeInTheDocument();
    expect(document.querySelector(".table-empty")).not.toBeNull();
  });

  it("renders nothing outside the wins view", () => {
    showScan("table", WINS);
    const element = mount("easy-wins");
    expect(element).toBeEmptyDOMElement();
    showScan("wins", WINS);
    expect(cards()).toHaveLength(3);
    showScan("summary", WINS);
    expect(element).toBeEmptyDOMElement();
  });

  it("has one card per easy win: the same count as the tab badge", () => {
    stubRemove(ITEMS);
    showScan("wins");
    mount("easy-wins");
    expect(cards()).toHaveLength(selectWins(store.getState()).length);
    expect(cards().length).toBeGreaterThan(0);
  });

  it("renders installed alternative, warnings, selection and copy per card", async () => {
    const user = userEvent.setup();
    const mock = stubRemove([UNRAR, STEAM_GAME, CHROME]);
    showScan("wins", WINS, UNRAR.id);
    mount("easy-wins");
    const [first, second, third] = cards();
    expect(first).toHaveTextContent("ungoogled-chromium-bin");
    expect(within(first!).getByRole("img", { name: "Fit: Drop-in" })).toBeInTheDocument();
    expect(within(second!).getByRole("img", { name: /not tracked for steam/u })).toBeInTheDocument();
    expect(within(third!).getByRole("img", { name: /removing it is not a one-command job/u })).toBeInTheDocument();
    expect(third).toHaveTextContent("file-roller");
    expect(third).toHaveAttribute("aria-current", "true");
    expect(first).not.toHaveAttribute("aria-current");
    expect(screen.getAllByRole("img", { name: "Loading the remove command…" })).toHaveLength(3);
    expect(await screen.findAllByRole("button", { name: "Copy remove command" })).toHaveLength(3);
    expect(within(first!).getByText("sudo pacman -Rns google-chrome")).toBeInTheDocument();
    expect(mock).toHaveBeenCalledOnce();
    await user.click(screen.getByRole("button", { name: "google-chrome" }));
    expect(store.getState().url.selected).toBe(CHROME.id);
    const query = new URLSearchParams(globalThis.location.search);
    expect(query.get("sel")).toBe(CHROME.id);
  });

  it("moves the highlight in place when the selection changes, without refetching", async () => {
    const mock = stubRemove([UNRAR, STEAM_GAME, CHROME]);
    showScan("wins", WINS, UNRAR.id);
    mount("easy-wins");
    await screen.findAllByRole("button", { name: "Copy remove command" });
    const before = cards()[0];
    store.set({ url: { ...store.getState().url, selected: CHROME.id } });
    expect(cards()[0]).toBe(before);
    expect(before).toHaveAttribute("aria-current", "true");
    expect(cards()[2]).not.toHaveAttribute("aria-current");
    expect(mock).toHaveBeenCalledOnce();
  });

  it("says the commands are unavailable when they cannot be loaded", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockRejectedValue(new Error("down")));
    showScan("wins", makeScan({ items: [CHROME] }));
    mount("easy-wins");
    expect(await screen.findByRole('alert')).toHaveAttribute('aria-label', 'Remove command unavailable: down');
  });

  it("shows no command for a win the backend no longer knows", async () => {
    stubRemove([]);
    showScan("wins", makeScan({ items: [CHROME] }));
    mount("easy-wins");
    expect(await screen.findByRole('alert')).toHaveAttribute('aria-label', 'No remove command');
  });

  it("stops listening for remove commands once it leaves the view", async () => {
    let answer: (value: Response) => void = () => {};
    vi.stubGlobal("fetch", vi.fn<typeof fetch>(() => new Promise<Response>((resolve) => (answer = resolve))));
    showScan("wins", makeScan({ items: [CHROME] }));
    const element = mount("easy-wins");
    showScan("table", makeScan({ items: [CHROME] }));
    answer({ json: () => Promise.resolve({}), ok: true, status: 200 } as Response);
    await Promise.resolve();
    expect(element).toBeEmptyDOMElement();
  });
});
