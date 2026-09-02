import { describe, expect, it } from "vitest";
import { EventRequestRegistry } from "./idempotency";

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
});
