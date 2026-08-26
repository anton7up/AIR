import { ArrowLeft } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { Loading } from "../components/Loading";
import { ProgramStepRenderer, type StepValue } from "../components/program/ProgramStepRenderer";
import { normalizeLegacyCustomState } from "../components/program/customOption";
import type { ProgramDayDetail } from "../types";

function initialValue(data: ProgramDayDetail) {
  if (data.step.value !== null && data.step.value !== undefined) {
    if (["multi_select", "ordered_select", "single_select", "priority_select", "action_picker", "scenario_choice", "plan_builder"].includes(data.step.type)) {
      return normalizeLegacyCustomState(data.step.value) as StepValue;
    }
    return data.step.value;
  }
  if (["multi_select", "ordered_select"].includes(data.step.type)) return [];
  if (["structured_input", "plan_builder", "comparison"].includes(data.step.type)) return {};
  return null;
}

function isEmpty(data: ProgramDayDetail, value: StepValue) {
  const emptyCustom = (item: unknown) => typeof item === "string" && item.startsWith("custom:") && !item.slice("custom:".length).trim();
  if (value === null || value === "" || emptyCustom(value)) return true;
  if (Array.isArray(value)) return value.length === 0 || value.some(emptyCustom) || (data.step.type === "ordered_select" && value.length !== data.step.max_selections);
  if (typeof value === "object") {
    if (data.step.type === "plan_builder") return data.step.builder_fields?.some(field => !value[field.id] || emptyCustom(value[field.id])) ?? true;
    if (data.step.type === "comparison") return data.step.comparison?.items.some(item => !value[item.id]) ?? true;
    return !Object.values(value).length || Object.values(value).some(item => !item.trim());
  }
  return false;
}

export function ProgramDayScreen({ dayNumber, devPreview = false, onBack, onCompleted }: { dayNumber: number; devPreview?: boolean; onBack: () => void; onCompleted: () => void }) {
  const [data, setData] = useState<ProgramDayDetail | null>(null);
  const [value, setValue] = useState<StepValue>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [confirmReset, setConfirmReset] = useState(false);
  const basePath = devPreview ? `/dev/program/${dayNumber}` : `/program/${dayNumber}`;
  useEffect(() => {
    api<ProgramDayDetail>(basePath)
      .then((loaded) => {
        setData(loaded);
        setValue(initialValue(loaded));
      })
      .catch((err) => setError(err.message));
  }, [basePath]);
  if (!data) return error ? <div className="inline-error">{error}<button onClick={onBack}>Назад</button></div> : <Loading />;
  const requiredEmpty = data.step.required && isEmpty(data, value);
  const next = async () => {
    setBusy(true); setError("");
    try {
      if (data.step.type === "completion") {
        const completed = await api<ProgramDayDetail>(`${basePath}/complete`, { method: "POST" });
        if (devPreview) { setData(completed); return; }
        onCompleted(); return;
      }
      const updated = await api<ProgramDayDetail>(`${basePath}/state`, { method: "POST", body: JSON.stringify({ step_id: data.step.id, value }) });
      setData(updated);
      setValue(initialValue(updated));
    } catch (err) { setError(err instanceof Error ? err.message : "Не удалось сохранить ответ"); }
    finally { setBusy(false); }
  };
  const resetPreview = async () => {
    setBusy(true); setError("");
    try {
      const reset = await api<ProgramDayDetail>(`${basePath}/reset`, { method: "POST" });
      setData(reset); setValue(initialValue(reset)); setConfirmReset(false);
    } catch (err) { setError(err instanceof Error ? err.message : "Не удалось сбросить DEV-ответы"); }
    finally { setBusy(false); }
  };
  const saveDraft = async (draftValue: StepValue) => {
    setError("");
    try {
      const updated = await api<ProgramDayDetail>(`${basePath}/draft`, { method: "POST", body: JSON.stringify({ step_id: data.step.id, value: draftValue }) });
      setData(updated);
      setValue(initialValue(updated));
    } catch (err) { setError(err instanceof Error ? err.message : "Не удалось сохранить свой вариант"); }
  };
  if (devPreview && data.completed) return <main className="screen program-session">
    <button className="back-button" onClick={onBack}><ArrowLeft /> Программа</button>
    <div className="dev-preview-panel"><span className="dev-mode-badge">DEV preview · День {dayNumber}</span><h1>Тестовое прохождение завершено</h1><p>Настоящий прогресс программы не изменён.</p><button className="primary-button" disabled={busy} onClick={() => void resetPreview()}>Пройти ещё раз</button><button className="secondary-button" onClick={onBack}>Вернуться в программу</button></div>
  </main>;
  return <main className="screen program-session">
    <button className="back-button" onClick={onBack}><ArrowLeft /> Программа</button>
    {devPreview && <div className="dev-preview-toolbar"><span className="dev-mode-badge">DEV preview</span><button onClick={() => setConfirmReset(true)}>Сбросить тестовые ответы дня</button></div>}
    {devPreview && confirmReset && <div className="dev-reset-confirm"><strong>Сбросить тестовые ответы Дня {dayNumber}?</strong><div><button className="danger-button" disabled={busy} onClick={() => void resetPreview()}>Сбросить</button><button className="secondary-button" onClick={() => setConfirmReset(false)}>Отмена</button></div></div>}
    <div className="step-progress"><i style={{ width: `${((data.step_index + 1) / data.total_steps) * 100}%` }} /></div>
    <p className="eyebrow">День {data.number} · шаг {data.step_index + 1} из {data.total_steps}</p>
    <h1>{data.step.title}</h1>{data.step.body && ["single_select", "multi_select", "priority_select", "action_picker", "scenario_choice", "ordered_select", "plan_builder", "comparison", "scale", "text", "structured_input"].includes(data.step.type) && <p className="step-body">{data.step.body}</p>}
    <ProgramStepRenderer step={data.step} value={value} onChange={setValue} onCustomSave={draftValue => void saveDraft(draftValue)} />
    {data.step.type === "task" && <div className="task-counter">Отмечено сегодня: <strong>{data.task_progress} / 3</strong></div>}
    {error && <p className="form-error">{error}</p>}
    <button className="primary-button step-continue" disabled={busy || requiredEmpty} onClick={next}>{busy ? "Сохраняем…" : data.step.button_text}</button>
  </main>;
}
