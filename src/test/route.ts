export type Reply = (() => Promise<Response>) | Response;

/**
 * A plain object rather than a real Response: reading a real body needs
 * macrotasks that fake timers hold back.
 */
export function respond(body: unknown, status = 200): Response {
  return { json: async () => structuredClone(body), ok: status < 400, status } as Response;
}

export function urlOf(input: Parameters<typeof fetch>[0]): string {
  if (typeof input === "string") return input;
  return input instanceof URL ? input.href : input.url;
}

/**
 * Routes `fetch` by URL. Each URL answers its replies in order; the last one
 * repeats. Calling it again swaps the table and restarts the order.
 */
export function route(mock: ReturnType<typeof vi.fn<typeof fetch>>, replies: Record<string, readonly Reply[]>): void {
  const seen = new Map<string, number>();
  mock.mockImplementation(async (input) => {
    const url = urlOf(input);
    const queue = replies[url] ?? [];
    const index = seen.get(url) ?? 0;
    seen.set(url, index + 1);
    const reply = queue[Math.min(index, queue.length - 1)];
    if (reply === undefined) throw new Error(`unexpected fetch ${url}`);
    return typeof reply === "function" ? reply() : reply;
  });
}

export function callsTo(mock: ReturnType<typeof vi.fn<typeof fetch>>, url: string): number {
  return mock.mock.calls.filter(([input]) => urlOf(input) === url).length;
}
