import { describe, expect, it } from "vitest";
import { hasPreparedCardContent } from "./personalizedCards";

describe("personalized program cards", () => {
  it("keeps prepared cards full and custom cards compact", () => {
    expect(hasPreparedCardContent({
      id: "driving",
      title: "🚗 За рулём / в дороге",
      why_it_happens: "Подготовленное объяснение",
      first_tip: "Подготовленное действие",
    })).toBe(true);
    expect(hasPreparedCardContent({
      id: "custom:После разговора с мамой",
      title: "После разговора с мамой",
    })).toBe(false);
  });
});
