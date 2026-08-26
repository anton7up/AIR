import { useEffect } from "react";
import { ensureInputActionsVisible, KeyboardAdjustmentGuard } from "./ensureInputActionsVisible";

export const MOBILE_INPUT_FONT_SIZE = 16;
export const KEYBOARD_THRESHOLD_PX = 120;

export type KeyboardViewport = {
  height: number;
  offsetTop: number;
  focused: boolean;
  keyboardOpen: boolean;
};

export function calculateKeyboardViewport(
  layoutHeight: number,
  visualHeight: number,
  offsetTop: number,
  focused: boolean,
): KeyboardViewport {
  const height = Math.max(1, Math.round(visualHeight || layoutHeight));
  return {
    height,
    offsetTop: Math.max(0, Math.round(offsetTop)),
    focused,
    keyboardOpen: focused && layoutHeight - height > KEYBOARD_THRESHOLD_PX,
  };
}

function isKeyboardInput(target: EventTarget | null): target is HTMLElement {
  return target instanceof HTMLElement && target.matches("[data-keyboard-aware-input]");
}

/** Keeps the visible Telegram/iOS viewport and focused fields in sync with CSS. */
export function useKeyboardAwareViewport(): void {
  useEffect(() => {
    const root = document.documentElement;
    const body = document.body;
    let focused: HTMLElement | null = null;
    let blurTimer = 0;
    let focusTimer = 0;
    let firstAdjustmentFrame = 0;
    let secondAdjustmentFrame = 0;
    const adjustmentGuard = new KeyboardAdjustmentGuard();
    let layoutBaseline = Math.max(
      window.innerHeight,
      document.documentElement.clientHeight,
      window.Telegram?.WebApp.viewportStableHeight ?? 0,
    );

    const cancelPendingAdjustment = () => {
      window.cancelAnimationFrame(firstAdjustmentFrame);
      window.cancelAnimationFrame(secondAdjustmentFrame);
      firstAdjustmentFrame = 0;
      secondAdjustmentFrame = 0;
    };
    const scheduleAdjustment = (visibleBottom: number) => {
      if (!focused || !adjustmentGuard.canAdjust()) return;
      cancelPendingAdjustment();
      firstAdjustmentFrame = window.requestAnimationFrame(() => {
        secondAdjustmentFrame = window.requestAnimationFrame(() => {
          if (!focused || !body.classList.contains("air-keyboard-open") || !adjustmentGuard.canAdjust()) return;
          adjustmentGuard.markAdjusted();
          ensureInputActionsVisible(focused, visibleBottom);
        });
      });
    };
    const update = () => {
      const viewport = window.visualViewport;
      if (focused === null) {
        layoutBaseline = Math.max(layoutBaseline, window.innerHeight, document.documentElement.clientHeight, window.Telegram?.WebApp.viewportStableHeight ?? 0);
      }
      const state = calculateKeyboardViewport(
        layoutBaseline,
        viewport?.height ?? window.Telegram?.WebApp.viewportHeight ?? window.innerHeight,
        viewport?.offsetTop ?? 0,
        focused !== null,
      );
      root.style.setProperty("--app-viewport-height", `${state.height}px`);
      root.style.setProperty("--app-viewport-offset-top", `${state.offsetTop}px`);
      body.classList.toggle("air-keyboard-open", state.keyboardOpen);
      if (state.keyboardOpen) scheduleAdjustment(state.offsetTop + state.height);
      else {
        cancelPendingAdjustment();
        adjustmentGuard.reset();
      }
    };
    const onFocus = (event: FocusEvent) => {
      if (!isKeyboardInput(event.target)) return;
      window.clearTimeout(blurTimer);
      window.clearTimeout(focusTimer);
      focused = event.target;
      adjustmentGuard.reset();
      update();
      focusTimer = window.setTimeout(update, 60);
    };
    const onBlur = (event: FocusEvent) => {
      if (!isKeyboardInput(event.target)) return;
      focused = null;
      cancelPendingAdjustment();
      adjustmentGuard.reset();
      body.classList.remove("air-keyboard-open");
      blurTimer = window.setTimeout(() => {
        if (isKeyboardInput(document.activeElement)) {
          focused = document.activeElement;
          update();
          return;
        }
        update();
      }, 80);
    };

    const telegram = window.Telegram?.WebApp;
    update();
    window.visualViewport?.addEventListener("resize", update);
    window.visualViewport?.addEventListener("scroll", update);
    window.addEventListener("resize", update);
    window.addEventListener("orientationchange", update);
    document.addEventListener("focusin", onFocus);
    document.addEventListener("focusout", onBlur);
    telegram?.onEvent?.("viewportChanged", update);
    return () => {
      window.clearTimeout(blurTimer);
      window.clearTimeout(focusTimer);
      cancelPendingAdjustment();
      window.visualViewport?.removeEventListener("resize", update);
      window.visualViewport?.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
      window.removeEventListener("orientationchange", update);
      document.removeEventListener("focusin", onFocus);
      document.removeEventListener("focusout", onBlur);
      telegram?.offEvent?.("viewportChanged", update);
      body.classList.remove("air-keyboard-open");
      root.style.removeProperty("--app-viewport-height");
      root.style.removeProperty("--app-viewport-offset-top");
    };
  }, []);
}
