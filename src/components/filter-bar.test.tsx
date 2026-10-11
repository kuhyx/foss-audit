import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { FilterState } from "../lib/filter.ts";

import { DEFAULT_FILTER } from "../lib/filter.ts";
import { ITEMS } from "../test/fixtures.ts";
import { FilterBar } from "./filter-bar.tsx";

function setup(filter: FilterState = DEFAULT_FILTER) {
  const onChange = vi.fn<(next: FilterState) => void>();
  render(<FilterBar filter={filter} items={ITEMS} onChange={onChange} shown={3} />);
  return { onChange, user: userEvent.setup() };
}

describe("FilterBar", () => {
  it("shows whole-scan counts on chips, only present sources, and the result count", () => {
    setup();
    const verdicts = screen.getByRole("group", { name: "Verdict" });
    expect(within(verdicts).getByRole("button", { name: /Non-free/u })).toHaveTextContent("3");
    const sources = screen.getByRole("group", { name: "Source" });
    expect(within(sources).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "pacman5",
      "aur1",
      "opt1",
      "local-bin1",
      "steam1",
    ]);
    expect(screen.getByText(/of 9 items/u).parentElement).toHaveTextContent("3 of 9 items");
    expect(screen.getByRole("button", { name: "Reset filters" })).toBeDisabled();
  });

  it("shows 0 for a verdict the scan does not contain", () => {
    const onChange = vi.fn();
    render(<FilterBar filter={DEFAULT_FILTER} items={ITEMS.slice(0, 2)} onChange={onChange} shown={2} />);
    expect(screen.getByRole("button", { name: /^Own code/u })).toHaveTextContent("0");
  });

  it("toggles verdict and source chips on and off", async () => {
    const { onChange, user } = setup({ ...DEFAULT_FILTER, sources: ["aur"], verdicts: ["nonfree"] });
    const nonfree = screen.getByRole("button", { name: /Non-free/u });
    expect(nonfree).toHaveAttribute("aria-pressed", "true");
    await user.click(nonfree);
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ verdicts: [] }));
    await user.click(screen.getByRole("button", { name: /^blob/iu }));
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ verdicts: ["nonfree", "blob"] }));
    await user.click(screen.getByRole("button", { name: /^steam/u }));
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ sources: ["aur", "steam"] }));
  });

  it("sets each segmented facet", async () => {
    const { onChange, user } = setup();
    const pick = async (group: string, option: string) => {
      await user.click(within(screen.getByRole("group", { name: group })).getByRole("button", { name: option }));
    };
    await pick("Installed as", "Dependency");
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ kind: "dependency" }));
    await pick("Orphan", "Yes");
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ orphan: "yes" }));
    await pick("Has alternative", "No");
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ hasAlt: "no" }));
    await pick("Alternative installed", "Yes");
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ altInstalled: "yes" }));
  });

  it("resets to the default filter", async () => {
    const { onChange, user } = setup({ ...DEFAULT_FILTER, orphan: "yes" });
    expect(within(screen.getByRole("group", { name: "Orphan" })).getByRole("button", { name: "Yes" }))
      .toHaveAttribute("aria-pressed", "true");
    await user.click(screen.getByRole("button", { name: "Reset filters" }));
    expect(onChange).toHaveBeenCalledWith(DEFAULT_FILTER);
  });
});
