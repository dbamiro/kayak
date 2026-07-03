import Link from "next/link";
import { SiteHeader } from "@/components/SiteHeader";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-slate-50">
      <SiteHeader />
      <section className="mx-auto max-w-5xl px-4 py-16">
        <p className="text-sm font-medium uppercase tracking-wide text-sea-600">Move-in specials</p>
        <h1 className="mt-2 text-4xl font-bold tracking-tight text-ink-950">
          Find apartments with the biggest move-in specials.
        </h1>
        <p className="mt-4 max-w-2xl text-lg text-ink-700">
          Kayak calculates the real rent after free months, waived fees, and concessions — so you compare
          effective rent and total savings, not just sticker price.
        </p>
        <div className="mt-8 flex flex-wrap gap-4">
          <Link
            href="/specials"
            className="rounded-lg bg-sea-600 px-5 py-2.5 text-sm font-semibold text-white shadow hover:bg-sea-500"
          >
            Browse Specials
          </Link>
          <Link
            href="/calculator"
            className="rounded-lg border border-slate-300 bg-white px-5 py-2.5 text-sm font-semibold text-ink-900 hover:bg-slate-50"
          >
            Calculate My Deal
          </Link>
        </div>
        <ul className="mt-12 grid gap-4 sm:grid-cols-2">
          {[
            "Weeks or months free — any amount",
            "Effective rent after concessions",
            "Waived admin & application fees",
            "Total savings & discount %",
          ].map((t) => (
            <li key={t} className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-ink-700 shadow-sm">
              {t}
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
