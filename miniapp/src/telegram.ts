export const AIR_BOT_USERNAME = "airnosmokebot";

// No BotFather Mini App short name is configured in this project yet.
// Opening the bot is the reliable external-browser fallback on iOS.
export const AIR_TELEGRAM_URL = `https://t.me/${AIR_BOT_USERNAME}`;
export const AIR_SUPPORT_URL = `${AIR_TELEGRAM_URL}?start=support`;

export function openAirSupport(): void {
  const telegram = window.Telegram?.WebApp;
  if (telegram?.openTelegramLink) {
    telegram.openTelegramLink(AIR_SUPPORT_URL);
    return;
  }
  window.location.assign(AIR_SUPPORT_URL);
}
