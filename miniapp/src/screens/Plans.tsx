import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Check, CreditCard, ShieldCheck } from "lucide-react";
import { ACCESS_PLANS, formatPlanPrice, type PlanId } from "../payments/plans";
import { emitPaymentEvent, isValidReceiptEmail, openConfirmationUrl, purchaseErrorMessage, startPurchase } from "../payments/purchase";
import type { AccessLinks } from "../types";

export function Plans({ links, initialEmail, onBack }: { links: AccessLinks; initialEmail: string | null; onBack: () => void }) {
  const [notice, setNotice] = useState("");
  const [email, setEmail] = useState(initialEmail ?? "");
  const [busyPlanId, setBusyPlanId] = useState<PlanId | null>(null);
  const purchaseLocked = useRef(false);

  useEffect(() => emitPaymentEvent("paywall_view"), []);

  const choosePlan = async (planId: PlanId) => {
    if (purchaseLocked.current) return;
    if (!isValidReceiptEmail(email)) {
      setNotice("Проверь email — на него мы отправим информацию о покупке.");
      return;
    }
    purchaseLocked.current = true;
    setBusyPlanId(planId);
    setNotice("");
    try {
      const result = await startPurchase(planId, email);
      openConfirmationUrl(result.confirmation_url);
    } catch (error) {
      setNotice(purchaseErrorMessage(error));
    } finally {
      purchaseLocked.current = false;
      setBusyPlanId(null);
    }
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

    <label className="receipt-email">
      <span>Email для получения чека</span>
      <input type="email" inputMode="email" autoComplete="email" value={email} onChange={event => setEmail(event.target.value)} placeholder="name@example.com" />
    </label>

    <section className="plan-list" aria-label="Тарифы AIR">
      {ACCESS_PLANS.map(plan => <article className={`plan-card${plan.featured ? " featured" : ""}`} key={plan.id} data-plan-id={plan.id}>
        {plan.badge && <span className="plan-badge">{plan.badge}</span>}
        <div className="plan-card-heading"><h2>{plan.name}</h2><strong>{formatPlanPrice(plan.priceRub)}</strong></div>
        <p>{plan.description}</p>
        <ul>{plan.features.map(feature => <li key={feature}><Check size={15} />{feature}</li>)}</ul>
        <button className="primary-button" type="button" disabled={busyPlanId !== null} onClick={() => void choosePlan(plan.id)}>{busyPlanId === plan.id ? "Открываем оплату…" : plan.cta}</button>
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
