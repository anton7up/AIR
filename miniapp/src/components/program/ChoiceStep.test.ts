import { describe, expect, it } from "vitest";
import {
  completeOtherAnswer,
  choiceIsSelected,
  customAnswer,
  mergeDisplayChoices,
  normalizeLegacyCustomState,
  OTHER_SENTINELS,
  sanitizeSelections,
  selectRememberedAnswer,
} from "./customOption";

describe("program Other option semantics", () => {
  it("selects remembered Мама without selecting or opening Other", () => {
    const result = selectRememberedAnswer([], "Мама", false, null);
    expect(result.selected).toBe(customAnswer("Мама"));
    expect(result.editor).toEqual({ isOpen: false, draft: "" });
    expect(sanitizeSelections(result.selected as string)).toEqual([customAnswer("Мама")]);
    expect(OTHER_SENTINELS.has(result.selected as string)).toBe(false);
  });

  it("adds a second custom answer in multi-select and closes Other", () => {
    const result = completeOtherAnswer([customAnswer("Мама")], " Девушка ", true, 3);
    expect(result.selected).toEqual([customAnswer("Мама"), customAnswer("Девушка")]);
    expect(result.editor).toEqual({ isOpen: false, draft: "" });
    expect((result.selected as string[]).some(item => OTHER_SENTINELS.has(item))).toBe(false);
  });

  it("replaces the selected answer with the real custom value in single-select", () => {
    const result = completeOtherAnswer(["money"], "Семья", false, null);
    expect(result.selected).toBe(customAnswer("Семья"));
    expect(result.editor.isOpen).toBe(false);
  });

  it("removes legacy sentinels and restores nested custom text", () => {
    expect(sanitizeSelections(["stress", "other", "custom:"])).toEqual(["stress"]);
    expect(normalizeLegacyCustomState({ main_reason: "custom", main_reason_custom: "Мама" }))
      .toEqual({ main_reason: customAnswer("Мама") });
    expect(normalizeLegacyCustomState({ value: "custom", custom_text: "Мама" }))
      .toBe(customAnswer("Мама"));
  });

  it("renders predefined, remembered and selected custom answers as one deduplicated list", () => {
    const choices = mergeDisplayChoices(
      [{ id: "health", label: "❤️ Здоровье" }, { id: "family", label: "Семья" }],
      ["Мама", " мама. ", "Семья", "Здоровье", "Девушка"],
      [customAnswer("Мама"), customAnswer("Аоаоао")],
    );
    expect(choices.map(option => option.label)).toEqual(["❤️ Здоровье", "Семья", "Мама", "Девушка", "Аоаоао"]);
    expect(choices.filter(option => option.label.toLocaleLowerCase("ru-RU").startsWith("мама"))).toHaveLength(1);
    expect(choiceIsSelected(choices[2], [customAnswer(" мама. ")])).toBe(true);
  });

  it("limits remembered answers while always keeping the current custom selection visible", () => {
    const choices = mergeDisplayChoices([], ["Один", "Два", "Три", "Четыре", "Пять", "Шесть"], [customAnswer("Текущий")]);
    expect(choices.map(option => option.label)).toEqual(["Один", "Два", "Три", "Четыре", "Пять", "Текущий"]);
  });

  it("does not add the same normalized custom answer twice", () => {
    const result = completeOtherAnswer([customAnswer("Мама")], " мама. ", true, 3);
    expect(result.selected).toEqual([customAnswer("Мама")]);
  });
});
