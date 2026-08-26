import { describe, expect, it, vi } from "vitest";
import { setupCanvasBitmap } from "./canvasSetup";

describe("AIR cloud Canvas restart setup", () => {
  it("rebuilds the same sharp bitmap and absolute transform across five restarts", () => {
    const setTransform = vi.fn();
    const clearRect = vi.fn();
    const canvas = {
      width: 300,
      height: 150,
      getBoundingClientRect: () => ({ width: 366, height: 540 }),
      getContext: () => ({ setTransform, clearRect }),
    } as unknown as HTMLCanvasElement;

    const setups = Array.from({ length: 6 }, () => setupCanvasBitmap(canvas, 2));
    expect(setups.every(setup => setup?.bitmapWidth === 732 && setup.bitmapHeight === 1080)).toBe(true);
    expect(canvas.width).toBe(732);
    expect(canvas.height).toBe(1080);
    expect(setTransform).toHaveBeenCalledTimes(12);
    for (let index = 0; index < 6; index += 1) {
      expect(setTransform.mock.calls[index * 2]).toEqual([1, 0, 0, 1, 0, 0]);
      expect(setTransform.mock.calls[index * 2 + 1]).toEqual([732 / 360, 0, 0, 1080 / 520, 0, 0]);
    }
    expect(clearRect).toHaveBeenCalledTimes(6);
  });
});
