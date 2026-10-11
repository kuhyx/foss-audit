import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { HelpOverlay } from "./help-overlay.tsx";

describe("HelpOverlay", () => {
  it("closes from the button and the scrim, not from inside the dialog", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<HelpOverlay onClose={onClose} />);
    const dialog = screen.getByRole("dialog", { name: "Keyboard shortcuts" });
    await user.click(dialog);
    expect(onClose).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Close" }));
    await user.click(dialog.parentElement!);
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});
