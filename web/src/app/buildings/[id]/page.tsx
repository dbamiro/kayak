"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { DealReportCard } from "@/components/DealReportCard";
import { SiteHeader } from "@/components/SiteHeader";
import { fmtMoney, rentRange, toNum } from "@/lib/format";
import {
  getBuilding,
  getBuildingHistory,
  getDealReport,
  getIncentives,
  type IncentiveCard,
  type ListingQuote,
} from "@/lib/kayak-api";

function summarizeListings(listings: ListingQuote[]) {
  let minListed: number | null = null;
  let maxListed: number | null = null;
  let minEff: number | null = null;
  let maxEff: number | null = null;
  for (const l of listings) {
    const listed = toNum(l.base_rent_monthly);
    const eff = toNum(l.effective_rent_monthly);
    if (listed !== null) {
      minListed = minListed === null ? listed : Math.min(minListed, listed);
      maxListed = maxListed === null ? listed : Math.max(maxListed, listed);
    }
    if (eff !== null) {
      minEff = minEff === null ? eff : Math.min(minEff, eff);
      maxEff = maxEff === null ? eff : Math.max(maxEff, eff);
    }
  }
  return { minListed, maxListed, minEff, maxEff };
}

function hasConcessions(l: ListingQuote): boolean {
  const c = l.concessions;
  return c != null && typeof c === "object" && Object.keys(c).length > 0;
}

function hasFees(l: ListingQuote): boolean {
  const f = l.fees;
  return f != null && typeof f === "object" && Object.keys(f).length > 0;
}

export default function BuildingPage() {
  const params = useParams();
  const id = params.id as string;

  const buildingQ = useQuery({
    queryKey: ["building", id],
    queryFn: () => getBuilding(id),
    enabled: !!id,
  });

  const historyQ = useQuery({
    queryKey: ["building-history", id],
    queryFn: () => getBuildingHistory(id),
    enabled: !!id,
  });

  const dealQ = useQuery({
    queryKey: ["deal", id],
    queryFn: () => getDealReport(id),
    enabled: !!id,
  });

  const specialsQ = useQuery({
    queryKey: ["incentives", id],
    queryFn: () => getIncentives({ building_id: id }),
    enabled: !!id,
  });

  const building = buildingQ.data?.building;
  const listings = buildingQ.data?.listings ?? [];
  const rent = summarizeListings(listings);

  const historyPreview = (() => {
    const series = historyQ.data?.series ?? {};
    const points: { date: string; base: number | null; eff: number | null; label: string }[] = [];
    for (const [listingId, snaps] of Object.entries(series)) {
      const last = snaps[snaps.length - 1];
      if (!last) continue;
      const label = historyQ.data?.floorplans?.[listingId] || listingId.slice(0, 8);
      points.push({
        date: last.captured_at,
        base: toNum(last.base_rent_monthly),
        eff: toNum(last.effective_rent_monthly),
        label,
      });
    }
    return points.slice(0, 6);
  })();

  return (
    <main className="min-h-screen bg-slate-50">
      <SiteHeader />
      <div className="mx-auto max-w-4xl px-4 py-8">
        <Link href="/search" className="text-sm text-sea-600">
          ← Search
        </Link>

        {buildingQ.isLoading && <p className="mt-4 text-ink-700">Loading building…</p>}
        {buildingQ.isError && (
          <p className="mt-4 text-red-600">{(buildingQ.error as Error).message}</p>
        )}

        {building && (
          <>
            <h1 className="mt-4 text-3xl font-bold text-ink-950">{building.name}</h1>
            <p className="mt-1 text-ink-700">
              {building.city}, {building.state}
              {building.neighborhood ? ` · ${building.neighborhood}` : ""}
            </p>
            {building.property_url && (
              <a
                href={building.property_url}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-2 inline-block text-sm text-sea-600 underline"
              >
                Property website
              </a>
            )}

            <section className="mt-6 grid gap-3 sm:grid-cols-0">
              <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:col-span-2">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-500">Rent snapshot</h2>
                <div className="mt-2 grid gap-4 sm:grid-cols-2">
                  <div>
                    <span className="text-sm text-ink-500">Listed </span>
                    <span className="text-xl font-bold text-ink-950">
                      {rentRange(rent.minListed, rent.maxListed)}
                    </span>
                    <span className="text-sm text-ink-500"> /mo</span>
                  </div>
                  <div>
                    <span className="text-sm text-ink-500">Effective </span>
                    <span className="text-xl font-bold text-ink-950">
                      {rentRange(rent.minEff, rent.maxEff)}
                    </span>
                    <span className="text-sm text-ink-500"> /mo</span>
                  </div>
                </div>
              </div>
            </section>

            {specialsQ.data && specialsQ.data.length > 0 && (
              <section className="mt-6 rounded-xl border border-violet-200 bg-violet-50/50 p-4 shadow-sm">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-violet-800">
                  Current specials
                </h2>
                <ul className="mt-3 space-y-3">
                  {specialsQ.data.map((s: IncentiveCard) => (
                    <li key={s.id} className="rounded-lg border border-violet-100 bg-white p-3 text-sm">
                      <p className="font-medium text-ink-900">
                        {s.special_summary || s.raw_text || "Move-in special"}
                      </p>
                      <div className="mt-2 flex flex-wrap gap-3 text-ink-700">
                        {s.listed_rent != null && <span>Listed {fmtMoney(s.listed_rent)}/mo</span>}
                        {s.effective_rent != null && (
                          <span>
                            Effective <strong className="text-sea-700">{fmtMoney(s.effective_rent)}/mo</strong>
                          </span>
                        )}
                        {s.total_savings != null && (
                          <span>
                            Savings <strong className="text-emerald-700">{fmtMoney(s.total_savings)}</strong>
                          </span>
                        )}
                        {s.is_demo && (
                          <span className="rounded bg-amber-100 px-1.5 text-xs text-amber-800">Demo</span>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
                <Link href="/specials" className="mt-3 inline-block text-sm text-sea-600 hover:underline">
                  Browse all specials →
                </Link>
              </section>
            )}

            {listings.length > 0 && (
              <section className="mt-6 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-500">Floorplans</h2>
                <div className="mt-3 overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr className="border-b text-ink-500">
                        <th className="py-2 pr-3">Unit / plan</th>
                        <th className="py-2 pr-3">Beds</th>
                        <th className="py-2 pr-3">Listed</th>
                        <th className="py-2 pr-3">Effective</th>
                        <th className="py-2">Signals</th>
                      </tr>
                    </thead>
                    <tbody>
                      {listings.map((l) => (
                        <tr key={l.listing_id} className="border-b border-slate-50">
                          <td className="py-2 pr-3 font-medium text-ink-900">
                            {l.floorplan_name || l.unit_label || "—"}
                          </td>
                          <td className="py-2 pr-3 text-ink-700">{l.bedrooms ?? "—"}</td>
                          <td className="py-2 pr-3">{fmtMoney(toNum(l.base_rent_monthly))}</td>
                          <td className="py-2 pr-3">{fmtMoney(toNum(l.effective_rent_monthly))}</td>
                          <td className="py-2 text-xs text-ink-600">
                            {hasConcessions(l) && (
                              <span className="mr-1 rounded bg-violet-100 px-1.5 py-0.5 text-violet-800">
                                Concession
                              </span>
                            )}
                            {hasFees(l) && (
                              <span className="rounded bg-orange-100 px-1.5 py-0.5 text-orange-800">Fees</span>
                            )}
                            {!hasConcessions(l) && !hasFees(l) && "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            {historyPreview.length > 0 && (
              <section className="mt-6 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-500">
                  Rent history preview
                </h2>
                <ul className="mt-3 space-y-2 text-sm">
                  {historyPreview.map((h) => (
                    <li key={h.label} className="flex flex-wrap justify-between gap-2 border-b border-slate-50 py-1">
                      <span className="font-medium text-ink-800">{h.label}</span>
                      <span className="text-ink-600">
                        {h.date ? new Date(h.date).toLocaleDateString() : "—"} · base {fmtMoney(h.base)} · eff{" "}
                        {fmtMoney(h.eff)}
                      </span>
                    </li>
                  ))}
                </ul>
                <p className="mt-2 text-xs text-ink-500">Full timeline unlocks in the Deal Report.</p>
              </section>
            )}
          </>
        )}

        {dealQ.isLoading && <p className="mt-8 text-ink-700">Loading deal report…</p>}
        {dealQ.isError && (
          <p className="mt-8 text-red-600">{(dealQ.error as Error).message}</p>
        )}
        {dealQ.data && (
          <div className="mt-8">
            <DealReportCard report={dealQ.data} buildingId={id} />
          </div>
        )}
      </div>
    </main>
  );
}
