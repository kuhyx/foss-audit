/**
 * One Claude prompt for a multi-selection from the all-items table.
 *
 * Unlike the summary view's bulk prompt (claude-prompt.ts), it covers every
 * selected item, FOSS ones included, so it is a separate builder: that button
 * must keep filtering to non-FOSS, or it would suddenly carry ~10k items.
 *
 * Non-FOSS and partly-FOSS items keep research -> suggest -> install, but in
 * groups (a shared curated alternative, else a shared namespace such as a
 * Maven group or npm scope), and the "wait for my pick" gate is once per
 * group: one decision for twelve com.google.android.gms artifacts, not twelve.
 * FOSS items only get a usage check and, if unused, a printed remove command.
 */
import type { Item } from "./schema.ts";

import {
  factLines,
  INSTALL_STEP,
  isPromptCandidate,
  isResearchOnly,
  REPO,
  RESEARCH_STEP,
  SCAN,
  suggestStep,
} from "./claude-prompt.ts";

export interface ItemGroup {
  readonly items: Item[];
  readonly label: string;
}

const FOSS_HEADING = "### already FOSS: confirm it is still used; if not, print its remove command";

function alternativeKey(item: Item): null | string {
  const names = item.alternative?.names ?? [];
  return names.length === 0 ? null : names.join(", ");
}

/**
Maven `group:artifact` -> group; npm `@scope/name` -> `@scope`; else none.
*/
function namespaceOf(item: Item): null | string {
  if (item.name.includes(":")) return item.name.slice(0, item.name.indexOf(":"));
  return item.name.startsWith("@") && item.name.includes("/") ? item.name.slice(0, item.name.indexOf("/")) : null;
}

function countBy(items: readonly Item[], key: (item: Item) => null | string): Map<string, number> {
  const counts = new Map<string, number>();
  for (const item of items) {
    const value = key(item);
    if (value !== null) counts.set(value, (counts.get(value) ?? 0) + 1);
  }
  return counts;
}

/**
 * True when more than one item has `value`. Only ever asked about values that
 * `counts` was built from, so a non-null value is always present with >= 1.
 */
function isShared(counts: Map<string, number>, value: null | string): value is string {
  return value !== null && counts.get(value) !== 1;
}

/**
 * Groups in order of first appearance. A shared alternative wins over a
 * shared namespace; a key only one item has is no group at all.
 */
export function groupItems(items: readonly Item[]): ItemGroup[] {
  const altCounts = countBy(items, alternativeKey);
  const rest = items.filter((item) => !isShared(altCounts, alternativeKey(item)));
  const nsCounts = countBy(rest, namespaceOf);

  function keyOf(item: Item): [string, string] {
    const alt = alternativeKey(item);
    if (isShared(altCounts, alt)) return [`alt:${alt}`, `shared alternative ${alt}`];
    const ns = namespaceOf(item);
    return isShared(nsCounts, ns) ? [`ns:${ns}`, `namespace ${ns}`] : [`item:${item.id}`, item.name];
  }

  const groups = new Map<string, ItemGroup>();
  for (const item of items) {
    const [key, label] = keyOf(item);
    const group = groups.get(key) ?? { items: [], label };
    group.items.push(item);
    groups.set(key, group);
  }
  return groups.values().toArray();
}

function itemLines(item: Item, mode: null | string): string[] {
  const suffix = mode === null ? "" : `: ${mode}`;
  const via = item.removeVia === "" ? [] : [`- remove via: ${item.removeVia}`];
  return ["", `#### ${item.name} (\`${item.id}\`)${suffix}`, ...factLines(item), ...via];
}

function groupSections(groups: readonly ItemGroup[]): string[] {
  return groups.flatMap((group, index) => {
    const size = group.items.length;
    const count = size === 1 ? "" : ` (${String(size)} items)`;
    const heading = `### Group ${String(index + 1)} of ${String(groups.length)}: ${group.label}${count}`;
    const items = group.items.flatMap((item) =>
      itemLines(item, isResearchOnly(item) ? "research only" : "research, suggest, install"),
    );
    return ["", heading, ...items];
  });
}

/**
Prompt for every selected item; see the module comment for the format.
*/
export function buildSelectionPrompt(items: readonly Item[]): string {
  const candidates = items.filter((item) => isPromptCandidate(item));
  const foss = items.filter((item) => !isPromptCandidate(item));
  const groups = groupItems(candidates);
  const hasCandidates = candidates.length > 0;
  const hasFoss = foss.length > 0;

  const replaceMust = hasCandidates
    ? [
        "- Work one group at a time, in the order listed: steps 0 and 1 for every item in the group, then wait for one pick from me for the whole group before step 2. One wait per group, not per item.",
        RESEARCH_STEP,
        suggestStep("stop and ask me which one to install for the whole group (or move on, for research-only items)"),
        INSTALL_STEP,
        "- must not: install anything for a group before I have picked from its step 1.",
      ]
    : [];
  const fossMust = hasFoss
    ? [
        "- already FOSS items: no research and no install. Confirm each is still used (something depends on it, or I run it); if it is not, print its remove command for me.",
      ]
    : [];
  const replaceDone = hasCandidates
    ? [
        "- every group has a curated.json entry per item with verified licences, committed in that repo with `.venv/bin/python -m pytest -q` green.",
        `- every installable group I picked for shows its alternative under \`alternative.installed\` in \`${SCAN}\`.`,
      ]
    : [];
  const fossDone = hasFoss
    ? ["- every already-FOSS item is marked still used (with the evidence) or unused (with its remove command printed)."]
    : [];
  const fossSection = hasFoss ? ["", FOSS_HEADING, ...foss.flatMap((item) => itemLines(item, null))] : [];

  return [
    `Work through ${String(items.length)} selected items: ${String(candidates.length)} to replace, ${String(foss.length)} already FOSS`,
    "",
    "## what",
    "I picked these items in foss-audit. For the non-FOSS and partly-FOSS ones (grouped under `## known`), research FOSS alternatives, suggest the best one per group, then install it unless an item is marked research only. For the already-FOSS ones, only check they are still used.",
    "## where",
    `This Arch Linux machine. Scanner and curated verdicts: ${REPO} (data/curated.json).`,
    "## must",
    ...replaceMust,
    ...fossMust,
    "- must not: remove, disable or uninstall any of them; print their remove commands for me instead.",
    "## done",
    ...replaceDone,
    ...fossDone,
    "## verify",
    `On this machine, from ${REPO}: \`${SCAN} | jq '.items[] | select(.id == "<id>") | {id, verdict, alternative}'\` for each id listed.`,
    "## known",
    ...groupSections(groups),
    ...fossSection,
  ].join("\n");
}
