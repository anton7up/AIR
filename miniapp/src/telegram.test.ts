import { describe, expect, it, vi } from "vitest";

import { AIR_EDIT_PROFILE_URL, AIR_SUPPORT_URL, openAirEditProfile, openAirSupport } from "./telegram";

describe("AIR Telegram support link", () => {
  it("uses the existing bot with a support start parameter", () => {
    expect(AIR_SUPPORT_URL).toBe("https://t.me/airnosmokebot?start=support");
    expect(AIR_EDIT_PROFILE_URL).toBe("https://t.me/airnosmokebot?start=edit_profile");
  });

  it("opens profile editing through Telegram", () => {
    const openTelegramLink = vi.fn();
    vi.stubGlobal("window", {
      Telegram: { WebApp: { openTelegramLink } },
      location: { assign: vi.fn() },
    });
    openAirEditProfile();
    expect(openTelegramLink).toHaveBeenCalledWith(AIR_EDIT_PROFILE_URL);
    vi.unstubAllGlobals();
  });

  it("uses Telegram openTelegramLink when available", () => {
    const openTelegramLink = vi.fn();
    vi.stubGlobal("window", {
      Telegram: {
        WebApp: {
          initData: "",
          ready: () => undefined,
          expand: () => undefined,
          close: () => undefined,
          colorScheme: "light",
          openTelegramLink,
        },
      },
      location: { assign: vi.fn() },
    });
    openAirSupport();
    expect(openTelegramLink).toHaveBeenCalledWith(AIR_SUPPORT_URL);
    vi.unstubAllGlobals();
  });

  it("falls back to a regular Telegram link outside the Mini App", () => {
    const assign = vi.fn();
    vi.stubGlobal("window", {
      location: { assign },
    });
    openAirSupport();
    expect(assign).toHaveBeenCalledWith(AIR_SUPPORT_URL);
    vi.unstubAllGlobals();
  });
});
