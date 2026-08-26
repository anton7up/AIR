import type { ProgramStep } from "../../types";

export function hasPreparedCardContent(card: NonNullable<ProgramStep["cards"]>[number]): boolean {
  return Boolean(card.why_it_happens?.trim() || card.first_tip?.trim());
}
