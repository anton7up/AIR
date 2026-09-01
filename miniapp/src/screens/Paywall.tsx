import { Activity, Award, ChartNoAxesCombined, Check, ClipboardCheck, LifeBuoy, Route } from "lucide-react";
import type { Access } from "../types";

const benefits = [
  [Route, "Персональная программа отказа"], [ClipboardCheck, "Ежедневные задания"],
  [ChartNoAxesCombined, "Статистика сэкономленных денег"], [Activity, "Этапы восстановления"],
  [Award, "Достижения"], [LifeBuoy, "SOS-помощь во время тяги"],
] as const;

export function Paywall({ access, activate, openPlans, refresh, busy }: { access: Access; activate: () => void; openPlans: () => void; refresh: () => void; busy: boolean }) {
  return <main className="paywall">
    <div className="paywall-orb"><span>AIR</span></div>
    <p className="eyebrow">Твой новый этап</p>
    <h1>Начни путь<br />без никотина</h1>
    <p className="lead">Персональная программа, которая поможет пройти первые и самые сложные этапы отказа.</p>
    <section className="benefits">
      {benefits.map(([Icon, text]) => <div className="benefit" key={text}><span><Icon size={18} /></span><p>{text}</p><Check size={16} className="check" /></div>)}
    </section>
    <div className="paywall-actions">
      <button className="primary-button" disabled={busy} onClick={access.development_activation_available ? activate : openPlans}>{busy ? "Подключаем…" : access.development_activation_available ? "Получить тестовый доступ" : "Получить доступ к AIR"}</button>
      <button className="text-button" disabled={busy} onClick={refresh}>У меня уже есть доступ</button>
      {access.is_admin && <button className="text-button" onClick={() => window.location.assign("/admin/payments")}>Админка платежей</button>}
      {access.status === "expired" && <p className="fine-print">Предыдущий доступ завершён</p>}
    </div>
  </main>;
}
