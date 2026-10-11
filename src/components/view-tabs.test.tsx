import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ViewTabs } from "./view-tabs.tsx";

describe("ViewTabs", () => {
  it("marks the current view and reports clicks", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<ViewTabs counts={{ summary: 9, table: 3, wins: 1234 }} onSelect={onSelect} view="table" />);
    expect(screen.getByRole("button", { name: /All items/u })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: /Easy wins/u })).toHaveTextContent("1,234");
    await user.click(screen.getByRole("button", { name: /Easy wins/u }));
    expect(onSelect).toHaveBeenCalledWith("wins");
  });
});
