"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { SiteHeader } from "@/components/SiteHeader";
import { fmtMoney } from "@/lib/format";
import { formatIncentiveHeadline } from "@/lib/incentive-display";
import { getIncentives, type IncentiveCard } from "@/lib/kayak-api";

function SpecialCard({ s }: { s: IncentiveCard }) {
  return (
    <li className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-sea-400">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          {s.is_demo && (
            <span className="rounded bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
              Demo data
            </span>
          )}
          {!s.is_demo && (s.verified_at || s.status === "verified" || s.status === "active") && (
            <span className="rounded bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-800">
              Verified
            </span>
          )}
          {s.status === "pending_review" && (
            <span className="rounded bg-slate-200 px-2 py-0.5 text-xs font-medium text-ink-700">
              Pending review
            </span>
          )}
        </div>
        {s.discount_percent != null && (
          <span className="text-sm font-bold text-emerald-700">{s.discount_percent}% off</span>
        )}
      </div>
      <h2 className="mt-2 text-lg font-semibold text-ink-950">
        {s.building_name || "Building"}
        {s.city ? ` · ${s.city}` : ""}
      </h2>
      <p className="mt-1 text-sm font-medium text-violet-900">
        {formatIncentiveHeadline(s)}
      </p>
      {s.special_summary && s.special_summary !== formatIncentiveHeadline(s) && (
        <p className="mt-1 text-sm text-ink-700">{s.special_summary}</p>
      )}
      <div className="mt-4 grid gap-2 text-sm sm:grid-cols-3">
        <div>
          <span className="text-ink-500">Listed </span>
          <span className="font-semibold">{fmtMoney(s.listed_rent)}</span>
        </div>
        <div>
          <span className="text-ink-500">Effective </span>
          <span className="font-semibold text-sea-700">{fmtMoney(s.effective_rent)}</span>
        </div>
        <div>
          <span className="text-ink-500">Savings </span>
          <span className="font-semibold text-emerald-700">{fmtMoney(s.total_savings)}</span>
        </div>
      </div>
      {s.building_id && (
        <Link
          href={`/buildings/${s.building_id}#deal-report`}
          className="mt-4 inline-block text-sm font-semibold text-sea-600 underline"
        >
          View Deal Report →
        </Link>
      )}
    </li>
  );
}

export default function SpecialsPage() {
  const q = useQuery({ queryKey: ["incentives"], queryFn: () => getIncentives({ limit: 50 }) });
  const hasDemo = (q.data || []).some((s) => s.is_demo);

  return (
    <main className="min-h-screen bg-slate-50">
      <SiteHeader />
      <div className="mx-auto max-w-5xl px-4 py-8">
        <h1 className="text-2xl font-bold text-ink-950">Move-in specials</h1>
        <p className="mt-1 text-ink-700">Ranked by total savings, then discount %, then effective rent.</p>
        {hasDemo && (
          <p className="mt-2 text-sm text-amber-800">
            Demo specials are labeled — confirm live offers with the leasing office.
          </p>
        )}
        {q.isLoading && <p className="mt-6">Loading…</p>}
        {q.isError && <p className="mt-6 text-red-600">{(q.error as Error).message}</p>}
        <ul className="mt-6 space-y-4">
          {(q.data || []).map((s) => (
            <SpecialCard key={s.id} s={s} />
          ))}
        </ul>
        {!q.isLoading && (q.data || []).length === 0 && (
          <p className="mt-6 text-ink-600">
            No move-in specials listed yet.{" "}
            <Link href="/submit-special" className="text-sea-600 underline">
              Submit a special
            </Link>{" "}
            or check back soon.
          </p>
        )}
      </div>
    </main>
  );
}
