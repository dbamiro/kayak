/** Display labels for move-in specials (any amount — not limited to months free). */

export type IncentiveLike = {
  incentive_type?: string | null;
  free_months?: number | null;
  raw_text?: string | null;
  gift_card_amount?: number | null;
  custom_credit_amount?: number | null;
  total_savings?: number | null;
  waived_fee_amount?: number | null;
  metadata?: Record<string, unknown> | null;
};

function weeksFromMeta(row: IncentiveLike): number | null {
  const w = row.metadata?.weeks_free;
  if (typeof w === "number") return w;
  if (typeof w === "string") {
    const n = Number(w);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

function weeksFromText(raw: string): number | null {
  const m = raw.match(/(\d+(?:\.\d+)?)\s*weeks?\s*free/i);
  if (!m) return null;
  const n = Number(m[1]);
  return Number.isFinite(n) ? n : null;
}

export function formatIncentiveHeadline(row: IncentiveLike): string {
  const raw = (row.raw_text || "").toLowerCase();
  const itype = row.incentive_type || "";

  const weeks = weeksFromMeta(row) ?? weeksFromText(row.raw_text || "");
  if (weeks != null && weeks > 0) {
    return weeks === 1 ? "1 week free" : `${weeks % 1 === 0 ? weeks : weeks.toFixed(1)} weeks free`;
  }

  const fm = row.free_months;
  if (fm != null && fm > 0) {
    if (itype === "free_weeks" && raw.includes("week")) {
      const w = weeksFromText(row.raw_text || "");
      if (w) return w === 1 ? "1 week free" : `${w} weeks free`;
    }
    if (Math.abs(fm - Math.round(fm)) < 0.05) {
      const n = Math.round(fm);
      return `${n} month${n === 1 ? "" : "s"} free`;
    }
    return `${fm.toFixed(1)} months free`;
  }

  if (itype === "waived_admin_fee" || raw.includes("waived admin")) return "Waived admin fee";
  if (itype === "waived_application_fee") return "Waived application fee";
  if (row.gift_card_amount) return `$${Number(row.gift_card_amount).toLocaleString()} gift card`;
  if (row.custom_credit_amount) return `$${Number(row.custom_credit_amount).toLocaleString()} rent credit`;
  if (itype === "free_parking" || raw.includes("free parking")) return "Free parking";
  if (itype === "look_and_lease") return "Look & lease special";
  if (row.raw_text) return row.raw_text.slice(0, 120);
  return itype.replace(/_/g, " ") || "Move-in special";
}
