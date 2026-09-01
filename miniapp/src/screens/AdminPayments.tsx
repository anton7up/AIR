import { useCallback, useEffect, useMemo, useState } from "react";
import { Check, Clipboard, LogOut, ReceiptText, RefreshCw } from "lucide-react";
import { adminApi, ApiError } from "../api/client";

type ReceiptStatus = "pending" | "sent";
type PaymentStatus = "pending" | "succeeded" | "canceled";
type PaymentOrder = {
  id: number;
  created_at: string;
  telegram_user_id: number;
  email: string;
  plan_id: string;
  plan_title: string;
  amount: string;
  currency: string;
  status: PaymentStatus;
  yookassa_payment_id: string | null;
  paid_at: string | null;
  receipt_status: ReceiptStatus;
  receipt_sent_at: string | null;
};
type PaymentsPayload = {
  stats: {
    successful_count: number;
    revenue: string;
    receipts_pending: number;
    receipts_sent: number;
  };
  orders: PaymentOrder[];
};
type Filter = "all" | "succeeded" | "receipt_pending" | "receipt_sent";

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "Все" },
  { id: "succeeded", label: "Оплаченные" },
  { id: "receipt_pending", label: "Ожидают чек" },
  { id: "receipt_sent", label: "Чек отправлен" },
];

const formatDate = (value: string | null) => value
  ? new Date(value).toLocaleString("ru-RU", { dateStyle: "short", timeStyle: "short" })
  : "—";
const formatMoney = (value: string) => `${new Intl.NumberFormat("ru-RU").format(Number(value))} ₽`;

export function AdminPayments() {
  const [data, setData] = useState<PaymentsPayload | null>(null);
  const [authState, setAuthState] = useState<"loading" | "login" | "denied" | "error" | "ready">("loading");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");
  const [changingOrder, setChangingOrder] = useState<number | null>(null);

  const load = useCallback(async () => {
    setError("");
    try {
      const payload = await adminApi<PaymentsPayload>("/payments");
      setData(payload);
      setAuthState("ready");
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) setAuthState("login");
      else if (caught instanceof ApiError && caught.status === 403) setAuthState("denied");
      else {
        setError(caught instanceof Error ? caught.message : "Не удалось загрузить платежи");
        setAuthState("error");
      }
    }
  }, []);

  useEffect(() => { queueMicrotask(() => void load()); }, [load]);

  const login = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true); setError("");
    try {
      await adminApi("/login", { method: "POST", body: JSON.stringify({ password }) });
      setPassword("");
      await load();
    } catch (caught) {
      setError(caught instanceof ApiError && caught.status === 401 ? "Неверный пароль" : "Не удалось войти");
    } finally { setBusy(false); }
  };

  const logout = async () => {
    try { await adminApi("/logout", { method: "POST" }); } finally {
      setData(null); setAuthState("login");
    }
  };

  const changeReceipt = async (order: PaymentOrder) => {
    const nextStatus: ReceiptStatus = order.receipt_status === "sent" ? "pending" : "sent";
    setChangingOrder(order.id); setError("");
    try {
      await adminApi(`/payments/${order.id}/receipt`, {
        method: "PATCH",
        body: JSON.stringify({ status: nextStatus }),
      });
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось изменить статус чека");
    } finally { setChangingOrder(null); }
  };

  const orders = useMemo(() => (data?.orders ?? []).filter(order => {
    if (filter === "succeeded") return order.status === "succeeded";
    if (filter === "receipt_pending") return order.status === "succeeded" && order.receipt_status === "pending";
    if (filter === "receipt_sent") return order.status === "succeeded" && order.receipt_status === "sent";
    return true;
  }), [data, filter]);

  if (authState === "loading") return <main className="admin-login"><p>Проверяем доступ…</p></main>;
  if (authState === "denied") return <main className="admin-login"><h1>Доступ запрещён</h1><p>Этот Telegram-аккаунт не входит в список администраторов AIR.</p></main>;
  if (authState === "error") return <main className="admin-login"><div><h1>Не удалось проверить доступ</h1><p>{error}</p><button className="primary-button" onClick={() => { setAuthState("loading"); void load(); }}>Попробовать снова</button></div></main>;
  if (authState === "login") return <main className="admin-login">
    <form onSubmit={login}>
      <ReceiptText size={40} />
      <p className="eyebrow">AIR ADMIN</p>
      <h1>Платежи AIR</h1>
      <label>Пароль администратора<input type="password" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} autoFocus /></label>
      {error && <p className="admin-error">{error}</p>}
      <button className="primary-button" disabled={busy || !password} type="submit">{busy ? "Входим…" : "Войти"}</button>
    </form>
  </main>;

  return <main className="admin-payments">
    <header><div><p className="eyebrow">AIR ADMIN</p><h1>Платежи AIR</h1><p>Реальные заказы из базы AIR и внутренний учёт чеков НПД.</p></div><div className="admin-header-actions"><button onClick={() => void load()}><RefreshCw size={16} />Обновить</button><button onClick={() => void logout()}><LogOut size={16} />Выйти</button></div></header>
    {error && <p className="admin-error">{error}</p>}
    {data && <>
      <section className="admin-stats">
        <article><span>Успешных платежей</span><strong>{data.stats.successful_count}</strong></article>
        <article><span>Выручка</span><strong>{formatMoney(data.stats.revenue)}</strong></article>
        <article><span>Ожидают чек</span><strong>{data.stats.receipts_pending}</strong></article>
        <article><span>Чеков отправлено</span><strong>{data.stats.receipts_sent}</strong></article>
      </section>
      <nav className="admin-filters" aria-label="Фильтры платежей">{FILTERS.map(item => <button key={item.id} className={filter === item.id ? "active" : ""} onClick={() => setFilter(item.id)}>{item.label}</button>)}</nav>
      <section className="admin-table-wrap"><table><thead><tr><th>Дата</th><th>Telegram ID</th><th>Email</th><th>Тариф</th><th>Сумма</th><th>Платёж</th><th>YooKassa payment_id</th><th>Оплачен</th><th>Чек НПД</th></tr></thead><tbody>
        {orders.map(order => <tr key={order.id}>
          <td>{formatDate(order.created_at)}</td>
          <td><CopyValue value={String(order.telegram_user_id)} /></td>
          <td><CopyValue value={order.email} /></td>
          <td><strong>{order.plan_title}</strong><small>{order.plan_id}</small></td>
          <td>{formatMoney(order.amount)}</td>
          <td><span className={`admin-status ${order.status}`}>{order.status}</span></td>
          <td>{order.yookassa_payment_id ? <CopyValue value={order.yookassa_payment_id} compact /> : "—"}</td>
          <td>{formatDate(order.paid_at)}</td>
          <td><span className={`receipt-status ${order.receipt_status}`}>{order.receipt_status === "sent" ? "Отправлен" : "Ожидает"}</span>{order.status === "succeeded" && <button className="receipt-action" disabled={changingOrder === order.id} onClick={() => void changeReceipt(order)}>{order.receipt_status === "sent" ? "Вернуть в ожидание" : "Отметить чек отправленным"}</button>}{order.receipt_sent_at && <small>{formatDate(order.receipt_sent_at)}</small>}</td>
        </tr>)}
        {orders.length === 0 && <tr><td className="admin-empty" colSpan={9}>Платежей по этому фильтру нет.</td></tr>}
      </tbody></table></section>
    </>}
  </main>;
}

function CopyValue({ value, compact = false }: { value: string; compact?: boolean }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  };
  const visible = compact && value.length > 18 ? `${value.slice(0, 8)}…${value.slice(-6)}` : value;
  return <button className="copy-value" title={value} onClick={() => void copy()}>{visible}{copied ? <Check size={14} /> : <Clipboard size={14} />}</button>;
}
