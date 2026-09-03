import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Dashboard } from "../types";
import { Home } from "./Home";

const dashboard: Dashboard = {
  first_name: "Антон",
  quit_started_at: null,
  elapsed_seconds: 0,
  days: 0,
  hours: 0,
  money_saved: 0,
  units_avoided: 0,
  unit_label: "электронки",
  program_day: 4,
  program_length: 30,
  recovery: { hours: 8, title: "Первый этап", description: "Описание", reached: false },
  today_task: { day: 4, title: "Задание", description: "Описание задания" },
  program_started: true,
  has_active_attempt: false,
  number_of_attempts: 1,
};

describe("home quit attempt state", () => {
  it("shows restart action after a completed attempt", () => {
    const html = renderToStaticMarkup(
      <Home data={dashboard} openProgram={() => undefined} openDesire={() => undefined} startAttempt={async () => undefined} />,
    );
    expect(html).toContain("Начать новый отказ");
    expect(html).toContain("Отсчёт не начат");
  });

  it("shows the active timer immediately after refreshed dashboard data", () => {
    const html = renderToStaticMarkup(
      <Home
        data={{ ...dashboard, has_active_attempt: true, quit_started_at: "2026-09-03T10:00:00Z", elapsed_seconds: 60, number_of_attempts: 2 }}
        openProgram={() => undefined}
        openDesire={() => undefined}
        startAttempt={async () => undefined}
      />,
    );
    expect(html).toContain("0 д");
    expect(html).toContain("01 мин");
    expect(html).not.toContain("Начать новый отказ");
    expect(html).not.toContain("Отсчёт не начат");
  });
});
