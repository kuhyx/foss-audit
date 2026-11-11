# foss-audit

Scans every program installed on this PC and sorts each one into FOSS / partly
FOSS / non-free (anything with no license grant, firmware blobs included); kuhy's
own code and untracked `~/.local/bin` files are flagged separately. It covers pacman and AUR,
pip, pipx, uv tools, conda, npm, cargo, flatpak, AppImages, `/opt`,
`~/.local/bin`, Steam, Wine and Waydroid. Non-free items get a curated FOSS
alternative, a fit rating, and the effort it would take to build one ourselves.

```bash
./run.sh            # scanner API on 127.0.0.1:5191 + UI on 127.0.0.1:5190, opens the browser
./run.sh --install-launcher   # adds "FOSS audit" to dmenu/rofi
scripts/deploy.sh   # always-on: systemd --user unit foss-audit.service, launcher opens it
```

Everything binds to localhost. The scan is live (about 1.5 s; the **Rescan**
button reruns it).

- **Verdicts:** the packager's license metadata decides first. Anything
  ambiguous is settled by hand in `data/curated.json`.
- **Easy wins view:** lists non-free items whose FOSS replacement is already
  installed, with a copy-to-clipboard removal command. The UI never runs
  commands itself.

API: `DOCS-api-contract.md`. Dev commands: `CLAUDE.md`.
