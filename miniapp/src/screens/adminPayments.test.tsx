import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { Profile } from "./Profile";
import type { Profile as ProfileType } from "../types";

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

describe("payments admin entry", () => {
  it("is hidden for ordinary users and visible only with the backend admin flag", () => {
    expect(renderToStaticMarkup(<Profile data={profile} isAdmin={false} />)).not.toContain("Админка платежей");
    expect(renderToStaticMarkup(<Profile data={profile} isAdmin />)).toContain("Админка платежей");
  });

  it("uses protected admin endpoints and provides the required filters", () => {
    const source = readFileSync(new URL("./AdminPayments.tsx", import.meta.url), "utf8");
    expect(source).toContain('adminApi<PaymentsPayload>("/payments")');
    expect(source).toContain('method: "PATCH"');
    expect(source).toContain("Ожидают чек");
    expect(source).toContain("Чек отправлен");
    expect(source).toContain('setAuthState("error")');
    expect(source).toContain("Попробовать снова");
  });
});
