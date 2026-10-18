/**
 * Every field of the selected item, plus its alternative in full.
 *
 * The remove command is copy-only; the UI never runs it. `requiredBy` is
 * shown prominently because a package others depend on is not a one-command
 * removal: `pacman -Rns` refuses, or takes the dependants with it.
 */
import type { Alternative, Item } from "../lib/schema.ts";

import { buildItemPrompt, isPromptCandidate } from "../lib/claude-prompt.ts";
import { EFFORT_LABELS, FIT_LABELS, hasTrackedDependants } from "../lib/verdict.ts";
import { CopyButton } from "./copy-button.tsx";
import { VerdictBadge } from "./verdict-badge.tsx";

export interface DetailPanelProps {
  readonly item: Item;
  readonly onClose: () => void;
}

function Field({ children, label }: { readonly children: React.ReactNode; readonly label: string }): React.JSX.Element {
  return (
    <div className="field">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function orDash(value: null | string): string {
  return value === null || value === "" ? "—" : value;
}

function AlternativeBlock({ alt }: { readonly alt: Alternative }): React.JSX.Element {
  const installed = new Set(alt.installed);
  return (
    <section aria-labelledby="alt-heading" className="panel-section">
      <h3 id="alt-heading">FOSS alternative</h3>
      {alt.names.length === 0 ? (
        <p className="muted">No named alternative in the curated list.</p>
      ) : (
        <ol className="alt-names">
          {alt.names.map((name) => {
            return (
              <li key={name}>{name}</li>
            );
          })}
        </ol>
      )}
      {alt.installed.length > 0 && (
        <p className="installed-line">
          <span className="badge badge-success">Already installed</span>{" "}
          {[...installed].join(", ")}
        </p>
      )}
      <dl className="fields">
        <Field label="Fit">{FIT_LABELS[alt.fit]}</Field>
        <Field label="Build-it effort">{alt.effort === null ? "—" : EFFORT_LABELS[alt.effort]}</Field>
        <Field label="Why that effort">{orDash(alt.effortReason)}</Field>
        <Field label="Lock-in">{orDash(alt.lockIn)}</Field>
      </dl>
    </section>
  );
}

export function DetailPanel({ item, onClose }: DetailPanelProps): React.JSX.Element {
  return (
    <aside aria-labelledby="panel-title" className="panel">
      <div className="panel-head">
        <h2 id="panel-title">{item.name}</h2>
        <button aria-label="Close details (Esc)" className="btn" onClick={onClose} type="button">
          Close
        </button>
      </div>
      <div className="panel-body">
        <dl className="fields">
          <Field label="Verdict">
            <VerdictBadge verdict={item.verdict} />
          </Field>
          <Field label="Own code">{item.own ? "yes — kuhy's own" : "no"}</Field>
          <Field label="Untracked file">
            {item.loose ? "yes — in ~/.local/bin, no repo or package tracks it" : "no"}
          </Field>
          <Field label="Dead launcher">
            {item.dangling ? "yes — the .desktop file's Exec target no longer exists" : "no"}
          </Field>
          <Field label="Evidence">{orDash(item.reason)}</Field>
          <Field label="Licence">{orDash(item.license)}</Field>
          <Field label="Version">{orDash(item.version)}</Field>
          <Field label="Source">{item.source}</Field>
          <Field label="Installed as">{item.explicit ? "explicit" : "dependency"}</Field>
          <Field label="Orphan">{item.orphan ? "yes — nothing requires it any more" : "no"}</Field>
          <Field label="Homepage">
            {item.url === null ? (
              "—"
            ) : (
              <a href={item.url} rel="noreferrer noopener" target="_blank">
                {item.url}
              </a>
            )}
          </Field>
          <Field label="ID">
            <code>{item.id}</code>
          </Field>
        </dl>

        <section aria-labelledby="remove-heading" className="panel-section">
          <h3 id="remove-heading">Remove</h3>
          <CopyButton command={item.removeCommand} />
        </section>

        <section aria-labelledby="req-heading" className="panel-section">
          <h3 id="req-heading">Required by</h3>
          {item.requiredBy.length === 0 ? (
            <p className="muted">
              {hasTrackedDependants(item)
                ? "Nothing depends on it."
                : `Not tracked: reverse dependencies are only known for pacman and AUR packages, not ${item.source}.`}
            </p>
          ) : (
            <>
              <p className="warning-line">
                by {item.requiredBy.length}{" "}
                {item.requiredBy.length === 1 ? "package" : "packages"}:
              </p>
              <ul className="req-list">
                {item.requiredBy.map((name) => {
                  return (
                    <li key={name}>
                      <code>{name}</code>
                    </li>
                  );
                })}
              </ul>
            </>
          )}
        </section>

        {item.alternative !== null && <AlternativeBlock alt={item.alternative} />}

        {isPromptCandidate(item) && (
          <section aria-labelledby="prompt-heading" className="panel-section">
            <h3 id="prompt-heading">Hand it to Claude</h3>
            <p className="muted">
              A prompt to research, suggest and install a FOSS alternative. It never removes {item.name}.
            </p>
            <CopyButton
              buttonText="Copy Claude prompt"
              command={buildItemPrompt(item)}
              label="Copy a Claude prompt for this item"
              showText={false}
            />
          </section>
        )}

      </div>
    </aside>
  );
}
