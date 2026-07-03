export function toNum(v: string | number | null | undefined): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

export function fmtMoney(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return `$${Math.round(n).toLocaleString()}`;
}

export function rentRange(min: number | null, max: number | null): string {
  if (min === null && max === null) return "—";
  if (min !== null && max !== null && min !== max) return `${fmtMoney(min)} – ${fmtMoney(max)}`;
  return fmtMoney(min ?? max);
}

export function dealSignalClass(signal: string | undefined): string {
  const s = (signal || "fair").toLowerCase();
  if (s === "strong") return "bg-emerald-100 text-emerald-800";
  if (s === "weak") return "bg-amber-100 text-amber-800";
  return "bg-slate-100 text-slate-700";
}

export function appOrigin(): string {
  if (typeof window !== "undefined") return window.location.origin;
  return process.env.NEXT_PUBLIC_APP_ORIGIN || "http://localhost:3000";
}
