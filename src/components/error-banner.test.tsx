import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ErrorBanner } from "./error-banner.tsx";

describe("ErrorBanner", () => {
  it("renders nothing without messages", () => {
    const { container } = render(<ErrorBanner messages={[]} onDismiss={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("lists messages and dismisses", async () => {
    const user = userEvent.setup();
    const onDismiss = vi.fn();
    render(<ErrorBanner messages={["flatpak: not installed"]} onDismiss={onDismiss} />);
    expect(screen.getByRole("alert")).toHaveTextContent("flatpak: not installed");
    await user.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(onDismiss).toHaveBeenCalledOnce();
  });
});
