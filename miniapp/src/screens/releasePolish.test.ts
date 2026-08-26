import { describe, expect, it } from "vitest";
import { achievementClassName } from "../progress/achievements";
import { SOS_MENU_ITEMS } from "../sos/menu";
import { formatProgramLabel, formatProgramText, resolveUserFacingValue } from "../program/labels";

describe("release polish", () => {
  it("does not expose unfinished AI support in SOS menu", () => {
    expect(SOS_MENU_ITEMS.map(item => item.id)).not.toContain("ai_support");
    expect(SOS_MENU_ITEMS.map(item => item.label)).not.toContain("Поговорить с AIR");
  });

  it("gives earned achievements a distinct visual state", () => {
    expect(achievementClassName(true)).toContain("earned");
    expect(achievementClassName(true)).toContain("unlocked");
    expect(achievementClassName(false)).toBe("locked");
  });

  it("never renders known or unknown technical plan identifiers", () => {
    expect(formatProgramLabel("strong_craving")).toBe("Сильное желание");
    expect(formatProgramText("unknown_internal_value")).toBe("Сохранённый вариант");
    expect(formatProgramText("supportTypeValue")).toBe("Сохранённый вариант");
    expect(formatProgramText("Позвоню другу")).toBe("Позвоню другу");
  });

  it("resolves current and legacy custom answer sentinels", () => {
    expect(resolveUserFacingValue("custom")).toBe("Свой вариант");
    expect(resolveUserFacingValue("other_option", "Позвоню другу")).toBe("Позвоню другу");
    expect(resolveUserFacingValue({ value: "custom", custom_text: "Выйду на воздух" })).toBe("Выйду на воздух");
    expect(resolveUserFacingValue({ main_reason: "custom", main_reason_custom: "Хочу свободы" })).toBe("Хочу свободы");
    expect(resolveUserFacingValue("custom:Выпью воды")).toBe("Выпью воды");
    expect(resolveUserFacingValue({ value: "custom", custom_text: "Устал после работы" })).toBe("Устал после работы");
  });
});
