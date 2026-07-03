"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { SiteHeader } from "@/components/SiteHeader";
import { getEntitlements, isLoggedIn } from "@/lib/kayak-api";

export default function BillingSuccessPage() {
  const loggedIn = isLoggedIn();
  const entQ = useQuery({
    queryKey: ["entitlements", "billing-success"],
    queryFn: getEntitlements,
    enabled: loggedIn,
    refetchInterval: (q) => {
      const codes = q.state.data?.active_plan_codes ?? [];
      return codes.includes("hunt_pass_30") || codes.includes("premium_plus_30") ? false : 2000;
    },
    retry: 5,
  });

  const active = entQ.data?.active_plan_codes ?? [];
  const unlocked = active.includes("hunt_pass_30") || active.includes("premium_plus_30");
  const pending = loggedIn && entQ.isLoading;

  return (
    <main className="min-h-screen bg-slate-50">
      <SiteHeader />
      <div className="mx-auto max-w-lg px-4 py-12 text-center">
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-8">
          <h1 className="text-2xl font-bold text-ink-950">
            {pending ? "Confirming payment…" : unlocked ? "You're unlocked" : "Payment received"}
          </h1>
          <p className="mt-2 text-ink-700">
            {pending && "Waiting for Stripe webhook confirmation — this usually takes a few seconds."}
            {!pending && unlocked &&
              "Your Hunt Pass is active. Open any building to see the full Deal Report — fees, history, and negotiation scripts."}
            {!pending && !unlocked && loggedIn &&
              "If access does not appear within a minute, check Account or contact support with your checkout email."}
            {!loggedIn && "Sign in to see your Hunt Pass on your account."}
          </p>
          <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:justify-center">
            <Link
              href="/search"
              className="rounded-lg bg-sea-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-sea-500"
            >
              Browse buildings
            </Link>
            <Link
              href="/account"
              className="rounded-lg border border-slate-300 px-5 py-2.5 text-sm font-semibold text-ink-900 hover:bg-white"
            >
              View account
            </Link>
          </div>
        </div>
      </div>
    </main>
  );
}
