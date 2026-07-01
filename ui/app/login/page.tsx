"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { login } from "@/lib/auth";
import { BRAND } from "@/lib/brand";
import { Logo } from "@/components/Logo";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("admin@grabon.in");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError("");
    const res = await login(email, password);
    setBusy(false);
    if (res.ok) router.replace("/channels");
    else setError(res.error || "Login failed.");
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-blue-50 via-ink to-violet-50 px-6">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex justify-center"><Logo size={40} /></div>
        <form onSubmit={onSubmit} className="rounded-2xl border border-edge bg-panel p-6 shadow-card">
          <h1 className="text-lg font-bold text-slate-900">Welcome back</h1>
          <p className="mt-1 text-sm text-slate-500">Sign in to {BRAND.name}.</p>

          <label className="mt-5 block text-xs font-medium text-slate-600">Email</label>
          <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" placeholder="you@company.com"
            className="mt-1 w-full rounded-lg border border-edge bg-field px-3 py-2 text-sm text-slate-800 outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/20" />

          <label className="mt-4 block text-xs font-medium text-slate-600">Password</label>
          <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" placeholder="••••••••"
            className="mt-1 w-full rounded-lg border border-edge bg-field px-3 py-2 text-sm text-slate-800 outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/20" />

          {error && <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-600">{error}</p>}

          <button disabled={busy}
            className="mt-5 w-full rounded-lg bg-brand px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-700 disabled:opacity-50">
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <p className="mt-4 text-center text-xs text-slate-400">
          <Link href="/" className="hover:text-slate-600">← Back to home</Link>
        </p>
      </div>
    </div>
  );
}
