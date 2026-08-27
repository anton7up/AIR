import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "./api/client";
import { BottomNav, type Tab } from "./components/BottomNav";
import { ErrorState, Loading } from "./components/Loading";
import { NicotineDesireModal } from "./components/NicotineDesireModal";
import { shouldShowPaywall, transitionPaywall, type PaywallView } from "./payments/flow";
import { Home } from "./screens/Home";
import { Paywall } from "./screens/Paywall";
import { Plans } from "./screens/Plans";
import { Profile } from "./screens/Profile";
import { Program } from "./screens/Program";
import { Progress } from "./screens/Progress";
import { Sos } from "./screens/Sos";
import type { Access, Dashboard, Profile as ProfileType, Program as ProgramType, Progress as ProgressType } from "./types";
import { setupTelegramTheme } from "./theme";
import { useKeyboardAwareViewport } from "./hooks/useKeyboardAwareViewport";

type Data = { dashboard?: Dashboard; program?: ProgramType; progress?: ProgressType; profile?: ProfileType };
export default function App() {
  useKeyboardAwareViewport();
  const [access, setAccess] = useState<Access | null>(null);
  const [tab, setTab] = useState<Tab>("home");
  const [data, setData] = useState<Data>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [desireOpen, setDesireOpen] = useState(false);
  const [paywallView, setPaywallView] = useState<PaywallView>("landing");

  const loadAccess = useCallback(async () => {
    setLoading(true); setError("");
    try { setAccess(await api<Access>("/access")); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Проверь соединение с AIR"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => {
    const telegram = window.Telegram?.WebApp;
    telegram?.ready();
    telegram?.expand();
    const cleanupTheme = setupTelegramTheme(telegram);
    queueMicrotask(() => void loadAccess());
    return cleanupTheme;
  }, [loadAccess]);

  useEffect(() => {
    if (access?.status !== "active") return;
    if (tab === "sos") return;
    const paths: Record<Exclude<Tab, "sos">, keyof Data> = { home: "dashboard", program: "program", progress: "progress", profile: "profile" };
    const key = paths[tab];
    if (data[key]) return;
    api<Dashboard | ProgramType | ProgressType | ProfileType>(`/${key}`).then(value => setData(current => ({ ...current, [key]: value }))).catch(err => setError(err.message));
  }, [access, tab, data]);

  const activate = async () => {
    if (!access?.development_activation_available) { setError("Оплата пока не подключена. Попробуй позже."); return; }
    setBusy(true); try { await api("/dev/activate", { method: "POST" }); await loadAccess(); } catch (err) { setError(err instanceof Error ? err.message : "Не удалось активировать доступ"); } finally { setBusy(false); }
  };

  const refreshAccess = async () => {
    setBusy(true); setError("");
    try { setAccess(await api<Access>("/access/refresh", { method: "POST" })); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Не удалось проверить доступ"); }
    finally { setBusy(false); }
  };

  const refreshAttemptData = useCallback(async () => {
    const [dashboard, progress, profile, program] = await Promise.all([
      api<Dashboard>("/dashboard"),
      api<ProgressType>("/progress"),
      api<ProfileType>("/profile"),
      api<ProgramType>("/program"),
    ]);
    setData(current => ({ ...current, dashboard, progress, profile, program }));
  }, []);

  const handleStartAttempt = useCallback(async () => {
    const firstAttempt = (data.dashboard?.number_of_attempts ?? 0) === 0;
    await api(firstAttempt ? "/program/start" : "/quit-attempt/restart", { method: "POST" });
    await refreshAttemptData();
    setTab("home");
  }, [data.dashboard?.number_of_attempts, refreshAttemptData]);

  const handleAttemptRestarted = useCallback(async () => {
    await refreshAttemptData();
    setTab("home");
  }, [refreshAttemptData]);

  if (loading) return <Loading />;
  if (error) return <ErrorState message={error} retry={() => { setError(""); void loadAccess(); }} />;
  if (!access) return <ErrorState message="Открой AIR из Telegram-бота." retry={loadAccess} />;
  if (shouldShowPaywall(access.status)) {
    if (paywallView === "plans" && !access.development_activation_available) {
      return <Plans links={access.links} onBack={() => setPaywallView(view => transitionPaywall(view, "back"))} />;
    }
    return <Paywall access={access} activate={activate} openPlans={() => setPaywallView(view => transitionPaywall(view, "open_plans"))} refresh={() => void refreshAccess()} busy={busy} />;
  }
  const screen = tab === "home" && data.dashboard ? <Home data={data.dashboard} openProgram={() => setTab("program")} openDesire={() => setDesireOpen(true)} startAttempt={handleStartAttempt} />
    : tab === "program" && data.program ? <Program data={data.program} onGoSos={() => setTab("sos")} onGoProgress={() => setTab("progress")} />
    : tab === "sos" ? <Sos onAttemptChanged={refreshAttemptData} onAttemptRestarted={handleAttemptRestarted} onGoHome={() => setTab("home")} />
    : tab === "progress" && data.progress ? <Progress data={data.progress} />
    : tab === "profile" && data.profile ? <Profile data={data.profile} /> : <Loading />;
  return <div className="app-shell">{screen}{desireOpen && <NicotineDesireModal onClose={() => setDesireOpen(false)} />}<BottomNav tab={tab} onChange={setTab} /></div>;
}
