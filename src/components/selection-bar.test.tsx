import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { buildRemoveScript } from "../lib/remove-script.ts";
import { buildSelectionPrompt } from "../lib/selection-prompt.ts";
import { CHROME, makeItem } from "../test/fixtures.ts";
import { SelectionBar } from "./selection-bar.tsx";

const BASH = makeItem();

describe("SelectionBar", () => {
  it("is hidden with nothing selected", () => {
    const { container } = render(<SelectionBar items={[]} onClear={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("counts the selection and clears it", async () => {
    const user = userEvent.setup();
    const onClear = vi.fn();
    render(<SelectionBar items={[CHROME, BASH]} onClear={onClear} />);
    expect(screen.getByRole("region", { name: "Selection" })).toHaveTextContent("2 selected");
    await user.click(screen.getByRole("button", { name: "Clear" }));
    expect(onClear).toHaveBeenCalledOnce();
  });

  it("copies one Claude prompt and one remove script for every selected item", async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
    render(<SelectionBar items={[CHROME, BASH]} onClear={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Copy Claude prompt (2)" }));
    expect(writeText).toHaveBeenLastCalledWith(buildSelectionPrompt([CHROME, BASH]));
    await user.click(screen.getByRole("button", { name: "Copy remove commands (2)" }));
    expect(writeText).toHaveBeenLastCalledWith(buildRemoveScript([CHROME, BASH]));
  });
});
