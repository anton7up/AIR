export const INPUT_ACTION_SAFE_MARGIN_PX = 16;

export function calculateActionScrollDelta(
  actionBottom: number,
  visibleBottom: number,
  safeMargin = INPUT_ACTION_SAFE_MARGIN_PX,
): number {
  return Math.max(0, Math.ceil(actionBottom - (visibleBottom - safeMargin)));
}

export class KeyboardAdjustmentGuard {
  private adjusted = false;

  canAdjust(): boolean {
    return !this.adjusted;
  }

  markAdjusted(): void {
    this.adjusted = true;
  }

  reset(): void {
    this.adjusted = false;
  }
}

function isScrollable(element: HTMLElement): boolean {
  const overflowY = window.getComputedStyle(element).overflowY;
  return /(auto|scroll|overlay)/.test(overflowY);
}

export function findInputScrollContainer(input: HTMLElement): HTMLElement {
  let parent = input.parentElement;
  while (parent) {
    if (isScrollable(parent)) return parent;
    parent = parent.parentElement;
  }
  return document.scrollingElement instanceof HTMLElement
    ? document.scrollingElement
    : document.documentElement;
}

function findEditorAction(input: HTMLElement): HTMLElement | null {
  const editor = input.closest(".custom-editor");
  if (!editor) return null;
  return editor.querySelector<HTMLElement>(".custom-save-button")
    ?? editor.closest(".sos-flow")?.querySelector<HTMLElement>(".keyboard-safe-actions .primary-button")
    ?? null;
}

/** Moves only the nearest scroll container by the exact amount needed to reveal Save. */
export function ensureInputActionsVisible(input: HTMLElement, visibleBottom: number): number {
  const action = findEditorAction(input);
  if (!action) return 0;
  const delta = calculateActionScrollDelta(action.getBoundingClientRect().bottom, visibleBottom);
  if (delta <= 0) return 0;
  findInputScrollContainer(input).scrollBy({ top: delta, behavior: "smooth" });
  return delta;
}
