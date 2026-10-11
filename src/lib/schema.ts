/**
 * The `/api/scan` response, validated at the fetch boundary.
 *
 * Mirrors DOCS-api-contract.md field for field. Every type the UI uses is
 * inferred from these schemas rather than written twice, so a contract change
 * that is not reflected here fails loudly in the parse (with the offending
 * path) instead of rendering `undefined` somewhere deep in a cell.
 */
import { z } from "zod";

export const SOURCES = [
  "pacman",
  "aur",
  "pip-user",
  "pipx",
  "uv-tool",
  "npm-global",
  "cargo",
  "flatpak",
  "appimage",
  "opt",
  "local-bin",
  "conda",
  "steam",
  "wine",
  "waydroid",
  "unowned",
  "app-home",
  "toolchain",
  "desktop",
  "docker",
  "user-app",
] as const;

/**
 * Display and chart order: the two "free" verdicts first, then non-free, so a
 * stacked bar reads as one free run followed by the rest. Whether the code is
 * kuhy's own is a separate flag (`Item.own`), not a verdict.
 */
export const VERDICTS = ["foss", "foss-partial", "nonfree"] as const;

/**
 * Best fit first; this order is also the sort order of the Fit column.
 */
export const FITS = ["drop-in", "good", "partial", "none"] as const;

/**
 * Smallest effort first; the sort order of the Effort column.
 */
export const EFFORTS = ["S", "M", "L", "XL"] as const;

export const sourceSchema = z.enum(SOURCES);
export const verdictSchema = z.enum(VERDICTS);

export const alternativeSchema = z.object({
  effort: z.enum(EFFORTS).nullable(),
  effortReason: z.string(),
  fit: z.enum(FITS),
  installed: z.array(z.string()),
  lockIn: z.string(),
  names: z.array(z.string()),
});

export const itemSchema = z.object({
  alternative: alternativeSchema.nullable(),
  dangling: z.boolean().default(false),
  explicit: z.boolean(),
  id: z.string(),
  license: z.string(),
  loose: z.boolean(),
  name: z.string(),
  orphan: z.boolean(),
  own: z.boolean(),
  reason: z.string(),
  removeCommand: z.string().nullable(),
  requiredBy: z.array(z.string()),
  source: sourceSchema,
  url: z.string().nullable(),
  verdict: verdictSchema,
  version: z.string().nullable(),
});

export const scanErrorSchema = z.object({
  message: z.string(),
  source: z.string(),
});

export const scanSchema = z.object({
  durationMs: z.number(),
  errors: z.array(scanErrorSchema),
  generatedAt: z.string(),
  host: z.string(),
  items: z.array(itemSchema),
});

export type Alternative = z.infer<typeof alternativeSchema>;
export type Effort = (typeof EFFORTS)[number];
export type Fit = (typeof FITS)[number];
export type Item = z.infer<typeof itemSchema>;
export type Scan = z.infer<typeof scanSchema>;
export type ScanError = z.infer<typeof scanErrorSchema>;
export type Source = z.infer<typeof sourceSchema>;
export type Verdict = z.infer<typeof verdictSchema>;

/**
 * Parses an untrusted body, or throws an Error naming the first bad path.
 *
 * One unexpected enum value (a new Source added to the backend, say) must not
 * blank the app silently: the message says exactly which field to look at.
 */
export function parseScan(body: unknown): Scan {
  const result = scanSchema.safeParse(body);
  if (result.success) return result.data;
  // zod reports at least one issue on failure; listing all of them avoids a
  // branch for an "empty issues" case that cannot happen.
  const detail = result.error.issues
    .map((issue) => `"${issue.path.join(".")}": ${issue.message}`)
    .join("; ");
  throw new Error(`/api/scan response failed validation at ${detail}`);
}
