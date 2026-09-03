export const PLAN_IDS = ["air_30_days", "air_lifetime"] as const;

export type PlanId = (typeof PLAN_IDS)[number];

export type AccessPlan = {
  id: PlanId;
  name: string;
  priceRub: number;
  compareAtPriceRub?: number;
  discountLabel?: string;
  description: string;
  features: readonly string[];
  cta: string;
  badge?: string;
  featured?: boolean;
};

export const ACCESS_PLANS: readonly AccessPlan[] = [
  {
    id: "air_30_days",
    name: "30 дней",
    priceRub: 990,
    compareAtPriceRub: 1_320,
    discountLabel: "−25% сегодня",
    description: "Полный доступ к AIR на 30 дней.",
    features: ["программа 30 дней", "SOS", "персональный план", "прогресс и достижения"],
    cta: "Выбрать 30 дней",
  },
  {
    id: "air_lifetime",
    name: "Навсегда",
    priceRub: 2_450,
    description: "Один платёж — доступ без ограничения по времени.",
    features: ["всё из AIR", "постоянный доступ", "сохранённый прогресс"],
    cta: "Получить навсегда",
    badge: "Лучший выбор",
    featured: true,
  },
] as const;

export function getAccessPlan(planId: PlanId) {
  return ACCESS_PLANS.find(plan => plan.id === planId)!;
}

export function formatPlanPrice(priceRub: number) {
  return `${new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(priceRub)} ₽`;
}
