import "./copy-button.ts";
import type { CopyButton } from "./copy-button.ts";

function mount(attributes: Record<string, string> = {}): CopyButton {
  const element = document.createElement("copy-button") as CopyButton;
  for (const [name, value] of Object.entries(attributes)) element.setAttribute(name, value);
  document.body.append(element);
  return element;
}

function click(element: CopyButton): void {
  element.querySelector("button")?.click();
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("copy-button", () => {
  it("copies the command to the clipboard and says so", async () => {
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
    const element = mount({ command: "sudo pacman -Rns google-chrome" });
    expect(element.querySelector(".command")?.textContent).toBe("sudo pacman -Rns google-chrome");
    click(element);
    await vi.waitFor(() => {
      expect(element.querySelector("button")?.nextElementSibling?.textContent).toBe("Copied");
    });
    expect(writeText).toHaveBeenCalledWith("sudo pacman -Rns google-chrome");
  });

  it("reports a clipboard failure instead of pretending", async () => {
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("denied"));
    const element = mount({ command: "rm x", label: "Copy it" });
    expect(element.querySelector("button")?.title).toBe("Copy it");
    click(element);
    await vi.waitFor(() => {
      expect(element.querySelector(".copy-status")?.textContent).toBe("Copy failed");
    });
  });

  it("does not bubble the click to a selectable parent", () => {
    vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
    const onParent = vi.fn();
    document.body.addEventListener("click", onParent);
    click(mount({ command: "x" }));
    document.body.removeEventListener("click", onParent);
    expect(onParent).not.toHaveBeenCalled();
  });

  it("builds long text on click behind a named button without printing it", async () => {
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
    const element = document.createElement("copy-button") as CopyButton;
    element.build = (): Promise<string> => Promise.resolve("a long prompt");
    element.setAttribute("button-text", "Copy Claude prompt");
    element.setAttribute("show-text", "false");
    document.body.append(element);
    expect(element.querySelector(".command")).toBeNull();
    expect(element.querySelector("button")?.textContent).toBe("Copy Claude prompt");
    click(element);
    await vi.waitFor(() => {
      expect(writeText).toHaveBeenCalledWith("a long prompt");
    });
  });

  it("says so when the build fails", async () => {
    const element = mount({});
    element.build = (): Promise<string> => Promise.reject(new Error("no"));
    document.body.replaceChildren(element);
    click(element);
    await vi.waitFor(() => {
      expect(element.querySelector(".copy-status")?.textContent).toBe("Could not load the remove commands");
    });
  });

  it("hides the command with show-text=false and shows a note when there is none", () => {
    expect(mount({ command: "x", "show-text": "false" }).querySelector(".command")).toBeNull();
    const none = mount();
    expect(none.textContent).toBe("No remove command");
    expect(none.querySelector("button")).toBeNull();
  });
});
