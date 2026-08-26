import { describe, expect, it } from "vitest";
import { isValidSaveDraft, KeyboardSafeSaveController } from "./keyboardSafeSave";

describe("keyboard-safe custom Save", () => {
  it("captures the first pointer event, saves once and ignores its following click", async () => {
    const controller = new KeyboardSafeSaveController();
    let apiCalls = 0;
    let usageCount = 0;
    let blurCalls = 0;
    let editorOpen = true;
    let finishRequest: (() => void) | undefined;
    const request = new Promise<void>(resolve => { finishRequest = resolve; });
    const save = () => {
      apiCalls += 1;
      usageCount += 1;
      return request.then(() => { editorOpen = false; });
    };

    expect(controller.activate("pointer", save, () => { blurCalls += 1; })).toBe(true);
    expect(controller.activate("click", save, () => { blurCalls += 1; })).toBe(false);
    expect(apiCalls).toBe(1);
    expect(usageCount).toBe(1);
    expect(blurCalls).toBe(1);
    expect(editorOpen).toBe(true);

    finishRequest?.();
    await request;
    await Promise.resolve();
    expect(editorOpen).toBe(false);
    expect(apiCalls).toBe(1);
  });

  it("starts save before blur and blur does not cancel the request", async () => {
    const controller = new KeyboardSafeSaveController();
    const order: string[] = [];
    let finishRequest: (() => void) | undefined;
    const request = new Promise<void>(resolve => { finishRequest = resolve; });

    controller.activate("pointer", () => {
      order.push("save");
      return request.then(() => { order.push("saved"); });
    }, () => { order.push("blur"); });

    expect(order).toEqual(["save", "blur"]);
    finishRequest?.();
    await request;
    await Promise.resolve();
    expect(order).toEqual(["save", "blur", "saved"]);
  });

  it("only disables Save for a genuinely invalid draft", () => {
    expect(isValidSaveDraft("")).toBe(false);
    expect(isValidSaveDraft("   ")).toBe(false);
    expect(isValidSaveDraft("Мама")).toBe(true);
  });
});
