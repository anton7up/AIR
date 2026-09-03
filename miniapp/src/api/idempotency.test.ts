import { describe, expect, it, vi } from "vitest";
import { EventRequestRegistry } from "./idempotency";
import { eventApi } from "./client";

describe("event idempotency keys", () => {
  it("shares one key for double taps and creates a new key for a new action", async () => {
    let sequence = 0;
    const registry = new EventRequestRegistry(() => `key-${++sequence}`);
    let resolve!: (value: number) => void;
    const pending = new Promise<number>(done => { resolve = done; });
    const keys: string[] = [];
    const request = (key: string) => { keys.push(key); return pending; };

    const first = registry.run("lapse", request, () => false);
    const second = registry.run("lapse", request, () => false);
    resolve(1);
    await Promise.all([first, second]);
    await registry.run("lapse", async key => { keys.push(key); return 2; }, () => false);
    expect(keys).toEqual(["key-1", "key-2"]);
  });

  it("reuses the same key after a network failure", async () => {
    let sequence = 0;
    const registry = new EventRequestRegistry(() => `key-${++sequence}`);
    const keys: string[] = [];
    const networkError = new Error("network");
    await expect(registry.run(
      "desire",
      async key => { keys.push(key); throw networkError; },
      error => error === networkError,
    )).rejects.toBe(networkError);
    await registry.run(
      "desire",
      async key => { keys.push(key); return true; },
      error => error === networkError,
    );
    expect(keys).toEqual(["key-1", "key-1"]);
  });

  it("sends an Idempotency-Key header for an event request", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ recorded: true }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ));
    vi.stubGlobal("window", { Telegram: undefined });
    vi.stubGlobal("fetch", fetchMock);

    await eventApi("/nicotine-desire", {
      method: "POST",
      body: JSON.stringify({ intensity: 5 }),
    });

    const options = fetchMock.mock.calls[0][1] as RequestInit;
    const headers = options.headers as Record<string, string>;
    expect(headers["Idempotency-Key"]).toMatch(/^[0-9a-f-]{36}$/i);
    vi.unstubAllGlobals();
  });
});
