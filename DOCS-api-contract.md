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
| `license` | string | raw license string from metadata, `""` when absent |
| `verdict` | `Verdict` | |
| `reason` | string | one-line evidence, may be `""` |
| `url` | string \| null | upstream homepage |
| `requiredBy` | string[] | pacman reverse deps, else `[]` |
| `alternative` | `Alternative` \| null | only set for non-FOSS items with a curated entry |
| `removeCommand` | string \| null | e.g. `sudo pacman -Rns google-chrome`; UI only copies it, never runs it |

`Source` = `"pacman" | "aur" | "pip-user" | "pipx" | "uv-tool" | "npm-global" | "cargo" | "flatpak" | "appimage" | "opt" | "local-bin" | "conda" | "steam" | "wine" | "waydroid"`

`Verdict` = `"foss" | "foss-partial" | "nonfree" | "blob" | "own" | "unknown"`

- `foss` — OSI/FSF license on the shipped thing
- `foss-partial` — free code with a non-free part (assets, weights, unRAR code)
- `nonfree` — proprietary, freeware, EULA, or source-available (BSL, NPSL, no grant)
- `blob` — firmware / driver / microcode with no alternative on this hardware
- `own` — kuhy's own code (scripts in `~/.local/bin`, own pip packages)
- `unknown` — no license found anywhere

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
