/**
 * Array helpers that keep `noUncheckedIndexedAccess` honest.
 */

/**
 * Bounds-checked access for any array. For
 * callers that have already guaranteed the index is valid and would otherwise
 * need an untestable `?? fallback` to satisfy noUncheckedIndexedAccess.
 */
export function elementAt<T>(values: readonly T[], index: number): T {
  const value = values[index];
  if (value === undefined) {
    throw new RangeError(`index ${index} out of range`);
  }
  return value;
}
