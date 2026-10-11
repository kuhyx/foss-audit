import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { CHROME, makeAlternative, makeItem, STEAM_GAME, UNRAR } from "../test/fixtures.ts";
import { EasyWins, orderWins } from "./easy-wins.tsx";

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
    expect(orderWins([good, none, dropIn, alsoDropIn]).map((item) => item.name)).toEqual([
      "b",
      "z",
      "a",
      "m",
    ]);
  });
});

describe("EasyWins", () => {
  it("shows an explained empty state", () => {
    render(<EasyWins items={[]} onSelect={vi.fn()} selected={null} />);
    expect(screen.getByText("No easy wins right now.")).toBeInTheDocument();
  });

  it("renders one card per win with installed alternative, warnings and copy", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<EasyWins items={[UNRAR, STEAM_GAME, CHROME]} onSelect={onSelect} selected="pacman:unrar" />);
    const cards = screen.getAllByRole("listitem");
    expect(cards).toHaveLength(3);
    expect(cards[0]).toHaveTextContent("ungoogled-chromium-bin");
    expect(cards[0]).toHaveTextContent("fit: Drop-in");
    expect(within(cards[1]!).getByText(/not tracked for steam/u)).toBeInTheDocument();
    expect(within(cards[2]!).getByText(/by file-roller: removing it/u)).toBeInTheDocument();
    expect(cards[2]).toHaveAttribute("aria-current", "true");
    expect(screen.getAllByRole("button", { name: "Copy" })).toHaveLength(3);
    await user.click(screen.getByRole("button", { name: "google-chrome" }));
    expect(onSelect).toHaveBeenCalledWith("aur:google-chrome");
  });

  it("omits the fit line for an item without an alternative", () => {
    render(<EasyWins items={[makeItem({ name: "odd" })]} onSelect={vi.fn()} selected={null} />);
    expect(screen.queryByText(/fit:/u)).toBeNull();
  });
});
