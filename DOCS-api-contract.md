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
| `requiredBy` | string[] | pacman reverse deps; `*-cache` sources: the `~/src/<repo>` projects whose lockfile or build file names it; else `[]` |
| `alternative` | `Alternative` \| null | only set for non-FOSS items with a curated entry |
| `removeCommand` | string \| null | e.g. `sudo pacman -Rns google-chrome`; UI only copies it, never runs it. Every scanner sets it: `null` is a bug (a test enforces it) |
| `removeVia` | string | why the command has its shape, e.g. `~/src/sufler via torch → nvidia-cudnn-cu13`; `""` when plain (UI schema tolerates its absence) |

`Source` = `"pacman" | "aur" | "pip-user" | "pipx" | "uv-tool" | "npm-global" | "cargo" | "flatpak" | "appimage" | "opt" | "local-bin" | "conda" | "steam" | "wine" | "waydroid" | "unowned" | "app-home" | "toolchain" | "desktop" | "docker" | "user-app" | "maven-cache" | "pub-cache" | "npm-cache" | "cargo-cache" | "pip-cache"`

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

Package caches (`cache_common.py` + `scan_cache_<eco>.py`; sources `maven-cache`
(`~/.gradle/caches/modules-2` + `~/.m2`), `pub-cache`, `npm-cache` (pnpm stores + `~/.npm/_cacache`),
`cargo-cache`, `pip-cache`): one item per package (`group:artifact` for Maven), `version` lists every
cached version newest first. The license is read from the package itself (POM and its parents,
Cargo.toml, package.json, METADATA, else its LICENSE file), with a cached registry lookup only when
the cache holds none; a failed lookup stays in the reason. The verdict is the worst over all cached
versions (the note says when versions are licensed differently); a free package whose newest version
has a runtime dependency on a non-free package of the same cache is `foss-partial`
(`depends on non-free <name>`). `requiredBy` is filled from `~/src` lockfiles/build files at most
four levels deep; empty means no project names it (transitive or stale), and the note says so.
`scripts/check_cache_licenses.py` runs them on the real caches and fails while any package's
license is unknown.

`removeCommand` of a `pip-cache`, `npm-cache`, `pub-cache` or `cargo-cache` item is never null and
removes the package for good (`cache_remove.py` + `cache_remove_<eco>.py`). Deleting the cache alone
is not enough while a `~/src` project pulls the package in, since the next build downloads it again.
Projects are the manifests and lockfiles at most four levels under `~/src`, plus workspace members up
to three levels below a lockfile; build output, vendored copies and hidden directories (including
`.claude/worktrees/*` checkouts) are not projects.

- a manifest that declares it gets the ecosystem's remove command, run in that manifest's own
  directory (`(cd ~/src/x/sub && cargo remove --dev foo)`);
- a manifest that reaches it through other dependencies gets every direct parent on such a chain
  removed. The graph is the nearest lockfile's (authoritative for what it lists), and the
  dependencies the cached copies declare fill in the rest, so an item with empty `requiredBy` is
  still transitive when a project reaches it. A manifest's own workspace members and path
  dependencies are never blamed (per manifest: a name linked locally in one repo is a registry
  package in another);
- a lockfile that lists it although nothing declared reaches it is re-locked once per lockfile
  (pub: blamed on the SDK packages instead, whose pubspecs are not in the cache), unless it is
  that project's own package or one of its path dependencies' manifests already removes it
  (`~/src/app lockfile lists x through its local pkg`);
- several projects: every project's step, then the package's own cache entries deleted once. No
  project reaches it: it is stale and only its exact cache entries are deleted.

Steps are subshells joined with `; `, so a failed `cd` never runs a removal elsewhere and one failing
step never hides the others. Paths keep `~` expandable, and cache paths are always exact, never
globs (zsh aborts on a glob that matches nothing). `removeVia` explains the shape:
`~/src/app declares foo`, `~/src/sufler/tts via torch → nvidia-cudnn-cu13`, or `stale: …`, plus a
note on anything else the cache step deletes.

- cargo: `cargo remove <manifest key>` (a renamed dependency's key, not its `package =`) with
  `--dev`, `--build` and `--target <cfg>`; re-lock `cargo update --workspace`; cache step
  `rm -rf` of `~/.cargo/registry/cache/<index>/<name>-<ver>.crate`, `registry/src/<index>/<name>-<ver>`
  and `git/checkouts/<db>/<rev>`.
- pub: `flutter pub remove` when the pubspec depends on the Flutter SDK, else `dart pub remove`, in
  the declaring pubspec's directory (a workspace member's own); pubspec.lock has no edges, so the
  graph is the cached pubspecs'. A locked package nothing cached reaches is blamed on the pubspec's
  `sdk:` dependencies (`flutter`, `flutter_test`); re-lock `dart|flutter pub get`. Cache step `rm -rf`
  of `hosted/<server>/<name>-<ver>`, `hosted-hashes/<server>/<name>-<ver>.sha256` and whole
  `git/<repo>-<sha>` checkouts (the note names the other packages a checkout holds).
- pip: projects are `pyproject.toml` and `requirements*.txt`. `poetry remove [--group g]` for poetry
  projects, else `uv remove` with `--optional <extra>` / `--group <group>` (`--frozen` without a
  uv.lock, so uv only edits pyproject.toml); requirements files and `[build-system] requires` have no
  remove CLI, so an anchored, case- and separator-insensitive `sed -i -E` deletes the line or
  string. Graph: uv.lock / poetry.lock, then the cached Requires-Dist; re-lock `uv lock` /
  `poetry lock`. Cache step: `uv cache clean --cache-dir ~/.cache/uv <name>` for uv's cache, plus
  `rm -rf` of the exact pip `http-v2` body and header files, legacy `http` entries and built
  `wheels/` (`pip cache remove` only ever touches wheels/), and of a whole cached uv environment
  (`archive-v0/<id>`, which `uv cache clean <name>` leaves; uv rebuilds it on demand).
- npm: a pnpm-lock.yaml's `importers` give each workspace project's declarations, removed with
  `pnpm remove` in that project's directory; `packageManagerDependencies` (pnpm fetching itself)
  with `npm pkg delete packageManager`. A package-lock.json's `packages[""]` and workspace entries
  use `npm uninstall` (`-w <path>` from the root); a lockfileVersion 1 lock takes the root's
  declarations from package.json. Graph: snapshots / `node_modules/*` entries, then the cached
  package.json dependencies; re-lock `pnpm install --lockfile-only` / `npm install
  --package-lock-only`. Cache step, `_cacache`: `npm cache clean --cache ~/.npm <key>`, one call per
  tarball key (npm 11 deletes the entry and its content but stops at the first key it cannot
  find); further keys of the same tarball (`pacote:tarball:<spec>` beside the
  `make-fetch-happen:request-cache:<url>` key) lose their `index-v5/<sha256(key)>` bucket instead,
  or they would dangle. pnpm has no per-package store command (`pnpm store prune` is store-wide),
  so: the v3/v10 index JSON (or a git package's `<url-dir>/`), the exact v11 `package_index` rows
  (`sqlite3 <store>/v11/index.db 'DELETE … WHERE key IN (…)'`) and `v11/links/<name>`. Shared
  content blobs stay for `pnpm store prune`; pnpm refetches a package whose index entry is gone.

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
