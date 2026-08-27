import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";

const styles = readFileSync(new URL("./styles.css", import.meta.url), "utf8");

describe("custom input CTA styles", () => {
  it("keeps normal CTAs opaque and hides Continue only while the keyboard is open", () => {
    expect(styles).toContain(".step-continue{margin-top:20px;position:static;opacity:1}");
    expect(styles).toContain(".step-continue:disabled{opacity:1}");
    expect(styles).toContain("body.air-keyboard-open .step-continue{display:none}");
    expect(styles).toContain("body.air-keyboard-open .bottom-nav{display:none}");
  });

  it("keeps Save in normal document flow without a translucent overlay", () => {
    expect(styles).toContain(".custom-save-button{position:static;opacity:1");
    expect(styles).not.toContain("air-custom-editor-open .custom-save-button{position:fixed");
    expect(styles).not.toContain("air-custom-editor-open .custom-editor{padding-bottom");
  });
});

describe("plans screen mobile layout", () => {
  it.each([390, 393, 430])("keeps the %ipx viewport within its width", width => {
    expect(width).toBeGreaterThanOrEqual(390);
    expect(styles).toContain(".plans-screen{box-sizing:border-box;width:100%;max-width:520px");
    expect(styles).toContain("overflow-x:clip");
    expect(styles).toContain(".plan-card{position:relative;min-width:0");
  });
});
