import { api, eventApi } from "./client";

type Request = <T>(path: string, options?: RequestInit) => Promise<T>;

export async function startOrRestartQuitAttempt(
  firstAttempt: boolean,
  refresh: () => Promise<void>,
  regularRequest: Request = api,
  idempotentRequest: Request = eventApi,
): Promise<void> {
  if (firstAttempt) {
    await regularRequest("/program/start", { method: "POST" });
  } else {
    await idempotentRequest("/quit-attempt/restart", { method: "POST" });
  }
  await refresh();
}
