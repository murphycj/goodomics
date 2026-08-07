import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AUTH_INVALID_EVENT, ACCESS_TOKEN_KEY } from "./auth";
import { apiClient } from "./client";
import { ApiError, toApiError } from "./errors";
import { getInsight } from "./generated/sdk.gen";
import { apiFetch, requireOk } from "./transport";

class MemoryStorage implements Storage {
  private values = new Map<string, string>();
  get length() { return this.values.size; }
  clear() { this.values.clear(); }
  getItem(key: string) { return this.values.get(key) ?? null; }
  key(index: number) { return [...this.values.keys()][index] ?? null; }
  removeItem(key: string) { this.values.delete(key); }
  setItem(key: string, value: string) { this.values.set(key, value); }
}

describe("shared API client", () => {
  const localStorage = new MemoryStorage();
  const dispatchEvent = vi.fn();

  beforeEach(() => {
    localStorage.clear();
    dispatchEvent.mockClear();
    vi.stubGlobal("window", { dispatchEvent, localStorage });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("injects bearer auth into same-origin generated requests", async () => {
    localStorage.setItem(ACCESS_TOKEN_KEY, "test-token");
    const fetch = vi.fn(async (input: RequestInfo | URL) => {
      const request = input instanceof Request ? input : new Request(input);
      expect(request.headers.get("Authorization")).toBe("Bearer test-token");
      return Response.json({ ok: true });
    });
    apiClient.setConfig({ baseUrl: "http://goodomics.test", fetch });

    await apiClient.get({ url: "/api/v1/test", throwOnError: true });
    expect(fetch).toHaveBeenCalledOnce();
  });

  it("clears authenticated 401 responses and emits the invalid-session event", async () => {
    localStorage.setItem(ACCESS_TOKEN_KEY, "expired-token");
    apiClient.setConfig({
      baseUrl: "http://goodomics.test",
      fetch: async () => Response.json({ detail: "Expired" }, { status: 401 }),
    });

    await expect(
      apiClient.get({ url: "/api/v1/test", throwOnError: true }),
    ).rejects.toMatchObject({ message: "Expired", status: 401 });
    expect(localStorage.getItem(ACCESS_TOKEN_KEY)).toBeNull();
    expect(dispatchEvent).toHaveBeenCalledWith(expect.any(Event));
    expect((dispatchEvent.mock.calls[0]?.[0] as Event).type).toBe(
      AUTH_INVALID_EVENT,
    );
  });

  it("validates generated SDK responses before returning them", async () => {
    apiClient.setConfig({
      baseUrl: "http://goodomics.test",
      fetch: async () => Response.json({ insight_id: "missing-required-fields" }),
    });

    const request = getInsight({
      client: apiClient,
      path: { insight_ref: "missing-required-fields" },
      throwOnError: true,
    });

    await expect(request).rejects.toBeInstanceOf(ApiError);
    await expect(request).rejects.toMatchObject({
      cause: { name: "ZodError" },
      message: expect.stringContaining("Invalid API response"),
    });
  });

  it("reuses authentication, invalidation, and errors for manual transports", async () => {
    localStorage.setItem(ACCESS_TOKEN_KEY, "manual-token");
    const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = new Request(input, init);
      expect(request.headers.get("Authorization")).toBe("Bearer manual-token");
      return Response.json({ detail: "Expired manual request" }, { status: 401 });
    });
    vi.stubGlobal("fetch", fetch);

    const response = await apiFetch("http://goodomics.test/download");
    await expect(requireOk(response)).rejects.toMatchObject({
      message: "Expired manual request",
      status: 401,
    });
    expect(localStorage.getItem(ACCESS_TOKEN_KEY)).toBeNull();
    expect(dispatchEvent).toHaveBeenCalledWith(expect.any(Event));
  });
});

describe("API error normalization", () => {
  it("handles FastAPI string details", () => {
    expect(toApiError({ detail: "Not found" }, new Response(null, { status: 404 })))
      .toMatchObject({ message: "Not found", status: 404 });
  });

  it("handles FastAPI validation details", () => {
    const error = toApiError({
      detail: [{ type: "missing", loc: ["body", "name"], msg: "Field required", input: null }],
    });
    expect(error).toBeInstanceOf(ApiError);
    expect(error.message).toContain("body.name: Field required");
  });
});
