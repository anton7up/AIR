import { describe, expect, it } from "vitest";
import { actionCompletionStep, BREATHING_PHASES, BREATHING_DURATION_SECONDS, breathingCompletion, breathingState, recommendedTool, toolCompletionStep } from "./logic";

describe("square breathing", () => {
  it("uses four ordered phases and repeats cycles", () => {
    expect(BREATHING_PHASES.map(item => item.id)).toEqual(["inhale", "hold_in", "exhale", "hold_out"]);
    expect(breathingState(0).phase.id).toBe("inhale");
    expect(breathingState(4).phase.id).toBe("hold_in");
    expect(breathingState(8).phase.id).toBe("exhale");
    expect(breathingState(12).phase.id).toBe("hold_out");
    expect(breathingState(16).cycle).toBe(2);
    expect(breathingState(BREATHING_DURATION_SECONDS).finished).toBe(true);
    expect(breathingCompletion(20, true)).toEqual({ cycles: 2, duration_seconds: 20, ended_early: true });
    expect(toolCompletionStep()).toBe("after");
    expect(actionCompletionStep()).toBe("result");
  });
  it("prefers trigger-specific recommendation over overall", () => {
    const analytics = { best_overall_tool: "breathing", best_tool_by_trigger: { stress: "change_activity" } };
    expect(recommendedTool(analytics, "stress")).toBe("change_activity");
    expect(recommendedTool(analytics, "coffee")).toBe("breathing");
  });
});
