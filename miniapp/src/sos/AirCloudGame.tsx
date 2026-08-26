import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import {
  CLOUD_GAME_HEIGHT,
  CLOUD_GAME_WIDTH,
  CLOUD_PLAYER_HEIGHT,
  CLOUD_PLAYER_WIDTH,
  calculateGameStageHeight,
  cloudGameMetadata,
  createCloudGame,
  finishCloudGame,
  stepCloudGame,
  type CloudGameMetadata,
  type CloudGameState,
  type Direction,
  type Platform,
} from "./cloudGame";
import { setupCanvasBitmap } from "./canvasSetup";

type SavedResult = { metadata: CloudGameMetadata; newRecord: boolean; fell: boolean; saved: boolean };

type Props = {
  initialBestHeight: number;
  onRecord: (metadata: CloudGameMetadata) => Promise<{ metadata: CloudGameMetadata; new_record: boolean }>;
  onComplete: (metadata: CloudGameMetadata) => void;
};

export function AirCloudGame({ initialBestHeight, onRecord, onComplete }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const [snapshot, setSnapshot] = useState<CloudGameState>(() => createCloudGame());
  const stateRef = useRef<CloudGameState>(snapshot);
  const directionRef = useRef<Direction>(0);
  const frameRef = useRef<number | null>(null);
  const layoutFrameRef = useRef<number | null>(null);
  const endingRef = useRef(false);
  const mountedRef = useRef(true);
  const bestRef = useRef(initialBestHeight);
  const onRecordRef = useRef(onRecord);
  const [bestHeight, setBestHeight] = useState(initialBestHeight);
  const [stageHeight, setStageHeight] = useState(() => Math.round(window.innerHeight * 0.6));
  const [result, setResult] = useState<SavedResult | null>(null);
  const [saving, setSaving] = useState(false);
  const [run, setRun] = useState(0);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);
  useEffect(() => { onRecordRef.current = onRecord; }, [onRecord]);

  useLayoutEffect(() => {
    if (result) return;
    setupCanvasBitmap(canvasRef.current);
    drawGame(canvasRef.current, stateRef.current, prefersReducedMotion());
  }, [result, run, stageHeight]);

  useEffect(() => {
    const previousBodyOverflow = document.body.style.overflow;
    const previousOverscroll = document.documentElement.style.overscrollBehavior;
    document.body.classList.add("air-game-scroll-lock");
    document.body.style.overflow = "hidden";
    document.documentElement.style.overscrollBehavior = "none";
    return () => {
      document.body.classList.remove("air-game-scroll-lock");
      document.body.style.overflow = previousBodyOverflow;
      document.documentElement.style.overscrollBehavior = previousOverscroll;
    };
  }, []);

  const updateCanvasLayout = useCallback(() => {
    const viewportHeight = window.visualViewport?.height || window.innerHeight;
    const stageTop = stageRef.current?.getBoundingClientRect().top ?? viewportHeight * 0.25;
    const navigationTop = document.querySelector(".bottom-nav")?.getBoundingClientRect().top;
    const bottomBoundary = navigationTop && navigationTop > stageTop ? navigationTop : viewportHeight - 8;
    setStageHeight(calculateGameStageHeight(viewportHeight, stageTop, bottomBoundary));
    if (layoutFrameRef.current !== null) cancelAnimationFrame(layoutFrameRef.current);
    layoutFrameRef.current = window.requestAnimationFrame(() => {
      setupCanvasBitmap(canvasRef.current);
      drawGame(canvasRef.current, stateRef.current, prefersReducedMotion());
      layoutFrameRef.current = null;
    });
  }, []);

  useEffect(() => {
    updateCanvasLayout();
    const viewport = window.visualViewport;
    const telegram = window.Telegram?.WebApp;
    const resizeObserver = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(updateCanvasLayout);
    if (stageRef.current) resizeObserver?.observe(stageRef.current);
    window.addEventListener("resize", updateCanvasLayout);
    window.addEventListener("orientationchange", updateCanvasLayout);
    viewport?.addEventListener("resize", updateCanvasLayout);
    telegram?.onEvent?.("viewportChanged", updateCanvasLayout);
    return () => {
      resizeObserver?.disconnect();
      window.removeEventListener("resize", updateCanvasLayout);
      window.removeEventListener("orientationchange", updateCanvasLayout);
      viewport?.removeEventListener("resize", updateCanvasLayout);
      telegram?.offEvent?.("viewportChanged", updateCanvasLayout);
      if (layoutFrameRef.current !== null) cancelAnimationFrame(layoutFrameRef.current);
      layoutFrameRef.current = null;
    };
  }, [updateCanvasLayout]);

  const saveAttempt = useCallback(async (fell: boolean) => {
    if (endingRef.current) return;
    endingRef.current = true;
    setSaving(true);
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    stateRef.current = fell ? stateRef.current : finishCloudGame(stateRef.current);
    const local = cloudGameMetadata(stateRef.current, bestRef.current);
    try {
      const saved = await onRecordRef.current(local);
      bestRef.current = saved.metadata.best_height;
      setBestHeight(saved.metadata.best_height);
      if (mountedRef.current) setResult({ metadata: saved.metadata, newRecord: saved.new_record, fell, saved: true });
    } catch {
      if (mountedRef.current) setResult({ metadata: local, newRecord: false, fell, saved: false });
    } finally {
      if (mountedRef.current) setSaving(false);
    }
  }, []);

  useEffect(() => {
    endingRef.current = false;
    directionRef.current = 0;
    stateRef.current = createCloudGame();
    setSnapshot(stateRef.current);
    setResult(null);
    setupCanvasBitmap(canvasRef.current);
    let previous = performance.now();
    let previousHudUpdate = previous;
    const reducedMotion = prefersReducedMotion();

    const keyDirection = (key: string): Direction | null => {
      if (key === "ArrowLeft" || key.toLowerCase() === "a") return -1;
      if (key === "ArrowRight" || key.toLowerCase() === "d") return 1;
      return null;
    };
    const keyDown = (event: KeyboardEvent) => {
      const direction = keyDirection(event.key);
      if (direction === null) return;
      event.preventDefault();
      directionRef.current = direction;
    };
    const keyUp = (event: KeyboardEvent) => {
      if (keyDirection(event.key) !== null) directionRef.current = 0;
    };
    window.addEventListener("keydown", keyDown);
    window.addEventListener("keyup", keyUp);

    const frame = (now: number) => {
      const next = stepCloudGame(stateRef.current, (now - previous) / 1000, directionRef.current);
      previous = now;
      stateRef.current = next;
      drawGame(canvasRef.current, next, reducedMotion);
      if (now - previousHudUpdate >= 80) {
        previousHudUpdate = now;
        setSnapshot(next);
      }
      if (next.status === "fallen") {
        void saveAttempt(true);
        return;
      }
      frameRef.current = requestAnimationFrame(frame);
    };
    drawGame(canvasRef.current, stateRef.current, reducedMotion);
    frameRef.current = requestAnimationFrame(frame);
    return () => {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
      window.removeEventListener("keydown", keyDown);
      window.removeEventListener("keyup", keyUp);
      directionRef.current = 0;
    };
  }, [run, saveAttempt]);

  const move = (event: ReactPointerEvent<HTMLDivElement>, direction: Direction) => {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    directionRef.current = direction;
  };
  const stop = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    directionRef.current = 0;
  };
  const retry = () => {
    endingRef.current = false;
    directionRef.current = 0;
    setResult(null);
    window.requestAnimationFrame(() => setRun(value => value + 1));
  };
  const retrySave = (savedResult: SavedResult) => {
    endingRef.current = false;
    void saveAttempt(savedResult.fell);
  };

  return <div className="air-cloud-game">
    {!result && <>
      <div className="air-game-hud">
        <span><small>Высота</small><strong>{snapshot.height} м</strong></span>
        <span><small>Рекорд</small><strong>{bestHeight} м</strong></span>
        <button type="button" onClick={() => void saveAttempt(false)}>✕ Закончить</button>
      </div>
      <div ref={stageRef} className="air-game-stage" style={{ height: `${stageHeight}px` }}>
        <canvas ref={canvasRef} aria-label="Игра Выше облаков" />
        {snapshot.boostEffectSeconds > 0 && <div className="air-boost-label" aria-live="polite">AIR BOOST</div>}
        <div className="air-touch-zone left" role="button" tabIndex={-1} aria-label="Двигаться влево" onPointerDown={event => move(event, -1)} onPointerUp={stop} onPointerCancel={stop} onContextMenu={event => event.preventDefault()} />
        <div className="air-touch-zone right" role="button" tabIndex={-1} aria-label="Двигаться вправо" onPointerDown={event => move(event, 1)} onPointerUp={stop} onPointerCancel={stop} onContextMenu={event => event.preventDefault()} />
      </div>
    </>}
    {result && <div className="air-game-result">
      <div className="air-result-cloud" aria-hidden="true">☁</div>
      <p>{result.fell ? "Облачко мягко вернулось ниже" : "Полёт завершён"}</p>
      <strong>Высота: {result.metadata.height} м</strong>
      {result.newRecord ? <h3>Новый рекорд — {result.metadata.best_height} м</h3> : <span>Рекорд: {result.metadata.best_height} м</span>}
      {!result.saved && <><span className="air-game-save-error">Не удалось сохранить результат. Проверь соединение.</span><button className="primary-button" disabled={saving} onClick={() => retrySave(result)}>{saving ? "Сохраняем…" : "Повторить сохранение"}</button></>}
      {result.saved && result.fell && <button className="primary-button" onClick={retry}>Ещё раз</button>}
      {result.saved && <button className={result.fell ? "secondary-button" : "primary-button"} onClick={() => onComplete(result.metadata)}>{result.fell ? "Закончить" : "Продолжить"}</button>}
    </div>}
  </div>;
}

function prefersReducedMotion(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

function drawGame(canvas: HTMLCanvasElement | null, state: CloudGameState, reducedMotion: boolean): void {
  if (!canvas) return;
  const context = canvas.getContext("2d");
  if (!context) return;
  context.setTransform(canvas.width / CLOUD_GAME_WIDTH, 0, 0, canvas.height / CLOUD_GAME_HEIGHT, 0, 0);
  const high = Math.min(1, state.height / 1400);
  const gradient = context.createLinearGradient(0, 0, 0, CLOUD_GAME_HEIGHT);
  gradient.addColorStop(0, `rgb(${Math.round(154 - high * 30)}, ${Math.round(215 - high * 18)}, ${Math.round(238 + high * 8)})`);
  gradient.addColorStop(1, "#f4fbfa");
  context.fillStyle = gradient;
  context.fillRect(0, 0, CLOUD_GAME_WIDTH, CLOUD_GAME_HEIGHT);

  if (!reducedMotion) {
    context.globalAlpha = 0.3;
    context.fillStyle = "#ffffff";
    for (let index = 0; index < 13; index += 1) {
      const x = (index * 83 + state.scrollOffset * 0.08) % (CLOUD_GAME_WIDTH + 30) - 15;
      const y = (index * 127 + state.scrollOffset * 0.16) % CLOUD_GAME_HEIGHT;
      context.beginPath(); context.arc(x, y, 2 + index % 3, 0, Math.PI * 2); context.fill();
    }
    context.globalAlpha = 1;
  }

  for (const platform of state.platforms) drawPlatform(context, platform, state.elapsedSeconds);
  drawAirCloud(context, state.player.x, state.player.y, state.player.vy, state.boostEffectSeconds > 0);
}

function drawPlatform(context: CanvasRenderingContext2D, platform: Platform, elapsed: number): void {
  const { x, y, width, kind } = platform;
  context.save();
  context.globalAlpha = kind === "disappearing" ? (platform.opacity ?? 0.68) : 1;
  context.shadowColor = "rgba(44, 113, 128, .16)";
  context.shadowBlur = 10;
  context.fillStyle = kind === "moving" ? "rgba(239,252,251,.96)" : "rgba(255,255,255,.95)";
  context.beginPath();
  context.roundRect(x, y, width, kind === "disappearing" ? 10 : 13, 8);
  context.fill();
  context.fillStyle = kind === "boost" ? "rgba(89,180,164,.42)" : "rgba(111,190,181,.28)";
  context.fillRect(x + 9, y + 12, Math.max(10, width - 18), 3);
  if (kind === "moving") {
    context.fillStyle = "rgba(64,132,132,.5)";
    context.beginPath(); context.arc(x + width / 2 - 6, y + 6, 1.6, 0, Math.PI * 2); context.arc(x + width / 2 + 6, y + 6, 1.6, 0, Math.PI * 2); context.fill();
  }
  if (kind === "boost") {
    context.strokeStyle = "rgba(76,170,155,.6)";
    context.lineWidth = 1.6;
    for (let index = -1; index <= 1; index += 1) {
      const lift = (elapsed * 26 + index * 9) % 25;
      context.beginPath(); context.moveTo(x + width / 2 + index * 9, y - 2 - lift); context.quadraticCurveTo(x + width / 2 + index * 7, y - 10 - lift, x + width / 2 + index * 9, y - 17 - lift); context.stroke();
    }
  }
  context.restore();
}

function drawAirCloud(context: CanvasRenderingContext2D, x: number, y: number, vy: number, boosted: boolean): void {
  const stretch = Math.max(-2, Math.min(boosted ? 3.2 : 2, -vy / 180));
  context.save();
  context.translate(x + CLOUD_PLAYER_WIDTH / 2, y + CLOUD_PLAYER_HEIGHT / 2);
  context.scale(1 - stretch * 0.015, 1 + stretch * 0.02);
  context.strokeStyle = "#5d918d";
  context.lineWidth = 2.2;
  context.lineCap = "round";
  context.beginPath(); context.moveTo(-9, 13); context.lineTo(-10, 19); context.moveTo(9, 13); context.lineTo(10, 19); context.stroke();
  context.shadowColor = "rgba(47, 111, 121, .2)";
  context.shadowBlur = 9;
  context.fillStyle = "#ffffff";
  context.beginPath();
  context.arc(-10, 4, 10, Math.PI * .85, Math.PI * 1.85);
  context.arc(-3, -4, 12, Math.PI, Math.PI * 1.9);
  context.arc(10, 0, 12, Math.PI * 1.1, Math.PI * 2);
  context.roundRect(-19, 0, 38, 16, 8);
  context.fill();
  context.shadowBlur = 0;
  context.fillStyle = "#4f7777";
  context.beginPath(); context.arc(-6, 4, 1.6, 0, Math.PI * 2); context.arc(6, 4, 1.6, 0, Math.PI * 2); context.fill();
  context.strokeStyle = "#4f7777";
  context.lineWidth = 1.4;
  context.beginPath(); context.arc(0, 5, 4, .2, Math.PI - .2); context.stroke();
  context.restore();
}
