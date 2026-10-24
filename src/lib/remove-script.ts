/**
 * A shell script that removes every selected item, for kuhy to read and run
 * himself: the UI only copies it, exactly like a single remove command.
 *
 * Commands of a manager that takes many names in one call are merged into a
 * single invocation (`sudo pacman -Rns a b c`), placed where the first of them
 * stood; everything else keeps its own line in selection order. There is no
 * `set -e`: one package that refuses to go must not stop the rest.
 */
import type { Item } from "./schema.ts";

/**
 * Managers known to accept several names per call. pipx, `dotnet tool`,
 * steam URLs and `rm` paths are deliberately absent: single-argument, or a
 * path where one typo would widen the blast radius.
 */
const MERGEABLE = [
  "sudo pacman -Rns",
  "flatpak uninstall",
  "cargo uninstall",
  "npm uninstall -g",
  "sudo npm uninstall -g",
  "pip uninstall --user",
  "uv tool uninstall",
  "gem uninstall",
] as const;

/**
One plain package name: no quoting, spaces or shell operators to merge across.
*/
const PLAIN_ARGUMENT = /^[\w@%+,./:=-]+$/u;

interface Line {
  readonly args: string[];
  readonly comments: string[];
  readonly prefix: string;
}

/**
Splits `<manager> <name>` for a mergeable manager, else null.
*/
function splitMergeable(command: string): null | { arg: string; prefix: string } {
  for (const prefix of MERGEABLE) {
    const argument = command.slice(prefix.length + 1);
    if (command.startsWith(`${prefix} `) && PLAIN_ARGUMENT.test(argument)) return { arg: argument, prefix };
  }
  return null;
}

function viaComment(item: Item): string[] {
  return item.removeVia === "" ? [] : [`# ${item.id}: ${item.removeVia}`];
}

/**
The script for `items`, in their order; see the module comment.
*/
export function buildRemoveScript(items: readonly Item[]): string {
  const lines: Line[] = [];
  const merged = new Map<string, Line>();
  for (const item of items) {
    const comments = viaComment(item);
    if (item.removeCommand === null) {
      lines.push({ args: [], comments: [...comments, `# no remove command: ${item.id}`], prefix: "" });
      continue;
    }
    const split = splitMergeable(item.removeCommand);
    const existing = split === null ? undefined : merged.get(split.prefix);
    if (split === null) {
      lines.push({ args: [], comments, prefix: item.removeCommand });
    } else if (existing === undefined) {
      const line = { args: [split.arg], comments, prefix: split.prefix };
      merged.set(split.prefix, line);
      lines.push(line);
    } else {
      existing.comments.push(...comments);
      if (!existing.args.includes(split.arg)) existing.args.push(split.arg);
    }
  }

  const count = items.length;
  const body = lines.flatMap((line) => {
    const command = [line.prefix, ...line.args].join(" ");
    return command === "" ? line.comments : [...line.comments, command];
  });
  return [
    "#!/bin/bash",
    `# foss-audit: remove commands for ${String(count)} selected ${count === 1 ? "item" : "items"}.`,
    "# Review before running. Not fail-fast on purpose: one failed command does not stop the rest.",
    "",
    ...body,
    "",
  ].join("\n");
}
