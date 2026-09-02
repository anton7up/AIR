import type { Access } from "./types";

const DAY_MS = 24 * 60 * 60 * 1000;

function pluralDays(value: number): string {
  const mod100 = value % 100;
  const mod10 = value % 10;
  if (mod100 >= 11 && mod100 <= 14) return "дней";
  if (mod10 === 1) return "день";
  if (mod10 >= 2 && mod10 <= 4) return "дня";
  return "дней";
}

export type AccessPresentation = { active: boolean; title: string; expiresLabel: string | null; remainingLabel: string | null; actionLabel: string | null; virtual: boolean };

export function accessPresentation(access: Access, now = new Date()): AccessPresentation {
  const virtual = ["developer", "tester", "development"].includes(access.plan);
  if (virtual && access.status === "active") return { active: true, title: "Доступ активен", expiresLabel: null, remainingLabel: null, actionLabel: null, virtual: true };
  if (access.plan === "air_lifetime" && access.status === "active") return { active: true, title: "Навсегда", expiresLabel: null, remainingLabel: null, actionLabel: null, virtual: false };
  const expiresAt = access.ends_at ? new Date(access.ends_at) : null;
  const validDate = expiresAt !== null && !Number.isNaN(expiresAt.getTime());
  const timeLeft = validDate ? expiresAt.getTime() - now.getTime() : 0;
  if (access.plan === "air_30_days" && access.status === "active" && validDate && timeLeft > 0) {
    const days = Math.max(0, Math.ceil(timeLeft / DAY_MS));
    return { active: true, title: "30 дней", expiresLabel: expiresAt.toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" }), remainingLabel: `${days} ${pluralDays(days)}`, actionLabel: "Продлить доступ", virtual: false };
  }
  return { active: false, title: "Нет активного доступа", expiresLabel: null, remainingLabel: null, actionLabel: "Выбрать тариф", virtual: false };
}
