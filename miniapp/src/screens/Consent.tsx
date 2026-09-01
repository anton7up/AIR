import { FileText, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { api } from "../api/client";
import type { ConsentStatus } from "../types";

export function ConsentScreen({ onAccepted }: { onAccepted: (status: ConsentStatus) => void }) {
  const [declined, setDeclined] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const accept = async () => {
    setBusy(true);
    setError("");
    try {
      const status = await api<ConsentStatus>("/consent/accept", { method: "POST" });
      onAccepted(status);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось сохранить согласие");
    } finally {
      setBusy(false);
    }
  };

  const close = () => {
    if (window.Telegram?.WebApp) window.Telegram.WebApp.close();
    else window.close();
  };

  if (declined) {
    return <main className="payment-return-screen consent-screen">
      <ShieldCheck size={36} />
      <h1>Без согласия на обработку персональных данных<br />AIR не сможет персонализировать программу.</h1>
      <p>Ты можешь вернуться и изменить решение.</p>
      <button className="primary-button" onClick={() => setDeclined(false)}>Вернуться</button>
      <button className="secondary-button" onClick={close}>Закрыть</button>
    </main>;
  }

  return <main className="payment-return-screen consent-screen">
    <p className="eyebrow">Перед началом</p>
    <ShieldCheck size={36} />
    <h1>Перед началом</h1>
    <p>AIR использует твои ответы, чтобы персонализировать программу, отслеживать прогресс и подбирать поддержку в моменты тяги к никотину.</p>
    <a className="consent-document-link" href="/personal-data-consent"><FileText size={17} />Согласие на обработку персональных данных</a>
    {error && <p className="payment-check-error">{error}</p>}
    <button className="primary-button" disabled={busy} onClick={() => void accept()}>{busy ? "Сохраняем…" : "Согласен"}</button>
    <button className="secondary-button" disabled={busy} onClick={() => setDeclined(true)}>Не согласен</button>
  </main>;
}
