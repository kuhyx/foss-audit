import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { buildRemoveScript } from "../lib/remove-script.ts";
import { buildSelectionPrompt } from "../lib/selection-prompt.ts";
import { CHROME, makeItem } from "../test/fixtures.ts";
import { postedIds, stubRemove } from "../test/remove-stub.ts";
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

  it("fetches nothing on selection, then the selected ids when a copy button is used", async () => {
    const user = userEvent.setup();
    const mock = stubRemove([CHROME, BASH]);
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
    render(<SelectionBar items={[CHROME, BASH]} onClear={vi.fn()} />);
    expect(mock).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Copy Claude prompt (2)" }));
    await screen.findByText("Copied");
    expect(writeText).toHaveBeenLastCalledWith(buildSelectionPrompt([CHROME, BASH]));
    await user.click(screen.getByRole("button", { name: "Copy remove commands (2)" }));
    await waitFor(() => {
      expect(writeText).toHaveBeenCalledTimes(2);
    });
    expect(writeText).toHaveBeenLastCalledWith(buildRemoveScript([CHROME, BASH]));
    expect(postedIds(mock)).toEqual([[CHROME.id, BASH.id]]);
  });

  it("says so, and copies nothing, when the remove commands cannot be loaded", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockRejectedValue(new Error("down")));
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
    render(<SelectionBar items={[CHROME]} onClear={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Copy remove commands (1)" }));
    expect(await screen.findByText("Could not load the remove commands")).toBeInTheDocument();
    expect(writeText).not.toHaveBeenCalled();
  });
});
