# UI contract: store, actions, elements

Read side: `src/client/store.ts` (`AppState`), `src/client/selectors.ts`
(memoised derived data). Write side: `src/client/actions.ts`. Elements extend
`StoreElement` (`src/client/store-element.ts`).

## State slices

| slice | meaning |
| --- | --- |
| `scan` | `loading`, `error`, or `ready` (`scan`, `refreshing`, `refreshError`) |
| `progress` | latest `/api/scan/progress` reply or null |
| `url` | `view`, `filter`, `sort`, `selected` (mirrors the query string) |
| `selection` | checked ids and the shift-click anchor (memory only) |
| `helpOpen` | the `?` sheet |
| `dismissedErrorKey` | banner key the user dismissed |

Selectors: `selectItems`, `selectResults` (filtered), `selectWins`,
`selectSelectedItem`, `selectCheckedItems`, `selectTabCounts`,
`selectBannerMessages`.

## Actions

`setView` (push), `setQuery`, `setFilter`, `setSort`, `openItem`,
`closeItem`, `drill(verdicts, sources)` (push), `clickRow(id, order, isShift)`,
`setRowsChecked(ids, isOn)`, `clearSelection`, `openHelp`, `closeHelp`,
`toggleHelp`, `dismissBanner`, `rescan`. Low level: `navigate(patch, {push})`.
Remove commands: `src/client/remove-api.ts` (`withRemove(s)`,
`fetchRemove`) and `src/client/remove.ts` (`watchRemove(ids, onChange)`).

## Rules

- Read state only through the store; write only through actions. No element
  touches `history`, `location`, or another element's DOM.
- Subscribe in `connectedCallback`, unsubscribe in `disconnectedCallback`
  (the base class does both). Compare slices by `===`; never re-run
  `applyFilter`.
- Elements stay in the DOM. Render only while your view is active (summary:
  `summary`; filter-bar, selection-bar, items-table: `table`; easy-wins:
  `wins`; detail-panel: `table` or `wins` with a selected item), otherwise
  clear your DOM. The shell toggles `hidden` on the `.view` wrappers.
- Hosts are `display: contents` (`src/styles/elements.css`). Observe inner
  boxes (`.table-scroll`, `.chart`) with `observeWidth`, never a host.
- Text goes in as text (`html()` in `src/render/dom.ts`), never as HTML.
- Rows carry `tabindex` (0 on the active row, -1 on the others). items-table
  refocuses `.tr.row[data-id=<prev>]` (scrolling the window to it) when
  `url.selected` goes from an id to null; full_flow step 6 asserts it.
- Esc has one owner: `keyboard.ts` (help, then panel, then blur search) and it
  calls `preventDefault`, which also stops a native dialog cancelling. A
  dialog's `cancel` handler calls `preventDefault` and its own close action.
- Register with `define(name, ctor)` (`src/client/store-element.ts`). Use `hasChanged(state, prev, ...sliceGetters)` there to skip unrelated updates. Shared helpers: `html()` and `verdictBadge()` in `src/render/`.
- Stubs live in `src/elements/*.ts` (`update(state, prev)` is the one hook); `watchRemove(ids, cb)` and `withRemove(s)` fetch remove commands.

## DOM ownership

| owner | DOM |
| --- | --- |
| shell (`src/client/shell.ts`, markup in `pages/index.astro`) | `#home`, `#app-msg`, `header.topbar` (`.scan-meta`, `input.search`, Rescan), `nav.tabs > button.tab > .tab-count`, `.view[data-view]` |
| `<summary-view>` | `.summary`, `.tiles .tile .tile-value`, `.chart svg` (via `src/render/source-chart.ts`) |
| `<filter-bar>` | `.filters`, `.chips[aria-label="Verdict"] .chip`, `.result-count strong`, a "Reset" button |
| `<selection-bar>` | `.selection-bar` with `.selection-count` and buttons starting "Copy"; only while ids are checked |
| `<items-table>` | `.table-scroll`, `.th-button`, `.tr.row[data-id]` (`aria-rowindex` = index + 2), `input.check`, `input[aria-label="Select all shown"]`, `.table-empty` |
| `<easy-wins>` | `.wins .win`, `.table-empty` |
| `<detail-panel>` | `.panel`, inside `.body` beside `main.content` |
| `<help-overlay>` | `.scrim > .help` |
| `<error-banner>` | `.banner[role=alert]` |
| `<scan-progress variant="header\|loading">` | `p.scan-live` or `.scan-live-loading` |
| `<copy-button>` (done) | `span.copy > [code.command] + button.btn + span.copy-status`. Attributes `command`, `button-text`, `label`, `show-text="false"`; or set the async `build` property (text made on click). Neither: "No remove command". |
