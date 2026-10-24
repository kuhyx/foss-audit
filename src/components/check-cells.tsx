/**
 * The selection checkboxes of the all-items table: one per row, one in the
 * header for "every row the current filter shows".
 *
 * A row checkbox stops its click from reaching the row, whose own click opens
 * the detail panel; shift is read from that click for range selection.
 */
import type { HeaderCheck } from "../lib/selection.ts";

export interface RowCheckboxProps {
  readonly checked: boolean;
  readonly name: string;
  readonly onCheck: (isShift: boolean) => void;
}

export function RowCheckbox({ checked, name, onCheck }: RowCheckboxProps): React.JSX.Element {
  return (
    <input
      aria-label={`Select ${name}`}
      checked={checked}
      className="check"
      onClick={(event): void => {
        event.stopPropagation();
        onCheck(event.shiftKey);
      }}
      // Controlled through onClick (which carries shiftKey); readOnly only
      // tells React that the missing onChange is intentional.
      readOnly
      type="checkbox"
    />
  );
}

export interface HeaderCheckboxProps {
  readonly onToggle: () => void;
  readonly state: HeaderCheck;
}

export function HeaderCheckbox({ onToggle, state }: HeaderCheckboxProps): React.JSX.Element {
  return (
    <input
      aria-label="Select all shown"
      checked={state === "all"}
      className="check"
      onClick={onToggle}
      readOnly
      // `indeterminate` is a DOM property with no attribute, so React cannot
      // render it; a callback ref re-applies it whenever `state` changes.
      ref={(node): void => {
        if (node !== null) node.indeterminate = state === "some";
      }}
      type="checkbox"
    />
  );
}
