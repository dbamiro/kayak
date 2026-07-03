import { apiFetch, getToken } from "@/lib/api";

export type SearchHit = {
  building_id: string;
  listing_id: string;
  name: string;
  city: string;
  neighborhood: string | null;
  dmv_area: string;
  bedrooms: string | null;
  base_rent_monthly: string | null;
  effective_rent_monthly: string | null;
  all_in_monthly: string | null;
  deal_signal: string;
  has_concession: boolean;
  has_fees: boolean;
  best_incentive_id?: string | null;
  incentive_type?: string | null;
  raw_text?: string | null;
  free_months?: number | null;
  lease_term_months?: number | null;
  listed_rent?: number | null;
  estimated_savings?: number | null;
  effective_rent?: number | null;
  all_in_effective_rent?: number | null;
  discount_percent?: number | null;
  confidence_score?: number | null;
  verified_at?: string | null;
  incentive_is_demo?: boolean | null;
};

export type SearchParams = {
  sort?: "default" | "savings" | "effective_rent" | "discount";
  min_free_months?: number;
  min_savings?: number;
  max_effective_rent?: number;
  has_incentive?: boolean;
  include_demo?: boolean;
  city?: string;
  dmv_area?: string;
  min_rent?: number;
  max_rent?: number;
  bedrooms_min?: number;
};

export type BuildingDetail = {
  id: string;
  name: string;
  slug: string;
  city: string;
  state: string;
  postal_code: string | null;
  neighborhood: string | null;
  dmv_area: string;
  property_url: string;
  latitude?: number | null;
  longitude?: number | null;
};

export type ListingQuote = {
  listing_id: string;
  unit_label: string | null;
  floorplan_name: string | null;
  bedrooms: string | null;
  bathrooms: string | null;
  sqft: number | null;
  snapshot_at: string;
  base_rent_monthly: string | null;
  effective_rent_monthly: string | null;
  all_in_monthly: string | null;
  leasing_pressure_score: number | null;
  negotiation_score: number | null;
  concessions: Record<string, unknown>;
  fees: Record<string, unknown>;
};

export type BuildingResponse = {
  building: BuildingDetail;
  listings: ListingQuote[];
};

export type SnapshotPoint = {
  captured_at: string;
  base_rent_monthly: string | null;
  effective_rent_monthly: string | null;
  all_in_monthly: string | null;
  leasing_pressure_score: number | null;
  negotiation_score: number | null;
};

export type BuildingHistoryResponse = {
  building_id: string;
  series: Record<string, SnapshotPoint[]>;
  floorplans: Record<string, string | null>;
};

export type IncentiveSummary = {
  special_text?: string | null;
  incentive_type?: string;
  free_months?: number | null;
  lease_term_months?: number | null;
  total_savings?: number | null;
  effective_rent?: number | null;
  discount_percent?: number | null;
  all_in_effective_rent?: number | null;
  is_demo?: boolean;
  verified?: boolean;
};

export type DealReportPreview = {
  listed_rent?: number | null;
  estimated_effective_rent?: number | null;
  incentive?: IncentiveSummary | null;
  deal_signal?: string;
  negotiation_signal?: string;
  potential_savings_range?: { min?: number; max?: number; disclaimer?: string } | null;
  hidden_fee_signal?: string;
  savings_disclaimer?: string;
  questions_for_leasing?: string[];
};

export type DealReportPaywall = {
  headline: string;
  subheadline: string;
  recommended_plan: string;
  price_cents: number;
  cta: string;
  value_bullets: string[];
};

export type DealReportFull = {
  fee_breakdown?: { raw_text: string; captured_at?: string }[];
  rent_history?: {
    captured_at: string;
    base_rent_monthly: string | null;
    effective_rent_monthly: string | null;
  }[];
  concession_history?: { raw_text: string; captured_at?: string }[];
  negotiation_score?: number | null;
  negotiation_script_email?: string;
  negotiation_script_phone?: string;
  recommended_asks?: string[];
  comparable_deals?: unknown[];
  wait_apply_negotiate_hint?: string;
};

export type DealReport = {
  building_id: string;
  building_name: string;
  access: "preview" | "full";
  preview: DealReportPreview;
  locked_sections: string[];
  paywall: DealReportPaywall | null;
  full_report: DealReportFull | null;
};

export type Plan = {
  code: string;
  name: string;
  price_cents: number;
  duration_days: number | null;
  description: string;
  plan_type?: string;
};

export type CheckoutSessionResponse = {
  checkout_session_id: string;
  checkout_url: string | null;
  stripe_session_id: string | null;
  mock_mode: boolean;
};

export type EntitlementsResponse = {
  user: { id: string; email: string | null; name: string | null };
  active_plan_codes: string[];
  expires_at_by_plan: Record<string, string | null>;
  feature_flags: Record<string, boolean>;
};

export type MeResponse = {
  id: string;
  email: string;
  name: string | null;
  email_verified: boolean;
  is_admin?: boolean;
};

export function getSearch(params?: SearchParams): Promise<SearchHit[]> {
  if (!params) return apiFetch<SearchHit[]>("/search");
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    qs.set(k, String(v));
  }
  const q = qs.toString();
  return apiFetch<SearchHit[]>(`/search${q ? `?${q}` : ""}`);
}

export function getBuilding(id: string): Promise<BuildingResponse> {
  return apiFetch<BuildingResponse>(`/buildings/${id}`);
}

export function getBuildingHistory(id: string): Promise<BuildingHistoryResponse> {
  return apiFetch<BuildingHistoryResponse>(`/buildings/${id}/history`);
}

export function getDealReport(id: string): Promise<DealReport> {
  return apiFetch<DealReport>(`/deal-reports/${id}`);
}

export function getPlans(): Promise<Plan[]> {
  return apiFetch<Plan[]>("/plans");
}

export function getEntitlements(): Promise<EntitlementsResponse> {
  return apiFetch<EntitlementsResponse>("/me/entitlements");
}

export function getMe(): Promise<MeResponse> {
  return apiFetch<MeResponse>("/auth/me");
}

export function createCheckoutSession(planCode: string): Promise<CheckoutSessionResponse> {
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  return apiFetch<CheckoutSessionResponse>("/checkout/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      plan_code: planCode,
      success_url: `${origin}/billing/success`,
      cancel_url: `${origin}/billing/cancel`,
    }),
  });
}

export function mockCompleteCheckout(planCode: string): Promise<{ ok: boolean; feature_flags: Record<string, boolean> }> {
  return apiFetch("/checkout/mock-complete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ plan_code: planCode }),
  });
}

export function isLoggedIn(): boolean {
  return !!getToken();
}

export type IncentiveCard = {
  id: string;
  building_id?: string | null;
  building_name?: string | null;
  city?: string | null;
  neighborhood?: string | null;
  dmv_area?: string | null;
  incentive_type: string;
  free_months?: number | null;
  lease_term_months?: number | null;
  listed_rent?: number | null;
  raw_text?: string | null;
  special_summary?: string | null;
  is_demo?: boolean;
  status?: string | null;
  capture_method?: string | null;
  verification_method?: string | null;
  submitted_by_email?: string | null;
  reviewed_by_email?: string | null;
  gift_card_amount?: number | null;
  custom_credit_amount?: number | null;
  metadata?: Record<string, unknown> | null;
  verified_at?: string | null;
  confidence_score?: number | null;
  total_savings?: number | null;
  effective_rent?: number | null;
  discount_percent?: number | null;
};

export type IncentiveCalculation = {
  gross_rent_total: number;
  concession_value: number;
  fee_adjustments: number;
  total_savings: number;
  effective_rent: number;
  all_in_effective_rent: number;
  discount_percent: number;
};

export function getIncentives(
  params?: Record<string, string | number | boolean>,
): Promise<IncentiveCard[]> {
  const q = new URLSearchParams();
  if (params) {
    Object.entries(params).forEach(([k, v]) => q.set(k, String(v)));
  }
  const qs = q.toString();
  return apiFetch<IncentiveCard[]>(`/incentives${qs ? `?${qs}` : ""}`);
}

export function calculateIncentive(body: Record<string, number>): Promise<IncentiveCalculation> {
  return apiFetch<IncentiveCalculation>("/incentives/calculate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function parseIncentiveText(body: {
  raw_text: string;
  listed_rent?: number;
  lease_term_months?: number;
}): Promise<{ parsed: Record<string, unknown>; calculation: IncentiveCalculation | null }> {
  return apiFetch("/incentives/parse", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function submitIncentive(body: Record<string, unknown>): Promise<IncentiveCard> {
  return apiFetch<IncentiveCard>("/incentives/submit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function adminListIncentives(params?: {
  status?: string;
  capture_method?: string;
  limit?: number;
}): Promise<IncentiveCard[]> {
  const q = new URLSearchParams();
  if (params?.status) q.set("status", params.status);
  if (params?.capture_method) q.set("capture_method", params.capture_method);
  if (params?.limit) q.set("limit", String(params.limit));
  const qs = q.toString();
  return apiFetch<IncentiveCard[]>(`/admin/incentives${qs ? `?${qs}` : ""}`);
}

export function adminVerifyIncentive(
  id: string,
  body: Record<string, string | number | undefined>,
): Promise<IncentiveCard> {
  return apiFetch<IncentiveCard>(`/admin/incentives/${id}/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function adminRejectIncentive(id: string, reason?: string): Promise<IncentiveCard> {
  return apiFetch<IncentiveCard>(`/admin/incentives/${id}/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason: reason || null }),
  });
}

export type AdminImportResult = {
  dry_run: boolean;
  created_count: number;
  error_count: number;
  errors: { row: number; field: string | null; message: string }[];
  created_incentive_ids: string[];
};

export async function adminImportIncentivesCsv(
  file: File,
  options?: { dryRun?: boolean },
): Promise<AdminImportResult> {
  const API = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
  const token = getToken();
  const form = new FormData();
  form.append("file", file);
  const qs = options?.dryRun ? "?dry_run=true" : "";
  const res = await fetch(`${API}/admin/incentives/import${qs}`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json() as Promise<AdminImportResult>;
}
