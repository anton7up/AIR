import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ConsentScreen } from "./Consent";
import { PersonalDataConsent } from "./PersonalDataConsent";

describe("personal data consent", () => {
  it("shows the exact first-step wording and explicit choices", () => {
    const html = renderToStaticMarkup(<ConsentScreen onAccepted={() => undefined} />);
    expect(html).toContain("Перед началом");
    expect(html).toContain("в моменты тяги к никотину");
    expect(html).toContain("Согласие на обработку персональных данных");
    expect(html).toContain("Согласен");
    expect(html).toContain("Не согласен");
  });

  it("renders the complete consent document", () => {
    const html = renderToStaticMarkup(<PersonalDataConsent />);
    expect(html).toContain("Согласие на обработку персональных данных");
    expect(html).toContain("Правдину Антону Денисовичу");
    expect(html).toContain("Факт предоставления согласия, дата, время и версия согласия сохраняются AIR");
    expect(html).not.toContain("Здесь будет размещён");
  });
});
