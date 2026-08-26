import { describe, expect, it } from "vitest";
import { calculateKeyboardViewport, MOBILE_INPUT_FONT_SIZE } from "./useKeyboardAwareViewport";

describe("keyboard-aware viewport", () => {
  it("uses the visual viewport while a mobile keyboard is open", () => {
    expect(calculateKeyboardViewport(844, 480, 12, true)).toEqual({
      height: 480,
      offsetTop: 12,
      focused: true,
      keyboardOpen: true,
    });
  });

  it("does not report a keyboard after blur or a small viewport resize", () => {
    expect(calculateKeyboardViewport(844, 480, 0, false).keyboardOpen).toBe(false);
    expect(calculateKeyboardViewport(844, 780, 0, true).keyboardOpen).toBe(false);
  });

  it("restores the full layout after a focused field is blurred", () => {
    const focused = calculateKeyboardViewport(844, 480, 0, true);
    const blurred = calculateKeyboardViewport(844, 844, 0, false);
    expect(focused.height).toBe(480);
    expect(focused.keyboardOpen).toBe(true);
    expect(blurred).toMatchObject({ height: 844, focused: false, keyboardOpen: false });
  });

  it("keeps mobile input text large enough to prevent iOS zoom", () => {
    expect(MOBILE_INPUT_FONT_SIZE).toBeGreaterThanOrEqual(16);
  });
});
