export const NICOTINE_TYPE_LABELS: Readonly<Record<string, string>> = {
  cigarettes: "Сигареты",
  heated_tobacco: "IQOS / Glo",
  disposable_e_cigarette: "Одноразовые электронные сигареты",
  vape: "Вейп",
  snus: "Снюс",
  hookah: "Кальян",
};

export function nicotineTypeLabel(type: string): string {
  return NICOTINE_TYPE_LABELS[type] ?? "Другой вид никотина";
}
