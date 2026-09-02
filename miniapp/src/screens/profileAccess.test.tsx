import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Access, Profile as ProfileType } from "../types";
import { accessPresentation } from "../profileAccess";
import { Profile } from "./Profile";

const baseAccess: Access = {
  status: "active", plan: "air_30_days", ends_at: "2026-09-12T12:00:00Z",
  development_activation_available: false, receipt_email: "person@example.com", is_admin: false,
  links: { support: null, terms: null, privacy: null },
};
const profile: ProfileType = {
  first_name: "Антон", username: "anton", nicotine_type: "cigarettes", daily_units: 10,
  unit_label: "сигарет", quit_started_at: null, registered_at: "2026-01-01T00:00:00Z",
  access_status: "active", plan: "air_30_days", motivation: null,
  links: { support: null, terms: null, privacy: null },
};

describe("profile access", () => {
  it("keeps functional items before legal links", () => {
    const html = renderToStaticMarkup(<Profile data={profile} access={baseAccess} isAdmin={false} onOpenPlans={() => undefined} />);
    expect(html.indexOf("Доступ к AIR")).toBeLessThan(html.indexOf("Изменить данные"));
    expect(html.indexOf("Изменить данные")).toBeLessThan(html.indexOf("Поддержка"));
    expect(html.indexOf("Поддержка")).toBeLessThan(html.indexOf("Юридическая информация"));
    expect(html).not.toContain("Управление доступом");
    expect(html).not.toContain("Условия использования");
    expect(html).not.toContain("Прогресс");
    expect(html).not.toContain("Достижения");
  });

  it("shows real 30-day expiry and a localized nonnegative remainder", () => {
    const details = accessPresentation(baseAccess, new Date("2026-09-02T12:00:00Z"));
    expect(details).toMatchObject({ active: true, title: "30 дней", remainingLabel: "10 дней", actionLabel: "Продлить доступ" });
    expect(details.expiresLabel).toContain("сентября 2026");
    const html = renderToStaticMarkup(<Profile data={profile} access={baseAccess} isAdmin={false} onOpenPlans={() => undefined} />);
    expect(html).toContain("Доступ активен до");
    expect(html).toContain("Продлить доступ");
  });

  it("treats a past end date as inactive even with a stale active status", () => {
    expect(accessPresentation({ ...baseAccess, ends_at: "2026-09-01T00:00:00Z" }, new Date("2026-09-02T00:00:00Z"))).toMatchObject({ active: false, title: "Нет активного доступа", actionLabel: "Выбрать тариф" });
  });

  it("uses correct Russian day forms", () => {
    const now = new Date("2026-09-02T12:00:00Z");
    for (const [days, label] of [[1, "1 день"], [2, "2 дня"], [5, "5 дней"], [21, "21 день"], [22, "22 дня"], [25, "25 дней"]] as const) {
      const endsAt = new Date(now.getTime() + days * 24 * 60 * 60 * 1000).toISOString();
      expect(accessPresentation({ ...baseAccess, ends_at: endsAt }, now).remainingLabel).toBe(label);
    }
  });

  it("does not invent expiry for lifetime, developer or tester access", () => {
    expect(accessPresentation({ ...baseAccess, plan: "air_lifetime", ends_at: null })).toMatchObject({ title: "Навсегда", actionLabel: null, remainingLabel: null });
    for (const plan of ["developer", "tester"]) {
      expect(accessPresentation({ ...baseAccess, plan, ends_at: null })).toMatchObject({ title: "Доступ активен", virtual: true, actionLabel: null });
    }
  });

  it("offers existing plans for inactive access", () => {
    const html = renderToStaticMarkup(<Profile data={profile} access={{ ...baseAccess, status: "expired" }} isAdmin={false} onOpenPlans={() => undefined} />);
    expect(html).toContain("Сейчас у тебя нет активного доступа");
    expect(html).toContain("Выбрать тариф");
  });

  it("keeps legal routes grouped behind one Profile item", () => {
    const source = String.raw`${Profile}`;
    expect(source).toContain("Юридическая информация");
  });
});
