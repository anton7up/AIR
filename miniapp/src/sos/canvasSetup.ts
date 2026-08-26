import { canvasBitmapSize } from "./cloudGame";

export function setupCanvasBitmap(
  canvas: HTMLCanvasElement | null,
  devicePixelRatio = window.devicePixelRatio || 1,
): ReturnType<typeof canvasBitmapSize> | null {
  if (!canvas) return null;
  const rect = canvas.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) return null;
  const bitmap = canvasBitmapSize(rect.width, rect.height, devicePixelRatio);
  // Assigning both dimensions deliberately resets all inherited Canvas state.
  canvas.width = bitmap.bitmapWidth;
  canvas.height = bitmap.bitmapHeight;
  const context = canvas.getContext("2d");
  context?.setTransform(1, 0, 0, 1, 0, 0);
  context?.clearRect(0, 0, bitmap.bitmapWidth, bitmap.bitmapHeight);
  context?.setTransform(bitmap.scaleX, 0, 0, bitmap.scaleY, 0, 0);
  return bitmap;
}
