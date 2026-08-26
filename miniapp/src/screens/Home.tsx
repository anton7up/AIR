import { ArrowRight, Clock3, Leaf, Plus, WalletCards, Wind } from "lucide-react";
import { useEffect, useState } from "react";
import type { Dashboard } from "../types";

const money = new Intl.NumberFormat("ru-RU");
export function Home({ data, openProgram, openDesire, startAttempt }: { data: Dashboard; openProgram: () => void; openDesire: () => void; startAttempt: () => Promise<void> }) {
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState("");
  const begin = async () => {
    setStarting(true); setStartError("");
    try { await startAttempt(); }
    catch (error) { setStartError(error instanceof Error ? error.message : "Не удалось начать отсчёт"); }
    finally { setStarting(false); }
  };
  const firstAttempt = data.number_of_attempts === 0;
  return <main className="screen home-screen">
    <header className="hello"><div><p>Добро пожаловать</p><h1>Привет, {data.first_name}</h1></div><div className="mini-logo">AIR</div></header>
    <section className="hero-card">
      <div className="hero-breeze" /><p className="eyebrow">Без никотина</p>
      {data.has_active_attempt
        ? <NicotineTimer key={data.quit_started_at} initialSeconds={data.elapsed_seconds} />
        : <><strong>{firstAttempt ? "Отсчёт ещё не начат" : "Отсчёт не начат"}</strong><div className="hero-rule" /><p>{firstAttempt ? "Начни, когда будешь готов. AIR сохранит твою точку старта." : "Ты можешь начать новую попытку в любой момент."}</p><button className="hero-start-button" disabled={starting} onClick={() => void begin()}>{starting ? "Начинаем…" : firstAttempt ? "Начать отказ" : "Начать новый отказ"}</button>{startError && <small className="hero-error">{startError}</small>}</>}
      {data.has_active_attempt && <><div className="hero-rule" /><p>Каждый час — часть нового ритма</p></>}
    </section>
    {data.has_active_attempt && <section className="stat-grid">
      <article><WalletCards /><span>Сэкономлено</span><strong>{money.format(data.money_saved)} ₽</strong></article>
      <article><Leaf /><span>Не употреблено</span><strong>{data.units_avoided} <small>{data.unit_label}</small></strong></article>
      <article><Clock3 /><span>Время</span><strong>{data.days * 24 + data.hours} ч</strong></article>
      <article><Wind /><span>Программа</span><strong>День {data.program_day}</strong></article>
    </section>}
    <button className="desire-button" onClick={openDesire}><Plus /> Отметить желание никотина</button>
    <div className="section-heading"><div><p>Сегодня</p><h2>Твоё задание</h2></div><span>{data.today_task.day}/{data.program_length}</span></div>
    <article className="task-card"><div className="day-pill">День {data.today_task.day}</div><h3>{data.today_task.title}</h3><p>{data.today_task.description}</p><button onClick={openProgram}>Начать задание <ArrowRight size={18} /></button></article>
    {data.has_active_attempt && <><div className="section-heading"><div><p>Ближайший этап</p><h2>Восстановление</h2></div></div>
    <article className="recovery-card"><div className="recovery-time">{data.recovery.hours < 24 ? `${data.recovery.hours} ч` : `${Math.round(data.recovery.hours / 24)} д`}</div><div><h3>{data.recovery.title}</h3><p>{data.recovery.description}</p></div></article></>}
  </main>;
}

function NicotineTimer({ initialSeconds }: { initialSeconds: number }) {
  const [seconds, setSeconds] = useState(initialSeconds);
  useEffect(() => {
    const timer = window.setInterval(() => setSeconds(value => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (seconds < 86400) return <strong>{days} д <span>{hours} ч {String(minutes).padStart(2, "0")} мин</span></strong>;
  return <strong>{days} {dayWord(days)} <span>{hours} ч</span></strong>;
}

function dayWord(value: number) {
  if (value % 10 === 1 && value % 100 !== 11) return "день";
  if ([2, 3, 4].includes(value % 10) && ![12, 13, 14].includes(value % 100)) return "дня";
  return "дней";
}
