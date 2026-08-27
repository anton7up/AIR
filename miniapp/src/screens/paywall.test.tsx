import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { shouldShowPaywall, transitionPaywall } from "../payments/flow";
import { ACCESS_PLANS, PLAN_IDS, formatPlanPrice } from "../payments/plans";
import { startPurchase } from "../payments/purchase";
import type { Access } from "../types";
import { Paywall } from "./Paywall";
import { Plans } from "./Plans";

const access: Access = {
  status: "free",
  plan: "free",
  ends_at: null,
  development_activation_available: false,
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
    expect(ACCESS_PLANS.map(plan => plan.priceRub)).toEqual([1_000, 2_500]);
    expect(normalize(formatPlanPrice(1_000))).toBe("1 000 ₽");
    expect(normalize(formatPlanPrice(2_500))).toBe("2 500 ₽");
  });

  it("renders both products, real prices, CTAs, support and disclaimer", () => {
    const markup = normalize(renderToStaticMarkup(<Plans links={access.links} onBack={() => undefined} />));
    expect(markup).toContain("30 дней");
    expect(markup).toContain("1 000 ₽");
    expect(markup).toContain("Навсегда");
    expect(markup).toContain("2 500 ₽");
    expect(markup).toContain("Выбрать 30 дней");
    expect(markup).toContain("Получить навсегда");
    expect(markup).toContain("Безопасная оплата");
    expect(markup).toContain("Поддержка");
    expect(markup).toContain("не заменяет медицинскую помощь");
  });

  it("does not grant ordinary-user access when a tariff is tapped", () => {
    const result = startPurchase("air_30_days");
    expect(result).toEqual(expect.objectContaining({ status: "unavailable", planId: "air_30_days" }));
    expect(shouldShowPaywall(access.status)).toBe(true);
  });

  it("preserves tester and developer bypass because active access skips paywall", () => {
    expect(shouldShowPaywall("active")).toBe(false);
    expect(shouldShowPaywall("free")).toBe(true);
    expect(shouldShowPaywall("expired")).toBe(true);
  });

  it.each(["light", "dark", "dark-blue"])("renders without errors in %s theme", () => {
    expect(() => renderToStaticMarkup(<Plans links={access.links} onBack={() => undefined} />)).not.toThrow();
  });
});
