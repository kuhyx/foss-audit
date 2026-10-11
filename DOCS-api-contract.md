# API contract: backend scanner ⇄ React UI

The Python backend (`foss_audit/server.py`) binds `127.0.0.1:5191`. The Vite
dev/preview server proxies `/api` to it, so the UI always fetches same-origin.

## `GET /api/scan[?refresh=1]`

Scans the machine live. The result is cached in memory; `refresh=1` forces a
rescan (a full scan takes a few seconds). Response body:

```jsonc
{
  "generatedAt": "2026-10-11T14:02:11Z", // ISO-8601 UTC
  "durationMs": 2310,
  "host": "kuhy-pc",
  "items": [Item, ...],
  "errors": [{ "source": "flatpak", "message": "flatpak not installed" }]
}
```

### `Item`

| field | type | notes |
|---|---|---|
| `id` | string | `"<source>:<name>"`, unique |
| `name` | string | package / program name |
| `version` | string \| null | |
| `source` | `Source` | where it was found (see below) |
| `explicit` | boolean | pacman: installed explicitly (not as a dep). Other sources: `true` |
| `orphan` | boolean | pacman dependency nothing requires any more |
| `own` | boolean | kuhy's own code: his AUR packages, pip installs of his repos, scripts in `~/.local/bin` (verdict comes from his LICENSE files) |
| `loose` | boolean | a `~/.local/bin` file no package, pip distribution, symlink target or kuhyx repo accounts for |
| `license` | string | raw license string from metadata, `""` when absent |
| `verdict` | `Verdict` | |
| `reason` | string | one-line evidence, may be `""` |
| `url` | string \| null | upstream homepage |
| `requiredBy` | string[] | pacman reverse deps, else `[]` |
| `alternative` | `Alternative` \| null | only set for non-FOSS items with a curated entry |
| `removeCommand` | string \| null | e.g. `sudo pacman -Rns google-chrome`; UI only copies it, never runs it |

`Source` = `"pacman" | "aur" | "pip-user" | "pipx" | "uv-tool" | "npm-global" | "cargo" | "flatpak" | "appimage" | "opt" | "local-bin" | "conda" | "steam" | "wine" | "waydroid"`

`Verdict` = `"foss" | "foss-partial" | "nonfree"`

- `foss` — OSI/FSF license on the shipped thing
- `foss-partial` — free code with a non-free part (assets, weights, unRAR code)
- `nonfree` — proprietary, freeware, EULA, source-available (BSL, NPSL), firmware
  blobs (reason starts `firmware blob:`), and anything with no license grant at all
  (reason `no license (all rights reserved)` or `unrecognised license: …`)

A checkout counts as kuhy's when its remote is under `github.com/kuhyx/`, or when it
has no remote at all and sits directly under `~/src` (local-only repos); a repo with
anyone else's remote is not own. Own code is licensed by its checkout: a LICENSE/COPYING file, else the
`pyproject.toml` / `package.json` license field. AUR packages and VCS pip installs
are mapped from their `github.com/kuhyx/<repo>` URL to the local checkout by git
remote; loose `~/.local/bin` copies and built binaries (symlink targets outside any
checkout) by a same-named tracked file in a kuhyx repo, ignoring `_`/`-` and the
extension (`book_guard_desktop` ← `book_guard_desktop.dart`). Outside a checkout,
only a named package root (package.json / pyproject.toml with a name) can supply a
license, so a stray `~/.local/share/COPYING` licenses nothing. No license is
ever hand-assigned for kuhy's code in `data/curated.json`.

pnpm global shims in `~/.local/bin` (a non-ELF `sh` file whose `exec` line runs
`"$basedir…/…/node_modules/<pkg>/…"`) are traced to that package and licensed by its
`package.json` / LICENSE: `own=false`, `loose=false`, reason `pnpm shim -> <package dir>`.

### `Alternative`

| field | type | notes |
|---|---|---|
| `names` | string[] | FOSS alternatives, best first |
| `fit` | `"drop-in" \| "good" \| "partial" \| "none"` | |
| `effort` | `"S" \| "M" \| "L" \| "XL" \| null` | build-it-ourselves effort; S <1 wk, M 1–4 wk, L 1–6 mo, XL infeasible |
| `effortReason` | string | |
| `lockIn` | string | hardware / network-service note, may be `""` |
| `installed` | string[] | which of the alternatives are installed **right now** (computed live) |

"Easy win" (UI view) = `verdict ∈ {nonfree, foss-partial}`, `alternative.fit ∈ {drop-in, good}`
and `alternative.installed.length > 0`. Show `requiredBy` next to it: a package
other packages still need is not a one-click removal.
