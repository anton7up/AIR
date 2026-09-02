import { Brain, Check, Footprints, Gamepad2, Hand, LifeBuoy, RotateCcw, ShieldCheck, Wind } from "lucide-react";
import { useEffect, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import { api, eventApi } from "../api/client";
import { Options, Scale } from "../components/NicotineDesireModal";
import { AirCloudGame } from "../sos/AirCloudGame";
import type { CloudGameMetadata } from "../sos/cloudGame";
import { SquareBreathing } from "../sos/SosInteractive";
import { nextAction, recordAction, replacementActions, switchActions, type ReplacementFocus } from "../sos/actionLibrary";
import { formatProgramLabel, formatProgramText } from "../program/labels";
import { CustomOptionInput } from "../components/program/ChoiceStep";
import { KeyboardSafeSaveButton } from "../components/KeyboardSafeSaveButton";
import { actionCompletionStep, recommendedTool, toolCompletionStep, type SupportType } from "../sos/logic";
import { SOS_MENU_ITEMS } from "../sos/menu";
import type { RememberedResponse, StepOption, SupportContext } from "../types";

type FlowStep = "intro" | "intensity" | "trigger" | "custom_reason" | "support" | "replacement_focus" | "proposal" | "custom_action" | "motivation_setup" | "driving_pause" | "exercise" | "after" | "result" | "done" | "lapse_type" | "lapse_trigger" | "lapse_done";
type Focus = ReplacementFocus;

const SUPPORT_ICONS: Record<string, typeof Wind> = { breathing: Wind, distraction: Gamepad2, motivation: Brain, personal_plan: ShieldCheck, replacement_action: Hand, change_activity: Footprints };
const SUPPORTS = SOS_MENU_ITEMS.map(item => ({ ...item, icon: SUPPORT_ICONS[item.id] }));

const MOTIVATION_OPTIONS: StepOption[] = [{ id: "Здоровье", label: "Здоровье" }, { id: "Деньги", label: "Деньги" }, { id: "Свобода от зависимости", label: "Свобода от зависимости" }, { id: "Физическая форма", label: "Физическая форма" }, { id: "Близкие", label: "Близкие" }, { id: "Хочу снова контролировать свои решения", label: "Контроль своих решений" }];
const TRIGGER_PLAN_CATEGORY: Record<string, string> = { stress: "stress", coffee: "coffee", after_meal: "after_meal", work_study: "work_study", social: "social", alcohol: "alcohol", boredom: "boredom", before_sleep: "before_sleep" };
const SOS_TRIGGER_LABELS: Record<string, string> = {
  morning: "☀️ Утро",
  coffee: "☕ Кофе",
  after_meal: "🍽 После еды",
  work_study: "💻 Работа / учёба",
  stress: "😰 Стресс",
  boredom: "😑 Скука",
  alcohol: "🍺 Алкоголь",
  social: "👥 Компания",
  before_sleep: "🌙 Перед сном",
  driving: "🚗 В дороге",
  entertainment: "🎮 Игры / отдых",
  other: "➕ Другое",
};

export function Sos({ onAttemptChanged, onAttemptRestarted, onGoHome }: { onAttemptChanged: () => Promise<void>; onAttemptRestarted: () => Promise<void>; onGoHome: () => void }) {
  const [context, setContext] = useState<SupportContext | null>(null);
  const [step, setStep] = useState<FlowStep>("intro");
  const [before, setBefore] = useState<number | null>(null);
  const [currentBefore, setCurrentBefore] = useState<number | null>(null);
  const [after, setAfter] = useState<number | null>(null);
  const [trigger, setTrigger] = useState<string | null>(null);
  const [reasonResponse, setReasonResponse] = useState<RememberedResponse | null>(null);
  const [rememberedReasons, setRememberedReasons] = useState<RememberedResponse[]>([]);
  const [customReason, setCustomReason] = useState("");
  const [support, setSupport] = useState<SupportType | null>(null);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [actionId, setActionId] = useState<number | null>(null);
  const [used, setUsed] = useState<Partial<Record<SupportType, number>>>({});
  const [focus, setFocus] = useState<Focus>("mouth");
  const [proposalHistory, setProposalHistory] = useState<string[]>([]);
  const [personalActions, setPersonalActions] = useState<RememberedResponse[]>([]);
  const [customAction, setCustomAction] = useState("");
  const [toolMetadata, setToolMetadata] = useState<Record<string, unknown> | null>(null);
  const [selectedMotivation, setSelectedMotivation] = useState<string | null>(null);
  const [customMotivation, setCustomMotivation] = useState("");
  const [lapseType, setLapseType] = useState<string | null>(null);
  const [finalSummary, setFinalSummary] = useState<{ before: number; after: number } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { void api<SupportContext>("/support-context").then(setContext); }, []);
  const [triggerViewportHeight, setTriggerViewportHeight] = useState(() => window.innerHeight);
  useEffect(() => {
    if (step !== "trigger") return;
    const update = () => setTriggerViewportHeight(
      window.visualViewport?.height || window.Telegram?.WebApp?.viewportHeight || window.innerHeight,
    );
    const viewport = window.visualViewport;
    const telegram = window.Telegram?.WebApp;
    update();
    window.addEventListener("resize", update);
    window.addEventListener("orientationchange", update);
    viewport?.addEventListener("resize", update);
    telegram?.onEvent?.("viewportChanged", update);
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("orientationchange", update);
      viewport?.removeEventListener("resize", update);
      telegram?.offEvent?.("viewportChanged", update);
    };
  }, [step]);
  const bestTool = recommendedTool(context?.tool_analytics, trigger);
  const recommendedForTrigger = Boolean(trigger && context?.tool_analytics.best_tool_by_trigger[trigger]);
  const availableSupports = SUPPORTS.filter(item => item.id !== "personal_plan" || context?.personal_plan.has_plan);
  const orderedSupports = availableSupports;
  const personalPool: StepOption[] = personalActions.map(item => ({ id: `user_response:${item.id}`, label: item.value, response_id: item.id, personalized_reason: item.parent_response_id === reasonResponse?.id ? "Раньше помогало в этой ситуации" : item.context_id === trigger ? "Ты раньше выбирал это для такого триггера" : "Твоя сохранённая стратегия" }));
  const planItem = trigger ? context?.personal_plan.by_category[TRIGGER_PLAN_CATEGORY[trigger]] : undefined;
  const planPool: StepOption[] = (planItem?.steps || []).map((label, index) => ({ id: `personal_plan:${planItem?.category}:${index}`, label, personalized_reason: "Из твоего личного плана для этой ситуации" }));
  const standardPool = support === "replacement_action" ? replacementActions(focus, trigger) : switchActions(trigger);
  const prioritizedPool = support === "change_activity" ? [...personalPool, ...planPool] : personalPool;
  const proposalPool = [...prioritizedPool, ...standardPool.filter(item => !prioritizedPool.some(personal => personal.label.trim().toLocaleLowerCase("ru-RU") === item.label.trim().toLocaleLowerCase("ru-RU")))];
  const proposal = nextAction(proposalPool, proposalHistory);

  const start = async (selectedTrigger = trigger, selectedReason = reasonResponse) => {
    if (!before || !selectedTrigger) return;
    setBusy(true);
    const result = await eventApi<{ id: number }>("/sos/start", { method: "POST", body: JSON.stringify({ intensity_before: before, trigger_id: selectedTrigger, reason_response_id: selectedReason?.id ?? null }) });
    setSessionId(result.id); setStep("support"); setBusy(false);
  };
  const beginExercise = async (id: SupportType, selectedAction: string | null, userResponseId: number | null = null) => {
    if (!sessionId) return;
    setBusy(true);
    const result = await eventApi<{ id: number; intensity_before: number }>(`/sos/${sessionId}/actions`, { method: "POST", body: JSON.stringify({ support_type: id, support_action: selectedAction, user_response_id: userResponseId }) });
    setSupport(id); setActionId(result.id); setCurrentBefore(result.intensity_before); setAfter(null); setToolMetadata(null); setStep("exercise"); setBusy(false);
  };
  const loadReasons = async () => {
    const result = await api<{ items: RememberedResponse[] }>(`/responses/reasons${trigger && trigger !== "other" ? `?context_id=${encodeURIComponent(trigger)}` : ""}`);
    setRememberedReasons(result.items); setStep("custom_reason");
  };
  const loadActions = async (selectedFocus?: Focus) => {
    if (trigger === "driving") {
      setPersonalActions([]);
      return;
    }
    const params = new URLSearchParams();
    if (trigger && trigger !== "other") params.set("context_id", trigger);
    if (reasonResponse) params.set("reason_response_id", String(reasonResponse.id));
    if (selectedFocus) params.set("focus", selectedFocus);
    const result = await api<{ items: RememberedResponse[] }>(`/responses/actions?${params.toString()}`);
    setPersonalActions(result.items);
  };
  const saveReason = async () => {
    if (!customReason.trim()) return;
    setBusy(true);
    const saved = await api<RememberedResponse>("/responses", { method: "POST", body: JSON.stringify({ response_type: "reason", value: customReason, context_id: trigger && trigger !== "other" ? trigger : null }) });
    setReasonResponse(saved); setTrigger(saved.context_id || "other"); await start(saved.context_id || "other", saved); setBusy(false);
  };
  const saveCustomAction = async () => {
    if (!customAction.trim() || !support) return;
    setBusy(true);
    const saved = await api<RememberedResponse>("/responses", { method: "POST", body: JSON.stringify({ response_type: support === "replacement_action" ? "replacement" : "coping_action", value: customAction, context_id: trigger && trigger !== "other" ? trigger : null, parent_response_id: reasonResponse?.id ?? null, focus: support === "replacement_action" ? focus : null }) });
    setPersonalActions(items => [saved, ...items.filter(item => item.id !== saved.id)]); await beginExercise(support, `user_response:${saved.id}`, saved.id); setBusy(false);
  };
  const chooseSupport = (id: SupportType) => {
    setSupport(id); setProposalHistory([]);
    if (id === "distraction" && trigger === "driving") { setStep("driving_pause"); return; }
    if (id === "replacement_action") { setStep("replacement_focus"); return; }
    if (id === "change_activity") { void loadActions().then(() => setStep("proposal")); return; }
    if (id === "motivation" && !context?.has_personal_motivation) { setStep("motivation_setup"); return; }
    void beginExercise(id, null);
  };
  const finishAction = async () => {
    if (!sessionId || !actionId || !support || !after) return;
    setBusy(true);
    await eventApi(`/sos/${sessionId}/actions/${actionId}/complete`, { method: "POST", body: JSON.stringify({ intensity_after: after, metadata: toolMetadata }) });
    setUsed(items => ({ ...items, [support]: (items[support] || 0) + 1 })); setStep(actionCompletionStep()); setBusy(false);
  };
  const saveMotivation = async () => {
    const value = customMotivation.trim() || selectedMotivation;
    if (value) {
      await api("/motivation", { method: "PATCH", body: JSON.stringify({ motivation: value }) });
      setContext(current => current ? { ...current, motivation_text: value, has_personal_motivation: true } : current);
    }
    if (support) await beginExercise(support, null);
  };
  const another = () => { setAfter(null); setCurrentBefore(null); setSupport(null); setActionId(null); setToolMetadata(null); setStep("support"); };
  const finishSession = async () => {
    if (!sessionId || !after || !before) return;
    setBusy(true);
    const result = await eventApi<{ intensity_before: number; intensity_after: number }>(`/sos/${sessionId}/complete`, { method: "POST", body: JSON.stringify({ intensity_after: after, nicotine_used_after: false }) });
    setFinalSummary({ before: result.intensity_before, after: result.intensity_after }); setStep("done"); setBusy(false);
  };
  const saveLapse = async () => {
    if (!lapseType) return;
    setBusy(true);
    if (sessionId && (after || before)) await eventApi(`/sos/${sessionId}/complete`, { method: "POST", body: JSON.stringify({ intensity_after: after || before, nicotine_used_after: true }) });
    await eventApi("/lapse", { method: "POST", body: JSON.stringify({ lapse_type: lapseType, trigger_id: trigger }) });
    await onAttemptChanged(); setStep("lapse_done"); setBusy(false);
  };
  const restart = async () => { setBusy(true); await eventApi("/quit-attempt/restart", { method: "POST" }); reset(); await onAttemptRestarted(); };
  const reset = () => { setStep("intro"); setBefore(null); setCurrentBefore(null); setAfter(null); setTrigger(null); setReasonResponse(null); setRememberedReasons([]); setCustomReason(""); setSupport(null); setSessionId(null); setActionId(null); setUsed({}); setPersonalActions([]); setCustomAction(""); setToolMetadata(null); setLapseType(null); setFinalSummary(null); setBusy(false); };

  const gameActive = step === "exercise" && support === "distraction";
  const triggerActive = step === "trigger";
  const triggerStyle = triggerActive
    ? ({ "--air-trigger-viewport-height": `${triggerViewportHeight}px` } as CSSProperties)
    : undefined;
  return <main className={`screen sos-screen${gameActive ? " game-active" : ""}${triggerActive ? " trigger-active" : ""}`} style={triggerStyle}>
    {step === "intro" && <Flow title="Сейчас главное — пройти этот момент" body="Тебе не нужно сейчас решать, как прожить всю жизнь без никотина. Давай пройдём ближайшие несколько минут." icon={<LifeBuoy />}><button className="primary-button" onClick={() => setStep("intensity")}>Начать SOS</button><LapseButton onClick={() => setStep("lapse_type")} /></Flow>}
    {step === "intensity" && <Flow title="Насколько сильно тебе сейчас хочется никотина?" body="Выбери число от 1 до 10."><Scale value={before} onChange={setBefore} /><button className="primary-button" disabled={!before} onClick={() => setStep("trigger")}>Продолжить</button></Flow>}
    {step === "trigger" && <Flow title="Что сейчас вызвало желание?" body="Выбери ситуацию, которая ближе всего."><Options className="sos-trigger-grid" options={context?.triggers || []} value={trigger} onChange={value => { setTrigger(value); setReasonResponse(null); }} primary={context?.primary_triggers} labelFor={option => SOS_TRIGGER_LABELS[option.id] ?? option.label} /><button className="primary-button trigger-cta" disabled={!trigger || busy} onClick={() => trigger === "other" ? void loadReasons() : void start()}>Продолжить</button></Flow>}
    {step === "custom_reason" && <Flow title="Что именно произошло?" body="Можно выбрать прежний вариант или написать новый."><div className="quick-options">{rememberedReasons.map(item => <button key={item.id} onClick={() => { setReasonResponse(item); setTrigger(item.context_id || "other"); void start(item.context_id || "other", item); }}><span>{item.value}</span></button>)}</div><CustomOptionInput label="Новый вариант" value={customReason} onChange={setCustomReason} placeholder="Например: устал после сложного разговора" /><div className="keyboard-safe-actions"><KeyboardSafeSaveButton className="primary-button" disabled={!customReason.trim() || busy} onSave={saveReason}>Сохранить и продолжить</KeyboardSafeSaveButton><button className="secondary-button" onClick={() => setStep("trigger")}>Назад к ситуациям</button></div></Flow>}
    {step === "support" && <Flow title={Object.keys(used).length ? "Что попробуем дальше?" : "Что тебе сейчас больше подходит?"} body={bestTool ? recommendedForTrigger ? "⭐ Этот способ лучше всего помогал в похожей ситуации. Остальные тоже доступны." : "⭐ Этот способ чаще всего помогал тебе. Можно выбрать любой." : "Все способы можно использовать повторно."}><div className="support-grid">{orderedSupports.map(item => <button className={item.id === bestTool ? "recommended" : ""} key={item.id} disabled={busy} onClick={() => chooseSupport(item.id)}>{item.id === bestTool && <span className="tool-star" aria-label="Персональная рекомендация">⭐</span>}<item.icon /><strong>{item.label}</strong><small>{used[item.id] ? `Уже использовано: ${used[item.id]}` : item.hint}</small></button>)}</div><LapseButton onClick={() => setStep("lapse_type")} /></Flow>}
    {step === "replacement_focus" && <Flow title="Что хочется занять?" body="AIR покажет одно конкретное действие."><Options options={[{ id: "mouth", label: "Рот" }, { id: "hands", label: "Руки" }, { id: "both", label: "Руки и рот" }]} value={focus} onChange={value => { setFocus(value as Focus); setProposalHistory([]); }} /><button className="primary-button" onClick={() => void loadActions(focus).then(() => setStep("proposal"))}>Продолжить</button></Flow>}
    {step === "proposal" && support && proposal && <Flow title={support === "change_activity" ? "Попробуй переключиться" : "Попробуй сейчас"} body={trigger === "driving" ? "Безопасность важнее: выполняй действие только без отвлечения от управления." : "Одно небольшое действие — без необходимости делать всё идеально."}>{proposal.personalized_reason && <p className="personal-action-reason">{proposal.personalized_reason}</p>}<div className="action-proposal">{proposal.label}</div><button className="primary-button" disabled={busy} onClick={() => void beginExercise(support, proposal.id, proposal.response_id ?? null)}>Сделаю</button><button className="secondary-button" onClick={() => setProposalHistory(history => recordAction(history, proposal.id))}>Другой вариант</button>{trigger !== "driving" && <button className="secondary-button" onClick={() => { setCustomAction(""); setStep("custom_action"); }}>Свой вариант</button>}</Flow>}
    {step === "custom_action" && support && <Flow title="Свой вариант" body="Напиши одно конкретное действие, которое готов сделать сейчас."><CustomOptionInput label="Моё действие" value={customAction} onChange={setCustomAction} placeholder={support === "replacement_action" ? "Например: жвачка и бутылка воды" : "Например: выйду и пройдусь пять минут"} /><div className="keyboard-safe-actions"><KeyboardSafeSaveButton className="primary-button" disabled={!customAction.trim() || busy} onSave={saveCustomAction}>Сделаю это</KeyboardSafeSaveButton><button className="secondary-button" onClick={() => setStep("proposal")}>Вернуться к вариантам</button></div></Flow>}
    {step === "motivation_setup" && <Flow title="Хочешь оставить напоминание на сложный момент?" body="Можно выбрать готовую причину, написать свою или пропустить."><Options options={MOTIVATION_OPTIONS} value={selectedMotivation} onChange={setSelectedMotivation} /><CustomOptionInput label="Своя причина" value={customMotivation} onChange={setCustomMotivation} placeholder="Написать свою причину (необязательно)" /><div className="keyboard-safe-actions"><KeyboardSafeSaveButton className="primary-button" disabled={busy} onSave={saveMotivation}>Сохранить и продолжить</KeyboardSafeSaveButton><button className="secondary-button" onClick={() => support && void beginExercise(support, null)}>Пропустить</button></div></Flow>}
    {step === "driving_pause" && <Flow title="Сначала остановись безопасно" body="Играй только после безопасной остановки. Игра требует смотреть на экран."><button className="primary-button" onClick={() => support && void beginExercise(support, null)}>Я остановился</button><button className="secondary-button" onClick={() => setStep("support")}>Выбрать другой способ</button></Flow>}
    {step === "exercise" && support && sessionId && actionId && <ToolExercise support={support} context={context} trigger={trigger} proposal={proposal?.label} sessionId={sessionId} actionId={actionId} onComplete={metadata => { setToolMetadata(metadata); setStep(toolCompletionStep()); }} />}
    {step === "after" && <Flow title="Насколько хочется никотина сейчас?" body="Просто отметь текущее значение — любой ответ нормален."><Scale value={after} onChange={setAfter} /><button className="primary-button" disabled={!after || busy} onClick={() => void finishAction()}>Сохранить результат</button></Flow>}
    {step === "result" && currentBefore && after && <Flow title="Что хочешь сделать дальше?" body={`Было: ${currentBefore}/10 · Сейчас: ${after}/10. ${effectText(currentBefore, after)}`} icon={<Check />}><button className="primary-button" onClick={another}><RotateCcw /> Попробовать другой способ</button><button className="secondary-button" disabled={busy} onClick={() => void finishSession()}>Мне уже нормально</button><LapseButton onClick={() => setStep("lapse_type")} /></Flow>}
    {step === "done" && finalSummary && <Flow title="SOS завершён" body={finalSummary.after < finalSummary.before ? `Было ${finalSummary.before}/10 → стало ${finalSummary.after}/10. Этот результат сохранён.` : `Итоговая оценка: ${finalSummary.after}/10. Этот момент сохранён без оценок и давления.`} icon={<Check />}><button className="primary-button" onClick={() => { reset(); onGoHome(); }}>Вернуться на главную</button></Flow>}
    {step === "lapse_type" && <Flow title="Что произошло?" body="Без осуждения. Это событие не сбросит программу."><Options options={[{ id: "single", label: "Один эпизод" }, { id: "multiple", label: "Несколько эпизодов" }, { id: "regular", label: "Я снова начал регулярно употреблять никотин" }]} value={lapseType} onChange={setLapseType} /><button className="primary-button" disabled={!lapseType} onClick={() => setStep("lapse_trigger")}>Продолжить</button></Flow>}
    {step === "lapse_trigger" && <Flow title="Что стало главной причиной?" body="Основные ситуации показаны первыми."><Options options={context?.triggers || []} value={trigger} onChange={setTrigger} primary={context?.primary_triggers} /><button className="primary-button" disabled={!trigger || busy} onClick={() => void saveLapse()}>Сохранить</button></Flow>}
    {step === "lapse_done" && <Flow title="Попытка завершена" body="Предыдущий результат сохранён. Программа AIR продолжается с текущего дня. Ты можешь начать новый отсчёт прямо сейчас или сделать это позже."><button className="primary-button" disabled={busy} onClick={() => void restart()}>Начать новый отказ сейчас</button><button className="secondary-button" onClick={() => { reset(); onGoHome(); }}>Сделать это позже</button></Flow>}
  </main>;
}

function ToolExercise({ support, context, trigger, proposal, sessionId, actionId, onComplete }: { support: SupportType; context: SupportContext | null; trigger: string | null; proposal?: string; sessionId: number; actionId: number; onComplete: (metadata: Record<string, unknown>) => void }) {
  if (support === "breathing") return <Flow title="Квадратное дыхание" body="Следуй за маркером по сторонам квадрата."><SquareBreathing onComplete={onComplete} /></Flow>;
  if (support === "distraction") return <Flow title="Выше облаков" body="Помоги облачку AIR подниматься всё выше. Нажимай на левую или правую половину поля."><AirCloudGame initialBestHeight={context?.game_best_height || 0} onRecord={metadata => eventApi<{ metadata: CloudGameMetadata; new_record: boolean }>(`/sos/${sessionId}/actions/${actionId}/game-result`, { method: "POST", body: JSON.stringify({ height: metadata.height, jumps: metadata.jumps, duration_seconds: metadata.duration_seconds, boosts_used: metadata.boosts_used }) })} onComplete={onComplete} /></Flow>;
  if (support === "motivation") return <Flow title="Твоя причина всё ещё с тобой" body="Вернись к тому, ради чего ты начал."><MotivationCard context={context} /><button className="primary-button" onClick={() => onComplete({ viewed: true })}>Оценить желание сейчас</button></Flow>;
  if (support === "personal_plan") return <PersonalPlanExercise context={context} trigger={trigger} onComplete={onComplete} />;
  if (support === "ai_support") return <Flow title="Поговорить с AIR" body="Персональная поддержка AIR появится здесь. Будущий помощник сможет учитывать твою историю и ситуации."><p className="sos-mantra">Желание — это не приказ.</p><button className="primary-button" onClick={() => onComplete({ placeholder_viewed: true })}>Оценить желание сейчас</button></Flow>;
  return <Flow title="Сделай это сейчас" body={proposal || "Одно небольшое действие поможет разорвать автоматический сценарий."}><div className="action-proposal">{proposal}</div><button className="primary-button" onClick={() => onComplete({ action_completed: true })}>Готово — оценить желание</button></Flow>;
}
function PersonalPlanExercise({ context, trigger, onComplete }: { context: SupportContext | null; trigger: string | null; onComplete: (metadata: Record<string, unknown>) => void }) {
  const contextual = trigger ? context?.personal_plan.by_category[TRIGGER_PLAN_CATEGORY[trigger]] : undefined;
  const [selected, setSelected] = useState(contextual ?? null);
  const [stepIndex, setStepIndex] = useState(0);
  const item = selected;
  if (!item) return <Flow title="Мой план" body="Для этой ситуации отдельного плана пока нет. Ниже — сохранённые стратегии без привязки к текущему триггеру."><div className="personal-plan-list">{context?.personal_plan.items.map(plan => <button key={plan.category} onClick={() => { setSelected(plan); setStepIndex(0); }}><strong>{formatProgramLabel(plan.category_label || plan.category)}</strong><small>{plan.steps.length} шаг.</small></button>)}</div></Flow>;
  const currentStep = item.steps[stepIndex];
  const isLast = stepIndex >= item.steps.length - 1;
  const categoryLabel = formatProgramLabel(item.category_label || item.category);
  return <Flow title={contextual ? `Мой план: ${categoryLabel}` : categoryLabel} body={contextual ? "Этот план относится именно к выбранной ситуации." : "Ты выбрал этот раздел из всего личного плана."}>{item.reasons?.length > 0 && <div className="plan-reasons"><small>Причина / ситуация</small>{item.reasons.map(reason => <strong key={reason}>{formatProgramText(reason)}</strong>)}</div>}<div className="personal-plan-step"><small>Твой план · шаг {stepIndex + 1} из {item.steps.length}</small><strong>{formatProgramText(currentStep)}</strong></div><button className="primary-button" onClick={() => isLast ? onComplete({ category: item.category, source_day: item.source_day, steps_completed: item.steps.length }) : setStepIndex(value => value + 1)}>{isLast ? "Готово — оценить желание" : "Готово — следующий шаг"}</button>{contextual && context && context.personal_plan.items.length > 1 && <button className="secondary-button" onClick={() => setSelected(null)}>Весь мой план</button>}</Flow>;
}
function MotivationCard({ context }: { context: SupportContext | null }) { const stats = context?.motivation_stats; return <div className="motivation-card"><small>Ты решил отказаться от никотина потому что:</small><strong>{context?.motivation_text || "Хочешь вернуть себе свободу выбора."}</strong>{stats && <div>{stats.elapsed_seconds > 0 && <span>Без никотина: {formatElapsed(stats.elapsed_seconds)}</span>}{stats.money_saved > 0 && <span>Не потрачено: {Math.round(stats.money_saved).toLocaleString("ru-RU")} ₽</span>}{stats.cravings_survived > 0 && <span>Пережито желаний: {stats.cravings_survived}</span>}</div>}</div>; }
function effectText(before: number, after: number) { const effect = before - after; if (effect > 0) return `Стало легче на ${effect} ${effect === 1 ? "пункт" : "пункта"}.`; if (effect === 0) return "Желание пока осталось на том же уровне."; return "Сейчас желание стало сильнее. Можно попробовать другой способ."; }
function formatElapsed(seconds: number) { const days = Math.floor(seconds / 86400); const hours = Math.floor((seconds % 86400) / 3600); return days > 0 ? `${days} д ${hours} ч` : `${hours} ч`; }
function Flow({ title, body, icon, children }: { title: string; body: string; icon?: ReactNode; children: ReactNode }) { return <section className="sos-flow">{icon && <div className="pulse">{icon}</div>}<p className="eyebrow">AIR рядом</p><h1>{title}</h1><p className="flow-body">{body}</p>{children}</section>; }
function LapseButton({ onClick }: { onClick: () => void }) { return <button className="lapse-button" onClick={onClick}>Я употребил никотин</button>; }
