import { useLayoutEffect, useState } from "react";
import type { StepOption } from "../../types";
import { KeyboardSafeSaveButton } from "../KeyboardSafeSaveButton";
import { isValidSaveDraft } from "../keyboardSafeSave";
import { choiceIsSelected, completeOtherAnswer, customAnswerText, mergeDisplayChoices, removeChoiceSelection, sanitizeSelections, selectRememberedAnswer } from "./customOption";

function syncEditorBodyClass() {
  window.requestAnimationFrame(() => {
    document.body.classList.toggle("air-custom-editor-open", Boolean(document.querySelector('[data-custom-editor-open="true"]')));
  });
}

export function CustomOptionInput({ value, placeholder, label = "Твой вариант", saveLabel = "Сохранить", onChange, onSave }: {
  value: string; placeholder?: string; label?: string; saveLabel?: string; onChange: (value: string) => void; onSave?: () => void;
}) {
  const resize = (element: HTMLTextAreaElement) => {
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, 180)}px`;
  };
  return <div className="custom-editor" data-custom-editor-open="true">
    <label className="custom-option-input"><span>{label}</span><textarea data-keyboard-aware-input maxLength={500} rows={3} value={value} onInput={event => resize(event.currentTarget)} onFocus={event => resize(event.currentTarget)} onChange={event => onChange(event.target.value)} placeholder={placeholder || "Напиши свой вариант"} /></label>
    {onSave && <KeyboardSafeSaveButton className="primary-button custom-save-button" disabled={!isValidSaveDraft(value)} onSave={onSave}>{saveLabel}</KeyboardSafeSaveButton>}
  </div>;
}

export function ChoiceStep({ options, value, multiple, max, allowOther = false, otherPlaceholder, rememberedOptions = [], onChange, onCustomSave }: {
  options: StepOption[]; value: string | string[] | null; multiple: boolean;
  max: number | null; allowOther?: boolean; otherPlaceholder?: string; rememberedOptions?: { id: number; value: string }[]; onChange: (value: string | string[]) => void; onCustomSave?: (value: string | string[]) => void;
}) {
  const selected = sanitizeSelections(value);
  const [isOtherEditorOpen, setOtherEditorOpen] = useState(false);
  const [customDraft, setCustomDraft] = useState("");
  const visibleOptions = mergeDisplayChoices(
    options.filter(option => option.id !== "other" && option.id !== "__other__"),
    rememberedOptions.map(item => item.value),
    selected,
  );

  useLayoutEffect(() => {
    syncEditorBodyClass();
    return syncEditorBodyClass;
  }, [isOtherEditorOpen]);

  const toggle = (id: string) => {
    setOtherEditorOpen(false); setCustomDraft("");
    const rememberedText = customAnswerText(id);
    if (rememberedText) { chooseRemembered(rememberedText); return; }
    if (!multiple) { onChange(id); return; }
    const option = visibleOptions.find(item => item.id === id);
    if (option && choiceIsSelected(option, selected)) onChange(removeChoiceSelection(option, selected));
    else if (!max || selected.length < max) onChange([...selected, id]);
  };
  const chooseRemembered = (text: string) => {
    const result = selectRememberedAnswer(selected, text, multiple, max);
    setOtherEditorOpen(result.editor.isOpen); setCustomDraft(result.editor.draft);
    onChange(result.selected);
    onCustomSave?.(result.selected);
  };
  const saveOther = () => {
    const text = customDraft.trim();
    if (!text) return;
    const result = completeOtherAnswer(selected, text, multiple, max);
    onChange(result.selected);
    onCustomSave?.(result.selected);
    setCustomDraft(result.editor.draft);
    setOtherEditorOpen(result.editor.isOpen);
  };

  return <div className="step-choices">
    {multiple && <p className="selection-count">Выбрано: {selected.length}{max ? ` из ${max}` : ""}</p>}
    {visibleOptions.map(option => <button type="button" key={option.id} className={choiceIsSelected(option, selected) ? "selected" : ""} onClick={() => toggle(option.id)}>
      <span>{option.label}</span><i>{choiceIsSelected(option, selected) ? "✓" : ""}</i>
    </button>)}
    {allowOther && <button type="button" aria-expanded={isOtherEditorOpen} className={isOtherEditorOpen ? "selected other-action" : "other-action"} onClick={() => { setCustomDraft(""); setOtherEditorOpen(current => !current); }}><span>➕ Другое</span><i>{isOtherEditorOpen ? "✓" : ""}</i></button>}
    {isOtherEditorOpen && <CustomOptionInput value={customDraft} placeholder={otherPlaceholder} onChange={setCustomDraft} onSave={saveOther} />}
  </div>;
}

export function OrderedChoiceStep({ options, value, max, allowOther = false, otherPlaceholder, rememberedOptions = [], onChange, onCustomSave }: {
  options: StepOption[]; value: string[]; max: number | null; allowOther?: boolean; otherPlaceholder?: string;
  rememberedOptions?: { id: number; value: string }[]; onChange: (value: string[]) => void; onCustomSave?: (value: string[]) => void;
}) {
  const selected = sanitizeSelections(value);
  const [isOtherEditorOpen, setOtherEditorOpen] = useState(false);
  const [customDraft, setCustomDraft] = useState("");
  const available = mergeDisplayChoices(
    options.filter(option => option.id !== "other" && option.id !== "__other__"),
    rememberedOptions.map(item => item.value),
    selected,
  );

  useLayoutEffect(() => {
    syncEditorBodyClass();
    return syncEditorBodyClass;
  }, [isOtherEditorOpen]);

  const toggle = (id: string) => {
    const option = available.find(item => item.id === id);
    const position = option ? selected.findIndex(value => choiceIsSelected(option, [value])) : -1;
    const next = position >= 0 && option ? removeChoiceSelection(option, selected) : (!max || selected.length < max) ? [...selected, id] : selected;
    onChange(next);
    if (customAnswerText(id)) onCustomSave?.(next);
    setOtherEditorOpen(false); setCustomDraft("");
  };
  const saveOther = () => {
    const result = completeOtherAnswer(selected, customDraft, true, max);
    const next = Array.isArray(result.selected) ? result.selected : [result.selected];
    onChange(next); onCustomSave?.(next);
    setCustomDraft(result.editor.draft); setOtherEditorOpen(result.editor.isOpen);
  };

  return <div className="ordered-picker">
    <p className="selection-count">Выбрано: {selected.length}{max ? ` из ${max}` : ""}</p>
    {available.map(option => {
      const position = selected.findIndex(value => choiceIsSelected(option, [value]));
      return <button type="button" key={option.id} className={position >= 0 ? "selected" : ""} onClick={() => toggle(option.id)}><i>{position >= 0 ? position + 1 : ""}</i><span>{option.label}</span></button>;
    })}
    {allowOther && <button type="button" aria-expanded={isOtherEditorOpen} className={isOtherEditorOpen ? "selected other-action" : "other-action"} onClick={() => { setCustomDraft(""); setOtherEditorOpen(current => !current); }}><i>{isOtherEditorOpen ? "✓" : ""}</i><span>➕ Другое</span></button>}
    {isOtherEditorOpen && <CustomOptionInput value={customDraft} placeholder={otherPlaceholder} onChange={setCustomDraft} onSave={saveOther} />}
  </div>;
}
