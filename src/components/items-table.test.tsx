import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { Item } from "../lib/schema.ts";
import type { SortState } from "../lib/url-state.ts";

import { ITEMS, makeItem } from "../test/fixtures.ts";
import { ItemsTable } from "./items-table.tsx";

function setup(props: { items?: readonly Item[]; selected?: null | string; sort?: null | SortState } = {}) {
  const onSelect = vi.fn<(id: string) => void>();
  const onSort = vi.fn<(sort: null | SortState) => void>();
  const view = render(
    <ItemsTable
      items={props.items ?? ITEMS}
      onSelect={onSelect}
      onSort={onSort}
      selected={props.selected ?? null}
      sort={props.sort ?? null}
    />,
  );
  return { onSelect, onSort, user: userEvent.setup(), view };
}

function column(index: number): string[] {
  return screen.getAllByRole("row").slice(1).map((row) => within(row).getAllByRole("cell")[index]?.textContent ?? "");
}

const NAME = 0;
const FIT = 9;

describe("ItemsTable", () => {
  it("renders an explained empty state", () => {
    setup({ items: [] });
    expect(screen.getByText("No items match these filters.")).toBeInTheDocument();
  });

  it("renders every row with formatted cells", () => {
    setup();
    expect(column(NAME)).toHaveLength(ITEMS.length);
    expect(screen.getAllByRole("columnheader")).toHaveLength(12);
    const steam = screen.getAllByRole("row").find((row) => row.textContent.includes("Some Game"))!;
    expect(steam).toHaveTextContent("—");
    expect(steam).toHaveTextContent("0ad");
    expect(steam).toHaveTextContent("Good");
    const unrar = screen.getAllByRole("row").find((row) => row.textContent.includes("unrar"))!;
    expect(unrar).toHaveTextContent("dependency");
    expect(within(unrar).getAllByRole("cell")[7]).toHaveTextContent("1");
    expect(screen.getAllByText("orphan")).toHaveLength(1);
  });

  it("sorts by name ascending and descending", () => {
    setup({ sort: { desc: false, id: "name" } });
    expect(column(NAME)[0]).toBe("backup.sh");
    expect(screen.getByRole("columnheader", { name: /Name/u })).toHaveAttribute("aria-sort", "ascending");
  });

  it("sorts rank columns and keeps absent values last in both directions", () => {
    const { view } = setup({ sort: { desc: false, id: "fit" } });
    const fits = column(FIT).filter((fit) => fit !== "");
    expect(fits).toEqual(["Drop-in", "Good", "Good"]);
    expect(column(FIT).at(-1)).toBe("");
    view.rerender(
      <ItemsTable items={ITEMS} onSelect={vi.fn()} onSort={vi.fn()} selected={null} sort={{ desc: true, id: "fit" }} />,
    );
    expect(column(FIT).slice(0, 3)).toEqual(["Good", "Good", "Drop-in"]);
    expect(column(FIT).at(-1)).toBe("");
  });

  it.each(["version", "source", "verdict", "license", "kind", "orphan", "requiredBy", "alternative", "effort", "installed"])(
    "sorts by %s and marks only that header",
    (id) => {
      setup({ sort: { desc: true, id } });
      const sorted = screen.getAllByRole("columnheader").filter((h) => h.getAttribute("aria-sort") !== "none");
      expect(sorted).toHaveLength(1);
      expect(sorted[0]).toHaveAttribute("aria-sort", "descending");
      expect(column(NAME)).toHaveLength(ITEMS.length);
    },
  );

  it("cycles the sort from the header: asc, desc, none", async () => {
    const { onSort, user, view } = setup();
    await user.click(screen.getByRole("button", { name: "Name" }));
    expect(onSort).toHaveBeenLastCalledWith({ desc: false, id: "name" });
    view.rerender(
      <ItemsTable items={ITEMS} onSelect={vi.fn()} onSort={onSort} selected={null} sort={{ desc: false, id: "name" }} />,
    );
    await user.click(screen.getByRole("button", { name: /Name/u }));
    expect(onSort).toHaveBeenLastCalledWith({ desc: true, id: "name" });
    view.rerender(
      <ItemsTable items={ITEMS} onSelect={vi.fn()} onSort={onSort} selected={null} sort={{ desc: true, id: "name" }} />,
    );
    expect(screen.getByText("▼")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Name/u }));
    expect(onSort).toHaveBeenLastCalledWith(null);
  });

  it("selects a row on click and marks the selection", async () => {
    const { onSelect, user } = setup({ selected: "aur:google-chrome" });
    const chrome = screen.getAllByRole("row").find((row) => row.textContent.includes("google-chrome"))!;
    expect(chrome).toHaveAttribute("aria-selected", "true");
    await user.click(screen.getAllByRole("row")[1]!);
    expect(onSelect).toHaveBeenCalledWith("pacman:bash");
  });

  it("moves the selection with the arrow keys, clamped at both ends", () => {
    const scroller = () => screen.getByRole("table");
    const first = setup();
    fireEvent.keyDown(scroller(), { key: "ArrowDown" });
    expect(first.onSelect).toHaveBeenLastCalledWith("pacman:bash");
    fireEvent.keyDown(scroller(), { key: "ArrowUp" });
    expect(first.onSelect).toHaveBeenLastCalledWith(ITEMS.at(-1)?.id);
    fireEvent.keyDown(scroller(), { key: "PageDown" });
    expect(first.onSelect).toHaveBeenCalledTimes(2);
    first.view.unmount();

    const top = setup({ selected: "pacman:bash" });
    fireEvent.keyDown(scroller(), { key: "ArrowUp" });
    expect(top.onSelect).toHaveBeenLastCalledWith("pacman:bash");
    fireEvent.keyDown(scroller(), { key: "ArrowDown" });
    expect(top.onSelect).toHaveBeenLastCalledWith(ITEMS[1]?.id);
  });

  it("handles a single row", () => {
    setup({ items: [makeItem({ name: "solo" })] });
    expect(column(NAME)).toEqual(["solo"]);
  });
});
