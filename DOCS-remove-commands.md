# Remove commands for cached packages

How `Item.removeCommand` and `removeVia` are built for the `*-cache` sources
(see `DOCS-api-contract.md`). The UI only copies them, never runs them.

`maven-cache` `removeCommand` removes the artifact for good, because deleting only the cache lets
the next build download it again (`scan_cache_maven_decl/_catalog/_graph/_remove.py`). Declarations
are read from `build.gradle[.kts]`, `settings.gradle[.kts]`, every `gradle/*.versions.toml` (accessor
names from `create("x") { from(files(...)) }` in the settings file, `libs` by default) and `pom.xml`.
A project *reaches* an artifact when it declares it or declares anything whose cached POM graph
(POM runtime deps of every cached version, `<parent>` POMs, and the dependencies and `available-at`
links of cached Gradle `.module` files, which is what Gradle resolves for Kotlin Multiplatform
artifacts) pulls it in, so an empty `requiredBy` is not proof of staleness. For every reaching project the command first drops each reaching
declaration: `${EDITOR:-vi} +<line> <file>` for lines a sed cannot cut safely (spread over several
lines, opening a `{` block, sharing the line with another dependency, an assignment, any `pom.xml`
block), bottom-up per file; then `sed -i` with exact-content line deletes (`\#^<line>$#d`) for the
build-file line, the catalog entry and every accessor reference (`libs.a.b`, `libs.plugins.x`), and a
substitution dropping the alias from each single-line `[bundles]` array (the bundle stays). After all
projects comes one `rm -rf` of the artifact's dirs in the caches it was found in
(`~/.gradle/caches/modules-2/files-2.1/<group>/<artifact>`, `~/.m2/repository/<group path>/<artifact>`).
An artifact no project reaches is stale: the command is that `rm -rf` alone. Steps are joined by
`; ` so one failing step does not hide the others. `removeVia`: `~/src/a declares it; ~/src/b via
g:x → g:y → <artifact>` (one shortest chain per reaching declaration, at most five per project),
or `stale: no ~/src project reaches it`.

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
  (pub: pinned by the SDK instead, see below), unless it is
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
  graph is the cached pubspecs'. A locked package nothing cached reaches comes from the pubspec's
  `sdk:` dependencies (`flutter`, `flutter_test`), whose pubspecs are not in the cache. An SDK
  package is never removed: that project gets no step, only the cache entry goes, and `removeVia`
  says `pinned by the Flutter SDK; only removable with the app (<projects>)`. Projects that reach
  it through a real parent keep their steps. Re-lock `dart|flutter pub get`. Cache step `rm -rf`
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
