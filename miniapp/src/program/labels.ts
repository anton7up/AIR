const LABELS: Record<string, string> = {
  motivation: "Мотивация", both: "Руки и рот", water: "Выпить воды", object: "Взять предмет в руки",
  stress: "Стресс", coffee: "Кофе", after_meal: "После еды", work_study: "Работа / учёба",
  social: "Компания", alcohol: "Алкоголь / вечеринка", before_sleep: "Перед сном", boredom: "Скука",
  strong_craving: "Сильное желание", lapse: "После эпизода", general: "Общий план",
  personal_plan: "Мой план", breathing: "Спокойное дыхание", distraction: "Поиграть",
  change_activity: "Переключиться", replacement_action: "Занять рот / руки", mouth: "Рот", hands: "Руки",
  switch: "Переключиться", action: "Действие", trigger: "Триггер", saved_actions: "Сохранённые действия",
};

const CUSTOM_SENTINELS = new Set(["custom", "other", "user_defined", "own", "other_option", "custom_value", "__other__"]);
const CUSTOM_TEXT_KEYS = ["custom_text", "custom_value", "user_text", "other_text", "text"];

function customText(record: Record<string, unknown>): string | undefined {
  for (const key of CUSTOM_TEXT_KEYS) {
    const candidate = record[key];
    if (typeof candidate === "string" && candidate.trim() && !CUSTOM_SENTINELS.has(candidate.trim().toLowerCase())) return candidate.trim();
  }
  for (const [key, candidate] of Object.entries(record)) {
    if ((key.endsWith("_custom") || key.endsWith("_custom_text")) && typeof candidate === "string" && candidate.trim()) return candidate.trim();
  }
  return undefined;
}

export function resolveUserFacingValue(value: unknown, explicitCustomText?: string): string {
  const preferred = explicitCustomText?.trim();
  if (Array.isArray(value)) return value.map(item => resolveUserFacingValue(item)).filter(Boolean).join(" → ") || "Не указано";
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    const ownText = customText(record);
    if ("value" in record) return resolveUserFacingValue(record.value, ownText);
    const primaryKey = Object.keys(record).find(key => !CUSTOM_TEXT_KEYS.includes(key) && !key.endsWith("_custom") && !key.endsWith("_custom_text"));
    if (primaryKey && CUSTOM_SENTINELS.has(String(record[primaryKey]).trim().toLowerCase())) return ownText || "Свой вариант";
    return Object.entries(record)
      .filter(([key, item]) => item != null && item !== "" && !CUSTOM_TEXT_KEYS.includes(key) && !key.endsWith("_custom") && !key.endsWith("_custom_text"))
      .map(([key, item]) => `${formatProgramLabel(key)}: ${resolveUserFacingValue(item, ownText)}`)
      .join(" · ") || ownText || "Не указано";
  }
  if (value == null) return "Не указано";
  const raw = String(value);
  if (raw.startsWith("custom:")) return raw.slice("custom:".length).trim() || preferred || "Свой вариант";
  const cleaned = raw.trim();
  if (CUSTOM_SENTINELS.has(cleaned.toLowerCase())) return preferred || "Свой вариант";
  if (LABELS[cleaned]) return LABELS[cleaned];
  if (!cleaned) return "Не указано";
  if (/^[A-Za-z][A-Za-z0-9_]*$/.test(cleaned) || /[a-z][A-Z]/.test(cleaned)) return "Сохранённый вариант";
  return cleaned;
}

export function formatProgramLabel(value: string): string {
  return resolveUserFacingValue(value);
}

export const formatProgramText = resolveUserFacingValue;
