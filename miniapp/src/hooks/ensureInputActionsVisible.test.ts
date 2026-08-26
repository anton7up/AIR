import { describe, expect, it } from "vitest";
import {
  calculateActionScrollDelta,
  INPUT_ACTION_SAFE_MARGIN_PX,
  KeyboardAdjustmentGuard,
} from "./ensureInputActionsVisible";

describe("custom input action visibility", () => {
  it("calculates a positive delta when Save is under the visible viewport", () => {
    expect(calculateActionScrollDelta(612, 480)).toBe(148);
  });

  it("does nothing when Save is already visible with a safe margin", () => {
    expect(calculateActionScrollDelta(464, 480)).toBe(0);
    expect(INPUT_ACTION_SAFE_MARGIN_PX).toBeGreaterThanOrEqual(12);
    expect(INPUT_ACTION_SAFE_MARGIN_PX).toBeLessThanOrEqual(20);
  });

  it("allows only one correction while typing in the current focus", () => {
    const guard = new KeyboardAdjustmentGuard();
    let corrections = 0;
    if (guard.canAdjust()) { guard.markAdjusted(); corrections += 1; }
    for (let index = 0; index < 4; index += 1) {
      if (guard.canAdjust()) corrections += 1;
    }
    expect(corrections).toBe(1);
  });

  it("resets after blur so a new focus can adjust again", () => {
    const guard = new KeyboardAdjustmentGuard();
    guard.markAdjusted();
    expect(guard.canAdjust()).toBe(false);
    guard.reset();
    expect(guard.canAdjust()).toBe(true);
  });
});
