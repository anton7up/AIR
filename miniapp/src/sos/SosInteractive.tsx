import { useEffect, useRef, useState } from "react";
import {
  breathingCompletion,
  BREATHING_CYCLES,
  breathingState,
} from "./logic";

export function SquareBreathing({ onComplete }: { onComplete: (metadata: Record<string, unknown>) => void }) {
  const [elapsed, setElapsed] = useState(0);
  const completed = useRef(false);
  const state = breathingState(elapsed);
  useEffect(() => {
    const timer = window.setInterval(() => setElapsed(value => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, []);
  useEffect(() => {
    if (!state.finished || completed.current) return;
    completed.current = true;
    onComplete(breathingCompletion(elapsed, false));
  }, [elapsed, onComplete, state.finished]);
  const finishEarly = () => {
    if (completed.current) return;
    completed.current = true;
    onComplete(breathingCompletion(elapsed, true));
  };
  return <div className="square-breathing">
    <div className="breathing-square"><span className="breathing-marker" /><div><strong>{state.phase.label}</strong><span>{state.secondsLeftInPhase} сек</span></div></div>
    <p>Цикл {state.cycle} из {BREATHING_CYCLES}</p>
    <button className="secondary-button" onClick={finishEarly}>Закончить раньше</button>
  </div>;
}
