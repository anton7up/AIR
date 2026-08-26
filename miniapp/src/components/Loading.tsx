export function Loading() { return <main className="center-state"><div className="air-loader" /><p>Подготавливаем AIR…</p></main>; }
export function ErrorState({ message, retry }: { message: string; retry: () => void }) {
  return <main className="center-state"><div className="brand-mark">AIR</div><h2>Не удалось открыть AIR</h2><p>{message}</p><button className="primary-button" onClick={retry}>Попробовать снова</button></main>;
}
