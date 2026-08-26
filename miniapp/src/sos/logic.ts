export type SupportType = "breathing" | "distraction" | "change_activity" | "replacement_action" | "motivation" | "personal_plan" | "ai_support";
export type BreathingPhaseId = "inhale" | "hold_in" | "exhale" | "hold_out";

export const BREATHING_PHASES: { id: BreathingPhaseId; label: string }[] = [
  { id: "inhale", label: "Вдох" },
  { id: "hold_in", label: "Задержи" },
  { id: "exhale", label: "Выдох" },
  { id: "hold_out", label: "Задержи" },
];
export const BREATHING_PHASE_SECONDS = 4;
export const BREATHING_CYCLES = 4;
export const BREATHING_DURATION_SECONDS = BREATHING_PHASES.length * BREATHING_PHASE_SECONDS * BREATHING_CYCLES;

export function breathingState(elapsedSeconds: number) {
  const safeElapsed = Math.max(0, elapsedSeconds);
  const phaseIndex = Math.floor(safeElapsed / BREATHING_PHASE_SECONDS) % BREATHING_PHASES.length;
  return {
    phase: BREATHING_PHASES[phaseIndex],
    cycle: Math.min(BREATHING_CYCLES, Math.floor(safeElapsed / 16) + 1),
    secondsLeftInPhase: BREATHING_PHASE_SECONDS - (safeElapsed % BREATHING_PHASE_SECONDS),
    finished: safeElapsed >= BREATHING_DURATION_SECONDS,
  };
}

export function breathingCompletion(elapsedSeconds: number, endedEarly: boolean) {
  return {
    cycles: endedEarly ? Math.max(1, Math.ceil(elapsedSeconds / 16)) : BREATHING_CYCLES,
    duration_seconds: endedEarly ? elapsedSeconds : BREATHING_DURATION_SECONDS,
    ended_early: endedEarly,
  };
}

export function recommendedTool(
  analytics: { best_overall_tool: string | null; best_tool_by_trigger: Record<string, string> } | undefined,
  trigger: string | null,
): string | null {
  return (trigger && analytics?.best_tool_by_trigger[trigger]) || analytics?.best_overall_tool || null;
}

export function toolCompletionStep(): "after" {
  return "after";
}

export function actionCompletionStep(): "result" {
  return "result";
}
