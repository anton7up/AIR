import { useEffect, useState } from "react";
import { ArrowLeft, Check, CreditCard, ShieldCheck } from "lucide-react";
import { ACCESS_PLANS, formatPlanPrice, type PlanId } from "../payments/plans";
import { emitPaymentEvent, startPurchase } from "../payments/purchase";
import type { AccessLinks } from "../types";

export function Plans({ links, onBack }: { links: AccessLinks; onBack: () => void }) {
  const [notice, setNotice] = useState("");

  useEffect(() => emitPaymentEvent("paywall_view"), []);

  const choosePlan = (planId: PlanId) => {
    const result = startPurchase(planId);
    setNotice(result.message);
  };

  const legalLinks = [
    ["Условия использования", links.terms],
    ["Политика конфиденциальности", links.privacy],
    ["Поддержка", links.support],
  ].filter((item): item is [string, string] => Boolean(item[1]));

  return <main className="plans-screen">
    <button className="plans-back" type="button" onClick={onBack}><ArrowLeft size={19} /> Назад</button>
    <header className="plans-header">
      <p className="eyebrow">AIR PREMIUM</p>
      <h1>Полный доступ к AIR</h1>
      <p>Получишь всю программу, SOS, статистику, персональный план и прогресс.</p>
    </header>

    <section className="plan-list" aria-label="Тарифы AIR">
      {ACCESS_PLANS.map(plan => <article className={`plan-card${plan.featured ? " featured" : ""}`} key={plan.id} data-plan-id={plan.id}>
        {plan.badge && <span className="plan-badge">{plan.badge}</span>}
        <div className="plan-card-heading"><h2>{plan.name}</h2><strong>{formatPlanPrice(plan.priceRub)}</strong></div>
        <p>{plan.description}</p>
        <ul>{plan.features.map(feature => <li key={feature}><Check size={15} />{feature}</li>)}</ul>
        <button className="primary-button" type="button" onClick={() => choosePlan(plan.id)}>{plan.cta}</button>
      </article>)}
    </section>

    {notice && <p className="purchase-notice" role="status">{notice}</p>}

    <section className="payment-trust" aria-label="Информация об оплате">
      <ShieldCheck size={21} />
      <div><strong>Безопасная оплата</strong><span><CreditCard size={14} /> Картой или через СБП</span></div>
    </section>

    {legalLinks.length > 0 && <nav className="payment-links" aria-label="Документы и поддержка">
      {legalLinks.map(([label, url]) => <a href={url} target="_blank" rel="noreferrer" key={label}>{label}</a>)}
    </nav>}
    <p className="payment-disclaimer">AIR — информационный сервис поддержки и не заменяет медицинскую помощь.</p>
  </main>;
}
