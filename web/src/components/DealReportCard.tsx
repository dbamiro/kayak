"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  createCheckoutSession,
  isLoggedIn,
  mockCompleteCheckout,
  type DealReport,
} from "@/lib/kayak-api";
import { dealSignalClass, fmtMoney, toNum } from "@/lib/format";

type Props = {
  report: DealReport;
  buildingId: string;
};

export function DealReportCard({ report, buildingId }: Props) {
  const router = useRouter();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [checkoutErr, setCheckoutErr] = useState<string | null>(null);

  const preview = report.preview;
  const paywall = report.paywall;
  const full = report.full_report;
  const isFull = report.access === "full";

  async function unlock(planCode: string) {
    setCheckoutErr(null);
    if (!isLoggedIn()) {
      router.push(`/login?returnTo=${encodeURIComponent(`/buildings/${buildingId}`)}`);
      return;
    }
    setBusy(true);
    try {
      const session = await createCheckoutSession(planCode);
      if (session.mock_mode) {
        await mockCompleteCheckout(planCode);
        await qc.invalidateQueries({ queryKey: ["deal", buildingId] });
        await qc.invalidateQueries({ queryKey: ["entitlements"] });
        router.push("/billing/success");
        return;
      }
      if (session.checkout_url) {
        window.location.href = session.checkout_url;
        return;
      }
      setCheckoutErr("Checkout is unavailable right now. Please try again in a few minutes.");
    } catch (e) {
      setCheckoutErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const savings = preview.potential_savings_range;
  const savingsMin = toNum(savings?.min as number | string | undefined);
  const savingsMax = toNum(savings?.max as number | string | undefined);

  return (
    <section id="deal-report" className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-ink-950">Deal Report</h2>
          <p className="text-sm text-ink-600">{report.building_name}</p>
        </div>
        {preview.deal_signal && (
          <span
            className={`rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${dealSignalClass(preview.deal_signal)}`}
          >
            {preview.deal_signal} deal
          </span>
        )}
      </div>

      {preview.incentive && (
        <div className="mt-4 rounded-lg border border-violet-200 bg-violet-50 p-4 text-sm">
          <p className="font-semibold text-violet-900">Current special</p>
          <p className="mt-1">{preview.incentive.special_text}</p>
          {preview.incentive.effective_rent != null && (
            <p className="mt-2">
              Effective <strong>{fmtMoney(preview.incentive.effective_rent)}/mo</strong>
              {preview.incentive.total_savings != null && (
                <> · Savings {fmtMoney(preview.incentive.total_savings)}</>
              )}
            </p>
          )}
        </div>
      )}

      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Stat label="Listed rent" value={fmtMoney(toNum(preview.listed_rent))} />
        <Stat label="Effective rent" value={fmtMoney(toNum(preview.estimated_effective_rent))} />
        <Stat
          label="Total savings"
          value={
            savingsMin !== null || savingsMax !== null
              ? `${fmtMoney(savingsMin)} – ${fmtMoney(savingsMax)}`
              : "—"
          }
          hint={preview.savings_disclaimer || savings?.disclaimer}
        />
      </div>

      {preview.negotiation_signal && (
        <p className="mt-3 text-sm text-ink-700">
          <span className="font-medium">Negotiation signal:</span> {preview.negotiation_signal}
        </p>
      )}
      {preview.hidden_fee_signal && (
        <p className="mt-1 text-sm text-ink-700">
          <span className="font-medium">Fees:</span> {preview.hidden_fee_signal}
        </p>
      )}

      {!isFull && paywall && (
        <div className="mt-6 rounded-lg border border-amber-200 bg-amber-50 p-4">
          <h3 className="font-semibold text-ink-950">{paywall.headline}</h3>
          <p className="mt-1 text-sm text-ink-700">{paywall.subheadline}</p>
          <ul className="mt-3 list-inside list-disc text-sm text-ink-800">
            {paywall.value_bullets.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
          {report.locked_sections.length > 0 && (
            <div className="mt-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-ink-500">Locked</p>
              <ul className="mt-1 flex flex-wrap gap-2">
                {report.locked_sections.map((s) => (
                  <li
                    key={s}
                    className="rounded-full border border-amber-300 bg-white px-2 py-0.5 text-xs text-ink-700"
                  >
                    🔒 {s.replaceAll("_", " ")}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <button
            type="button"
            disabled={busy}
            onClick={() => void unlock(paywall.recommended_plan)}
            className="mt-4 w-full rounded-lg bg-sea-600 py-2.5 text-sm font-semibold text-white hover:bg-sea-500 disabled:opacity-60 sm:w-auto sm:px-6"
          >
            {busy ? "Processing…" : paywall.cta}
          </button>
          <p className="mt-2 text-xs text-ink-500">
            Or{" "}
            <Link href="/pricing" className="text-sea-600 underline">
              compare plans
            </Link>
          </p>
          {checkoutErr && <p className="mt-2 text-sm text-red-600">{checkoutErr}</p>}
        </div>
      )}

      {isFull && full && (
        <div className="mt-6 space-y-6 border-t border-slate-100 pt-6">
          <FullSection title="Fee breakdown">
            {(full.fee_breakdown || []).length === 0 ? (
              <EmptyNote>No fee text captured yet.</EmptyNote>
            ) : (
              <ul className="space-y-2 text-sm text-ink-800">
                {(full.fee_breakdown || []).map((f, i) => (
                  <li key={i} className="rounded border border-slate-100 bg-slate-50 p-2">
                    {f.raw_text}
                  </li>
                ))}
              </ul>
            )}
          </FullSection>

          <FullSection title="Rent history">
            {(full.rent_history || []).length === 0 ? (
              <EmptyNote>No history points yet.</EmptyNote>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b text-ink-500">
                      <th className="py-1 pr-3">Date</th>
                      <th className="py-1 pr-3">Base</th>
                      <th className="py-1">Effective</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(full.rent_history || []).slice(0, 8).map((h, i) => (
                      <tr key={i} className="border-b border-slate-50">
                        <td className="py-1 pr-3 text-ink-700">
                          {h.captured_at ? new Date(h.captured_at).toLocaleDateString() : "—"}
                        </td>
                        <td className="py-1 pr-3">{fmtMoney(toNum(h.base_rent_monthly))}</td>
                        <td className="py-1">{fmtMoney(toNum(h.effective_rent_monthly))}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </FullSection>

          <FullSection title="Concession history">
            {(full.concession_history || []).length === 0 ? (
              <EmptyNote>No concession snapshots yet.</EmptyNote>
            ) : (
              <ul className="space-y-2 text-sm text-ink-800">
                {(full.concession_history || []).map((c, i) => (
                  <li key={i} className="rounded border border-slate-100 bg-slate-50 p-2">
                    {c.raw_text}
                  </li>
                ))}
              </ul>
            )}
          </FullSection>

          {(full.negotiation_score != null || full.negotiation_script_email) && (
            <FullSection title="Negotiation">
              {full.negotiation_score != null && (
                <p className="text-sm text-ink-700">
                  Score: <strong>{full.negotiation_score}</strong>
                </p>
              )}
              {full.recommended_asks && full.recommended_asks.length > 0 && (
                <ul className="mt-2 list-inside list-disc text-sm text-ink-800">
                  {full.recommended_asks.map((a) => (
                    <li key={a}>{a}</li>
                  ))}
                </ul>
              )}
              {full.negotiation_script_email && (
                <pre className="mt-2 max-h-40 overflow-auto rounded bg-slate-100 p-2 text-xs whitespace-pre-wrap">
                  {full.negotiation_script_email}
                </pre>
              )}
              {full.negotiation_script_phone && (
                <pre className="mt-2 max-h-32 overflow-auto rounded bg-slate-100 p-2 text-xs whitespace-pre-wrap">
                  {full.negotiation_script_phone}
                </pre>
              )}
            </FullSection>
          )}

          {full.wait_apply_negotiate_hint && (
            <p className="text-sm italic text-ink-600">{full.wait_apply_negotiate_hint}</p>
          )}
        </div>
      )}
    </section>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg bg-slate-50 p-3">
      <div className="text-xs font-medium uppercase tracking-wide text-ink-500">{label}</div>
      <div className="mt-0.5 text-lg font-semibold text-ink-950">{value}</div>
      {hint && <p className="mt-1 text-xs text-ink-500">{hint}</p>}
    </div>
  );
}

function FullSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-ink-950">{title}</h3>
      <div className="mt-2">{children}</div>
    </div>
  );
}

function EmptyNote({ children }: { children: React.ReactNode }) {
  return <p className="text-sm text-ink-500">{children}</p>;
}
