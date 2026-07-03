const API = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

const ACCESS_KEY = "access_token";
const REFRESH_KEY = "refresh_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ACCESS_KEY);
}

export function setAuthTokens(access: string, refresh: string) {
  localStorage.setItem(ACCESS_KEY, access);
  localStorage.setItem(REFRESH_KEY, refresh);
}

export function clearAuth() {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  const token = typeof window !== "undefined" ? localStorage.getItem(ACCESS_KEY) : null;
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`${API}${path}`, { ...init, headers });
  if (!res.ok) {
    const text = await res.text();
    let msg = text || res.statusText;
    try {
      const j = JSON.parse(text) as { detail?: unknown };
      if (typeof j?.detail === "string") msg = j.detail;
      else if (Array.isArray(j?.detail))
        msg = (j.detail as { msg?: string }[]).map((x) => x.msg || "").join("; ") || msg;
      else if (j?.detail != null) msg = JSON.stringify(j.detail);
    } catch {
      /* use text */
    }
    throw new Error(msg);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export { API };
