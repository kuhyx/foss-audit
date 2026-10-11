/**
 * Scanner errors (`errors[]`) and a failed rescan, as one dismissible banner.
 *
 * A failing scanner does not fail the scan: the other sources still report,
 * so this is a warning above the data, not a replacement for it.
 */
export interface ErrorBannerProps {
  readonly messages: readonly string[];
  readonly onDismiss: () => void;
}

export function ErrorBanner({
  messages,
  onDismiss,
}: ErrorBannerProps): null | React.JSX.Element {
  if (messages.length === 0) return null;
  return (
    <div className="banner" role="alert">
      <ul>
        {messages.map((message) => {
          return (
            <li key={message}>{message}</li>
          );
        })}
      </ul>
      <button className="btn" onClick={onDismiss} type="button">
        Dismiss
      </button>
    </div>
  );
}
