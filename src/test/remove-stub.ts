import type { RemovableItem } from "../lib/schema.ts";

import { respond, urlOf } from "./route.ts";

export type FetchMock = ReturnType<typeof vi.fn<typeof fetch>>;

function idsOf(init: RequestInit | undefined): string[] {
  return (JSON.parse(init?.body as string) as { ids: string[] }).ids;
}

/**
 * Answers `POST /api/remove` from `items` the way the backend does (unknown
 * ids left out) and refuses every other URL. Installed as the global `fetch`;
 * setup.ts unstubs it after each test.
 */
export function stubRemove(items: readonly RemovableItem[]): FetchMock {
  const mock = vi.fn<typeof fetch>((input, init) => {
    const url = urlOf(input);
    if (url !== "/api/remove") return Promise.reject(new Error(`unexpected fetch ${url}`));
    const ids = idsOf(init);
    const reply = Object.fromEntries(
      items
        .filter((item) => ids.includes(item.id))
        .map((item) => [item.id, { removeCommand: item.removeCommand, removeVia: item.removeVia }]),
    );
    return Promise.resolve(respond(reply));
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

/**
 * The id lists posted to /api/remove so far, one entry per request.
 */
export function postedIds(mock: FetchMock): string[][] {
  return mock.mock.calls.map(([, init]) => idsOf(init));
}
