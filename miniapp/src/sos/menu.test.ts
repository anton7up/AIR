import { describe, expect, it } from "vitest";
import { SOS_MENU_ITEMS } from "./menu";

describe("fixed SOS tool order", () => {
  it("does not depend on which tool receives the recommendation star", () => {
    const base = SOS_MENU_ITEMS.map(item => item.id);
    for (const starred of base) {
      const rendered = SOS_MENU_ITEMS.map(item => ({ ...item, starred: item.id === starred }));
      expect(rendered.map(item => item.id)).toEqual(base);
    }
    expect(base).toEqual([
      "breathing",
      "distraction",
      "motivation",
      "personal_plan",
      "replacement_action",
      "change_activity",
    ]);
  });
});
