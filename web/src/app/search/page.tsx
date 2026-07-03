"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { SiteHeader } from "@/components/SiteHeader";
import { fmtMoney } from "@/lib/format";
import { formatIncentiveHeadline } from "@/lib/incentive-display";
import { getSearch, type SearchHit, type SearchParams } from "@/lib/kayak-api";

type BuildingCard = {
  building_id: string;
  name: string;
  city: string;
  submarket: string;
  listings: SearchHit[];
  minListed: number | null;
  maxListed: number | null;
  minEffective: number | null;
  maxEffective: number | null;
  dealSignal: string;
  hasConcession: boolean;
  hasFees: boolean;
  incentive: SearchHit | null;
};

function toNum(v: string | number | null | undefined): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function rentRange(min: number | null, max: number | null): string {
  if (min === null && max === null) return "—";
  if (min !== null && max !== null && min !== max) return `${fmtMoney(min)} – ${fmtMoney(max)}`;
  return fmtMoney(min ?? max);
}

function groupByBuilding(rows: SearchHit[]): BuildingCard[] {
  const map = new Map<string, BuildingCard>();
  const order: string[] = [];
  for (const r of rows) {
    let card = map.get(r.building_id);
    if (!card) {
      card = {
        building_id: r.building_id,
        name: r.name,
        city: r.city,
        submarket: r.neighborhood || r.dmv_area.replaceAll("_", " "),
        listings: [],
        minListed: null,
        maxListed: null,
        minEffective: null,
        maxEffective: null,
        dealSignal: r.deal_signal || "fair",
        hasConcession: false,
        hasFees: false,
        incentive: r.best_incentive_id ? r : null,
      };
      map.set(r.building_id, card);
      order.push(r.building_id);
    }
    card!.listings.push(r);
    if (r.best_incentive_id && !card!.incentive) {
      card!.incentive = r;
    }
    const listed = toNum(r.base_rent_monthly) ?? toNum(r.listed_rent);
    const eff = toNum(r.effective_rent_monthly) ?? toNum(r.effective_rent);
    if (listed !== null) {
      card!.minListed = card!.minListed === null ? listed : Math.min(card!.minListed, listed);
      card!.maxListed = card!.maxListed === null ? listed : Math.max(card!.maxListed, listed);
    }
    if (eff !== null) {
      card!.minEffective = card!.minEffective === null ? eff : Math.min(card!.minEffective, eff);
      card!.maxEffective = card!.maxEffective === null ? eff : Math.max(card!.maxEffective, eff);
    }
    if (r.has_concession) card!.hasConcession = true;
    if (r.has_fees) card!.hasFees = true;
    if (r.deal_signal === "strong") card!.dealSignal = "strong";
    else if (r.deal_signal === "weak" && card!.dealSignal !== "strong") card!.dealSignal = "weak";
  }
  return order.map((id) => map.get(id)!);
}

function specialBadge(hit: SearchHit): string | null {
  if (!hit.best_incentive_id) return null;
  return formatIncentiveHeadline(hit);
}

function dealBadge(signal: string) {
  const s = signal.toLowerCase();
  const cls =
    s === "strong"
      ? "bg-emerald-100 text-emerald-800"
      : s === "weak"
        ? "bg-amber-100 text-amber-800"
        : "bg-slate-100 text-slate-700";
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium capitalize ${cls}`}>{s} deal</span>
  );
}

type SortKey = SearchParams["sort"];

export default function SearchPage() {
  const [sort, setSort] = useState<SortKey>("default");
  const [minFreeMonths, setMinFreeMonths] = useState("");
  const [customFreeMonths, setCustomFreeMonths] = useState("");
  const [minSavings, setMinSavings] = useState("");
  const [specialsOnly, setSpecialsOnly] = useState(false);
  const [excludeDemo, setExcludeDemo] = useState(false);

  const effectiveMinFreeMonths = customFreeMonths.trim() || minFreeMonths;

  const queryParams = useMemo((): SearchParams => {
    const p: SearchParams = {};
    if (sort && sort !== "default") p.sort = sort;
    if (effectiveMinFreeMonths) p.min_free_months = Number(effectiveMinFreeMonths);
    if (minSavings) p.min_savings = Number(minSavings);
    if (specialsOnly) p.has_incentive = true;
    if (excludeDemo) p.include_demo = false;
    return p;
  }, [sort, effectiveMinFreeMonths, minSavings, specialsOnly, excludeDemo]);

  const filtersActive = specialsOnly || !!minFreeMonths || !!minSavings || (sort && sort !== "default");

  const q = useQuery({
    queryKey: ["search", queryParams],
    queryFn: () => getSearch(queryParams),
  });

  const cards = groupByBuilding(q.data || []);

  return (
    <main className="min-h-screen bg-slate-50">
      <SiteHeader />
      <div className="mx-auto max-w-5xl px-4 py-8">
        <Link href="/" className="text-sm text-sea-600">
          ← Home
        </Link>
        <h1 className="mt-4 text-2xl font-bold text-ink-950">Find apartments by real savings</h1>
        <p className="mt-1 text-sm text-ink-700">
          Compare sticker rent vs effective rent after free months, waived fees, and concessions.
        </p>

        <div className="mt-6 grid gap-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:grid-cols-2 lg:grid-cols-4">
          <label className="block text-sm">
            <span className="font-medium text-ink-800">Sort</span>
            <select
              value={sort ?? "default"}
              onChange={(e) => setSort(e.target.value as SortKey)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-2 text-ink-900"
            >
              <option value="default">Best match</option>
              <option value="savings">Biggest savings</option>
              <option value="effective_rent">Lowest effective rent</option>
              <option value="discount">Highest discount</option>
            </select>
          </label>
          <label className="block text-sm">
            <span className="font-medium text-ink-800">Minimum free months</span>
            <select
              value={minFreeMonths}
              onChange={(e) => setMinFreeMonths(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-2 text-ink-900"
            >
              <option value="">Any</option>
              <option value="1">1+</option>
              <option value="2">2+</option>
              <option value="3">3+</option>
              <option value="4">4+</option>
              <option value="5">5+</option>
              <option value="6">6+</option>
            </select>
          </label>
          <label className="block text-sm sm:col-span-2">
            <span className="font-medium text-ink-800">Custom minimum free months</span>
            <input
              type="number"
              min={0}
              step={0.1}
              placeholder="e.g. 1.5, 2.5, 6"
              value={customFreeMonths}
              onChange={(e) => setCustomFreeMonths(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-2 text-ink-900"
            />
          </label>
          <label className="block text-sm">
            <span className="font-medium text-ink-800">Minimum savings</span>
            <select
              value={minSavings}
              onChange={(e) => setMinSavings(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-2 text-ink-900"
            >
              <option value="">Any</option>
              <option value="1000">$1,000+</option>
              <option value="3000">$3,000+</option>
              <option value="5000">$5,000+</option>
              <option value="10000">$10,000+</option>
            </select>
          </label>
          <label className="flex items-end gap-2 text-sm">
            <input
              type="checkbox"
              checked={specialsOnly}
              onChange={(e) => setSpecialsOnly(e.target.checked)}
              className="h-4 w-4 rounded border-slate-300"
            />
            <span className="font-medium text-ink-800">Show specials only</span>
          </label>
          <label className="flex items-end gap-2 text-sm">
            <input
              type="checkbox"
              checked={excludeDemo}
              onChange={(e) => setExcludeDemo(e.target.checked)}
              className="h-4 w-4 rounded border-slate-300"
            />
            <span className="font-medium text-ink-800">Hide demo data</span>
          </label>
        </div>

        {q.isLoading && <p className="mt-6 text-ink-700">Loading…</p>}
        {q.isError && <p className="mt-6 text-red-600">{(q.error as Error).message}</p>}

        {!q.isLoading && !q.isError && cards.length === 0 && (
          <div className="mt-6 rounded-xl border border-slate-200 bg-white p-6 text-center">
            {filtersActive ? (
              <>
                <p className="font-medium text-ink-900">No specials match these filters yet.</p>
                <p className="mt-2 text-sm text-ink-600">
                  Try lowering minimum free months or savings, or turn off &quot;Show specials only&quot;.
                </p>
                <Link
                  href="/submit-special"
                  className="mt-4 inline-block text-sm font-semibold text-sea-600 hover:underline"
                >
                  Submit a special you found →
                </Link>
              </>
            ) : (
              <p className="text-ink-700">
                No listings yet. Run seed + incentive migration, or crawl a pilot building — see README.
              </p>
            )}
          </div>
        )}

        <ul className="mt-6 space-y-4">
          {cards.map((b) => {
            const inc = b.incentive;
            const badge = inc ? specialBadge(inc) : null;
            return (
              <li key={b.building_id}>
                <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-sea-500">
                  <Link href={`/buildings/${b.building_id}`} className="block">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="text-lg font-semibold text-ink-950">{b.name}</div>
                        <p className="text-sm text-ink-700">
                          {b.city} · {b.submarket}
                        </p>
                        <p className="mt-1 text-xs text-ink-500">
                          {b.listings.length} listing{b.listings.length === 1 ? "" : "s"} in latest snapshots
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {inc?.incentive_is_demo && (
                          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
                            Demo data
                          </span>
                        )}
                        {badge && (
                          <span className="rounded-full bg-violet-100 px-2 py-0.5 text-xs font-semibold text-violet-900">
                            {badge}
                          </span>
                        )}
                        {dealBadge(b.dealSignal)}
                        {b.hasConcession && (
                          <span className="rounded-full bg-violet-100 px-2 py-0.5 text-xs font-medium text-violet-800">
                            Concession
                          </span>
                        )}
                      </div>
                    </div>

                    {inc ? (
                      <div className="mt-3 space-y-1 text-sm">
                        {inc.estimated_savings != null && (
                          <p className="font-semibold text-emerald-700">
                            Save {fmtMoney(inc.estimated_savings)}
                          </p>
                        )}
                        {inc.effective_rent != null && (
                          <p className="text-ink-800">
                            Effective rent{" "}
                            <strong className="text-sea-700">{fmtMoney(inc.effective_rent)}/mo</strong>
                          </p>
                        )}
                        {inc.discount_percent != null && (
                          <p className="text-ink-600">
                            {inc.discount_percent}% off lease value
                          </p>
                        )}
                      </div>
                    ) : (
                      <div className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
                        <div>
                          <span className="text-ink-500">Listed </span>
                          <span className="font-semibold text-ink-900">{rentRange(b.minListed, b.maxListed)}</span>
                          <span className="text-ink-500"> /mo</span>
                        </div>
                        <div>
                          <span className="text-ink-500">Effective </span>
                          <span className="font-semibold text-ink-900">{rentRange(b.minEffective, b.maxEffective)}</span>
                          <span className="text-ink-500"> /mo</span>
                        </div>
                        <p className="sm:col-span-2 text-xs text-ink-500">No current special tracked</p>
                      </div>
                    )}
                  </Link>
                  <div className="mt-4 flex flex-wrap gap-2 border-t border-slate-100 pt-4">
                    <Link
                      href={`/buildings/${b.building_id}`}
                      className="rounded-lg bg-sea-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-sea-500"
                    >
                      {inc ? "View savings breakdown" : "View details"}
                    </Link>
                    <Link
                      href={`/buildings/${b.building_id}#deal-report`}
                      className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-ink-900 hover:bg-slate-50"
                    >
                      Deal Report
                    </Link>
                  </div>
                </article>
              </li>
            );
          })}
        </ul>
      </div>
    </main>
  );
}
