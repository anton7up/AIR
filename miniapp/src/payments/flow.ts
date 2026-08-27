export type PaywallView = "landing" | "plans";
export type PaywallEvent = "open_plans" | "back";

export function transitionPaywall(view: PaywallView, event: PaywallEvent): PaywallView {
  if (event === "open_plans") return "plans";
  if (event === "back") return "landing";
  return view;
}

export function shouldShowPaywall(status: "free" | "active" | "expired") {
  return status !== "active";
}
