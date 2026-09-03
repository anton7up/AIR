import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Check, CreditCard, ShieldCheck } from "lucide-react";
import { ACCESS_PLANS, formatPlanPrice, type PlanId } from "../payments/plans";
import { closeEmailKeyboardOnEnter, emitPaymentEvent, purchaseErrorMessage, receiptEmailError, startPurchase, type PurchaseStartResult } from "../payments/purchase";
import type { AccessLinks } from "../types";
import { PaymentCheckout } from "./PaymentCheckout";

export function Plans({ links, initialEmail, onBack, onPaymentSucceeded }: { links: AccessLinks; initialEmail: string | null; onBack: () => void; onPaymentSucceeded: () => void }) {
  const [notice, setNotice] = useState("");
  const [email, setEmail] = useState(initialEmail ?? "");
  const [emailError, setEmailError] = useState("");
  const [busyPlanId, setBusyPlanId] = useState<PlanId | null>(null);
  const [pendingPayment, setPendingPayment] = useState<PurchaseStartResult | null>(null);
  const purchaseLocked = useRef(false);
  const emailInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => emitPaymentEvent("paywall_view"), []);

  const choosePlan = async (planId: PlanId) => {
    if (purchaseLocked.current) return;
    const validationError = receiptEmailError(email);
    if (validationError) {
      setEmailError(validationError);
      setNotice("");
      emailInputRef.current?.focus();
      return;
    }
    purchaseLocked.current = true;
    setBusyPlanId(planId);
    setNotice("");
    try {
      const result = await startPurchase(planId, email);
      setPendingPayment(result);
    } catch (error) {
      setNotice(purchaseErrorMessage(error));
    } finally {
      purchaseLocked.current = false;
      setBusyPlanId(null);
    }
  };

  const legalLinks = [
    ["Условия использования", "/terms"],
    ["Публичная оферта", "/offer"],
    ["Политика конфиденциальности", "/privacy"],
    ["Поддержка", links.support ?? "mailto:anton.d.pravdin@gmail.com"],
  ].filter((item): item is [string, string] => Boolean(item[1]));

  if (pendingPayment) {
    return <PaymentCheckout payment={pendingPayment} onSucceeded={onPaymentSucceeded} onNewPayment={() => setPendingPayment(null)} />;
  }

  return <main className="plans-screen">
    <button className="plans-back" type="button" onClick={onBack}><ArrowLeft size={19} /> Назад</button>
    <header className="plans-header">
      <p className="eyebrow">AIR PREMIUM</p>
      <h1>Полный доступ к AIR</h1>
      <p>Получишь всю программу, SOS, статистику, персональный план и прогресс.</p>
    </header>

    <label className={`receipt-email${emailError ? " has-error" : ""}`}>
      <span>Email для получения чека</span>
      <input ref={emailInputRef} type="email" inputMode="email" enterKeyHint="done" autoComplete="email" value={email} aria-invalid={Boolean(emailError)} aria-describedby={emailError ? "receipt-email-error" : undefined} onChange={event => {
        const value = event.target.value;
        setEmail(value);
        if (emailError) setEmailError(receiptEmailError(value));
      }} onKeyDown={closeEmailKeyboardOnEnter} placeholder="name@example.com" />
      {emailError && <small id="receipt-email-error" className="receipt-email-error" role="alert">{emailError}</small>}
    </label>

    <section className="plan-list" aria-label="Тарифы AIR">
      {ACCESS_PLANS.map(plan => <article className={`plan-card${plan.featured ? " featured" : ""}`} key={plan.id} data-plan-id={plan.id}>
        {plan.badge && <span className="plan-badge">{plan.badge}</span>}
        <div className="plan-card-heading">
          <h2>{plan.name}</h2>
          <div className="plan-price">
            {plan.compareAtPriceRub && <del>{formatPlanPrice(plan.compareAtPriceRub)}</del>}
            <strong>{formatPlanPrice(plan.priceRub)}</strong>
            {plan.discountLabel && <small>{plan.discountLabel}</small>}
          </div>
        </div>
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
