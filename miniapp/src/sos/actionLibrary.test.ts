import { describe, expect, it } from "vitest";
import { nextAction, recordAction, REPLACEMENT_ACTIONS, replacementActions, switchActions } from "./actionLibrary";

describe("SOS action libraries", () => {
  it("has at least twenty-five useful replacements for every focus", () => {
    expect(REPLACEMENT_ACTIONS.mouth.length).toBeGreaterThanOrEqual(25);
    expect(REPLACEMENT_ACTIONS.hands.length).toBeGreaterThanOrEqual(25);
    expect(REPLACEMENT_ACTIONS.both.length).toBeGreaterThanOrEqual(25);
  });

  it("adds context actions and excludes the last five while alternatives remain", () => {
    const pool = switchActions("stress");
    expect(pool.length).toBeGreaterThanOrEqual(35);
    expect(pool[0].id).toContain("stress");
    const history = pool.slice(0, 5).reduce((items, action) => recordAction(items, action.id), [] as string[]);
    expect(history).toHaveLength(5);
    expect(history).not.toContain(nextAction(pool, history).id);
  });

  it("walks through the broader pool before repeating and still excludes the latest five", () => {
    const pool = switchActions("boredom");
    let history: string[] = [];
    for (let index = 0; index < 12; index += 1) {
      const next = nextAction(pool, history);
      expect(history.slice(-5)).not.toContain(next.id);
      history = recordAction(history, next.id);
    }
    expect(new Set(history).size).toBe(12);
  });

  it("filters stimulating coffee replacements for coffee and bedtime triggers", () => {
    for (const trigger of ["coffee", "before_sleep"]) {
      for (const focus of ["mouth", "hands", "both"] as const) {
        expect(replacementActions(focus, trigger).map(item => item.label.toLowerCase()).join(" ")).not.toContain("кофе");
      }
    }
  });

  it("prioritizes after-meal replacements and keeps driving replacements safe", () => {
    expect(replacementActions("mouth", "after_meal").slice(0, 5).map(item => item.label).join(" ")).toMatch(/зуб|жвач|вод/);
    const driving = replacementActions("hands", "driving").map(item => item.label.toLowerCase()).join(" ");
    expect(driving).not.toMatch(/телефон|напиши|пройдись|убери со стола/);
    expect(driving).toContain("останов");
  });

  it("keeps driving suggestions screen-safe", () => {
    const driving = switchActions("driving");
    const labels = driving.map(item => item.label.toLowerCase()).join(" ");
    expect(driving.length).toBeGreaterThanOrEqual(20);
    expect(labels).not.toContain("посмотри на экран");
    expect(labels).not.toContain("напиши");
    expect(labels).not.toContain("пройдись");
    expect(labels).toContain("дорог");
  });
});
