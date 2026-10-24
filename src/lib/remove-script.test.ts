import { CHROME, makeItem, OWN_SCRIPT, STEAM_GAME, UNRAR } from "../test/fixtures.ts";
import { buildRemoveScript } from "./remove-script.ts";

function body(script: string): string[] {
  return script.split("\n").filter((line) => line !== "" && !line.startsWith("#!") && !line.startsWith("# foss-audit") && !line.startsWith("# Review"));
}

describe("buildRemoveScript", () => {
  it("is a bash script without set -e, so one failure does not stop the rest", () => {
    const script = buildRemoveScript([CHROME]);
    expect(script.split("\n", 1)[0]).toBe("#!/bin/bash");
    expect(script).toContain("# foss-audit: remove commands for 1 selected item");
    expect(script).not.toMatch(/set -e/u);
    expect(script.endsWith("\n")).toBe(true);
  });

  it("merges commands of one manager into one invocation where the first one stood", () => {
    const flatpak = makeItem({ name: "a", removeCommand: "flatpak uninstall org.a.App", source: "flatpak" });
    const flatpak2 = makeItem({ name: "b", removeCommand: "flatpak uninstall org.b.App", source: "flatpak" });
    expect(body(buildRemoveScript([CHROME, STEAM_GAME, flatpak, UNRAR, flatpak2]))).toEqual([
      "sudo pacman -Rns google-chrome unrar",
      "steam steam://uninstall/1",
      "flatpak uninstall org.a.App org.b.App",
    ]);
  });

  it("merges every multi-argument manager and dedupes repeated names", () => {
    const commands = [
      "cargo uninstall ripgrep",
      "cargo uninstall fd-find",
      "npm uninstall -g @scope/cli",
      "npm uninstall -g left-pad",
      "sudo npm uninstall -g yarn",
      "sudo npm uninstall -g pnpm",
      "sudo pacman -Rns unrar",
      "sudo pacman -Rns unrar",
    ];
    const items = commands.map((command, index) => makeItem({ name: `n${String(index)}`, removeCommand: command }));
    expect(body(buildRemoveScript(items))).toEqual([
      "cargo uninstall ripgrep fd-find",
      "npm uninstall -g @scope/cli left-pad",
      "sudo npm uninstall -g yarn pnpm",
      "sudo pacman -Rns unrar",
    ]);
  });

  it("keeps single-argument and compound commands one per line", () => {
    const commands = [
      "pipx uninstall black",
      "pipx uninstall ruff",
      "rm '/home/kuhy/.local/share/applications/a.desktop'",
      "rm '/home/kuhy/.local/share/applications/b.desktop'",
      "docker rm -f 1a2b && docker rmi img:1",
      "sudo pacman -Rns two words",
    ];
    const items = commands.map((command, index) => makeItem({ name: `n${String(index)}`, removeCommand: command }));
    expect(body(buildRemoveScript(items))).toEqual(commands);
  });

  it("comments items without a remove command instead of dropping them", () => {
    expect(body(buildRemoveScript([OWN_SCRIPT, CHROME]))).toEqual([
      "# no remove command: local-bin:backup.sh",
      "sudo pacman -Rns google-chrome",
    ]);
  });

  it("puts removeVia as a comment above its command, merged or not", () => {
    const via = { ...UNRAR, removeVia: "~/src/sufler via torch" };
    const steam = { ...STEAM_GAME, removeVia: "Steam client" };
    expect(body(buildRemoveScript([CHROME, steam, via]))).toEqual([
      "# pacman:unrar: ~/src/sufler via torch",
      "sudo pacman -Rns google-chrome unrar",
      "# steam:Some Game: Steam client",
      "steam steam://uninstall/1",
    ]);
  });

  it("pluralises the header", () => {
    expect(buildRemoveScript([CHROME, UNRAR])).toContain("for 2 selected items");
  });
});
