export const CUSTOM_PREFIX = "custom:";
export const OTHER_SENTINELS = new Set(["custom", "other", "__other__", "user_defined", "own", "other_option", "custom_value"]);
export type OtherEditorState = { isOpen: boolean; draft: string };
export const CLOSED_OTHER_EDITOR: OtherEditorState = { isOpen: false, draft: "" };

export function customAnswer(text: string): string {
  return `${CUSTOM_PREFIX}${text.trim()}`;
}

export function customAnswerText(value: string): string | null {
  if (!value.startsWith(CUSTOM_PREFIX)) return null;
  return value.slice(CUSTOM_PREFIX.length).trim() || null;
}

export function answerDisplayKey(value: string): string {
  return value.trim().replace(/^[^\p{L}\p{N}]+/u, "").replace(/\s+/g, " ").toLocaleLowerCase("ru-RU").replace(/[\s.!?…,:;]+$/g, "").trim();
}

function sameCustomAnswer(left: string, right: string): boolean {
  const leftText = customAnswerText(left);
  const rightText = customAnswerText(right);
  return leftText !== null && rightText !== null && answerDisplayKey(leftText) === answerDisplayKey(rightText);
}

export type DisplayChoice = { id: string; label: string };

/** Combines configured, remembered and selected custom answers into one visual list. */
export function mergeDisplayChoices(
  options: DisplayChoice[],
  remembered: string[],
  selected: string[],
  rememberedLimit = 5,
): DisplayChoice[] {
  const result: DisplayChoice[] = [];
  const seen = new Set<string>();
  const append = (option: DisplayChoice) => {
    const key = answerDisplayKey(option.label);
    if (!key || seen.has(key)) return;
    seen.add(key);
    result.push(option);
  };
  options.forEach(append);
  remembered.slice(0, rememberedLimit).forEach(text => append({ id: customAnswer(text), label: text.trim() }));
  selected.map(customAnswerText).filter((text): text is string => Boolean(text)).forEach(text => append({ id: customAnswer(text), label: text }));
  return result;
}

export function choiceIsSelected(option: DisplayChoice, selected: string[]): boolean {
  if (selected.includes(option.id)) return true;
  const key = answerDisplayKey(option.label);
  return selected.some(value => {
    const text = customAnswerText(value);
    return text !== null && answerDisplayKey(text) === key;
  });
}

export function removeChoiceSelection(option: DisplayChoice, selected: string[]): string[] {
  const key = answerDisplayKey(option.label);
  return selected.filter(value => {
    if (value === option.id) return false;
    const text = customAnswerText(value);
    return text === null || answerDisplayKey(text) !== key;
  });
}

export function sanitizeSelections(value: string | string[] | null): string[] {
  const values = Array.isArray(value) ? value : value ? [value] : [];
  return values.filter(item => !OTHER_SENTINELS.has(item.trim().toLowerCase()) && !(item.startsWith(CUSTOM_PREFIX) && !customAnswerText(item)));
}

export function normalizeLegacyCustomState(value: unknown): unknown {
  if (typeof value === "string") return OTHER_SENTINELS.has(value.trim().toLowerCase()) ? null : value;
  if (Array.isArray(value)) return value.map(normalizeLegacyCustomState).filter(item => item !== null);
  if (!value || typeof value !== "object") return value;
  const record = value as Record<string, unknown>;
  if (typeof record.value === "string" && OTHER_SENTINELS.has(record.value.trim().toLowerCase())) {
    const text = typeof record.custom_text === "string" ? record.custom_text.trim() : "";
    return text ? customAnswer(text) : null;
  }
  const normalized: Record<string, unknown> = {};
  for (const [key, item] of Object.entries(record)) {
    if (key.endsWith("_custom") || key.endsWith("_custom_text") || key === "custom_text") continue;
    if (typeof item === "string" && OTHER_SENTINELS.has(item.trim().toLowerCase())) {
      const companion = record[`${key}_custom`] ?? record[`${key}_custom_text`];
      if (typeof companion === "string" && companion.trim()) normalized[key] = customAnswer(companion);
      continue;
    }
    normalized[key] = normalizeLegacyCustomState(item);
  }
  return normalized;
}

export function toggleRememberedSelection(selected: string[], text: string, multiple: boolean, max: number | null): string | string[] {
  const answer = customAnswer(text);
  if (!multiple) return answer;
  if (selected.some(item => sameCustomAnswer(item, answer))) return selected.filter(item => !sameCustomAnswer(item, answer));
  if (max && selected.length >= max) return selected;
  return [...selected, answer];
}

export function saveCustomSelection(selected: string[], text: string, multiple: boolean, max: number | null): string | string[] {
  const answer = customAnswer(text);
  if (!multiple) return answer;
  if (!customAnswerText(answer) || selected.some(item => sameCustomAnswer(item, answer))) return selected;
  if (max && selected.length >= max) return selected;
  return [...selected, answer];
}

export function selectRememberedAnswer(selected: string[], text: string, multiple: boolean, max: number | null) {
  return { selected: toggleRememberedSelection(selected, text, multiple, max), editor: CLOSED_OTHER_EDITOR };
}

export function completeOtherAnswer(selected: string[], text: string, multiple: boolean, max: number | null) {
  return { selected: saveCustomSelection(selected, text, multiple, max), editor: CLOSED_OTHER_EDITOR };
}
