import { useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle2, Clock3, ExternalLink, XCircle } from "lucide-react";
import { paymentApi } from "../api/client";
import { openExternalCheckout, paymentStatusPhase, type PaymentOrderStatus, type PaymentPhase, type PurchaseStartResult } from "../payments/purchase";
const AUTO_POLL_DELAYS = [0, 1800, 2800, 4000, 5500, 7000];

export function PaymentCheckout({
  payment,
  onSucceeded,
  onNewPayment,
}: {
  payment: PurchaseStartResult;
  onSucceeded: () => void;
  onNewPayment: () => void;
}) {
  const [phase, setPhase] = useState<PaymentPhase>("ready");
  const [checkError, setCheckError] = useState("");
  const checkingRef = useRef(false);

  const checkStatus = useCallback(async () => {
    if (checkingRef.current) return "pending" as const;
    checkingRef.current = true;
    try {
      const current = await paymentApi<PaymentOrderStatus>(`/${payment.order_id}/status`);
      const nextPhase = paymentStatusPhase(current);
      setPhase(nextPhase);
      setCheckError("");
      return current.status;
    } catch {
      setCheckError("Не удалось проверить статус. AIR попробует ещё раз.");
      return "pending" as const;
    } finally {
      checkingRef.current = false;
    }
  }, [payment.order_id]);

  useEffect(() => {
    if (phase !== "waiting") return;
    let cancelled = false;
    let timer: number | undefined;
    let attempt = 0;
    const poll = async () => {
      const status = await checkStatus();
      if (cancelled || status !== "pending") return;
      attempt += 1;
      if (attempt < AUTO_POLL_DELAYS.length) {
        timer = window.setTimeout(poll, AUTO_POLL_DELAYS[attempt]);
      }
    };
    timer = window.setTimeout(poll, AUTO_POLL_DELAYS[0]);
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [checkStatus, phase]);

  useEffect(() => {
    if (phase !== "waiting") return;
    const checkOnFocus = () => { void checkStatus(); };
    const checkWhenVisible = () => {
      if (document.visibilityState === "visible") void checkStatus();
    };
    window.addEventListener("focus", checkOnFocus);
    document.addEventListener("visibilitychange", checkWhenVisible);
    return () => {
      window.removeEventListener("focus", checkOnFocus);
      document.removeEventListener("visibilitychange", checkWhenVisible);
    };
  }, [checkStatus, phase]);

  useEffect(() => {
    if (phase !== "succeeded") return;
    const timer = window.setTimeout(onSucceeded, 900);
    return () => window.clearTimeout(timer);
  }, [onSucceeded, phase]);

  const openCheckout = () => {
    setPhase("waiting");
    openExternalCheckout(payment.confirmation_url);
  };

  const icon = phase === "succeeded"
    ? <CheckCircle2 size={48} />
    : phase === "canceled"
      ? <XCircle size={48} />
      : <Clock3 size={48} />;

  return <main className="payment-checkout-screen">
    {icon}
    <p className="eyebrow">AIR PREMIUM</p>
    <h1>{phase === "ready" ? "Всё готово к оплате" : phase === "succeeded" ? "Оплата прошла" : phase === "canceled" ? "Оплата отменена" : "Ожидаем оплату"}</h1>
    <p>{phase === "ready"
      ? "Открой безопасную страницу YooKassa во внешнем браузере."
      : phase === "succeeded"
        ? "Доступ активирован. Открываем AIR…"
        : phase === "canceled"
          ? "Доступ не изменился. Можно выбрать тариф и попробовать ещё раз."
          : "После оплаты вернись в Telegram — AIR проверит статус автоматически."}</p>
    {checkError && <small className="payment-check-error" role="status">{checkError}</small>}
    {phase === "canceled"
      ? <button className="primary-button" type="button" onClick={onNewPayment}>Выбрать тариф снова</button>
      : phase !== "succeeded" && <button className="primary-button" type="button" onClick={openCheckout}><ExternalLink size={18} />{phase === "ready" ? "Перейти к оплате" : "Снова открыть оплату"}</button>}
  </main>;
}
