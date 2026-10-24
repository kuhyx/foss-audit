import { act, fireEvent, render, renderHook, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { Item } from "../lib/schema.ts";
import type { SortState } from "../lib/url-state.ts";

import { useSelection } from "../hooks/use-selection.ts";
import { ITEMS, makeItem } from "../test/fixtures.ts";
import { ItemsTable } from "./items-table.tsx";

interface HarnessProps {
  readonly items: readonly Item[];
  readonly onSelect?: (id: string) => void;
  readonly onSelection?: (ids: ReadonlySet<string>) => void;
  readonly selected?: null | string;
  readonly sort?: null | SortState;
}

// The table is controlled; this owns the selection the way App does, so a
// rerender with different `items` is a filter change that keeps the selection.
function Harness({ items, onSelect = vi.fn(), onSelection = vi.fn(), selected = null, sort = null }: HarnessProps) {
  const selection = useSelection();
  onSelection(selection.ids);
  return (
    <ItemsTable
      checked={selection.ids}
      items={items}
      onCheck={selection.click}
      onCheckAll={selection.set}
      onSelect={onSelect}
      onSort={vi.fn()}
      selected={selected}
      sort={sort}
    />
  );
}

function setup(props: Partial<HarnessProps> = {}) {
  let ids: ReadonlySet<string> = new Set();
  const onSelect = vi.fn<(id: string) => void>();
  const onSelection = (next: ReadonlySet<string>): void => {
    ids = next;
  };
  const all = { items: ITEMS, onSelect, onSelection, ...props };
  const view = render(<Harness {...all} />);
  return {
    checked: (): string[] => [...ids].toSorted((a, b) => a.localeCompare(b)),
    onSelect,
    rerender: (next: Partial<HarnessProps>): void => {
      view.rerender(<Harness {...all} {...next} />);
    },
    user: userEvent.setup(),
  };
}

function box(name: string): HTMLElement {
  return screen.getByRole("checkbox", { name: `Select ${name}` });
}

const HEADER = "Select all shown";
const LETTERS = ["d", "a", "e", "c", "b"].map((name) => makeItem({ name }));

describe("ItemsTable selection", () => {
  it("toggles a row from its checkbox without opening the detail panel", async () => {
    const { checked, onSelect, user } = setup();
    await user.click(box("unrar"));
    expect(checked()).toEqual(["pacman:unrar"]);
    expect(box("unrar")).toBeChecked();
    expect(onSelect).not.toHaveBeenCalled();
    await user.click(box("unrar"));
    expect(checked()).toEqual([]);
  });

  it("still opens the detail panel when the row itself is clicked", async () => {
    const { checked, onSelect, user } = setup();
    await user.click(screen.getByText("unrar"));
    expect(onSelect).toHaveBeenCalledWith("pacman:unrar");
    expect(checked()).toEqual([]);
  });

  it("shift-selects the range in the current sorted order", async () => {
    const { checked, user } = setup({ items: LETTERS, sort: { desc: false, id: "name" } });
    await user.click(box("b"));
    await user.keyboard("{Shift>}");
    await user.click(box("d"));
    await user.keyboard("{/Shift}");
    expect(checked()).toEqual(["pacman:b", "pacman:c", "pacman:d"]);
  });

  it("shift-selects the range in the current filtered order", async () => {
    const { checked, rerender, user } = setup({ items: LETTERS });
    rerender({ items: LETTERS.filter((item) => item.name !== "e") });
    await user.click(box("d"));
    await user.keyboard("{Shift>}");
    await user.click(box("c"));
    await user.keyboard("{/Shift}");
    expect(checked()).toEqual(["pacman:a", "pacman:c", "pacman:d"]);
  });

  it("selects every shown row from the header, indeterminate when partial", async () => {
    const { checked, user } = setup({ items: LETTERS });
    expect(screen.getByRole("checkbox", { name: HEADER })).not.toBeChecked();
    await user.click(box("a"));
    expect(screen.getByRole("checkbox", { name: HEADER })).toBePartiallyChecked();
    await user.click(screen.getByRole("checkbox", { name: HEADER }));
    expect(checked()).toHaveLength(5);
    expect(screen.getByRole("checkbox", { name: HEADER })).toBeChecked();
    await user.click(screen.getByRole("checkbox", { name: HEADER }));
    expect(checked()).toEqual([]);
  });

  it("keeps the selection across a filter change and adds to it", async () => {
    const google = [makeItem({ name: "com.google.a" }), makeItem({ name: "com.google.b" })];
    const firebase = [makeItem({ name: "firebase-x" })];
    const { checked, rerender, user } = setup({ items: google });
    await user.click(screen.getByRole("checkbox", { name: HEADER }));
    rerender({ items: firebase });
    expect(screen.getByRole("checkbox", { name: HEADER })).not.toBeChecked();
    await user.click(screen.getByRole("checkbox", { name: HEADER }));
    expect(checked()).toEqual(["pacman:com.google.a", "pacman:com.google.b", "pacman:firebase-x"]);
    // Deselecting all shown rows leaves the hidden ones selected.
    await user.click(screen.getByRole("checkbox", { name: HEADER }));
    expect(checked()).toEqual(["pacman:com.google.a", "pacman:com.google.b"]);
  });

  it("toggles the open row with Space on the scroller only", () => {
    const { checked } = setup({ selected: "pacman:unrar" });
    const scroller = screen.getByRole("table");
    fireEvent.keyDown(scroller, { key: " " });
    expect(checked()).toEqual(["pacman:unrar"]);
    // Space on a focused checkbox or sort button is theirs, not a second toggle.
    fireEvent.keyDown(box("bash"), { key: " " });
    fireEvent.keyDown(screen.getByRole("button", { name: "Name" }), { key: " " });
    expect(checked()).toEqual(["pacman:unrar"]);
    fireEvent.keyDown(scroller, { key: " " });
    expect(checked()).toEqual([]);
  });

  it("hands focus back to the scroller after a checkbox click, and skips row checkboxes on Tab", async () => {
    const { checked, user } = setup({ selected: "pacman:unrar" });
    await user.click(box("bash"));
    expect(screen.getByRole("table")).toHaveFocus();
    expect(box("bash")).toHaveAttribute("tabindex", "-1");
    fireEvent.keyDown(screen.getByRole("table"), { key: " " });
    expect(checked()).toEqual(["pacman:bash", "pacman:unrar"]);
  });

  it("ignores Space when no row is open", () => {
    const { checked } = setup();
    const isEvent = fireEvent.keyDown(screen.getByRole("table"), { key: " " });
    expect(isEvent).toBe(true);
    expect(checked()).toEqual([]);
  });
});

describe("useSelection", () => {
  it("clears the ids and the anchor", () => {
    const { result } = renderHook(() => useSelection());
    act(() => {
      result.current.click("b", ["a", "b", "c"], false);
    });
    act(() => {
      result.current.clear();
    });
    expect([...result.current.ids]).toEqual([]);
    act(() => {
      result.current.click("c", ["a", "b", "c"], true);
    });
    expect([...result.current.ids]).toEqual(["c"]);
  });
});
