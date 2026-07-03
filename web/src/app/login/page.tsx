"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { apiFetch, setAuthTokens } from "@/lib/api";

type LoginResponse = {
  access_token: string;
  refresh_token: string;
  user: { id: string; email: string; name: string | null };
};

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const returnTo = searchParams.get("returnTo") || "/account";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setLoading(true);
    try {
      const r = await apiFetch<LoginResponse>("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      setAuthTokens(r.access_token, r.refresh_token);
      router.push(returnTo.startsWith("/") ? returnTo : "/account");
      router.refresh();
    } catch (ex) {
      setErr((ex as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen px-4 py-10">
      <div className="mx-auto max-w-md">
        <Link href="/" className="text-sm text-sea-600">
          ← Home
        </Link>
        <h1 className="mt-4 text-2xl font-bold text-ink-950">Log in</h1>
        <p className="mt-1 text-sm text-ink-700">
          No account?{" "}
          <Link href={`/register?returnTo=${encodeURIComponent(returnTo)}`} className="text-sea-600 underline">
            Register
          </Link>
        </p>
        <form onSubmit={onSubmit} className="mt-6 space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <label className="block text-sm font-medium text-ink-900">
            Email
            <input
              type="email"
              required
              autoComplete="email"
              className="mt-1 w-full rounded border border-slate-300 px-3 py-2"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <label className="block text-sm font-medium text-ink-900">
            Password
            <input
              type="password"
              required
              minLength={8}
              autoComplete="current-password"
              className="mt-1 w-full rounded border border-slate-300 px-3 py-2"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          {err && <p className="text-sm text-red-600">{err}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-sea-600 py-2.5 text-sm font-semibold text-white hover:bg-sea-500 disabled:opacity-60"
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<main className="px-4 py-10">Loading…</main>}>
      <LoginForm />
    </Suspense>
  );
}
