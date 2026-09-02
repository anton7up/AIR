import { EventRequestRegistry } from "./idempotency";

const API_URL = (
  import.meta.env.DEV
    ? import.meta.env.VITE_API_URL || "http://127.0.0.1:8000"
    : window.location.origin
).replace(/\/$/, "");

function authHeaders(): HeadersInit {
  const initData = window.Telegram?.WebApp.initData;
  if (initData) return { "X-Telegram-Init-Data": initData };
  if (import.meta.env.DEV) {
    const devId = import.meta.env.VITE_DEV_TELEGRAM_ID;
    return devId ? { "X-Dev-Telegram-Id": devId } : {};
  }
  return {};
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

class NetworkError extends Error {}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...options,
      headers: { "Content-Type": "application/json", ...authHeaders(), ...options?.headers },
    });
  } catch {
    throw new NetworkError("Ошибка сети: не удалось связаться с AIR");
  }
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new ApiError(response.status, "AIR вернул некорректный ответ");
  }
  if (!response.ok) {
    const detail = typeof body === "object" && body !== null && "detail" in body
      ? String(body.detail)
      : `Ошибка AIR (${response.status})`;
    throw new ApiError(response.status, detail);
  }
  return body as T;
}

export function api<T>(path: string, options?: RequestInit): Promise<T> {
  return request<T>(`/api/v1/mini-app${path}`, options);
}

const eventRequests = new EventRequestRegistry(() => crypto.randomUUID());

function eventFingerprint(path: string, options?: RequestInit): string {
  return `${options?.method ?? "POST"}:${path}:${String(options?.body ?? "")}`;
}

export function eventApi<T>(path: string, options?: RequestInit): Promise<T> {
  const fingerprint = eventFingerprint(path, options);
  return eventRequests.run(
    fingerprint,
    key => api<T>(path, {
      ...options,
      headers: { ...options?.headers, "Idempotency-Key": key },
    }),
    error => error instanceof NetworkError,
  );
}

export function paymentApi<T>(path: string, options?: RequestInit): Promise<T> {
  return request<T>(`/api/v1/payments${path}`, options);
}

export function adminApi<T>(path: string, options?: RequestInit): Promise<T> {
  return request<T>(`/api/v1/admin${path}`, {
    ...options,
    credentials: "include",
  });
}
