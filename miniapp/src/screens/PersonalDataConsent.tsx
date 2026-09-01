export function PersonalDataConsent() {
  return <main className="legal-document-screen">
    <article>
      <p className="eyebrow">AIR · версия 1.0</p>
      <h1>Согласие на обработку персональных данных</h1>
      <p>Здесь будет размещён полный текст юридического документа о согласии на обработку персональных данных.</p>
      <p>Настоящий текст будет добавлен отдельно до публикации документа.</p>
      <button className="primary-button" onClick={() => window.history.back()}>Вернуться</button>
    </article>
  </main>;
}
