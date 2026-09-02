/// <reference types="vite/client" />

interface TelegramWebApp {
  initData: string;
  ready(): void;
  expand(): void;
  close(): void;
  openLink?(url: string): void;
  openTelegramLink?(url: string): void;
  colorScheme: "light" | "dark";
  themeParams?: import("./theme").TelegramThemeParams;
  viewportHeight?: number;
  viewportStableHeight?: number;
  onEvent?(event: "viewportChanged" | "themeChanged", callback: () => void): void;
  offEvent?(event: "viewportChanged" | "themeChanged", callback: () => void): void;
}

interface Window {
  Telegram?: { WebApp: TelegramWebApp };
}
