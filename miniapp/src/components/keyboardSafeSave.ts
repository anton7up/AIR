type SaveSource = "pointer" | "click";

export class KeyboardSafeSaveController {
  private saveInProgress = false;
  private skipNextClick = false;

  activate(source: SaveSource, save: () => void | Promise<void>, blur: () => void): boolean {
    if (source === "click" && this.skipNextClick) {
      this.skipNextClick = false;
      return false;
    }
    if (this.saveInProgress) return false;

    if (source === "pointer") this.skipNextClick = true;
    this.saveInProgress = true;
    let result: void | Promise<void>;
    try {
      result = save();
    } catch (error) {
      this.saveInProgress = false;
      throw error;
    }

    // The save has already captured the current draft before iOS starts closing the keyboard.
    blur();
    if (result instanceof Promise) {
      void result.then(
        () => { this.saveInProgress = false; },
        () => { this.saveInProgress = false; },
      );
    } else {
      this.saveInProgress = false;
    }
    return true;
  }
}

export function isValidSaveDraft(value: string): boolean {
  return Boolean(value.trim());
}
