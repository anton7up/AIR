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

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...authHeaders(), ...options?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "Ошибка соединения с AIR" }));
    throw new ApiError(response.status, body.detail || "Ошибка AIR");
  }
  return response.json() as Promise<T>;
}

export function api<T>(path: string, options?: RequestInit): Promise<T> {
  return request<T>(`/api/v1/mini-app${path}`, options);
}

export function paymentApi<T>(path: string, options?: RequestInit): Promise<T> {
  return request<T>(`/api/v1/payments${path}`, options);
}
