import { useRef, useState } from "react";
import { ArrowLeft, CalendarDays, ChevronRight, CircleHelp, FileLock2, FileText, Gem, PencilLine, ReceiptText, ShieldCheck, UserRound } from "lucide-react";
import { openAirEditProfile, openAirSupport } from "../telegram";
import type { Access, Profile as ProfileType } from "../types";
import { accessPresentation } from "../profileAccess";
import { nicotineTypeLabel } from "../nicotine";

export function Profile({ data, access, isAdmin, onOpenPlans }: { data: ProfileType; access: Access; isAdmin: boolean; onOpenPlans: () => void }) {
  const accessCard = useRef<HTMLElement>(null);
  const [legalOpen, setLegalOpen] = useState(false);
  const presentation = accessPresentation(access);
  const revealAccess = () => {
    accessCard.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    accessCard.current?.focus({ preventScroll: true });
  };
  if (legalOpen) return <main className="screen profile-legal"><button className="profile-back" type="button" onClick={() => setLegalOpen(false)}><ArrowLeft /> Назад</button><header><p className="eyebrow">AIR</p><h1>Юридическая информация</h1><p>Документы сервиса AIR</p></header><section className="menu-list"><button onClick={() => window.location.assign("/terms")}><FileText /><span>Условия использования</span><ChevronRight /></button><button onClick={() => window.location.assign("/offer")}><ReceiptText /><span>Публичная оферта</span><ChevronRight /></button><button onClick={() => window.location.assign("/privacy")}><FileLock2 /><span>Политика конфиденциальности</span><ChevronRight /></button><button onClick={() => window.location.assign("/personal-data-consent")}><FileText /><span>Согласие на обработку персональных данных</span><ChevronRight /></button></section></main>;

  return <main className="screen"><header className="profile-header"><div className="avatar"><UserRound /></div><h1>{data.first_name}</h1><p>{data.username ? `@${data.username}` : "Telegram-пользователь"}</p></header>
    <section className="premium-card profile-access-card" id="profile-access" ref={accessCard} tabIndex={-1}>
      <div><Gem /><span>Доступ к AIR</span></div><strong><ShieldCheck size={16} /> {presentation.active ? "Активен" : "Не активен"}</strong>
      {presentation.active && !presentation.virtual && <div className="profile-access-detail"><span>Тариф</span><b>{presentation.title}</b></div>}
      {presentation.expiresLabel && <div className="profile-access-detail"><span>Доступ активен до</span><b><CalendarDays /> {presentation.expiresLabel}</b></div>}
      {presentation.remainingLabel && <div className="profile-access-detail"><span>Осталось</span><b>{presentation.remainingLabel}</b></div>}
      {access.plan === "air_lifetime" && presentation.active && <p>Доступ к AIR без ограничения по времени.</p>}
      {presentation.virtual && <p>Доступ активен без ограничения по сроку тарифа.</p>}
      {!presentation.active && <p>Сейчас у тебя нет активного доступа.</p>}
      {presentation.actionLabel && <button type="button" className="profile-access-action" onClick={onOpenPlans}>{presentation.actionLabel}</button>}
    </section>
    <section className="profile-facts"><div><span>Тип никотина</span><strong>{nicotineTypeLabel(data.nicotine_type)}</strong></div><div><span>Исходный уровень</span><strong>{data.daily_units} {data.unit_label} в день</strong></div><div><span>Начало отказа</span><strong>{data.quit_started_at ? new Date(data.quit_started_at).toLocaleString("ru-RU", { dateStyle: "short", timeStyle: "short" }) : "Не начат"}</strong></div><div><span>Регистрация</span><strong>{new Date(data.registered_at).toLocaleDateString("ru-RU")}</strong></div></section>
    <section className="menu-list"><button onClick={revealAccess}><Gem /><span>Доступ к AIR</span><ChevronRight /></button><button onClick={openAirEditProfile}><PencilLine /><span>Изменить данные<small>Обновить ответы знакомства</small></span><ChevronRight /></button>{isAdmin && <button onClick={() => window.location.assign("/admin/payments")}><ReceiptText /><span>Админка платежей</span><ChevronRight /></button>}<button onClick={openAirSupport}><CircleHelp /><span>Поддержка<small>Написать в AIR-бот</small></span><ChevronRight /></button><button onClick={() => setLegalOpen(true)}><FileText /><span>Юридическая информация</span><ChevronRight /></button></section>
    <p className="version">AIR · первый шаг к свободному дыханию</p>
  </main>;
}
