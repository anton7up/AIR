import { ArrowLeft } from "lucide-react";
import type { ReactNode } from "react";

export function LegalPage({
  title,
  version,
  children,
}: {
  title: string;
  version?: string;
  children: ReactNode;
}) {
  const goBack = () => {
    if (window.history.length > 1) window.history.back();
    else window.location.assign("/mini-app/");
  };

  return <main className="legal-document-screen">
    <article>
      <button className="legal-back" type="button" onClick={goBack}><ArrowLeft size={18} /> Назад</button>
      <header className="legal-header">
        <p className="eyebrow">AIR{version ? ` · версия ${version}` : ""}</p>
        <h1>{title}</h1>
        <p>Дата редакции: 01.09.2026</p>
      </header>
      <div className="legal-content">{children}</div>
    </article>
  </main>;
}

export function LegalList({ children }: { children: ReactNode }) {
  return <ul>{children}</ul>;
}
