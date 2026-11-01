/**
 * Compact age of an ISO timestamp: `45s`, `4m`, `3h`, `2d`.
 */

const UNITS = [
  { label: "d", seconds: 86_400 },
  { label: "h", seconds: 3600 },
  { label: "m", seconds: 60 },
] as const;

/**
 * `""` when `iso` does not parse, so a bad stamp renders nothing.
 */
export function formatAge(iso: string, now: number): string {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "";
  const seconds = Math.max(0, Math.floor((now - then) / 1000));
  const unit = UNITS.find((candidate) => seconds >= candidate.seconds);
  return unit === undefined ? `${seconds}s` : `${Math.floor(seconds / unit.seconds)}${unit.label}`;
}
