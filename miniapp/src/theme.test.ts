import { describe, expect, it } from "vitest";
import { setupTelegramTheme, telegramThemeVariables, themePreviewTokens, type TelegramThemeParams } from "./theme";

const themes: { name: string; scheme: "light" | "dark"; params: TelegramThemeParams }[] = [
  { name: "light", scheme: "light", params: { bg_color: "#f4f8f6", secondary_bg_color: "#ffffff", text_color: "#19332c", hint_color: "#61756f" } },
  { name: "dark", scheme: "dark", params: { bg_color: "#0e1d19", secondary_bg_color: "#172a25", text_color: "#e8f3ef", hint_color: "#a8bbb5" } },
  { name: "dark-blue", scheme: "dark", params: { bg_color: "#0f1e35", secondary_bg_color: "#182b47", text_color: "#f2f6ff", hint_color: "#a9b8cc" } },
];

describe("Telegram theme tokens", () => {
  for (const theme of themes) it(`maps valid readable ${theme.name} tokens`, () => {
    const css = telegramThemeVariables(theme.params);
    const tokens = themePreviewTokens(theme.params, theme.scheme);
    expect(css["--tg-theme-bg-color"]).toBe(theme.params.bg_color);
    expect(Object.values(tokens).every(Boolean)).toBe(true);
    expect(contrast(tokens.text, tokens.page)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(tokens.secondary, tokens.page)).toBeGreaterThanOrEqual(3);
    expect(contrast(tokens.muted, tokens.page)).toBeGreaterThanOrEqual(3);
    expect(contrast(tokens.text, tokens.surface)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(tokens.secondary, tokens.surface)).toBeGreaterThanOrEqual(3);
    expect(contrast(tokens.border, tokens.surface)).toBeGreaterThanOrEqual(1.3);
    expect(contrast(tokens.borderStrong, tokens.surface)).toBeGreaterThan(contrast(tokens.border, tokens.surface));
    expect(contrast(tokens.onAccent, tokens.accent)).toBeGreaterThanOrEqual(4.2);
    expect(tokens.page).not.toBe(tokens.surface);
    expect(tokens.surfaceElevated).not.toBe(tokens.surface);
  });

  it("reacts to themeChanged without a reload", () => {
    const values = new Map<string, string>();
    const root = {
      dataset: {} as Record<string, string | undefined>,
      style: {
        setProperty: (name: string, value: string) => values.set(name, value),
        removeProperty: (name: string) => { values.delete(name); },
      },
    };
    let update: () => void = () => {};
    const webApp = {
      colorScheme: "light" as "light" | "dark",
      themeParams: { bg_color: "#ffffff", text_color: "#111111" },
      onEvent: (event: "themeChanged", callback: () => void) => { expect(event).toBe("themeChanged"); update = callback; },
      offEvent: () => undefined,
    };
    const cleanup = setupTelegramTheme(webApp, root);
    expect(root.dataset.airColorScheme).toBe("light");
    expect(values.get("--tg-theme-bg-color")).toBe("#ffffff");

    webApp.colorScheme = "dark";
    webApp.themeParams = { bg_color: "#0f1e35", text_color: "#f2f6ff" };
    update();
    expect(root.dataset.airColorScheme).toBe("dark");
    expect(values.get("--tg-theme-bg-color")).toBe("#0f1e35");
    cleanup();
  });
});

function contrast(first: string, second: string) {
  const [lighter, darker] = [luminance(first), luminance(second)].sort((a, b) => b - a);
  return (lighter + 0.05) / (darker + 0.05);
}

function luminance(hex: string) {
  const values = hex.match(/[a-f\d]{2}/gi)?.map(value => parseInt(value, 16) / 255) ?? [];
  const channels = values.map(value => value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4);
  return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
}
