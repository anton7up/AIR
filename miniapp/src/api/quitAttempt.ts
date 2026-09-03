import { api, eventApi } from "./client";

type Request = <T>(path: string, options?: RequestInit) => Promise<T>;

export async function startOrRestartQuitAttempt(
  firstAttempt: boolean,
  refresh: () => Promise<void>,
  regularRequest: Request = api,
  idempotentRequest: Request = eventApi,
): Promise<void> {
  const request = firstAttempt ? regularRequest : idempotentRequest;
  const path = firstAttempt ? "/program/start" : "/quit-attempt/restart";
  await request(path, { method: "POST" });
  await refresh();
}
