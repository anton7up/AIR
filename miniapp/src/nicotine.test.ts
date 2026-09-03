import { describe, expect, it } from "vitest";
import { nicotineTypeLabel } from "./nicotine";

describe("nicotine type labels", () => {
  it("shows the disposable e-cigarette label without falling back", () => {
    expect(nicotineTypeLabel("disposable_e_cigarette"))
      .toBe("Одноразовые электронные сигареты");
  });

  it.each([
    ["cigarettes", "Сигареты"],
    ["heated_tobacco", "IQOS / Glo"],
    ["vape", "Вейп"],
    ["snus", "Снюс"],
    ["hookah", "Кальян"],
  ])("keeps the existing %s label", (type, expected) => {
    expect(nicotineTypeLabel(type)).toBe(expected);
  });

  it("keeps the legacy fallback for an unknown type", () => {
    expect(nicotineTypeLabel("legacy_unknown_type")).toBe("Другой вид никотина");
  });
});
