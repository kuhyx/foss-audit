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
| `dangling` | boolean | `desktop` only: a `.desktop` launcher whose `Exec` target no longer exists (default `false`; the UI schema tolerates its absence) |
| `license` | string | raw license string from metadata, `""` when absent |
| `verdict` | `Verdict` | |
| `reason` | string | one-line evidence, may be `""` |
| `url` | string \| null | upstream homepage |
| `requiredBy` | string[] | pacman reverse deps, else `[]` |
| `alternative` | `Alternative` \| null | only set for non-FOSS items with a curated entry |
| `removeCommand` | string \| null | e.g. `sudo pacman -Rns google-chrome`; UI only copies it, never runs it |

`Source` = `"pacman" | "aur" | "pip-user" | "pipx" | "uv-tool" | "npm-global" | "cargo" | "flatpak" | "appimage" | "opt" | "local-bin" | "conda" | "steam" | "wine" | "waydroid" | "unowned" | "app-home" | "toolchain" | "desktop" | "docker" | "user-app"`

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
extension (`book_guard_desktop` ← `book_guard_desktop.dart`), else by the name of the
directory a tracked file sits in, entry point first (`imageviewer` ← `C/imageViewer/main.c`). Outside a checkout,
only a named package root (package.json / pyproject.toml with a name) can supply a
license, so a stray `~/.local/share/COPYING` licenses nothing. No license is
ever hand-assigned for kuhy's code in `data/curated.json`.

pnpm global shims in `~/.local/bin` (a non-ELF `sh` file whose `exec` line runs
`"$basedir…/…/node_modules/<pkg>/…"`) are traced to that package and licensed by its
`package.json` / LICENSE: `own=false`, `loose=false`, reason `pnpm shim -> <package dir>`.

Native `~/.local/bin` binaries that name their own terms (claude: "Anthropic's
Commercial Terms") get that as a `LicenseRef-*` license, reason `-> <target>; binary cites …`.

Software no package manager tracks (`scan_unowned.py`):

- `unowned`: real executables (not symlinks, 0-byte stubs, `*.so*`, `*.debug`, …) in
  `/usr/bin` and `/usr/local/bin` that `pacman -Qqo` does not own. Own copies are traced
  to the tracked file they came from like `~/.local/bin` (`built from` / `copy of`);
  hand-placed scripts are `own`, native binaries are not; all are `loose`.
  `removeCommand` is `sudo rm <path>`.
- Backups `<x>.orig`, `<x>.bak[-N]`, `<x>.broken-<tag>.bak` are skipped while `<x>` still
  exists in either root. Once it is gone the backup is reported under the base name
  `<x>`, and the real location stays visible in the reason tail through `Item.note`
  (`<path>: backup left after <x> was removed`), which survives a curated reason.
- `npm-global` also covers `sudo npm -g` packages in `/usr/lib/node_modules` that
  pacman does not own (reason `… (system npm)`, `sudo npm uninstall -g <pkg>`).
- `app-home`: self-updating installs that keep themselves in
  `~/.config/<name>/app-<version>/` (Discord's Squirrel updater); the highest version
  wins; `removeCommand` is `rm -rf ~/.config/<name>`.
- `user-app` (`scan_userapp.py`): one item per `~/.local/share/<app>/` that holds an executable ELF
  (not `.so`) within three levels; node_modules/.git/cache trees are pruned and only the
  4-byte magic is read. The license is the directory's LICENSE/COPYING file, else `nonfree`
  until `curated.json` says otherwise. Skipped: Steam, flatpak, pipx, uv, Wine/lutris
  prefixes, apps a `~/.local/bin` symlink points into, and kuhy's own code. Special items:
  `gh-copilot`, `android-sdk` (`~/sdk/Android/Sdk`, nonfree "Android SDK License"),
  `PrismLauncher java runtimes` (foss when OpenJDK), one item per
  `Steam/compatibilitytools.d/*` (GE-Proton), `godot export templates`,
  `github actions-runner` and `llama.cpp (llama-server)` (mangatl's vendored copy).

- `toolchain` (`scan_toolchain.py`): one item per toolchain family with every installed
  version in `version` (`~/.rustup/toolchains` -> `rust (rustup)`, `~/.pyenv/versions` ->
  `python (pyenv)` minus virtualenvs, `~/.nvm/versions/node` -> `node (nvm)`,
  `~/sdk/fvm/versions` -> `flutter (fvm)`, `~/sdk/go` -> `go` only when `bin/go` exists);
  the license is the family constant, judged against the LICENSE file the toolchain ships
  when there is one; no `removeCommand`. Global tools are one item each: `.dotnet/tools`
  (LICENSE or nuspec in `.store`), `~/.pub-cache/bin` (LICENSE of the hosted package),
  user gems (`s.licenses` of the gemspec), and `go install`ed tools in ~/sdk/go/bin or
  ~/go/bin, one item per module (`go version -m`, LICENSE from the module cache); anything without a license is `nonfree`.
`docker` (`scan_docker.py`): local Docker images, one item per repository (tags merged
into `version`, `docker rmi <repo>:<tag> ...`). The license is the
`org.opencontainers.image.licenses` label (read with ONE batched `docker image inspect`),
else a built-in table for Docker Hub official images, else `curated.json`. Skipped: tag
`local`, repositories ending `-mcp`, `kuhyx/` namespaces, `<none>`, and bare names that are
neither official images nor carry a source/url label pointing outside kuhyx. No docker or
unreachable daemon gives no items.

Steam apps (offline; the store site is blocked) are licensed
`LicenseRef-Steam-Subscriber-Agreement`, plus `LicenseRef-EULA-<appid>` when Steam's
local `appcache/appinfo.vdf` lists an app-specific EULA, plus the recognised ids of the
install root's LICENSE/COPYING files (Proton: `BSD OFL-1.1`). The reason ends with
`EULA: <name> <url>` and `bundled components: <id>: a, b; …` from a `licenses/` folder;
that tail survives a curated reason. A curated verdict entry may carry a third element,
a license appended to the scanned one (`LicenseRef-Microsoft-Redistributable`).

`.desktop` launchers (`scan_desktop.py`, source `desktop`): the `Exec` target of every
launcher in `~/.local/share/applications`, `/usr/share/applications`,
`/usr/local/share/applications` and the Flatpak export dirs (an earlier directory shadows a
later file of the same name). `env`/`exec`/`VAR=x`, `sh -c '…'` and interpreter prefixes
(`python3 /opt/x/main.py`) are skipped to reach the program. Targets another scanner already
lists are dropped: pacman-owned files, `/usr/bin`, `/usr/local/bin`, `/opt`,
`~/.local/bin`, `~/.local/share/*`, AppImages up to three levels below `$HOME`, Steam,
Flatpak, Wine and Waydroid launchers, URL handlers, and kuhy's own checkouts. What is left is
named by `Name=` (Discord's `Game <id>` stubs by the target's file name), licensed by a LICENSE
beside or above the target, else unknown (curated). A launcher whose target does not exist
is `dangling: true`, reason `launcher without target: <exec path>`, `removeCommand`
`rm '<desktop file>'`; dead launchers owned by a pacman package are left to the pacman item.

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
