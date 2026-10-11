/**
 * Copies a shell command to the clipboard. The UI never runs commands itself:
 * removing a package is the user's decision, made in their own terminal.
 */
import { useState } from "react";

export interface CopyButtonProps {
  readonly command: null | string;
  readonly label?: string;
}

type CopyStatus = "copied" | "failed" | "idle";

const STATUS_TEXT: Readonly<Record<CopyStatus, string>> = {
  copied: "Copied",
  failed: "Copy failed",
  idle: "",
};

export function CopyButton({
  command,
  label = "Copy remove command",
}: CopyButtonProps): React.JSX.Element {
  const [status, setStatus] = useState<CopyStatus>("idle");

  async function copy(text: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(text);
      setStatus("copied");
    } catch {
      // Clipboard access needs a secure context (localhost counts) and focus;
      // say so rather than pretending the copy happened.
      setStatus("failed");
    }
  }

  if (command === null) {
    return <span className="muted">No remove command</span>;
  }

  return (
    <span className="copy">
      <code className="command">{command}</code>
      <button
        className="btn"
        onClick={(event): void => {
          event.stopPropagation();
          void copy(command);
        }}
        title={label}
        type="button"
      >
        Copy
      </button>
      <span aria-live="polite" className="copy-status">
        {STATUS_TEXT[status]}
      </span>
    </span>
  );
}
