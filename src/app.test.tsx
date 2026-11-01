import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { App } from "./app.tsx";
import { makeProgress, makeScan } from "./test/fixtures.ts";
import { respond as fakeResponse, route } from "./test/route.ts";

const fetchMock = vi.fn<typeof fetch>();

function respond(body: unknown, status = 200): Response {
  return Response.json(body, { status });
}

async function renderApp(url = "/", scan = makeScan()) {
  globalThis.history.replaceState(null, "", url);
  fetchMock.mockResolvedValueOnce(respond(scan));
  const user = userEvent.setup();
  render(<App />);
  await screen.findByRole("heading", { name: "FOSS audit" });
  return user;
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("shows a loading message, then the summary", async () => {
    globalThis.history.replaceState(null, "", "/");
    fetchMock.mockResolvedValueOnce(respond(makeScan()));
    render(<App />);
    expect(screen.getByText("Scanning installed programs…")).toBeInTheDocument();
    expect(await screen.findByText("44.4% free")).toBeInTheDocument();
  });

  it("shows live progress while the first scan runs, then the summary", async () => {
    globalThis.history.replaceState(null, "", "/");
    const progress = [
      makeProgress({ itemsFound: 120, running: [{ done: 40, source: "npm-cache", total: 100 }], sourcesDone: 14 }),
      makeProgress({ generatedAt: "2026-10-11T14:02:11Z", scanning: false, sourcesDone: 26 }),
    ];
    route(fetchMock, {
      "/api/scan": [fakeResponse({ scanning: true }, 202), fakeResponse(makeScan())],
      "/api/scan/progress": progress.map((body) => fakeResponse(body)),
    });
    render(<App />);
    expect(await screen.findByText("14/26")).toBeInTheDocument();
    expect(screen.getByText("npm-cache 40/100")).toBeInTheDocument();
    expect(screen.getByText("120 items")).toBeInTheDocument();
    expect(await screen.findByText("44.4% free")).toBeInTheDocument();
  });

  it("shows a compact progress in the header while a rescan runs", async () => {
    const user = await renderApp();
    const scanning = makeScan({ scanning: true });
    const progress = makeProgress({
      generatedAt: scanning.generatedAt,
      running: [{ done: 3400, source: "npm-cache", total: 12_000 }],
      sourcesDone: 14,
    });
    route(fetchMock, {
      "/api/scan": [fakeResponse(scanning)],
      "/api/scan/progress": [fakeResponse(progress)],
      "/api/scan?refresh=1": [fakeResponse(scanning)],
    });
    await user.click(screen.getByRole("button", { name: "Rescan" }));
    expect(await screen.findByLabelText("Rescan progress")).toHaveTextContent("14/26 · npm-cache 3400/12000");
    expect(screen.getByLabelText("Scan age")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Rescanning…" })).toBeDisabled();
    expect(screen.getByText("44.4% free")).toBeInTheDocument();
  });

  it("explains a failed first load", async () => {
    globalThis.history.replaceState(null, "", "/");
    fetchMock.mockResolvedValueOnce(respond({}, 502));
    render(<App />);
    expect(await screen.findByText(/Could not load the scan: HTTP 502/u)).toBeInTheDocument();
  });

  it("drills from a tile into the filtered table, and Back returns", async () => {
    const user = await renderApp();
    await user.click(screen.getByRole("button", { name: /^Non-free/u }));
    expect(globalThis.location.search).toBe("?view=table&v=nonfree");
    expect(screen.getByText(/of 9 items/u).parentElement).toHaveTextContent("5 of 9 items");
    expect(screen.getByRole("button", { name: /All items/u })).toHaveTextContent("5");
  });

  it("switches views from the nav and shows the easy wins", async () => {
    const user = await renderApp();
    await user.click(screen.getByRole("button", { name: /Easy wins/u }));
    expect(screen.getByText(/3 non-free or partly-free items/u)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "unrar" }));
    expect(screen.getByRole("heading", { name: "unrar" })).toBeInTheDocument();
  });

  it("typing a search jumps to the table and filters it", async () => {
    const user = await renderApp();
    await user.type(screen.getByRole("searchbox"), "unrar");
    await waitFor(() => {
      expect(globalThis.location.search).toBe("?view=table&q=unrar");
    });
    expect(await screen.findByText(/of 9 items/u)).toBeInTheDocument();
  });

  it("filters, sorts and selects through the URL", async () => {
    const user = await renderApp("/?view=table");
    await user.click(screen.getByRole("button", { name: /^opt/u }));
    expect(globalThis.location.search).toBe("?view=table&src=opt");
    await user.click(screen.getByRole("button", { name: "Name" }));
    expect(globalThis.location.search).toContain("sort=name");
    await user.click(screen.getByText("mystery"));
    expect(screen.getByRole("heading", { name: "mystery" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Close details (Esc)" }));
    expect(screen.queryByRole("heading", { name: "mystery" })).toBeNull();
  });

  it("keeps a multi-selection across filters and shows the selection bar", async () => {
    const user = await renderApp("/?view=table");
    expect(screen.queryByRole("region", { name: "Selection" })).toBeNull();
    await user.click(screen.getByRole("checkbox", { name: "Select unrar" }));
    await user.click(screen.getByRole("button", { name: /^opt/u }));
    await user.click(screen.getByRole("checkbox", { name: "Select mystery" }));
    expect(screen.getByRole("region", { name: "Selection" })).toHaveTextContent("2 selected");
    expect(screen.queryByRole("heading", { name: "mystery" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Clear" }));
    expect(screen.queryByRole("region", { name: "Selection" })).toBeNull();
  });

  it("does not show the detail panel on the summary", async () => {
    await renderApp("/?sel=pacman%3Aunrar");
    expect(screen.queryByRole("heading", { name: "unrar" })).toBeNull();
  });

  it("shows scanner errors in a dismissible banner", async () => {
    const user = await renderApp("/", makeScan({ errors: [{ message: "flatpak not installed", source: "flatpak" }] }));
    expect(screen.getByRole("alert")).toHaveTextContent("flatpak: flatpak not installed");
    await user.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("rescans, and reports a failed rescan without losing the data", async () => {
    const user = await renderApp();
    fetchMock.mockResolvedValueOnce(respond(makeScan({ host: "rescanned" })));
    await user.click(screen.getByRole("button", { name: "Rescan" }));
    expect(await screen.findByText("rescanned")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenLastCalledWith("/api/scan?refresh=1");

    fetchMock.mockRejectedValueOnce(new Error("backend down"));
    await user.click(screen.getByRole("button", { name: "Rescan" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Rescan failed: backend down");
    expect(screen.getByText("rescanned")).toBeInTheDocument();
  });

  it("handles / ? and Esc in priority order", async () => {
    await renderApp("/?view=table&sel=pacman%3Aunrar");
    const search = screen.getByRole("searchbox");

    fireEvent.keyDown(globalThis.window, { key: "/" });
    expect(search).toHaveFocus();
    search.blur();

    fireEvent.keyDown(globalThis.window, { key: "?" });
    expect(screen.getByRole("dialog", { name: "Keyboard shortcuts" })).toBeInTheDocument();

    fireEvent.keyDown(globalThis.window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("heading", { name: "unrar" })).toBeInTheDocument();

    fireEvent.keyDown(globalThis.window, { key: "Escape" });
    expect(screen.queryByRole("heading", { name: "unrar" })).toBeNull();

    act(() => {
      search.focus();
    });
    fireEvent.keyDown(search, { key: "Escape" });
    expect(search).not.toHaveFocus();
  });

  it("closes help from its own button and toggles with ?", async () => {
    const user = await renderApp();
    fireEvent.keyDown(globalThis.window, { key: "?" });
    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.keyDown(globalThis.window, { key: "?" });
    fireEvent.keyDown(globalThis.window, { key: "?" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
