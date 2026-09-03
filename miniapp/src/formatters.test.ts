import { describe, expect, it } from "vitest";
import { formatNicotineUnits } from "./formatters";

describe("formatNicotineUnits", () => {
  it.each([
    [0.25, "0,25"],
    [0.5, "0,5"],
    [0.75, "0,75"],
    [1, "1"],
    [2.5, "2,5"],
  ])("formats %s naturally in Russian", (value, expected) => {
    expect(formatNicotineUnits(value)).toBe(expected);
  });
});
