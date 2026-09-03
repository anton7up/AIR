import { describe, expect, it, vi } from "vitest";
import { startOrRestartQuitAttempt } from "./quitAttempt";

describe("quit attempt start flow", () => {
  it("uses the idempotent event request for restart and refreshes after success", async () => {
    const regularRequest = vi.fn();
    const idempotentRequest = vi.fn().mockResolvedValue({ id: 2, status: "active" });
    const refresh = vi.fn().mockResolvedValue(undefined);

    await startOrRestartQuitAttempt(false, refresh, regularRequest, idempotentRequest);

    expect(regularRequest).not.toHaveBeenCalled();
    expect(idempotentRequest).toHaveBeenCalledWith(
      "/quit-attempt/restart",
      { method: "POST" },
    );
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("keeps the first program start on the existing non-event endpoint", async () => {
    const regularRequest = vi.fn().mockResolvedValue({ quit_attempt_id: 1 });
    const idempotentRequest = vi.fn();
    const refresh = vi.fn().mockResolvedValue(undefined);

    await startOrRestartQuitAttempt(true, refresh, regularRequest, idempotentRequest);

    expect(regularRequest).toHaveBeenCalledWith("/program/start", { method: "POST" });
    expect(idempotentRequest).not.toHaveBeenCalled();
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("surfaces an API error and does not refresh stale data", async () => {
    const failure = new Error("Не удалось начать новый отказ");
    const refresh = vi.fn().mockResolvedValue(undefined);

    await expect(startOrRestartQuitAttempt(
      false,
      refresh,
      vi.fn(),
      vi.fn().mockRejectedValue(failure),
    )).rejects.toBe(failure);
    expect(refresh).not.toHaveBeenCalled();
  });
});
