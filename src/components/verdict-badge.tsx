/**
 * A verdict as a colour dot plus its label.
 *
 * The text never wears the categorical colour (illegible on the surface, and
 * colour-alone identity fails under CVD); the dot carries identity and the
 * label carries meaning.
 */
import type { Verdict } from "../lib/schema.ts";

import { VERDICT_COLORS, VERDICT_HINTS, VERDICT_LABELS } from "../lib/verdict.ts";

export interface VerdictBadgeProps {
  readonly verdict: Verdict;
}

export function VerdictBadge({ verdict }: VerdictBadgeProps): React.JSX.Element {
  return (
    <span className="verdict" title={VERDICT_HINTS[verdict]}>
      <span
        aria-hidden="true"
        className="dot"
        style={{ background: VERDICT_COLORS[verdict] }}
      />
      {VERDICT_LABELS[verdict]}
    </span>
  );
}
