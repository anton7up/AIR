import { CircleUserRound, House, LifeBuoy, Route, TrendingUp } from "lucide-react";

export type Tab = "home" | "program" | "sos" | "progress" | "profile";
const items: { id: Tab; label: string; icon: typeof House }[] = [
  { id: "home", label: "Главная", icon: House },
  { id: "program", label: "Программа", icon: Route },
  { id: "sos", label: "SOS", icon: LifeBuoy },
  { id: "progress", label: "Прогресс", icon: TrendingUp },
  { id: "profile", label: "Профиль", icon: CircleUserRound },
];

export function BottomNav({ tab, onChange }: { tab: Tab; onChange: (tab: Tab) => void }) {
  return <nav className="bottom-nav" aria-label="Основная навигация">
    {items.map(({ id, label, icon: Icon }) => <button key={id} className={tab === id ? "active" : ""} onClick={() => onChange(id)}>
      <Icon size={21} strokeWidth={1.8} /><span>{label}</span>
    </button>)}
  </nav>;
}
