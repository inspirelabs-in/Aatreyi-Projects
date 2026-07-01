"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import { Card, ErrorBox } from "@/components/ui";

export default function NewOrganizationPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    setError("");
    try {
      const org = await api.createOrganization({
        name: name.trim(),
        slug: slug.trim() || undefined,
      });
      router.push(`/settings/users?org_id=${org.id}`);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <h1 className="text-lg font-semibold text-slate-900">Create Organization</h1>

      <Card>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-slate-600">Organization name *</label>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="My News Network"
              className="mt-1 w-full rounded-lg border border-edge bg-field px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/20" />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600">
              Slug <span className="text-slate-400">(auto-generated if empty)</span>
            </label>
            <input value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="my-news-network"
              className="mt-1 w-full rounded-lg border border-edge bg-field px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/20" />
          </div>
          {error && <ErrorBox error={error} />}
          <button disabled={busy} className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-blue-700 disabled:opacity-50">
            {busy ? "Creating…" : "Create organization"}
          </button>
        </form>
      </Card>
    </div>
  );
}
