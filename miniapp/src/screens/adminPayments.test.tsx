import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { Profile } from "./Profile";
import type { Access, Profile as ProfileType } from "../types";

const profile: ProfileType = {
  first_name: "Admin",
  username: "admin",
  nicotine_type: "cigarettes",
  daily_units: 10,
  unit_label: "сигарет",
  quit_started_at: null,
  registered_at: "2026-01-01T00:00:00Z",
  access_status: "active",
  plan: "air_30_days",
  motivation: null,
  links: { support: null, terms: null, privacy: null },
};
const access: Access = { status: "active", plan: "air_30_days", ends_at: "2026-10-01T00:00:00Z", development_activation_available: false, receipt_email: null, is_admin: false, links: { support: null, terms: null, privacy: null } };

describe("payments admin entry", () => {
  it("is hidden for ordinary users and visible only with the backend admin flag", () => {
    expect(renderToStaticMarkup(<Profile data={profile} access={access} isAdmin={false} onOpenPlans={() => undefined} />)).not.toContain("Админка платежей");
    const adminMarkup = renderToStaticMarkup(<Profile data={profile} access={access} isAdmin onOpenPlans={() => undefined} />);
    expect(adminMarkup).toContain("Админка платежей");
    expect(adminMarkup.indexOf("Изменить данные")).toBeLessThan(adminMarkup.indexOf("Админка платежей"));
    expect(adminMarkup.indexOf("Админка платежей")).toBeLessThan(adminMarkup.indexOf("Поддержка"));
  });

  it("uses protected admin endpoints and provides the required filters", () => {
    const source = readFileSync(new URL("./AdminPayments.tsx", import.meta.url), "utf8");
    expect(source).toContain('adminApi<PaymentsPayload>("/payments")');
    expect(source).toContain('adminApi<{ is_admin: boolean }>("/access")');
    expect(source).toContain('method: "PATCH"');
    expect(source).toContain("Ожидают чек");
    expect(source).toContain("Чек отправлен");
    expect(source).toContain('setAuthState("error")');
    expect(source).toContain("Попробовать снова");
    expect(source).toContain("await load()");
    expect(source).not.toContain("window.location.reload()");
  });

  it("sends the HttpOnly admin cookie on every protected request", () => {
    const source = readFileSync(new URL("../api/client.ts", import.meta.url), "utf8");
    expect(source).toContain('credentials: "include"');
  });
});
