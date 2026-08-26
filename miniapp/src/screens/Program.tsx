import { Check, ChevronRight, LifeBuoy, LockKeyhole, ShieldCheck, TrendingUp } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { PersonalPlan, Program as ProgramType, SupportContext } from "../types";
import { formatProgramLabel, formatProgramText } from "../program/labels";
import { ProgramDayScreen } from "./ProgramDay";

export function Program({ data: initialData, onGoSos, onGoProgress }: { data: ProgramType; onGoSos: () => void; onGoProgress: () => void }) {
  const [data, setData] = useState(initialData);
  const [selectedDay, setSelectedDay] = useState<{ number: number; devPreview: boolean } | null>(null);
  const [plan, setPlan] = useState<PersonalPlan | null>(null);
  const [showPlan, setShowPlan] = useState(false);
  const refresh = async () => { setData(await api<ProgramType>("/program")); setSelectedDay(null); };
  useEffect(() => { void api<ProgramType>("/program").then(setData); }, []);
  if (selectedDay !== null) return <ProgramDayScreen dayNumber={selectedDay.number} devPreview={selectedDay.devPreview} onBack={() => setSelectedDay(null)} onCompleted={() => void refresh()} />;
  const openPlan = async () => { if (!plan) setPlan((await api<SupportContext>("/support-context")).personal_plan); setShowPlan(true); };
  return <main className="screen"><header className="page-header"><p className="eyebrow">30 спокойных шагов</p><h1>Программа</h1><p>{data.completed_count >= 30 ? "Все 30 дней пройдены. Твои инструменты остаются рядом." : `Двигайся в своём темпе. Текущий день: День ${data.current_day}.`}</p>{data.is_program_dev && <span className="dev-mode-badge">DEV PROGRAM MODE</span>}</header>
    {data.completed_count >= 30 && <section className="program-finished"><span>🎉</span><h2>30 дней AIR пройдены</h2><p>Ты больше не в начале. Возвращайся к поддержке и своему плану тогда, когда это нужно.</p><div><button onClick={onGoSos}><LifeBuoy /> SOS</button><button onClick={() => void openPlan()}><ShieldCheck /> Мой план</button><button onClick={onGoProgress}><TrendingUp /> Прогресс</button></div>{showPlan && <div className="program-personal-plan">{plan?.items.length ? plan.items.map(item => <article key={item.category}><strong>{formatProgramLabel(item.category_label || item.category)}</strong>{item.reasons?.length > 0 && <div className="plan-reasons"><small>Часто вызывает желание</small>{item.reasons.map(reason => <p key={reason}>{formatProgramText(reason)}</p>)}</div>}<small>Твой план</small>{item.steps.map((step, index) => <p key={`${item.category}-${index}`}>{index + 1}. {formatProgramText(step)}</p>)}</article>) : <p>Личный план пока пуст. Его можно собрать из решений в днях программы.</p>}</div>}</section>}
    <div className="program-list">{data.days.map(day => <article key={day.number} className={`program-day ${day.status} ${day.dev_unlocked ? "dev-access" : ""}`}>
      <div className="day-number">{day.completed ? <Check size={18} /> : day.status === "locked" ? <LockKeyhole size={16} /> : day.number}</div>
      <div className="day-copy"><small>День {day.number} {day.dev_unlocked && <b className="dev-inline-badge">DEV</b>}</small><h3>{day.title}</h3><p>{day.description}</p>
        {day.interactive && day.status !== "locked" && <button onClick={() => setSelectedDay({ number: day.number, devPreview: false })}>{day.completed ? "Открыть снова" : "Начать сессию"} <ChevronRight size={16} /></button>}
        {day.dev_preview_available && <button className="dev-preview-button" onClick={() => setSelectedDay({ number: day.number, devPreview: true })}>DEV preview <ChevronRight size={16} /></button>}
      </div>
    </article>)}</div>
  </main>;
}
