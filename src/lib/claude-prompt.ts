/**
 * Copyable prompts that hand one non-FOSS item (or all of them) to a Claude
 * session: 0. research, 1. suggest, 2. install a FOSS alternative.
 *
 * The prompt is written in kuhy's backlog-note format (what / where / must /
 * done / verify) so his spec gate accepts it without a grilling round, and it
 * carries every scan fact so the receiving session does not have to rescan.
 * Removing the original is always left to him: the prompt only quotes the
 * remove command, exactly like the UI.
 */
import type { Item } from "./schema.ts";

import { EFFORT_LABELS, FIT_LABELS, hasTrackedDependants, VERDICT_LABELS } from "./verdict.ts";

const REPO = "~/src/foss-audit";
const SCAN = ".venv/bin/python -m foss_audit.scan";

/**
Everything the scanner does not call plain FOSS gets a prompt.
*/
export function isPromptCandidate(item: Item): boolean {
  return item.verdict !== "foss";
}

/**
 * Items with nothing to install in their place: firmware blobs (the kernel
 * needs them; there is no free build to swap in) and Steam library entries
 * (a purchased game or runtime is not replaced by installing something else).
 * Their prompt stops after the suggestion step.
 */
export function isResearchOnly(item: Item): boolean {
  return item.reason.startsWith("firmware blob") || item.source === "steam";
}

function orFallback(value: null | string, fallback: string): string {
  return value === null || value === "" ? fallback : value;
}

function alternativeLine(item: Item): string {
  const alt = item.alternative;
  if (alt === null) {
    return "curated alternatives: none yet";
  }
  const names = alt.names.length === 0 ? "none named" : alt.names.join(", ");
  const details = [
    `fit: ${FIT_LABELS[alt.fit]}`,
    `build-it effort: ${alt.effort === null ? "unknown" : EFFORT_LABELS[alt.effort]}`,
    ...(alt.effortReason === "" ? [] : [`why: ${alt.effortReason}`]),
    ...(alt.lockIn === "" ? [] : [`lock-in: ${alt.lockIn}`]),
  ];
  const installed = alt.installed.length === 0 ? "" : `; already installed: ${alt.installed.join(", ")}`;
  return `curated alternatives: ${names} (${details.join(", ")})${installed}`;
}

function requiredByLine(item: Item): string {
  if (item.requiredBy.length > 0) {
    return item.requiredBy.join(", ");
  }
  return hasTrackedDependants(item) ? "nothing" : `not tracked for ${item.source}`;
}

function removeLine(item: Item): string {
  return item.removeCommand === null ? "none known" : `\`${item.removeCommand}\` (do not run it)`;
}

/**
The scan facts for one item, as `- ` bullet lines.
*/
function factLines(item: Item): string[] {
  return [
    `- id: \`${item.id}\`, source: ${item.source}, version: ${orFallback(item.version, "unknown")}`,
    `- verdict: ${VERDICT_LABELS[item.verdict]}; evidence: ${orFallback(item.reason, "none recorded")}`,
    `- licence: ${orFallback(item.license, "none found")}`,
    `- homepage: ${orFallback(item.url, "unknown")}`,
    `- required by: ${requiredByLine(item)}`,
    `- ${alternativeLine(item)}`,
    `- remove command: ${removeLine(item)}`,
  ];
}

const RESEARCH_STEP =
  "- 0. research: find the current FOSS options for it (pacman, AUR, flatpak, upstream), including the curated ones listed for it. Verify each licence from a primary source (LICENSE file or upstream page) and check the project is still maintained.";

function suggestStep(stop: string): string {
  return `- 1. suggest: rank up to 3 candidates with fit (drop-in / good / partial / none), build-it effort (S / M / L / XL), lock-in and what I would lose. Update the matching entry in ${REPO}/data/curated.json (or add one), run the backend tests, commit it in that repo, then ${stop}.`;
}

const INSTALL_STEP =
  "- 2. install: install the alternative I pick, migrate config/data where that is cheap, and show it actually running.";

/**
Prompt for a single item; see the module comment for the format.
*/
export function buildItemPrompt(item: Item): string {
  const isResearch = isResearchOnly(item);
  const title = isResearch
    ? `Research FOSS alternatives to ${item.name}`
    : `Replace ${item.name} with a FOSS alternative`;
  const steps = isResearch
    ? [RESEARCH_STEP, suggestStep("stop: this item is research only, there is no install step")]
    : [RESEARCH_STEP, suggestStep("stop and ask me which one to install"), INSTALL_STEP];
  const installDone = isResearch
    ? []
    : [
        `- 2: a rescan lists the chosen alternative under \`alternative.installed\` for \`${item.id}\`, and its launch output is shown.`,
      ];

  return [
    title,
    "",
    "## what",
    `\`${item.name}\` is ${VERDICT_LABELS[item.verdict].toLowerCase()} per foss-audit. Research FOSS alternatives, suggest the best one${isResearch ? " (research only: nothing gets installed)" : ", then install it"}.`,
    "## where",
    `This Arch Linux machine. Scanner and curated verdicts: ${REPO} (data/curated.json).`,
    "## known",
    ...factLines(item),
    "## must",
    ...steps,
    `- must not: remove, disable or uninstall ${item.name}; when it is time, print its remove command for me instead.`,
    "- must not: install anything before I have picked from step 1.",
    "## done",
    "- 0: every candidate listed with its licence and a source link.",
    `- 1: curated.json updated and committed, \`.venv/bin/python -m pytest -q\` green, and \`${SCAN} | jq '.items[] | select(.id == "${item.id}") | .alternative'\` shows the new entry.`,
    ...installDone,
    "## verify",
    `On this machine, from ${REPO}: the jq command above after a rescan.`,
  ].join("\n");
}

/**
 * One prompt for every candidate in `items`, worked through one at a time so a
 * single session never installs a batch of things nobody picked.
 */
export function buildBulkPrompt(items: readonly Item[]): string {
  const candidates = items.filter((item) => isPromptCandidate(item));
  const sections = candidates.flatMap((item) => {
    const mode = isResearchOnly(item) ? "research only" : "research, suggest, install";
    return ["", `### ${item.name} (\`${item.id}\`): ${mode}`, ...factLines(item)];
  });

  return [
    `Replace ${String(candidates.length)} non-FOSS items with FOSS alternatives`,
    "",
    "## what",
    "For every item listed under `## known`, research FOSS alternatives, suggest the best one, then install it unless the item is marked research only (firmware blobs, Steam library entries).",
    "## where",
    `This Arch Linux machine. Scanner and curated verdicts: ${REPO} (data/curated.json).`,
    "## must",
    "- Work one item at a time, in the order listed: steps 0 and 1 for an item, then wait for my pick before step 2.",
    RESEARCH_STEP,
    suggestStep("stop and ask me which one to install (or move on, for research-only items)"),
    INSTALL_STEP,
    "- must not: remove, disable or uninstall any of them; print their remove commands for me instead.",
    "- must not: install anything before I have picked from step 1.",
    "- optional: skip items whose curated entry is already settled and whose alternative is already installed; list them at the end instead.",
    "## done",
    "- every item has a curated.json entry with verified licences, committed in that repo with `.venv/bin/python -m pytest -q` green.",
    `- every installable item I picked shows its alternative under \`alternative.installed\` in \`${SCAN}\`.`,
    "## verify",
    `On this machine, from ${REPO}: \`${SCAN} | jq '.items[] | select(.verdict != "foss") | {id, alternative}'\`.`,
    "## known",
    ...sections,
  ].join("\n");
}
