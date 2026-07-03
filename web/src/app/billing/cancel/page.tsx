"use client";

import Link from "next/link";
import { SiteHeader } from "@/components/SiteHeader";

export default function BillingCancelPage() {
  return (
    <main className="min-h-screen bg-slate-50">
      <SiteHeader />
      <div className="mx-auto max-w-lg px-4 py-12 text-center">
        <div className="rounded-xl border border-slate-200 bg-white p-8 shadow-sm">
          <h1 className="text-2xl font-bold text-ink-950">Checkout cancelled</h1>
          <p className="mt-2 text-ink-700">
            No charge was made. You can still browse move-in specials and Deal Report previews for free.
          </p>
          <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:justify-center">
            <Link
              href="/pricing"
              className="rounded-lg bg-sea-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-sea-500"
            >
              View pricing
            </Link>
            <Link
              href="/search"
              className="rounded-lg border border-slate-300 px-5 py-2.5 text-sm font-semibold text-ink-900 hover:bg-slate-50"
            >
              Back to search
            </Link>
          </div>
        </div>
      </div>
    </main>
  );
}
