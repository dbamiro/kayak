"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState, Suspense } from "react";
import { SiteHeader } from "@/components/SiteHeader";
import { clearAuth } from "@/lib/api";
import { getEntitlements, getMe, type EntitlementsResponse, type MeResponse } from "@/lib/kayak-api";

const PLAN_LABELS: Record<string, string> = {
  hunt_pass_30: "Premium Hunt Pass",
  premium_plus_30: "Premium Plus",
  concierge_one_time: "Concierge",
};

function AccountContent() {
  const searchParams = useSearchParams();
  const checkoutSuccess = searchParams.get("checkout") === "success";

  const [me, setMe] = useState<MeResponse | null>(null);
  const [ent, setEnt] = useState<EntitlementsResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setErr(null);
    setLoading(true);
    try {
      const m = await getMe();
      setMe(m);
      const e = await getEntitlements();
      setEnt(e);
    } catch {
      setMe(null);
      setEnt(null);
      setErr("Not signed in or session expired.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function logout() {
    clearAuth();
    setMe(null);
    setEnt(null);
    setErr("Not signed in or session expired.");
  }

  if (loading) {
    return (
      <main className="min-h-screen bg-slate-50">
        <SiteHeader />
        <p className="px-4 py-10 text-ink-700">Loading…</p>
      </main>
    );
  }

  if (!me) {
    return (
      <main className="min-h-screen bg-slate-50">
        <SiteHeader />
        <div className="mx-auto max-w-lg px-4 py-10">
          <h1 className="text-2xl font-bold">Account</h1>
          <p className="mt-2 text-ink-700">{err}</p>
          <div className="mt-6 flex gap-3">
            <Link href="/login" className="rounded-lg bg-sea-600 px-4 py-2 text-sm font-semibold text-white">
              Log in
            </Link>
            <Link href="/register" className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold">
              Register
            </Link>
          </div>
        </div>
      </main>
    );
  }

  const activePlans = ent?.active_plan_codes.filter((c) => c !== "free") ?? [];
  const primaryPlan = activePlans[0];
  const expiresAt = primaryPlan ? ent?.expires_at_by_plan[primaryPlan] : null;

  return (
    <main className="min-h-screen bg-slate-50">
      <SiteHeader />
      <div className="mx-auto max-w-lg px-4 py-10">
        <h1 className="text-2xl font-bold">Account</h1>
        <p className="mt-1 text-sm text-ink-700">
          {me.email}
          {me.name ? ` · ${me.name}` : ""}
        </p>
        <button
          type="button"
          onClick={logout}
          className="mt-4 rounded border border-slate-300 px-3 py-1.5 text-sm text-ink-900 hover:bg-slate-50"
        >
          Log out
        </button>

        {(checkoutSuccess || searchParams.get("from") === "billing") && (
          <div className="mt-6 rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">
            Payment successful — full Deal Reports are unlocked.{" "}
            <Link href="/search" className="font-semibold underline">
              Find a building
            </Link>
          </div>
        )}

        {ent && (
          <section className="mt-8 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-500">Plan &amp; access</h2>
            <p className="mt-2 text-lg font-semibold text-ink-950">
              {primaryPlan ? PLAN_LABELS[primaryPlan] || primaryPlan : "Free tier"}
            </p>
            {expiresAt && (
              <p className="mt-1 text-sm text-ink-600">
                Expires {new Date(expiresAt).toLocaleDateString(undefined, { dateStyle: "medium" })}
              </p>
            )}
            {!primaryPlan && (
              <Link href="/pricing" className="mt-3 inline-block text-sm font-semibold text-sea-600 underline">
                Unlock Hunt Pass →
              </Link>
            )}
            <ul className="mt-4 grid gap-1 border-t border-slate-100 pt-3 text-xs text-ink-700">
              {Object.entries(ent.feature_flags).map(([k, v]) => (
                <li key={k} className="flex justify-between">
                  <span>{k.replaceAll("_", " ")}</span>
                  <strong className={v ? "text-emerald-700" : "text-ink-400"}>{v ? "yes" : "no"}</strong>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </main>
  );
}

export default function AccountPage() {
  return (
    <Suspense fallback={<main className="min-h-screen px-4 py-10">Loading…</main>}>
      <AccountContent />
    </Suspense>
  );
}
