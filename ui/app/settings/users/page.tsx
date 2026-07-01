"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import type { Me, Organization as Org, User } from "@/lib/types";
import { Badge, Card, ErrorBox, Spinner } from "@/components/ui";

export default function UsersPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <UsersPageInner />
    </Suspense>
  );
}

function UsersPageInner() {
  const searchParams = useSearchParams();
  const orgParam = searchParams.get("org_id");
  const [me, setMe] = useState<Me | null>(null);
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [selectedOrgId, setSelectedOrgId] = useState<string>("");
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const m = await api.me();
      setMe(m);
      if (m.is_platform_admin) {
        const all = await api.organizations();
        setOrgs(all);
        // Honor ?org_id (e.g. right after creating an org) when it's a real org.
        const fromParam = orgParam && all.some((o) => o.id === orgParam) ? orgParam : null;
        setSelectedOrgId(fromParam || m.organization_id || (all[0]?.id ?? ""));
      } else {
        setSelectedOrgId(m.organization_id ?? "");
      }
    } catch (e) {
      setError(String(e));
    }
  }
  useEffect(() => { load(); }, []);

  useEffect(() => {
    if (!selectedOrgId) return;
    api.listUsers(selectedOrgId).then(setUsers).catch((e) => setError(String(e)));
  }, [selectedOrgId]);

  async function handleInvite(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    try {
      await api.createUser(selectedOrgId, {
        name: name.trim(),
        email: email.trim() || undefined,
        is_admin: isAdmin,
      });
      setName(""); setEmail(""); setIsAdmin(false);
      setUsers(await api.listUsers(selectedOrgId));
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  if (error) return <ErrorBox error={error} />;
  if (!me) return <Spinner />;

  const canInvite = me.is_platform_admin || me.organization_id === selectedOrgId;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold text-slate-900">Users</h1>
          {me.is_platform_admin && <Badge tone="amber">Platform Admin</Badge>}
        </div>
        {me.is_platform_admin && orgs.length > 0 && (
          <select
            value={selectedOrgId}
            onChange={(e) => setSelectedOrgId(e.target.value)}
            className="rounded-lg border border-edge bg-field px-3 py-1.5 text-sm text-slate-800 outline-none focus:border-brand"
          >
            {orgs.map((o) => (
              <option key={o.id} value={o.id}>{o.name} ({o.slug})</option>
            ))}
          </select>
        )}
      </div>

      {canInvite && (
        <Card title="Invite User">
          <form onSubmit={handleInvite} className="flex flex-wrap items-end gap-3">
            <div>
              <label className="block text-xs font-medium text-slate-600">Name *</label>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Full name"
                className="mt-1 w-52 rounded-lg border border-edge bg-field px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/20" />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600">Email</label>
              <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@company.com"
                className="mt-1 w-52 rounded-lg border border-edge bg-field px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/20" />
            </div>
            {me.is_platform_admin && (
              <div className="flex items-center gap-2 pb-1">
                <input id="is_admin" type="checkbox" checked={isAdmin} onChange={(e) => setIsAdmin(e.target.checked)}
                  className="h-4 w-4 rounded border-edge text-brand focus:ring-brand/20" />
                <label htmlFor="is_admin" className="text-sm text-slate-600 select-none">Org admin</label>
              </div>
            )}
            <button disabled={busy} className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-blue-700 disabled:opacity-50">
              {busy ? "Adding…" : "Invite"}
            </button>
          </form>
        </Card>
      )}

      <div className="overflow-hidden rounded-xl border border-edge">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Email</th>
              <th className="px-4 py-3">Role</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-edge">
            {users.length === 0 ? (
              <tr><td colSpan={3} className="px-4 py-8 text-center text-slate-400">No users yet.</td></tr>
            ) : (
              users.map((u) => (
                <tr key={u.id} className="bg-panel">
                  <td className="px-4 py-3 font-medium text-slate-900">{u.name}</td>
                  <td className="px-4 py-3 text-slate-600">{u.email || "—"}</td>
                  <td className="px-4 py-3">
                    {u.is_admin ? <Badge tone="amber">Admin</Badge> : <Badge>Member</Badge>}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
