import { Award, Check, Clock3, Leaf, LockKeyhole, Trophy, WalletCards } from "lucide-react";
import { formatNicotineUnits } from "../formatters";
import type { Progress as ProgressType } from "../types";
import { achievementClassName } from "../progress/achievements";

const money = new Intl.NumberFormat("ru-RU");

export function Progress({ data }: { data: ProgressType }) {
  return <main className="screen">
    <header className="page-header"><p className="eyebrow">Твой путь</p><h1>Прогресс</h1><p>Каждая попытка остаётся частью общего результата.</p></header>
    <section className="current-streak-card"><Clock3 /><span>Текущая серия</span><strong>{data.has_active_attempt ? formatDuration(data.current_streak_seconds) : "Отсчёт не начат"}</strong></section>
    <section className="streak-history-grid">
      <article><Trophy /><span>Лучшая серия</span><strong>{formatDuration(data.best_streak_seconds)}</strong></article>
      <article><Clock3 /><span>Всего без никотина</span><strong>{formatDuration(data.total_nicotine_free_seconds)}</strong></article>
    </section>
    <p className="attempt-count">Попыток: <strong>{data.number_of_attempts}</strong></p>
    {data.has_active_attempt && <section className="progress-summary current-attempt-stats">
      <article><WalletCards /><span>Сэкономлено в текущей попытке</span><strong>{money.format(data.money_saved)} ₽</strong></article>
      <article><Leaf /><span>Не употреблено в текущей попытке</span><strong>{formatNicotineUnits(data.units_avoided)} <small>{data.unit_label}</small></strong></article>
    </section>}
    <div className="program-progress">
      <div><span>Текущий день</span><strong>День {data.program_day} из {data.program_length}</strong></div>
      <div className="program-completed-label"><span>Выполнено</span><strong>{data.completed_program_days} из {data.program_length} дней</strong></div>
      <div className="progress-track"><i style={{ width: `${Math.min(100, data.completed_program_days / data.program_length * 100)}%` }} /></div>
    </div>
    {data.has_active_attempt && <><div className="section-heading"><div><p>Текущая попытка</p><h2>Восстановление</h2></div></div>
    <div className="timeline">{data.recovery_timeline.map(item => <div className={item.reached ? "reached" : ""} key={item.hours}><span>{item.reached ? <Check size={16} /> : <LockKeyhole size={14} />}</span><div><small>{item.hours < 24 ? `${item.hours} часов` : `${Math.round(item.hours / 24)} дней`}</small><h3>{item.title}</h3><p>{item.description}</p></div></div>)}</div></>}
    <div className="section-heading"><div><p>Твои отметки</p><h2>Достижения</h2></div></div>
    <div className="achievements">{data.achievements.map(item => <article className={achievementClassName(item.unlocked)} data-earned={item.unlocked} key={item.id}><Award /><span>{item.title}</span></article>)}</div>
  </main>;
}

function formatDuration(totalSeconds: number) {
  const days = Math.floor(totalSeconds / 86400);
  const hours = Math.floor((totalSeconds % 86400) / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  if (days > 0) return `${days} ${dayWord(days)} ${hours} ч`;
  if (hours > 0) return `${hours} ч ${minutes} мин`;
  return `${minutes} мин`;
}

function dayWord(value: number) {
  if (value % 10 === 1 && value % 100 !== 11) return "день";
  if ([2, 3, 4].includes(value % 10) && ![12, 13, 14].includes(value % 100)) return "дня";
  return "дней";
}
