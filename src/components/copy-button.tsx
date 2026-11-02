/**
 * Copies a shell command to the clipboard. The UI never runs commands itself:
 * removing a package is the user's decision, made in their own terminal.
 * Long text (a Claude prompt) is copied without being printed inline.
 * `AsyncCopyButton` builds its text on click (it needs remove commands fetched then).
 */
import { useState } from "react";

export interface CopyButtonProps {
  readonly buttonText?: string;
  readonly command: null | string;
  readonly label?: string;
  readonly showText?: boolean;
}

export interface AsyncCopyButtonProps {
  readonly build: () => Promise<string>;
  readonly buttonText: string;
  readonly label: string;
}

type CopyStatus = "copied" | "failed" | "idle" | "unavailable" | "working";

const STATUS_TEXT: Readonly<Record<CopyStatus, string>> = {
  copied: "Copied",
  failed: "Copy failed",
  idle: "",
  unavailable: "Could not load the remove commands",
  working: "Preparing…",
};

function useCopy(): { readonly run: (build: () => Promise<string>) => Promise<void>; readonly status: CopyStatus } {
  const [status, setStatus] = useState<CopyStatus>("idle");

  async function run(build: () => Promise<string>): Promise<void> {
    setStatus("working");
    let text: string;
    try {
      text = await build();
    } catch {
      setStatus("unavailable");
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      setStatus("copied");
    } catch {
      // Clipboard access needs a secure context (localhost counts) and focus;
      // say so rather than pretending the copy happened.
      setStatus("failed");
    }
  }

  return { run, status };
}

function CopyControl({
  build,
  buttonText,
  children,
  label,
}: AsyncCopyButtonProps & { readonly children?: React.ReactNode }): React.JSX.Element {
  const { run, status } = useCopy();
  return (
    <span className="copy">
      {children}
      <button
        className="btn"
        onClick={(event): void => {
          event.stopPropagation();
          void run(build);
        }}
        title={label}
        type="button"
      >
        {buttonText}
      </button>
      <span aria-live="polite" className="copy-status">
        {STATUS_TEXT[status]}
      </span>
    </span>
  );
}

export function AsyncCopyButton(props: AsyncCopyButtonProps): React.JSX.Element {
  return <CopyControl {...props} />;
}

export function CopyButton({
  buttonText = "Copy",
  command,
  label = "Copy remove command",
  showText = true,
}: CopyButtonProps): React.JSX.Element {
  if (command === null) {
    return <span className="muted">No remove command</span>;
  }
  return (
    <CopyControl build={(): Promise<string> => Promise.resolve(command)} buttonText={buttonText} label={label}>
      {showText && <code className="command">{command}</code>}
    </CopyControl>
  );
}
