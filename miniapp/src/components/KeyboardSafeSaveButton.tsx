import { useRef } from "react";
import type { ButtonHTMLAttributes, PointerEvent as ReactPointerEvent } from "react";
import { KeyboardSafeSaveController } from "./keyboardSafeSave";

type SaveSource = "pointer" | "click";

type Props = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "onClick" | "onPointerDown"> & {
  onSave: () => void | Promise<void>;
};

export function KeyboardSafeSaveButton({ onSave, className = "", type = "button", ...props }: Props) {
  const controllerRef = useRef(new KeyboardSafeSaveController());

  const blurFocusedInput = () => {
    const active = document.activeElement;
    if (active instanceof HTMLElement && active.matches("[data-keyboard-aware-input]")) active.blur();
  };
  const save = (source: SaveSource) => {
    controllerRef.current.activate(source, onSave, blurFocusedInput);
  };
  const onPointerDown = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (!event.isPrimary || event.button !== 0 || props.disabled) return;
    event.preventDefault();
    save("pointer");
  };

  return <button
    {...props}
    type={type}
    className={`${className} keyboard-safe-save-button`.trim()}
    onPointerDown={onPointerDown}
    onClick={event => {
      event.preventDefault();
      if (!props.disabled) save("click");
    }}
  />;
}
