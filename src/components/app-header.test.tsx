import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { makeProgress, makeScan } from "../test/fixtures.ts";
import { AppHeader } from "./app-header.tsx";

describe("AppHeader", () => {
  function setup(overrides: Partial<Parameters<typeof AppHeader>[0]> = {}) {
    const props = {
      onQuery: vi.fn(),
      onRescan: vi.fn(),
      progress: null,
      query: "",
      refreshing: false,
      scan: makeScan(),
      searchRef: { current: null },
      ...overrides,
    };
    render(<AppHeader {...props} />);
    return props;
  }

  it("shows host, time and duration, and wires search + rescan", async () => {
    const user = userEvent.setup();
    const props = setup();
    expect(screen.getByText("testhost")).toBeInTheDocument();
    expect(screen.getByText(/1,234 ms/u)).toBeInTheDocument();
    expect(document.querySelector("time")).toHaveAttribute("dateTime", "2026-10-11T14:02:11Z");
    await user.type(screen.getByRole("searchbox"), "c");
    expect(props.onQuery).toHaveBeenCalledWith("c");
    await user.click(screen.getByRole("button", { name: "Rescan" }));
    expect(props.onRescan).toHaveBeenCalledOnce();
  });

  it("disables Rescan while refreshing", () => {
    setup({ refreshing: true });
    const button = screen.getByRole("button", { name: "Rescanning…" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
  });

  it("shows the scan progress only while refreshing", () => {
    const progress = makeProgress({ running: [{ done: 3400, source: "npm-cache", total: 12_000 }], sourcesDone: 14 });
    const { unmount } = render(
      <AppHeader
        onQuery={vi.fn()}
        onRescan={vi.fn()}
        progress={progress}
        query=""
        refreshing={false}
        scan={makeScan()}
        searchRef={{ current: null }}
      />,
    );
    expect(screen.queryByLabelText("Rescan progress")).toBeNull();
    unmount();
    setup({ progress, refreshing: true });
    expect(screen.getByLabelText("Rescan progress")).toHaveTextContent("14/26 · npm-cache 3400/12000");
  });

  it("shows an unparseable timestamp verbatim", async () => {
    setup({ scan: makeScan({ generatedAt: "yesterday" }) });
    await waitFor(() => {
      expect(screen.getByText("yesterday")).toBeInTheDocument();
    });
  });
});
