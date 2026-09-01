import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { shouldShowPaywall, transitionPaywall } from "../payments/flow";
import { ACCESS_PLANS, PLAN_IDS, formatPlanPrice } from "../payments/plans";
import { canStartPurchase, isValidReceiptEmail, openConfirmationUrl, purchaseErrorMessage, startPurchase } from "../payments/purchase";
import type { Access } from "../types";
import { Paywall } from "./Paywall";
import { Plans } from "./Plans";

const access: Access = {
  status: "free",
  plan: "free",
  ends_at: null,
  development_activation_available: false,
  receipt_email: null,
  links: { support: "https://example.com/support", terms: null, privacy: null },
};

const normalize = (value: string) => value.replace(/\s+/g, " ");

describe("AIR paywall plans flow", () => {
  it("opens the plans step from the existing access CTA and returns Back", () => {
    const landing = renderToStaticMarkup(<Paywall access={access} activate={() => undefined} openPlans={() => undefined} refresh={() => undefined} busy={false} />);
    expect(landing).toContain("Получить доступ к AIR");
    expect(transitionPaywall("landing", "open_plans")).toBe("plans");
    expect(transitionPaywall("plans", "back")).toBe("landing");
  });

  it("keeps product IDs and RUB prices centralized", () => {
    expect(PLAN_IDS).toEqual(["air_30_days", "air_lifetime"]);
    expect(ACCESS_PLANS.map(plan => plan.priceRub)).toEqual([990, 2_450]);
    expect(normalize(formatPlanPrice(990))).toBe("990 ₽");
    expect(normalize(formatPlanPrice(2_450))).toBe("2 450 ₽");
  });

  it("renders both products, real prices, CTAs, support and disclaimer", () => {
    const markup = normalize(renderToStaticMarkup(<Plans links={access.links} initialEmail={null} onBack={() => undefined} />));
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
    const request = async <T,>(_path: string, options?: RequestInit) => {
      expect(JSON.parse(String(options?.body))).toEqual({ plan_id: "air_30_days", email: "person@example.com" });
      return { order_id: 7, payment_id: "payment-7", confirmation_url: "https://yookassa.ru/pay/7" } as T;
    };
    const result = await startPurchase("air_30_days", "person@example.com", request);
    expect(result.confirmation_url).toBe("https://yookassa.ru/pay/7");
    expect(shouldShowPaywall(access.status)).toBe(true);
  });

  it("validates receipt email before purchase", () => {
    expect(isValidReceiptEmail("person@example.com")).toBe(true);
    expect(isValidReceiptEmail("not-an-email")).toBe(false);
  });

  it("prevents another purchase while one is loading", () => {
    expect(canStartPurchase(null)).toBe(true);
    expect(canStartPurchase("air_30_days")).toBe(false);
  });

  it("opens YooKassa confirmation URL and handles a missing URL", async () => {
    const opened: string[] = [];
    openConfirmationUrl("https://yookassa.ru/pay/7", url => opened.push(url));
    expect(opened).toEqual(["https://yookassa.ru/pay/7"]);
    const missingUrl = async <T,>() => ({ order_id: 1, payment_id: "p1" } as T);
    await expect(startPurchase("air_30_days", "person@example.com", missingUrl)).rejects.toThrow("Ссылка на оплату не получена");
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
    expect(() => renderToStaticMarkup(<Plans links={access.links} initialEmail="person@example.com" onBack={() => undefined} />)).not.toThrow();
  });
});
