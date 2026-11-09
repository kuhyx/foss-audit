import type { CopyButton } from "../elements/copy-button.ts";

import "../elements/copy-button.ts";

// A <copy-button> showing `command`; with none it reads "No remove command".
export function commandButton(command: null | string | undefined): CopyButton {
  const button = document.createElement("copy-button") as CopyButton;
  if (command !== undefined && command !== null) button.setAttribute("command", command);
  return button;
}

// A <copy-button> whose text is built on click; `build` is set before it connects.
export function buildButton(build: () => Promise<string>, buttonText: string, label: string): CopyButton {
  const button = document.createElement("copy-button") as CopyButton;
  button.build = build;
  button.setAttribute("button-text", buttonText);
  button.setAttribute("label", label);
  return button;
}
