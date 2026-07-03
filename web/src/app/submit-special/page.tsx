"use client";

import { useState } from "react";
import Link from "next/link";
import { SiteHeader } from "@/components/SiteHeader";
import { submitIncentive } from "@/lib/kayak-api";

export default function SubmitSpecialPage() {
  const [buildingName, setBuildingName] = useState("");
  const [city, setCity] = useState("");
  const [rent, setRent] = useState(2400);
  const [term, setTerm] = useState(12);
  const [rawText, setRawText] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [ok, setOk] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setOk(false);
    try {
      await submitIncentive({
        building_name: buildingName,
        city: city || undefined,
        rent,
        lease_term_months: term,
        raw_special_text: rawText,
        source_url: sourceUrl || undefined,
      });
      setOk(true);
    } catch (ex) {
      setErr((ex as Error).message);
    }
  }

  return (
    <main className="min-h-screen bg-slate-50">
      <SiteHeader />
      <div className="mx-auto max-w-md px-4 py-8">
        <h1 className="text-2xl font-bold">Submit a special</h1>
        <p className="mt-1 text-sm text-ink-700">Share a move-in offer you found. We parse and calculate effective rent.</p>
        <form onSubmit={onSubmit} className="mt-6 space-y-4">
          <label className="block text-sm">
            Building name
            <input className="mt-1 w-full rounded border px-3 py-2" required value={buildingName} onChange={(e) => setBuildingName(e.target.value)} />
          </label>
          <label className="block text-sm">
            City
            <input className="mt-1 w-full rounded border px-3 py-2" value={city} onChange={(e) => setCity(e.target.value)} />
          </label>
          <label className="block text-sm">
            Listed rent
            <input type="number" className="mt-1 w-full rounded border px-3 py-2" required value={rent} onChange={(e) => setRent(Number(e.target.value))} />
          </label>
          <label className="block text-sm">
            Lease term (months)
            <input type="number" className="mt-1 w-full rounded border px-3 py-2" required value={term} onChange={(e) => setTerm(Number(e.target.value))} />
          </label>
          <label className="block text-sm">
            Special text
            <textarea className="mt-1 w-full rounded border px-3 py-2" required rows={3} value={rawText} onChange={(e) => setRawText(e.target.value)} placeholder="e.g. 2 months free + waived admin fee" />
          </label>
          <label className="block text-sm">
            Source URL (optional)
            <input type="url" className="mt-1 w-full rounded border px-3 py-2" value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} />
          </label>
          {err && <p className="text-sm text-red-600">{err}</p>}
          {ok && (
            <p className="text-sm text-emerald-700">
              Thanks — your submission is pending admin review and will appear in search once verified.
            </p>
          )}
          <button type="submit" className="w-full rounded-lg bg-sea-600 py-2.5 text-sm font-semibold text-white">
            Submit
          </button>
        </form>
      </div>
    </main>
  );
}
