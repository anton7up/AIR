import { ArrowDown, Award, BarChart3, CheckCircle2, Lightbulb, Quote, Target, Wind } from "lucide-react";
import type { ProgramStep, StructuredStepValue } from "../../types";
import { ChoiceStep, OrderedChoiceStep } from "./ChoiceStep";
import { formatProgramLabel, formatProgramText } from "../../program/labels";
import { hasPreparedCardContent } from "./personalizedCards";

export type StepValue = string | string[] | number | StructuredStepValue | null;
export function ProgramStepRenderer({ step, value, onChange, onCustomSave }: { step: ProgramStep; value: StepValue; onChange: (value: StepValue) => void; onCustomSave?: (value: StepValue) => void }) {
  const choiceTypes = ["multi_select", "single_select", "priority_select", "action_picker", "scenario_choice"];
  if (choiceTypes.includes(step.type)) {
    const selected = typeof value === "string" ? value : null;
    return <>
      <ChoiceStep options={step.options} value={typeof value === "string" || Array.isArray(value) ? value : null} multiple={step.type === "multi_select"} max={step.max_selections} allowOther={step.content.allow_other} otherPlaceholder={step.content.other_placeholder} rememberedOptions={step.content.remembered_options} onChange={onChange} onCustomSave={onCustomSave} />
      {selected && step.content.reactions?.[selected] && <div className="choice-reaction"><Lightbulb /> <p>{step.content.reactions[selected]}</p></div>}
    </>;
  }
  if (step.type === "ordered_select") {
    const selected = Array.isArray(value) ? value : [];
    return <OrderedChoiceStep options={step.options} value={selected} max={step.max_selections} allowOther={step.content.allow_other} otherPlaceholder={step.content.other_placeholder} rememberedOptions={step.content.remembered_options} onChange={onChange} onCustomSave={onCustomSave} />;
  }
  if (step.type === "plan_builder") {
    const current = value && typeof value === "object" && !Array.isArray(value) ? value : {};
    return <div className="plan-builder">{step.builder_fields?.map((field, index) => {
      const excluded = field.exclude_answer ? current[field.exclude_answer] : null;
      return <section key={field.id}>
        <small>Шаг {index + 1}</small><h3>{field.label}</h3>
        <ChoiceStep options={field.options.filter(option => option.id !== excluded)} value={current[field.id] ?? null} multiple={false} max={null} allowOther={field.allow_other} otherPlaceholder={field.other_placeholder} rememberedOptions={field.remembered_options} onChange={fieldValue => onChange({ ...current, [field.id]: fieldValue as string })} onCustomSave={fieldValue => onCustomSave?.({ ...current, [field.id]: fieldValue as string })} />
      </section>;
    })}</div>;
  }
  if (step.type === "comparison" && step.comparison) {
    const current = value && typeof value === "object" && !Array.isArray(value) ? value : {};
    return <div className="comparison-flow">{step.comparison.items.map(item => <section key={item.id}>
      <h3>{item.label}</h3>
      <div>{step.comparison!.scale.map(option => <button type="button" key={option.id} className={current[item.id] === option.id ? "selected" : ""} onClick={() => onChange({ ...current, [item.id]: option.id })}>{option.label}</button>)}</div>
    </section>)}</div>;
  }
  if (step.type === "result_card" && step.result) return <PersonalPlanCard title={step.result.title} items={step.result.items} style={step.result.style} />;
  if (step.type === "scale") return <div className="scale-row">{Array.from({ length: 10 }, (_, i) => i + 1).map(number => <button className={value === number ? "selected" : ""} onClick={() => onChange(number)} key={number}>{number}</button>)}</div>;
  if (step.type === "text") return <textarea data-keyboard-aware-input className="step-text" value={typeof value === "string" ? value : ""} onChange={event => onChange(event.target.value)} placeholder={step.content.placeholder ?? "Можно оставить пустым"} />;
  if (step.type === "structured_input") {
    const current = value && typeof value === "object" && !Array.isArray(value) ? value : {};
    return <div className="structured-input">{step.content.fields?.map(field => <label key={field.id}>
      <span>{field.label}</span>
      <textarea data-keyboard-aware-input maxLength={field.response_type ? 500 : 2000} value={current[field.id] ?? ""} placeholder={field.placeholder} onChange={event => onChange({ ...current, [field.id]: event.target.value })} />
    </label>)}</div>;
  }
  if (step.type === "theory") return <article className="theory-card">
    <Quote />
    <div className="theory-copy">{step.body.split(/\n\s*\n/).map((paragraph, index) => <p key={index}>{paragraph}</p>)}</div>
    {step.content.highlight && <strong className="theory-highlight">{step.content.highlight}</strong>}
  </article>;
  if (step.type === "personalized_insight" && step.insight) return <article className={`personal-insight ${step.insight.is_fallback ? "fallback" : ""} ${step.insight.body ? "" : "compact-custom"}`}>
    <small>{step.insight.is_fallback ? "Осторожная гипотеза" : "На основе твоих данных"}</small>
    <h3>{step.insight.title}</h3>{step.insight.body && <p>{step.insight.body}</p>}{step.insight.plan_items?.length ? <div className="insight-plan-list">{step.insight.plan_items.map(item => <section key={item.category}><strong>{formatProgramLabel(item.category_label || item.category)}</strong>{item.reasons?.length > 0 && <small>Причина: {item.reasons.map(reason => formatProgramText(reason)).join(" · ")}</small>}<span>{item.steps.map(planStep => formatProgramText(planStep)).join(" → ")}</span></section>)}</div> : null}
  </article>;
  if (step.type === "selected_insights") return <div className="selected-insights">{step.insights?.length ? step.insights.map(item => <article key={item.id}><Lightbulb /><p>{item.text}</p></article>) : <article><p>Ты не выбрал отдельные пункты — продолжим без предположений.</p></article>}</div>;
  if (step.type === "checkpoint") return <div className="checkpoint-grid">{step.analytics?.map(card => <article key={`${card.label}-${card.value}`}><BarChart3 /><small>{card.label}</small><strong>{card.value}</strong>{card.note && <p>{card.note}</p>}</article>)}</div>;
  if (step.type === "personalized_cards") return <div className="personal-cards">{step.cards?.map(card => {
    const hasPreparedContent = hasPreparedCardContent(card);
    return <article key={card.id} className={hasPreparedContent ? "" : "compact-custom"}><h3>{card.title}</h3>{hasPreparedContent && <><strong>Почему так происходит</strong><p>{card.why_it_happens}</p><strong>Что будем делать</strong><p>{card.first_tip}</p></>}</article>;
  })}</div>;
  if (step.type === "personalized_summary" && step.summary) return <div className="start-map">
    <Summary title="Главная причина" items={step.summary.primary_reason ? [step.summary.primary_reason] : []} />
    <Summary title="Основные ситуации" items={step.summary.primary_triggers} />
    <Summary title="Что ты ищешь в никотине" items={step.summary.beliefs} />
    <Summary title="Что тебя беспокоит" items={step.summary.concerns} />
  </div>;
  const Icon = step.type === "start" ? Wind : step.type === "task" ? Target : step.type === "completion" ? Award : Lightbulb;
  return <div className={`step-message ${step.type}`}><Icon size={42} /><div className="message-copy">{step.body.split(/\n\s*\n/).map((paragraph, index) => <p key={index}>{paragraph}</p>)}</div>{step.type === "completion" && <div className="achievement"><CheckCircle2 /> {step.options[0]?.label}</div>}</div>;
}

function PersonalPlanCard({ title, items, style }: { title: string; items: { label: string; value: string }[]; style: string }) {
  return <article className={`personal-plan-card ${style}`}><small>Персональный результат</small><h2>{title}</h2><div>{items.map((item, index) => <section key={`${item.label}-${index}`}>
    <span>{formatProgramLabel(item.label)}</span><strong>{formatProgramText(item.value)}</strong>{index < items.length - 1 && <ArrowDown />}
  </section>)}</div></article>;
}

function Summary({ title, items }: { title: string; items: string[] }) {
  return <div><small>{title}</small>{items.length ? items.map((item, index) => <strong key={`${item}-${index}`}>{formatProgramText(item)}</strong>) : <strong>Пока не выбрано</strong>}</div>;
}
