"use client";

import { useState } from "react";
import { SiteHeader } from "@/components/SiteHeader";
import { fmtMoney } from "@/lib/format";
import { calculateIncentive, parseIncentiveText, type IncentiveCalculation } from "@/lib/kayak-api";

export default function CalculatorPage() {
  const [rent, setRent] = useState(2400);
  const [term, setTerm] = useState(16);
  const [freeMonths, setFreeMonths] = useState(4);
  const [recurring, setRecurring] = useState(0);
  const [waived, setWaived] = useState(0);
  const [gift, setGift] = useState(0);
  const [parking, setParking] = useState(0);
  const [rawText, setRawText] = useState("4 months free on 16-month lease");
  const [result, setResult] = useState<IncentiveCalculation | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function runCalc() {
    setErr(null);
    try {
      const r = await calculateIncentive({
        listed_rent: rent,
        lease_term_months: term,
        free_months: freeMonths,
        recurring_fee_monthly: recurring,
        one_time_fee: 0,
        waived_fee_amount: waived,
        gift_card_amount: gift,
        parking_discount_monthly: parking,
      });
      setResult(r);
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  async function runParse() {
    setErr(null);
    try {
      const r = await parseIncentiveText({ raw_text: rawText, listed_rent: rent, lease_term_months: term });
      if (r.parsed.free_months != null) setFreeMonths(Number(r.parsed.free_months));
      if (r.calculation) setResult(r.calculation);
      else await runCalc();
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  return (
    <main className="min-h-screen bg-slate-50">
      <SiteHeader />
      <div className="mx-auto max-w-lg px-4 py-8">
        <h1 className="text-2xl font-bold">Savings calculator</h1>
        <p className="mt-1 text-sm text-ink-700">
          Example: $2,400/mo, 16 months, 4 months free → $1,800 effective rent.
        </p>
        <label className="mt-6 block text-sm">
          Special text (optional)
          <textarea
            className="mt-1 w-full rounded border px-3 py-2 text-sm"
            rows={2}
            value={rawText}
            onChange={(e) => setRawText(e.target.value)}
          />
        </label>
        <button type="button" onClick={() => void runParse()} className="mt-2 text-sm font-semibold text-sea-600">
          Parse text
        </button>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <label className="text-sm">
            Listed rent
            <input
              type="number"
              className="mt-1 w-full rounded border px-3 py-2"
              value={rent}
              onChange={(e) => setRent(Number(e.target.value))}
            />
          </label>
          <label className="text-sm">
            Lease months
            <input
              type="number"
              className="mt-1 w-full rounded border px-3 py-2"
              value={term}
              onChange={(e) => setTerm(Number(e.target.value))}
            />
          </label>
          <label className="text-sm">
            Free months
            <input
              type="number"
              step="0.1"
              className="mt-1 w-full rounded border px-3 py-2"
              value={freeMonths}
              onChange={(e) => setFreeMonths(Number(e.target.value))}
            />
          </label>
          <label className="text-sm">
            Waived fees
            <input
              type="number"
              className="mt-1 w-full rounded border px-3 py-2"
              value={waived}
              onChange={(e) => setWaived(Number(e.target.value))}
            />
          </label>
        </div>
        <button
          type="button"
          onClick={() => void runCalc()}
          className="mt-6 w-full rounded-lg bg-sea-600 py-2.5 text-sm font-semibold text-white"
        >
          Calculate
        </button>
        {err && <p className="mt-2 text-sm text-red-600">{err}</p>}
        {result && (
          <div className="mt-8 rounded-xl border border-emerald-200 bg-emerald-50 p-5 text-sm">
            <p>
              <span className="text-ink-500">Effective rent </span>
              <strong className="text-xl text-emerald-800">{fmtMoney(result.effective_rent)}/mo</strong>
            </p>
            <p className="mt-2">
              <span className="text-ink-500">Total savings </span>
              <strong>{fmtMoney(result.total_savings)}</strong> ({result.discount_percent}%)
            </p>
            <p className="mt-1">
              <span className="text-ink-500">All-in effective </span>
              {fmtMoney(result.all_in_effective_rent)}/mo
            </p>
          </div>
        )}
      </div>
    </main>
  );
}