/**
 * Sticky bar over the all-items table while anything is multi-selected:
 * "N selected · Clear" and the two bulk copies. It counts every selected item,
 * including ones the current filter hides, because the selection persists
 * across filter changes. Nothing here runs a command; it only copies.
 */
import type { Item } from "../lib/schema.ts";

import { withRemoves } from "../hooks/remove-api.ts";
import { buildRemoveScript } from "../lib/remove-script.ts";
import { buildSelectionPrompt } from "../lib/selection-prompt.ts";
import { AsyncCopyButton } from "./copy-button.tsx";

export interface SelectionBarProps {
  readonly items: readonly Item[];
  readonly onClear: () => void;
}

const numberFormat = new Intl.NumberFormat("en-US");

export function SelectionBar({ items, onClear }: SelectionBarProps): null | React.JSX.Element {
  if (items.length === 0) return null;
  const count = numberFormat.format(items.length);
  return (
    <section aria-label="Selection" className="selection-bar">
      <span className="selection-count">
        {count} selected ·{" "}
        <button className="link" onClick={onClear} type="button">
          Clear
        </button>
      </span>
      <AsyncCopyButton
        build={async (): Promise<string> => buildSelectionPrompt(await withRemoves(items))}
        buttonText={`Copy Claude prompt (${count})`}
        label="Copy one Claude prompt for every selected item: replace the non-FOSS ones, confirm the FOSS ones"
      />
      <AsyncCopyButton
        build={async (): Promise<string> => buildRemoveScript(await withRemoves(items))}
        buttonText={`Copy remove commands (${count})`}
        label="Copy a shell script with the remove command of every selected item (it is not run)"
      />
    </section>
  );
}
