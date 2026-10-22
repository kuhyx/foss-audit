/**
 * The `?` shortcut sheet.
 */
import { SHORTCUTS } from "../lib/views.ts";

export interface HelpOverlayProps {
  readonly onClose: () => void;
}

export function HelpOverlay({ onClose }: HelpOverlayProps): React.JSX.Element {
  return (
    <div className="scrim" onClick={onClose} role="presentation">
      <div
        aria-label="Keyboard shortcuts"
        aria-modal="true"
        className="help"
        onClick={(event): void => {
          event.stopPropagation();
        }}
        role="dialog"
      >
        <h2>Keyboard shortcuts</h2>
        <dl>
          {SHORTCUTS.map(([key, what]) => {
            return (
              <div className="help-row" key={key}>
                <dt>
                  <kbd>{key}</kbd>
                </dt>
                <dd>{what}</dd>
              </div>
            );
          })}
        </dl>
        <p className="muted">
          Every filter, the sort and the open row live in the URL, so the
          address bar is always a shareable link.
        </p>
        <button autoFocus className="btn" onClick={onClose} type="button">
          Close
        </button>
      </div>
    </div>
  );
}
