import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { CHROME, DEAD_LAUNCHER, makeAlternative, MYSTERY, OWN_SCRIPT, STEAM_GAME, UNRAR } from "../test/fixtures.ts";
import { DetailPanel } from "./detail-panel.tsx";

describe("DetailPanel", () => {
  it("shows every field, the alternative and the copyable remove command", () => {
    render(<DetailPanel item={CHROME} onClose={vi.fn()} />);
    expect(screen.getByRole("heading", { name: "google-chrome" })).toBeInTheDocument();
    expect(screen.getByText("Non-free")).toBeInTheDocument();
    expect(screen.getAllByText("custom:chrome")).toHaveLength(2);
    expect(screen.getByRole("link", { name: "https://www.google.com/chrome" })).toHaveAttribute("target", "_blank");
    expect(screen.getByText("aur:google-chrome")).toBeInTheDocument();
    expect(screen.getByText("Nothing depends on it.")).toBeInTheDocument();
    expect(screen.getByText("Chromium")).toBeInTheDocument();
    expect(screen.getByText("Already installed")).toBeInTheDocument();
    expect(screen.getByText("ungoogled-chromium-bin")).toBeInTheDocument();
    expect(screen.getByText("Drop-in")).toBeInTheDocument();
    expect(screen.getByText("XL · infeasible")).toBeInTheDocument();
    expect(screen.getByText("Google Sync")).toBeInTheDocument();
    expect(screen.getByText("sudo pacman -Rns google-chrome")).toBeInTheDocument();
  });

  it("copies a Claude prompt for a non-FOSS item", async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
    render(<DetailPanel item={CHROME} onClose={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Copy Claude prompt" }));
    expect(writeText).toHaveBeenCalledWith(expect.stringMatching(/^Replace google-chrome with a FOSS alternative\n/u));
  });

  it("offers no Claude prompt for FOSS items", () => {
    render(<DetailPanel item={OWN_SCRIPT} onClose={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Copy Claude prompt" })).toBeNull();
  });

  it("warns when other packages still need it", () => {
    render(<DetailPanel item={UNRAR} onClose={vi.fn()} />);
    expect(screen.getByText(/by 1 package:/u)).toBeInTheDocument();
    expect(screen.getByText("file-roller")).toBeInTheDocument();
    expect(screen.getByText(/dependency/u)).toBeInTheDocument();
  });

  it("pluralises the dependant count", () => {
    render(<DetailPanel item={{ ...UNRAR, requiredBy: ["a", "b"] }} onClose={vi.fn()} />);
    expect(screen.getByText(/by 2 packages:/u)).toBeInTheDocument();
  });

  it("lists the projects that use a cached package", () => {
    render(<DetailPanel item={{ ...UNRAR, requiredBy: ["~/src/todo"], source: "pub-cache" }} onClose={vi.fn()} />);
    expect(screen.getByRole("heading", { name: "Used by" })).toBeInTheDocument();
    expect(screen.getByText(/by 1 project:/u)).toBeInTheDocument();
  });

  it("says a cached package no project names may be transitive", () => {
    render(<DetailPanel item={{ ...UNRAR, requiredBy: [], source: "maven-cache" }} onClose={vi.fn()} />);
    expect(screen.getByText(/No ~\/src lockfile or build file names it/u)).toBeInTheDocument();
  });

  it("says dependants are untracked outside pacman/AUR", () => {
    render(<DetailPanel item={STEAM_GAME} onClose={vi.fn()} />);
    expect(screen.getByText(/Not tracked: .* not steam\./u)).toBeInTheDocument();
  });

  it("handles absent values: no alternative, url, version, licence or command", () => {
    render(<DetailPanel item={{ ...OWN_SCRIPT, license: "", orphan: true, version: null }} onClose={vi.fn()} />);
    expect(screen.queryByRole("heading", { name: "FOSS alternative" })).toBeNull();
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(3);
    expect(screen.getByText(/yes — nothing requires it/u)).toBeInTheDocument();
    expect(screen.getByText("No remove command")).toBeInTheDocument();
  });

  it("flags own code", () => {
    render(<DetailPanel item={OWN_SCRIPT} onClose={vi.fn()} />);
    expect(screen.getByText("yes — kuhy's own")).toBeInTheDocument();
  });

  it("flags untracked files", () => {
    render(<DetailPanel item={MYSTERY} onClose={vi.fn()} />);
    expect(screen.getByText(/yes — in ~\/\.local\/bin/u)).toBeInTheDocument();
  });

  it("flags dead launchers", () => {
    render(<DetailPanel item={DEAD_LAUNCHER} onClose={vi.fn()} />);
    expect(screen.getByText(/yes — the \.desktop file's Exec target no longer exists/u)).toBeInTheDocument();
  });

  it("explains an alternative with no names and nothing installed", () => {
    const item = { ...CHROME, alternative: makeAlternative({ names: [] }) };
    render(<DetailPanel item={item} onClose={vi.fn()} />);
    expect(screen.getByText("No named alternative in the curated list.")).toBeInTheDocument();
    expect(screen.queryByText("Already installed")).toBeNull();
  });

  it("closes", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<DetailPanel item={CHROME} onClose={onClose} />);
    await user.click(screen.getByRole("button", { name: "Close details (Esc)" }));
    expect(onClose).toHaveBeenCalledOnce();
  });
});
