import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "./api/client";
import { startOrRestartQuitAttempt } from "./api/quitAttempt";
import { BottomNav, type Tab } from "./components/BottomNav";
import { ErrorState, Loading } from "./components/Loading";
import { NicotineDesireModal } from "./components/NicotineDesireModal";
import { shouldShowPaywall, transitionPaywall, type PaywallView } from "./payments/flow";
import { Home } from "./screens/Home";
import { Paywall } from "./screens/Paywall";
import { ExternalPaymentReturn, PaymentReturn } from "./screens/PaymentReturn";
import { Plans } from "./screens/Plans";
import { Profile } from "./screens/Profile";
import { Program } from "./screens/Program";
import { Progress } from "./screens/Progress";
import { Sos } from "./screens/Sos";
import type { Access, Dashboard, Profile as ProfileType, Program as ProgramType, Progress as ProgressType } from "./types";
import { setupTelegramTheme } from "./theme";
import { useKeyboardAwareViewport } from "./hooks/useKeyboardAwareViewport";
import { AdminPayments } from "./screens/AdminPayments";
import { ConsentScreen } from "./screens/Consent";
import { PersonalDataConsent } from "./screens/PersonalDataConsent";
import { PrivacyPolicy, PublicOffer, TermsOfUse } from "./screens/LegalDocuments";
import type { ConsentStatus } from "./types";

type Data = { dashboard?: Dashboard; program?: ProgramType; progress?: ProgressType; profile?: ProfileType };
export default function App() {
  const pathname = window.location.pathname.replace(/\/$/, "");
  if (pathname === "/admin/payments") {
    return <AdminPayments />;
  }
  if (pathname === "/personal-data-consent") return <PersonalDataConsent />;
  if (pathname === "/privacy") return <PrivacyPolicy />;
  if (pathname === "/offer") return <PublicOffer />;
  if (pathname === "/terms") return <TermsOfUse />;
  return <AirApplication />;
}

function AirApplication() {
  useKeyboardAwareViewport();
  const [access, setAccess] = useState<Access | null>(null);
  const [consent, setConsent] = useState<ConsentStatus | null>(null);
  const [tab, setTab] = useState<Tab>("home");
  const [data, setData] = useState<Data>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [desireOpen, setDesireOpen] = useState(false);
  const [paywallView, setPaywallView] = useState<PaywallView>("landing");
  const [profilePlansOpen, setProfilePlansOpen] = useState(false);
  const [returnOrderId, setReturnOrderId] = useState<number | null>(() => {
    const params = new URLSearchParams(window.location.search);
    const value = params.get("payment") === "return" ? Number(params.get("order_id")) : NaN;
    return Number.isInteger(value) && value > 0 ? value : null;
  });
  const hasTelegramAuth = Boolean(window.Telegram?.WebApp.initData)
    || Boolean(import.meta.env.DEV && import.meta.env.VITE_DEV_TELEGRAM_ID);

  const loadAccess = useCallback(async () => {
    setError("");
    try { setAccess(await api<Access>("/access")); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Проверь соединение с AIR"); }
    finally { setLoading(false); }
  }, []);
  const loadInitial = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const current = await api<ConsentStatus>("/consent");
      setConsent(current);
      if (current.accepted) await loadAccess();
      else setLoading(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Проверь соединение с AIR");
      setLoading(false);
    }
  }, [loadAccess]);
  useEffect(() => {
    const telegram = window.Telegram?.WebApp;
    telegram?.ready();
    telegram?.expand();
    const cleanupTheme = setupTelegramTheme(telegram);
    if (returnOrderId === null || hasTelegramAuth) queueMicrotask(() => void loadInitial());
    return cleanupTheme;
  }, [hasTelegramAuth, loadInitial, returnOrderId]);

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
    await startOrRestartQuitAttempt(firstAttempt, refreshAttemptData);
    setTab("home");
  }, [data.dashboard?.number_of_attempts, refreshAttemptData]);

  const handleAttemptRestarted = useCallback(async () => {
    await refreshAttemptData();
    setTab("home");
  }, [refreshAttemptData]);

  if (returnOrderId !== null && !hasTelegramAuth) return <ExternalPaymentReturn />;
  if (loading) return <Loading />;
  if (error) return <ErrorState message={error} retry={() => { setError(""); void loadInitial(); }} />;
  if (consent && !consent.accepted) return <ConsentScreen onAccepted={current => { setConsent(current); setLoading(true); void loadAccess(); }} />;
  if (!access) return <ErrorState message="Открой AIR из Telegram-бота." retry={loadAccess} />;
  if (returnOrderId !== null) {
    const openAir = () => {
      window.history.replaceState({}, "", `${window.location.pathname}`);
      setReturnOrderId(null);
      void loadAccess();
    };
    return <PaymentReturn orderId={returnOrderId} onOpenAir={openAir} />;
  }
  if (shouldShowPaywall(access.status)) {
    if (paywallView === "plans" && !access.development_activation_available) {
      return <Plans links={access.links} initialEmail={access.receipt_email} onBack={() => setPaywallView(view => transitionPaywall(view, "back"))} onPaymentSucceeded={() => void loadAccess()} />;
    }
    return <Paywall access={access} activate={activate} openPlans={() => setPaywallView(view => transitionPaywall(view, "open_plans"))} refresh={() => void refreshAccess()} busy={busy} />;
  }
  const screen = tab === "home" && data.dashboard ? <Home data={data.dashboard} openProgram={() => setTab("program")} openDesire={() => setDesireOpen(true)} startAttempt={handleStartAttempt} />
    : tab === "program" && data.program ? <Program data={data.program} onGoSos={() => setTab("sos")} onGoProgress={() => setTab("progress")} />
    : tab === "sos" ? <Sos onAttemptChanged={refreshAttemptData} onAttemptRestarted={handleAttemptRestarted} onGoHome={() => setTab("home")} />
    : tab === "progress" && data.progress ? <Progress data={data.progress} />
    : tab === "profile" && data.profile && profilePlansOpen ? <Plans links={access.links} initialEmail={access.receipt_email} onBack={() => setProfilePlansOpen(false)} onPaymentSucceeded={() => { setProfilePlansOpen(false); void loadAccess(); }} />
    : tab === "profile" && data.profile ? <Profile data={data.profile} access={access} isAdmin={access.is_admin} onOpenPlans={() => setProfilePlansOpen(true)} /> : <Loading />;
  return <div className="app-shell">{screen}{desireOpen && <NicotineDesireModal onClose={() => setDesireOpen(false)} />}<BottomNav tab={tab} onChange={nextTab => { if (nextTab !== "profile" || tab !== "profile") setProfilePlansOpen(false); setTab(nextTab); }} /></div>;
}
