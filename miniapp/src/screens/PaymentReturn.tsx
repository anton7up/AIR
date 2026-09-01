import { useEffect, useState } from "react";
import { CheckCircle2, Clock3 } from "lucide-react";
import { paymentApi } from "../api/client";

type OrderStatus = {
  order_id: number;
  status: "pending" | "succeeded" | "canceled";
  access_active: boolean;
};

const POLL_DELAYS = [0, 1200, 1800, 2500, 3500];

export function PaymentReturn({ orderId, onOpenAir }: { orderId: number; onOpenAir: () => void }) {
  const [result, setResult] = useState<OrderStatus | null>(null);
  const [finished, setFinished] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      for (const delay of POLL_DELAYS) {
        if (delay) await new Promise(resolve => window.setTimeout(resolve, delay));
        if (cancelled) return;
        try {
          const current = await paymentApi<OrderStatus>(`/${orderId}/status`);
          if (cancelled) return;
          setResult(current);
          if (current.status !== "pending") break;
        } catch {
          // A temporary network error is retried by the next poll.
        }
      }
      if (!cancelled) setFinished(true);
    };
    void check();
    return () => { cancelled = true; };
  }, [orderId]);

  const succeeded = result?.status === "succeeded" && result.access_active;
  return <main className="payment-return-screen">
    {succeeded ? <CheckCircle2 size={48} /> : <Clock3 size={48} />}
    <p className="eyebrow">AIR PREMIUM</p>
    <h1>{succeeded ? "Оплата прошла" : result?.status === "canceled" ? "Оплата отменена" : "Проверяем оплату"}</h1>
    <p>{succeeded
      ? "Доступ уже активирован. Можно возвращаться в AIR."
      : result?.status === "canceled"
        ? "Доступ не изменился. Ты можешь выбрать тариф ещё раз."
        : finished
          ? "Подтверждение ещё обрабатывается. Открой AIR чуть позже — доступ появится автоматически."
          : "Обычно это занимает несколько секунд."}</p>
    <button className="primary-button" type="button" onClick={onOpenAir}>Открыть AIR</button>
  </main>;
}

export function ExternalPaymentReturn() {
  const returnToAir = () => window.close();
  return <main className="payment-return-screen">
    <CheckCircle2 size={48} />
    <p className="eyebrow">AIR PREMIUM</p>
    <h1>Оплата завершена</h1>
    <p>Вернитесь в Telegram — доступ активируется автоматически.</p>
    <button className="primary-button" type="button" onClick={returnToAir}>Вернуться в AIR</button>
  </main>;
}
