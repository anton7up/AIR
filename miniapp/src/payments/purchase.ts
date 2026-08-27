import { getAccessPlan, type PlanId } from "./plans";

export type PaymentAnalyticsEvent = "paywall_view" | "plan_selected" | "purchase_started";

export type PurchaseStartResult = {
  status: "unavailable";
  planId: PlanId;
  message: string;
};

export function emitPaymentEvent(name: PaymentAnalyticsEvent, planId?: PlanId) {
  if (typeof window === "undefined" || typeof CustomEvent === "undefined") return;
  window.dispatchEvent(new CustomEvent("air:payment-event", { detail: { name, planId } }));
}

// YooKassa integration will replace only this function's temporary result.
// It must never grant access or create a subscription on the client.
export function startPurchase(planId: PlanId): PurchaseStartResult {
  getAccessPlan(planId);
  emitPaymentEvent("plan_selected", planId);
  emitPaymentEvent("purchase_started", planId);
  return {
    status: "unavailable",
    planId,
    message: "Оплата подключается. Скоро здесь можно будет безопасно оформить доступ к AIR.",
  };
}
