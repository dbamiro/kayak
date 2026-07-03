"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { SiteHeader } from "@/components/SiteHeader";
import {
  createCheckoutSession,
  getPlans,
  isLoggedIn,
  mockCompleteCheckout,
  type Plan,
} from "@/lib/kayak-api";

const HUNT_PASS = "hunt_pass_30";

function fmtPrice(cents: number): string {
  if (cents === 0) return "Free";
  return `$${(cents / 100).toFixed(0)}`;
}

export default function PricingPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const [busyPlan, setBusyPlan] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const q = useQuery({
    queryKey: ["plans"],
    queryFn: getPlans,
  });

  async function startCheckout(plan: Plan) {
    setErr(null);
    if (plan.code === "free") return;
    if (!isLoggedIn()) {
      router.push(`/login?returnTo=${encodeURIComponent("/pricing")}`);
      return;
    }
    setBusyPlan(plan.code);
    try {
      const session = await createCheckoutSession(plan.code);
      if (session.mock_mode) {
        await mockCompleteCheckout(plan.code);
        await qc.invalidateQueries({ queryKey: ["entitlements"] });
        router.push("/billing/success");
        return;
      }
      if (session.checkout_url) {
        window.location.href = session.checkout_url;
        return;
      }
      setErr("Checkout is unavailable right now. Please try again in a few minutes.");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusyPlan(null);
    }
  }

  const plans = q.data || [];
  const hunt = plans.find((p) => p.code === HUNT_PASS);

  return (
    <main className="min-h-screen bg-slate-50">
      <SiteHeader />
      <div className="mx-auto max-w-3xl px-4 py-10">
        <h1 className="text-3xl font-bold text-ink-950">Pricing</h1>
        <p className="mt-2 text-ink-700">
          Browse move-in specials and calculate savings for free. Hunt Pass unlocks full Deal Reports — total savings
          breakdowns, lease-term comparisons, fee verification, and negotiation scripts when you are ready to apply.
        </p>

        {q.isLoading && <p className="mt-4">Loading plans…</p>}
        {q.isError && <p className="mt-4 text-red-600">{(q.error as Error).message}</p>}

        <ul className="mt-8 space-y-4">
          {plans
            .filter((p) => p.code !== "free")
            .map((p) => (
              <li
                key={p.code}
                className={`rounded-xl border bg-white p-5 shadow-sm ${
                  p.code === HUNT_PASS ? "border-sea-500 ring-1 ring-sea-200" : "border-slate-200"
                }`}
              >
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    {p.code === HUNT_PASS && (
                      <span className="mb-1 inline-block rounded-full bg-sea-100 px-2 py-0.5 text-xs font-semibold text-sea-800">
                        Recommended
                      </span>
                    )}
                    <div className="font-semibold text-ink-950">{p.name}</div>
                    <p className="mt-1 text-sm text-ink-700">{p.description}</p>
                  </div>
                  <div className="text-right">
                    <div className="text-2xl font-bold text-ink-950">{fmtPrice(p.price_cents)}</div>
                    {p.duration_days ? (
                      <div className="text-sm text-ink-500">for {p.duration_days} days</div>
                    ) : null}
                  </div>
                </div>
                {p.code === HUNT_PASS && (
                  <button
                    type="button"
                    disabled={busyPlan !== null}
                    onClick={() => void startCheckout(p)}
                    className="mt-4 w-full rounded-lg bg-sea-600 py-2.5 text-sm font-semibold text-white hover:bg-sea-500 disabled:opacity-60"
                  >
                    {busyPlan === p.code ? "Processing…" : "Unlock Hunt Pass"}
                  </button>
                )}
                {p.code !== HUNT_PASS && p.price_cents > 0 && (
                  <button
                    type="button"
                    disabled={busyPlan !== null}
                    onClick={() => void startCheckout(p)}
                    className="mt-4 w-full rounded-lg border border-slate-300 py-2.5 text-sm font-semibold text-ink-900 hover:bg-slate-50 disabled:opacity-60"
                  >
                    {busyPlan === p.code ? "Processing…" : `Choose ${p.name}`}
                  </button>
                )}
              </li>
            ))}
        </ul>

        {process.env.NODE_ENV === "development" && hunt && (
          <p className="mt-6 text-sm text-ink-500">
            Local dev: use <code className="rounded bg-slate-200 px-1">MOCK_CHECKOUT_MODE=true</code> for instant
            checkout, or set Stripe test keys + <code className="rounded bg-slate-200 px-1">MOCK_CHECKOUT_MODE=false</code>{" "}
            and follow <code className="rounded bg-slate-200 px-1">docs/STRIPE_RUNBOOK.md</code>.
          </p>
        )}
        {err && <p className="mt-4 text-sm text-red-600">{err}</p>}
      </div>
    </main>
  );
}
