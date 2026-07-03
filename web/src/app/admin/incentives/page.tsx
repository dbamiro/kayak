"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { SiteHeader } from "@/components/SiteHeader";
import {
  adminImportIncentivesCsv,
  adminListIncentives,
  adminRejectIncentive,
  adminVerifyIncentive,
  getMe,
  type AdminImportResult,
  type IncentiveCard,
} from "@/lib/kayak-api";
import { fmtMoney } from "@/lib/format";

export default function AdminIncentivesPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const [selected, setSelected] = useState<IncentiveCard | null>(null);
  const [freeMonths, setFreeMonths] = useState("");
  const [listedRent, setListedRent] = useState("");
  const [leaseTerm, setLeaseTerm] = useState("");
  const [rawText, setRawText] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [importResult, setImportResult] = useState<AdminImportResult | null>(null);

  const meQ = useQuery({ queryKey: ["me"], queryFn: getMe });

  useEffect(() => {
    if (meQ.isSuccess && !meQ.data.is_admin) {
      router.replace("/");
    }
  }, [meQ.isSuccess, meQ.data, router]);

  const pendingQ = useQuery({
    queryKey: ["admin-incentives", "pending_review"],
    queryFn: () => adminListIncentives({ status: "pending_review" }),
    enabled: Boolean(meQ.data?.is_admin),
  });

  const verifyMut = useMutation({
    mutationFn: () =>
      adminVerifyIncentive(selected!.id, {
        raw_text: rawText,
        listed_rent: listedRent ? Number(listedRent) : undefined,
        lease_term_months: leaseTerm ? Number(leaseTerm) : undefined,
        free_months: freeMonths ? Number(freeMonths) : undefined,
      }),
    onSuccess: () => {
      setSelected(null);
      void qc.invalidateQueries({ queryKey: ["admin-incentives"] });
      void qc.invalidateQueries({ queryKey: ["incentives"] });
    },
    onError: (e: Error) => setErr(e.message),
  });

  const rejectMut = useMutation({
    mutationFn: () => adminRejectIncentive(selected!.id, rejectReason || undefined),
    onSuccess: () => {
      setSelected(null);
      void qc.invalidateQueries({ queryKey: ["admin-incentives"] });
    },
    onError: (e: Error) => setErr(e.message),
  });

  const importMut = useMutation({
    mutationFn: ({ file, dryRun }: { file: File; dryRun: boolean }) =>
      adminImportIncentivesCsv(file, { dryRun }),
    onSuccess: (data) => {
      setImportResult(data);
      setErr(null);
      void qc.invalidateQueries({ queryKey: ["admin-incentives"] });
      void qc.invalidateQueries({ queryKey: ["incentives"] });
    },
    onError: (e: Error) => setErr(e.message),
  });

  function openReview(item: IncentiveCard) {
    setSelected(item);
    setRawText(item.raw_text || "");
    setListedRent(item.listed_rent != null ? String(item.listed_rent) : "");
    setLeaseTerm(item.lease_term_months != null ? String(item.lease_term_months) : "");
    setFreeMonths(item.free_months != null ? String(item.free_months) : "");
    setRejectReason("");
    setErr(null);
  }

  if (meQ.isLoading) {
    return (
      <main className="min-h-screen bg-slate-50">
        <SiteHeader />
        <p className="px-4 py-8">Loading…</p>
      </main>
    );
  }

  if (!meQ.data?.is_admin) {
    return (
      <main className="min-h-screen bg-slate-50">
        <SiteHeader />
        <p className="px-4 py-8 text-ink-700">
          Admin access required. Set <code className="rounded bg-slate-200 px-1">ADMIN_EMAILS</code> or{" "}
          <code className="rounded bg-slate-200 px-1">users.is_admin</code>.
        </p>
      </main>
    );
  }

  const pending = pendingQ.data || [];

  return (
    <main className="min-h-screen bg-slate-50">
      <SiteHeader />
      <div className="mx-auto max-w-5xl px-4 py-8">
        <h1 className="text-2xl font-bold text-ink-950">Review incentives</h1>
        <p className="mt-1 text-sm text-ink-700">
          User submissions and crawler-derived specials awaiting verification. Verified items appear in search without
          the demo badge.
        </p>

        <section className="mt-6 rounded-xl border border-sea-200 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-semibold text-ink-950">Bulk import verified specials (CSV)</h2>
          <p className="mt-1 text-sm text-ink-600">
            Upload admin-verified move-in specials. Copy{" "}
            <code className="rounded bg-slate-100 px-1">fixtures/incentives_import_template.csv</code> to{" "}
            <code className="rounded bg-slate-100 px-1">verified_specials.csv</code> — see{" "}
            <code className="rounded bg-slate-100 px-1">docs/DMV_INCENTIVE_IMPORT.md</code> (do not import the example
            file). Columns: building_name, address, city, state, neighborhood, source_url, listed_rent, lease_months,
            free_months, free_weeks, rent_credit, waived_fees, expires_at, notes.
          </p>
          <div className="mt-4 flex flex-wrap items-end gap-3">
            <label className="block text-sm">
              CSV file
              <input
                type="file"
                accept=".csv,text/csv"
                className="mt-1 block text-sm"
                onChange={(e) => {
                  setCsvFile(e.target.files?.[0] || null);
                  setImportResult(null);
                }}
              />
            </label>
            <button
              type="button"
              disabled={!csvFile || importMut.isPending}
              onClick={() => csvFile && importMut.mutate({ file: csvFile, dryRun: true })}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold text-ink-800 disabled:opacity-50"
            >
              Validate
            </button>
            <button
              type="button"
              disabled={!csvFile || importMut.isPending}
              onClick={() => csvFile && importMut.mutate({ file: csvFile, dryRun: false })}
              className="rounded-lg bg-sea-600 px-3 py-2 text-sm font-semibold text-white hover:bg-sea-500 disabled:opacity-50"
            >
              {importMut.isPending ? "Importing…" : "Import"}
            </button>
          </div>
          {importResult && (
            <div className="mt-4 text-sm">
              <p className="font-medium text-ink-900">
                {importResult.dry_run ? "Validation" : "Import"}: {importResult.created_count} ok,{" "}
                {importResult.error_count} errors
              </p>
              {importResult.errors.length > 0 && (
                <ul className="mt-2 list-inside list-disc text-red-700">
                  {importResult.errors.map((e, i) => (
                    <li key={`${e.row}-${i}`}>
                      Row {e.row}
                      {e.field ? ` (${e.field})` : ""}: {e.message}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </section>

        {pendingQ.isLoading && <p className="mt-4">Loading queue…</p>}
        {pendingQ.isError && <p className="mt-4 text-red-600">{(pendingQ.error as Error).message}</p>}

        {!selected && (
          <ul className="mt-6 space-y-3">
            {pending.length === 0 && (
              <li className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-ink-600">
                No pending submissions.
              </li>
            )}
            {pending.map((item) => (
              <li key={item.id} className="rounded-lg border border-slate-200 bg-white p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-semibold text-ink-950">
                      {item.building_name || "Unknown building"}
                      {item.city ? ` · ${item.city}` : ""}
                    </p>
                    <p className="mt-1 text-sm text-violet-900">{item.raw_text}</p>
                    <p className="mt-1 text-xs text-ink-500">
                      {item.capture_method} · {item.submitted_by_email || "anonymous"} ·{" "}
                      {item.status}
                    </p>
                  </div>
                  <div className="text-right text-sm">
                    <div>{fmtMoney(item.listed_rent)}/mo · {item.lease_term_months} mo</div>
                    <button
                      type="button"
                      onClick={() => openReview(item)}
                      className="mt-2 rounded-lg bg-sea-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-sea-500"
                    >
                      Review
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}

        {selected && (
          <div className="mt-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold">Review submission</h2>
            <p className="text-sm text-ink-600">{selected.building_name}</p>
            <div className="mt-4 space-y-3">
              <label className="block text-sm">
                Raw special text
                <textarea
                  className="mt-1 w-full rounded border px-3 py-2 text-sm"
                  rows={3}
                  value={rawText}
                  onChange={(e) => setRawText(e.target.value)}
                />
              </label>
              <div className="grid gap-3 sm:grid-cols-3">
                <label className="block text-sm">
                  Listed rent
                  <input
                    type="number"
                    className="mt-1 w-full rounded border px-3 py-2"
                    value={listedRent}
                    onChange={(e) => setListedRent(e.target.value)}
                  />
                </label>
                <label className="block text-sm">
                  Lease term (mo)
                  <input
                    type="number"
                    className="mt-1 w-full rounded border px-3 py-2"
                    value={leaseTerm}
                    onChange={(e) => setLeaseTerm(e.target.value)}
                  />
                </label>
                <label className="block text-sm">
                  Free months
                  <input
                    type="number"
                    step="0.1"
                    className="mt-1 w-full rounded border px-3 py-2"
                    value={freeMonths}
                    onChange={(e) => setFreeMonths(e.target.value)}
                  />
                </label>
              </div>
              <label className="block text-sm">
                Rejection reason (optional)
                <input
                  className="mt-1 w-full rounded border px-3 py-2"
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                />
              </label>
              {err && <p className="text-sm text-red-600">{err}</p>}
              <div className="flex flex-wrap gap-3 pt-2">
                <button
                  type="button"
                  disabled={verifyMut.isPending}
                  onClick={() => verifyMut.mutate()}
                  className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-60"
                >
                  {verifyMut.isPending ? "Verifying…" : "Verify & publish"}
                </button>
                <button
                  type="button"
                  disabled={rejectMut.isPending}
                  onClick={() => rejectMut.mutate()}
                  className="rounded-lg border border-red-300 px-4 py-2 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:opacity-60"
                >
                  Reject
                </button>
                <button
                  type="button"
                  onClick={() => setSelected(null)}
                  className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-ink-800"
                >
                  Back
                </button>
              </div>
            </div>
          </div>
        )}

        <p className="mt-8 text-sm text-ink-500">
          <Link href="/specials" className="text-sea-600 underline">
            View public specials
          </Link>
        </p>
      </div>
    </main>
  );
}
