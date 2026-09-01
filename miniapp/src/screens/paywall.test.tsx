import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { shouldShowPaywall, transitionPaywall } from "../payments/flow";
import { ACCESS_PLANS, PLAN_IDS, formatPlanPrice } from "../payments/plans";
import { canStartPurchase, closeEmailKeyboardOnEnter, isValidReceiptEmail, openExternalCheckout, paymentStatusPhase, purchaseErrorMessage, receiptEmailError, startPurchase } from "../payments/purchase";
import type { Access } from "../types";
import { Paywall } from "./Paywall";
import { PaymentCheckout } from "./PaymentCheckout";
import { ExternalPaymentReturn } from "./PaymentReturn";
import { Plans } from "./Plans";
import { AIR_BOT_USERNAME, AIR_TELEGRAM_URL } from "../telegram";

const access: Access = {
  status: "free",
  plan: "free",
  ends_at: null,
  development_activation_available: false,
  receipt_email: null,
  is_admin: false,
  links: { support: "https://example.com/support", terms: null, privacy: null },
};

const normalize = (value: string) => value.replace(/\s+/g, " ");
const checkoutSource = readFileSync(new URL("./PaymentCheckout.tsx", import.meta.url), "utf8");

describe("AIR paywall plans flow", () => {
  it("opens the plans step from the existing access CTA and returns Back", () => {
    const landing = renderToStaticMarkup(<Paywall access={access} activate={() => undefined} openPlans={() => undefined} refresh={() => undefined} busy={false} />);
    expect(landing).toContain("Получить доступ к AIR");
    expect(transitionPaywall("landing", "open_plans")).toBe("plans");
    expect(transitionPaywall("plans", "back")).toBe("landing");
  });

  it("hides payment admin from regular users and shows it only from backend access", () => {
    const regular = renderToStaticMarkup(<Paywall access={access} activate={() => undefined} openPlans={() => undefined} refresh={() => undefined} busy={false} />);
    const admin = renderToStaticMarkup(<Paywall access={{ ...access, is_admin: true }} activate={() => undefined} openPlans={() => undefined} refresh={() => undefined} busy={false} />);
    expect(regular).not.toContain("Админка платежей");
    expect(admin).toContain("Админка платежей");
  });

  it("keeps product IDs and RUB prices centralized", () => {
    expect(PLAN_IDS).toEqual(["air_30_days", "air_lifetime"]);
    expect(ACCESS_PLANS.map(plan => plan.priceRub)).toEqual([990, 2_450]);
    expect(normalize(formatPlanPrice(990))).toBe("990 ₽");
    expect(normalize(formatPlanPrice(2_450))).toBe("2 450 ₽");
  });

  it("renders both products, real prices, CTAs, support and disclaimer", () => {
    const markup = normalize(renderToStaticMarkup(<Plans links={access.links} initialEmail={null} onBack={() => undefined} onPaymentSucceeded={() => undefined} />));
    expect(markup).toContain("30 дней");
    expect(markup).toContain("990 ₽");
    expect(markup).toContain("Навсегда");
    expect(markup).toContain("2 450 ₽");
    expect(markup).toContain("Выбрать 30 дней");
    expect(markup).toContain("Получить навсегда");
    expect(markup).toContain("Безопасная оплата");
    expect(markup).toContain("Email для получения чека");
    expect(markup).toContain("Поддержка");
    expect(markup).toContain("не заменяет медицинскую помощь");
  });

  it("creates a payment through backend and never grants access on the client", async () => {
    const opened: string[] = [];
    const request = async <T,>(_path: string, options?: RequestInit) => {
      expect(JSON.parse(String(options?.body))).toEqual({ plan_id: "air_30_days", email: "person@example.com" });
      return { order_id: 7, payment_id: "payment-7", confirmation_url: "https://yookassa.ru/pay/7" } as T;
    };
    const result = await startPurchase("air_30_days", "person@example.com", request);
    expect(result.confirmation_url).toBe("https://yookassa.ru/pay/7");
    expect(opened).toEqual([]);
    expect(shouldShowPaywall(access.status)).toBe(true);
  });

  it("validates receipt email before purchase", () => {
    expect(isValidReceiptEmail("person@example.com")).toBe(true);
    expect(isValidReceiptEmail("not-an-email")).toBe(false);
    expect(receiptEmailError("  ")).toBe("Введите email для получения чека");
    expect(receiptEmailError("person@")).toBe("Введите корректный email");
    expect(receiptEmailError("person@example.com")).toBe("");
  });

  it("closes the email keyboard on Enter without starting a purchase", () => {
    let prevented = false;
    let blurred = false;
    closeEmailKeyboardOnEnter({
      key: "Enter",
      preventDefault: () => { prevented = true; },
      currentTarget: { blur: () => { blurred = true; } },
    });
    expect(prevented).toBe(true);
    expect(blurred).toBe(true);
  });

  it("prevents another purchase while one is loading", () => {
    expect(canStartPurchase(null)).toBe(true);
    expect(canStartPurchase("air_30_days")).toBe(false);
  });

  it("opens YooKassa externally through Telegram and falls back without its API", async () => {
    const opened: string[] = [];
    const fallback: string[] = [];
    expect(openExternalCheckout("https://yookassa.ru/pay/7", { openLink: url => opened.push(url) }, url => fallback.push(url))).toBe("telegram");
    expect(opened).toEqual(["https://yookassa.ru/pay/7"]);
    expect(fallback).toEqual([]);
    expect(openExternalCheckout("https://yookassa.ru/pay/8", undefined, url => fallback.push(url))).toBe("fallback");
    expect(fallback).toEqual(["https://yookassa.ru/pay/8"]);
    const missingUrl = async <T,>() => ({ order_id: 1, payment_id: "p1" } as T);
    await expect(startPurchase("air_30_days", "person@example.com", missingUrl)).rejects.toThrow("Ссылка на оплату не получена");
  });

  it("shows a separate direct checkout button and maps only backend statuses", () => {
    const payment = { order_id: 7, payment_id: "p7", confirmation_url: "https://yookassa.ru/pay/7" };
    const markup = normalize(renderToStaticMarkup(<PaymentCheckout payment={payment} onSucceeded={() => undefined} onNewPayment={() => undefined} />));
    expect(markup).toContain("Перейти к оплате");
    expect(markup).not.toContain("Ожидаем оплату");
    expect(paymentStatusPhase({ order_id: 7, status: "pending", access_active: false })).toBe("waiting");
    expect(paymentStatusPhase({ order_id: 7, status: "succeeded", access_active: true })).toBe("succeeded");
    expect(paymentStatusPhase({ order_id: 7, status: "canceled", access_active: false })).toBe("canceled");
    expect(checkoutSource).toContain("window.addEventListener(\"focus\"");
    expect(checkoutSource).toContain("document.addEventListener(\"visibilitychange\"");
    expect(checkoutSource).toContain("AUTO_POLL_DELAYS");
    expect(checkoutSource).not.toContain("setInterval");
  });

  it("renders an unauthenticated external return without an auth error", () => {
    const markup = normalize(renderToStaticMarkup(<ExternalPaymentReturn />));
    expect(markup).toContain("Оплата завершена");
    expect(markup).toContain("Вернитесь в Telegram");
    expect(markup).toContain("Вернуться в AIR");
    expect(AIR_BOT_USERNAME).toBe("airnosmokebot");
    expect(AIR_TELEGRAM_URL).toBe("https://t.me/airnosmokebot");
    expect(markup).toContain('href="https://t.me/airnosmokebot"');
    expect(markup).not.toContain("window.close");
    expect(markup).not.toContain("Открой AIR из Telegram");
  });

  it("keeps backend errors readable", () => {
    expect(purchaseErrorMessage(new Error("ЮKassa временно недоступна"))).toBe("ЮKassa временно недоступна");
    expect(purchaseErrorMessage(null)).toContain("Не удалось открыть оплату");
  });

  it("preserves tester and developer bypass because active access skips paywall", () => {
    expect(shouldShowPaywall("active")).toBe(false);
    expect(shouldShowPaywall("free")).toBe(true);
    expect(shouldShowPaywall("expired")).toBe(true);
  });

  it.each(["light", "dark", "dark-blue"])("renders without errors in %s theme", () => {
    expect(() => renderToStaticMarkup(<Plans links={access.links} initialEmail="person@example.com" onBack={() => undefined} onPaymentSucceeded={() => undefined} />)).not.toThrow();
  });
});
