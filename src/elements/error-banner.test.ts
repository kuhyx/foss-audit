import { screen } from "@testing-library/dom";
import userEvent from "@testing-library/user-event";

import "./error-banner.ts";
import { store } from "../client/store.ts";
import { mount, resetDocument, showScan } from "../test/elements.ts";
import { makeScan } from "../test/fixtures.ts";
import { spoken } from "../test/table-setup.ts";

beforeEach(() => {
  resetDocument();
});

describe("error-banner", () => {
  it("renders nothing without messages", () => {
    showScan("table");
    expect(mount("error-banner")).toBeEmptyDOMElement();
  });

  it("lists scanner errors and a failed rescan, then dismisses", async () => {
    const user = userEvent.setup();
    showScan("table", makeScan({ errors: [{ message: "not installed", source: "flatpak" }] }));
    const element = mount("error-banner");
    const banner = screen.getByRole("alert");
    expect(banner).toHaveClass("banner");
    expect(banner).toHaveTextContent("flatpak: not installed");
    const { scan } = store.getState();
    if (scan.kind !== "ready") throw new Error("not ready");
    store.set({ scan: { ...scan, refreshError: "HTTP 500 from /api/scan" } });
    expect(screen.getAllByRole("listitem").map((li) => spoken(li))).toEqual([
      "Error: flatpak: not installed",
      "Rescan failed: HTTP 500 from /api/scan",
    ]);
    expect(screen.getAllByRole("listitem")[1]?.textContent).toBe("⟳ ⚠ HTTP 500 from /api/scan");
    await user.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(element).toBeEmptyDOMElement();
  });
});
