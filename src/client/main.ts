import "../elements/copy-button.ts";
import "../elements/detail-panel.ts";
import "../elements/easy-wins.ts";
import "../elements/error-banner.ts";
import "../elements/filter-bar.ts";
import "../elements/help-overlay.ts";
import "../elements/items-table.ts";
import "../elements/scan-progress.ts";
import "../elements/selection-bar.ts";
import "../elements/summary-view.ts";
import { startKeyboard } from "./keyboard.ts";
import { startRetry } from "./retry.ts";
import { load } from "./scan.ts";
import { startShell } from "./shell.ts";
import { startUrlSync } from "./url-sync.ts";

// Page bootstrap: the shell swaps the prerendered homepage for the loading screen, then the scan fills the store.
startUrlSync();
startShell();
startKeyboard();
startRetry(load);
void load();
