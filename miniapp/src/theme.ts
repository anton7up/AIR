export type TelegramThemeParams = Partial<{
  bg_color: string;
  text_color: string;
  hint_color: string;
  link_color: string;
  button_color: string;
  button_text_color: string;
  secondary_bg_color: string;
  header_bg_color: string;
  section_bg_color: string;
  section_header_text_color: string;
  subtitle_text_color: string;
  destructive_text_color: string;
}>;

const THEME_PARAM_TO_CSS: Record<keyof TelegramThemeParams, string> = {
  bg_color: "--tg-theme-bg-color",
  text_color: "--tg-theme-text-color",
  hint_color: "--tg-theme-hint-color",
  link_color: "--tg-theme-link-color",
  button_color: "--tg-theme-button-color",
  button_text_color: "--tg-theme-button-text-color",
  secondary_bg_color: "--tg-theme-secondary-bg-color",
  header_bg_color: "--tg-theme-header-bg-color",
  section_bg_color: "--tg-theme-section-bg-color",
  section_header_text_color: "--tg-theme-section-header-text-color",
  subtitle_text_color: "--tg-theme-subtitle-text-color",
  destructive_text_color: "--tg-theme-destructive-text-color",
};

export function telegramThemeVariables(params: TelegramThemeParams = {}) {
  return Object.fromEntries(
    Object.entries(THEME_PARAM_TO_CSS)
      .filter(([key]) => Boolean(params[key as keyof TelegramThemeParams]))
      .map(([key, cssName]) => [cssName, params[key as keyof TelegramThemeParams] as string]),
  );
}

export function themePreviewTokens(params: TelegramThemeParams, scheme: "light" | "dark") {
  const page = params.bg_color ?? (scheme === "dark" ? "#0e1d19" : "#f4f8f6");
  const surface = params.secondary_bg_color ?? (scheme === "dark" ? "#172a25" : "#ffffff");
  const text = params.text_color ?? (scheme === "dark" ? "#e8f3ef" : "#19332c");
  const hint = params.subtitle_text_color ?? params.hint_color ?? (scheme === "dark" ? "#a8bbb5" : "#6d817b");
  return {
    page,
    surface,
    surfaceElevated: mixHex(text, surface, scheme === "dark" ? 0.08 : 0.06),
    text,
    secondary: mixHex(text, hint, scheme === "dark" ? 0.28 : 0.3),
    muted: mixHex(text, hint, scheme === "dark" ? 0.18 : 0.2),
    border: mixHex(text, surface, scheme === "dark" ? 0.25 : 0.22),
    borderStrong: mixHex(text, surface, scheme === "dark" ? 0.36 : 0.32),
    accent: scheme === "dark" ? "#73c7a9" : "#2c765f",
    onAccent: scheme === "dark" ? "#10241e" : "#ffffff",
    logoText: scheme === "dark" ? "#123b31" : "#174d3e",
  };
}

function mixHex(foreground: string, background: string, foregroundRatio: number) {
  const channels = (value: string) => value.match(/[a-f\d]{2}/gi)?.map(channel => parseInt(channel, 16)) ?? [];
  const front = channels(foreground);
  const back = channels(background);
  if (front.length !== 3 || back.length !== 3) return foreground;
  return `#${front.map((channel, index) => Math.round(channel * foregroundRatio + back[index] * (1 - foregroundRatio)).toString(16).padStart(2, "0")).join("")}`;
}

type ThemeRoot = {
  dataset: Record<string, string | undefined>;
  style: { setProperty(name: string, value: string): void; removeProperty(name: string): void };
};

type ThemeWebApp = {
  colorScheme?: "light" | "dark";
  themeParams?: TelegramThemeParams;
  onEvent?(event: "themeChanged", callback: () => void): void;
  offEvent?(event: "themeChanged", callback: () => void): void;
};

export function applyTelegramTheme(webApp: ThemeWebApp | undefined, root: ThemeRoot = document.documentElement) {
  root.dataset.airColorScheme = webApp?.colorScheme ?? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  for (const cssName of Object.values(THEME_PARAM_TO_CSS)) root.style.removeProperty(cssName);
  for (const [name, value] of Object.entries(telegramThemeVariables(webApp?.themeParams))) root.style.setProperty(name, value);
}

export function setupTelegramTheme(webApp: ThemeWebApp | undefined, root: ThemeRoot = document.documentElement) {
  const update = () => applyTelegramTheme(webApp, root);
  update();
  webApp?.onEvent?.("themeChanged", update);
  return () => webApp?.offEvent?.("themeChanged", update);
}
