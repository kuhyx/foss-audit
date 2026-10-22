/**
 * The public site's routes and content: the single source every artifact is
 * generated from (HTML pages, markdown mirrors, sitemap, llms.txt, catalog).
 *
 * The app itself has one route ("" with its view in the query string); the
 * other pages are static documentation. Lists come from the same constants
 * the UI renders (verdicts, sources, views, shortcuts), so a new source or
 * shortcut shows up here with no extra edit.
 */
import { SOURCES, VERDICTS } from "../lib/schema.ts";
import { VIEWS } from "../lib/url-state.ts";
import { VERDICT_HINTS, VERDICT_LABELS } from "../lib/verdict.ts";
import { SHORTCUTS, VIEW_HINTS, VIEW_LABELS } from "../lib/views.ts";

export type Block =
  | { readonly code: string; readonly kind: "code"; readonly lang: string }
  | { readonly items: readonly (readonly [string, string])[]; readonly kind: "terms" }
  | { readonly items: readonly LinkItem[]; readonly kind: "links" }
  | { readonly items: readonly string[]; readonly kind: "codes" }
  | { readonly kind: "heading"; readonly text: string }
  | { readonly kind: "paragraph"; readonly text: string };

export interface LinkItem {
  readonly note: string;
  /**
  Site-relative target path.
  */
  readonly path: string;
  readonly title: string;
}

export interface Page {
  readonly blocks: readonly Block[];
  readonly description: string;
  /**
  Site-relative: "" for the homepage, "name/" for the rest.
  */
  readonly path: string;
  readonly title: string;
}

const verdicts: Page = {
  blocks: [
    {
      kind: "paragraph",
      text: "The packager's licence metadata decides first: pacman and AUR licence fields, PyPI classifiers, npm and cargo manifests, flatpak metainfo. Anything ambiguous is settled by hand in data/curated.json, which also carries the FOSS alternative, a fit rating and the effort it would take to build one.",
    },
    { kind: "heading", text: "Verdicts" },
    { items: VERDICTS.map((v) => [VERDICT_LABELS[v], VERDICT_HINTS[v]] as const), kind: "terms" },
    {
      kind: "paragraph",
      text: "Whether the code is kuhy's own is a separate flag, not a verdict. An easy win is an item that is not fully free, has a drop-in or good FOSS alternative, and has at least one of those alternatives already installed.",
    },
  ],
  description: "How each installed program is classified as FOSS, partly FOSS or non-free.",
  path: "verdicts/",
  title: "How verdicts are decided",
};

const sources: Page = {
  blocks: [
    {
      kind: "paragraph",
      text: "One scan reads every package manager and install location below. Package caches (the -cache sources) also record which projects in ~/src depend on each package.",
    },
    { items: SOURCES, kind: "codes" },
  ],
  description: "Every package manager and install location the scanner reads.",
  path: "sources/",
  title: "What gets scanned",
};

const views: Page = {
  blocks: [
    { items: VIEWS.map((v) => [VIEW_LABELS[v], VIEW_HINTS[v]] as const), kind: "terms" },
    { kind: "heading", text: "Keyboard shortcuts" },
    { items: SHORTCUTS, kind: "terms" },
    {
      kind: "paragraph",
      text: "Every filter, the sort and the open row live in the URL query string, so the address bar is always a shareable link and Back returns to the previous view.",
    },
  ],
  description: "The Summary, All items and Easy wins views, and the keyboard shortcuts.",
  path: "views/",
  title: "Views and shortcuts",
};

const guides: readonly Page[] = [verdicts, sources, views];

const home: Page = {
  blocks: [
    {
      kind: "paragraph",
      text: "foss-audit scans every program installed on kuhy's Arch Linux PC and sorts each one into FOSS, partly FOSS or non-free (anything with no licence grant, firmware blobs included). kuhy's own code and untracked ~/.local/bin files are flagged separately. Non-free items get a curated FOSS alternative, a fit rating and the effort it would take to build one.",
    },
    {
      kind: "paragraph",
      text: "The explorer is a local app: a stdlib-only Python scanner API plus a React UI, both bound to localhost. The live scan takes about 1.5 seconds and the UI never runs commands itself; removal commands are copied to the clipboard.",
    },
    { kind: "heading", text: "Run it" },
    { code: "./run.sh                      # API on 127.0.0.1:5191, UI on 127.0.0.1:5190\n./run.sh --install-launcher   # adds \"FOSS audit\" to dmenu/rofi", kind: "code", lang: "bash" },
    { kind: "heading", text: "Documentation" },
    {
      items: [
        ...guides.map((p) => ({ note: p.description, path: p.path, title: p.title })),
        { note: "A described index of these pages for language models.", path: "llms.txt", title: "llms.txt" },
      ],
      kind: "links",
    },
  ],
  description:
    "Every program installed on kuhy's PC, whether it is FOSS, and the FOSS alternative for the ones that are not.",
  path: "",
  title: "FOSS audit",
};

export const PAGES: readonly Page[] = [home, ...guides];
