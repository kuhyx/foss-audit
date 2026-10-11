import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { CopyButton } from "./copy-button.tsx";

describe("CopyButton", () => {
  it("copies the command to the clipboard and says so", async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
    render(<CopyButton command="sudo pacman -Rns google-chrome" />);
    expect(screen.getByText("sudo pacman -Rns google-chrome")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Copy" }));
    expect(writeText).toHaveBeenCalledWith("sudo pacman -Rns google-chrome");
    expect(await screen.findByText("Copied")).toBeInTheDocument();
  });

  it("reports a clipboard failure instead of pretending", async () => {
    const user = userEvent.setup();
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("denied"));
    render(<CopyButton command="rm x" label="Copy it" />);
    await user.click(screen.getByRole("button", { name: "Copy" }));
    expect(await screen.findByText("Copy failed")).toBeInTheDocument();
  });

  it("does not bubble the click to a selectable parent", async () => {
    const user = userEvent.setup();
    vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
    const onParent = vi.fn();
    render(
      <div onClick={onParent} role="presentation">
        <CopyButton command="x" />
      </div>,
    );
    await user.click(screen.getByRole("button", { name: "Copy" }));
    expect(onParent).not.toHaveBeenCalled();
  });

  it("shows a note when there is no remove command", () => {
    render(<CopyButton command={null} />);
    expect(screen.getByText("No remove command")).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });
});
