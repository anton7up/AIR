import { paymentApi } from "../api/client";
import { getAccessPlan, type PlanId } from "./plans";

export type PaymentAnalyticsEvent = "paywall_view" | "plan_selected" | "purchase_started";

export type PurchaseStartResult = {
  order_id: number;
  payment_id: string;
  confirmation_url: string;
};

export type PaymentOrderStatus = {
  order_id: number;
  status: "pending" | "succeeded" | "canceled";
  access_active: boolean;
};

export type PaymentPhase = "ready" | "waiting" | "succeeded" | "canceled";

export function paymentStatusPhase(status: PaymentOrderStatus): PaymentPhase {
  if (status.status === "succeeded") return "succeeded";
  if (status.status === "canceled") return "canceled";
  return "waiting";
}

type ExternalLinkWebApp = { openLink?(url: string): void };

type PaymentRequest = <T>(path: string, options?: RequestInit) => Promise<T>;

export function emitPaymentEvent(name: PaymentAnalyticsEvent, planId?: PlanId) {
  if (typeof window === "undefined" || typeof CustomEvent === "undefined") return;
  window.dispatchEvent(new CustomEvent("air:payment-event", { detail: { name, planId } }));
}

export function isValidReceiptEmail(email: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());
}

export function receiptEmailError(email: string) {
  if (!email.trim()) return "Введите email для получения чека";
  if (!isValidReceiptEmail(email)) return "Введите корректный email";
  return "";
}

export function closeEmailKeyboardOnEnter(event: {
  key: string;
  preventDefault(): void;
  currentTarget: { blur(): void };
}) {
  if (event.key !== "Enter") return;
  event.preventDefault();
  event.currentTarget.blur();
}

export async function startPurchase(
  planId: PlanId,
  email: string,
  request: PaymentRequest = paymentApi,
): Promise<PurchaseStartResult> {
  getAccessPlan(planId);
  emitPaymentEvent("plan_selected", planId);
  emitPaymentEvent("purchase_started", planId);
  const result = await request<PurchaseStartResult>("/create", {
    method: "POST",
    body: JSON.stringify({ plan_id: planId, email: email.trim() }),
  });
  if (!result.confirmation_url) throw new Error("Ссылка на оплату не получена. Попробуй ещё раз.");
  return result;
}

export function canStartPurchase(busyPlanId: PlanId | null) {
  return busyPlanId === null;
}

export function purchaseErrorMessage(error: unknown) {
  return error instanceof Error && error.message
    ? error.message
    : "Не удалось открыть оплату. Попробуй ещё раз.";
}

export function openExternalCheckout(
  url: string,
  webApp: ExternalLinkWebApp | undefined = typeof window === "undefined" ? undefined : window.Telegram?.WebApp,
  fallback: (target: string) => void = target => {
    if (typeof window !== "undefined") window.location.assign(target);
  },
) {
  if (webApp?.openLink) {
    webApp.openLink(url);
    return "telegram" as const;
  }
  fallback(url);
  return "fallback" as const;
}
