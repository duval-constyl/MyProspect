import { vi } from "vitest";

export type MockResponse = { status?: number; body?: unknown };
type Handler = MockResponse | MockResponse[] | ((request: RecordedRequest) => MockResponse);

export type RecordedRequest = { method: string; path: string; query: URLSearchParams; body: unknown };

/**
 * Replaces fetch with a fake API. Keys are "METHOD /path" (without /api and query).
 * An array of responses is consumed in order; the last one is then repeated.
 */
export function mockApi(routes: Record<string, Handler>) {
  const requests: RecordedRequest[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    const method = (init?.method ?? "GET").toUpperCase();
    const path = url.pathname.replace(/^\/api/, "");
    const body = typeof init?.body === "string" ? JSON.parse(init.body) : undefined;
    const request = { method, path, query: url.searchParams, body };
    requests.push(request);
    const handler = routes[`${method} ${path}`];
    let response: MockResponse;
    if (handler === undefined) {
      response = { status: 404, body: { detail: `Route simulée absente : ${method} ${path}` } };
    } else if (typeof handler === "function") {
      response = handler(request);
    } else if (Array.isArray(handler)) {
      response = handler.length > 1 ? handler.shift()! : handler[0];
    } else {
      response = handler;
    }
    const status = response.status ?? 200;
    return new Response(status === 204 ? null : JSON.stringify(response.body ?? null), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { requests, fetchMock };
}
