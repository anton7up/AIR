import { Check, X } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { StepOption, SupportContext } from "../types";

export function NicotineDesireModal({ onClose }: { onClose: (saved: boolean) => void }) {
  const [context, setContext] = useState<SupportContext | null>(null);
  const [step, setStep] = useState(0);
  const [intensity, setIntensity] = useState<number | null>(null);
  const [trigger, setTrigger] = useState<string | null>(null);
  const [emotion, setEmotion] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { void api<SupportContext>("/support-context").then(setContext); }, []);
  const save = async () => {
    if (!intensity) return;
    setBusy(true);
    await api("/nicotine-desire", { method: "POST", body: JSON.stringify({ intensity, trigger_id: trigger, emotion, note }) });
    setStep(4); setBusy(false);
  };
  return <div className="modal-backdrop"><section className="flow-modal" role="dialog" aria-modal="true">
    <button className="modal-close" onClick={() => onClose(false)} aria-label="Закрыть"><X /></button>
    {step < 4 && <div className="mini-progress"><i style={{ width: `${(step + 1) * 25}%` }} /></div>}
    {step === 0 && <><p className="eyebrow">Отметить желание</p><h2>Насколько сильно тебе сейчас хочется никотина?</h2><Scale value={intensity} onChange={setIntensity} /><Next disabled={!intensity} onClick={() => setStep(1)} /></>}
    {step === 1 && <><p className="eyebrow">Что происходит</p><h2>Что сейчас вызвало желание?</h2><Options options={context?.triggers || []} value={trigger} onChange={setTrigger} primary={context?.primary_triggers} /><Next disabled={!trigger} onClick={() => setStep(2)} /></>}
    {step === 2 && <><p className="eyebrow">Твоё состояние</p><h2>Что ты сейчас чувствуешь?</h2><Options options={context?.emotions || []} value={emotion} onChange={setEmotion} /><Next disabled={!emotion} onClick={() => setStep(3)} /></>}
    {step === 3 && <><p className="eyebrow">Необязательно</p><h2>Что произошло прямо перед этим?</h2><textarea data-keyboard-aware-input className="step-text" value={note} onChange={event => setNote(event.target.value)} placeholder="Можно добавить короткую заметку" /><div className="keyboard-safe-actions"><button className="primary-button" disabled={busy} onClick={() => void save()}>{busy ? "Сохраняем…" : "Сохранить"}</button></div></>}
    {step === 4 && <div className="saved-state"><Check /><h2>Записано</h2><p>Ничего специально менять сейчас не нужно. AIR собирает твою персональную картину.</p><button className="primary-button" onClick={() => onClose(true)}>Готово</button></div>}
  </section></div>;
}

export function Scale({ value, onChange }: { value: number | null; onChange: (value: number) => void }) {
  return <div className="scale-row">{Array.from({ length: 10 }, (_, index) => index + 1).map(number => <button className={value === number ? "selected" : ""} onClick={() => onChange(number)} key={number}>{number}</button>)}</div>;
}

export function Options({ options, value, onChange, primary = [], className = "", labelFor }: { options: StepOption[]; value: string | null; onChange: (value: string) => void; primary?: string[]; className?: string; labelFor?: (option: StepOption) => string }) {
  return <div className={`quick-options${className ? ` ${className}` : ""}`}>{options.map(option => <button className={value === option.id ? "selected" : ""} onClick={() => onChange(option.id)} key={option.id}><span>{labelFor?.(option) ?? option.label}{primary.includes(option.id) && <small>Основная</small>}</span>{value === option.id && <Check />}</button>)}</div>;
}
function Next({ disabled, onClick }: { disabled: boolean; onClick: () => void }) { return <button className="primary-button" disabled={disabled} onClick={onClick}>Продолжить</button>; }
