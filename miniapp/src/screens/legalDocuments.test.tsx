import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { PrivacyPolicy, PublicOffer, TermsOfUse } from "./LegalDocuments";
import { PersonalDataConsent } from "./PersonalDataConsent";

const appSource = readFileSync(new URL("../App.tsx", import.meta.url), "utf8");
const profileSource = readFileSync(new URL("./Profile.tsx", import.meta.url), "utf8");
const styles = readFileSync(new URL("../styles.css", import.meta.url), "utf8");

describe("AIR legal documents", () => {
  it("renders all complete documents with edition date and Back", () => {
    const documents = [
      renderToStaticMarkup(<PersonalDataConsent />),
      renderToStaticMarkup(<PrivacyPolicy />),
      renderToStaticMarkup(<PublicOffer />),
      renderToStaticMarkup(<TermsOfUse />),
    ];
    for (const markup of documents) {
      expect(markup).toContain("01.09.2026");
      expect(markup).toContain("Назад");
      expect(markup).toContain("anton.d.pravdin@gmail.com");
      expect(markup).not.toContain("placeholder");
      expect(markup).not.toContain("Здесь будет размещён");
    }
  });

  it("publishes the expected routes", () => {
    for (const route of ["/personal-data-consent", "/privacy", "/offer", "/terms"]) {
      expect(appSource).toContain(`pathname === "${route}"`);
    }
  });

  it("links every legal document and AIR bot support from Profile", () => {
    expect(profileSource).toContain('window.location.assign("/terms")');
    expect(profileSource).toContain('window.location.assign("/offer")');
    expect(profileSource).toContain('window.location.assign("/privacy")');
    expect(profileSource).toContain('window.location.assign("/personal-data-consent")');
    expect(profileSource).toContain("openAirSupport");
  });

  it("uses semantic theme tokens and mobile-safe sizing", () => {
    expect(styles).toContain(".legal-document-screen");
    expect(styles).toContain("var(--air-page-bg)");
    expect(styles).toContain("var(--air-text-primary)");
    expect(styles).toContain("overflow-x:hidden");
    expect(styles).toContain("clamp(19px,5vw,36px)");
  });

  it("keeps the published offer prices and medical status", () => {
    const offer = renderToStaticMarkup(<PublicOffer />);
    expect(offer).toContain("990 рублей");
    expect(offer).toContain("2450 рублей");
    expect(offer).toContain("Автоматические регулярные списания отсутствуют");
    expect(offer).toContain("не является медицинской организацией");
  });
});
