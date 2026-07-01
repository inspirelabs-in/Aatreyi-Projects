"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Me, Organization } from "@/lib/types";
import { Badge, Card, ErrorBox, Spinner } from "@/components/ui";

export default function OrganizationsPage() {
  const [me, setMe] = useState<Me | null>(null);
  const [orgs, setOrgs] = useState<Organization[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const [m, all] = await Promise.all([api.me(), api.organizations()]);
        setMe(m);
        setOrgs(all);
      } catch (e) { setError(String(e)); }
    })();
  }, []);

  if (error) return <ErrorBox error={error} />;
  if (orgs === null || me === null) return <Spinner />;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold text-slate-900">Organizations</h1>
          {me.is_platform_admin && <Badge tone="amber">Platform Admin</Badge>}
        </div>
        {me.is_platform_admin && (
          <Link href="/organizations/new"
            className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-blue-700">
            + Create organization
          </Link>
        )}
      </div>

      {orgs.length === 0 ? (
        <p className="text-slate-500">No organizations yet.</p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {orgs.map((o) => (
            <Card key={o.id}>
              <div className="flex items-center justify-between">
                <span className="font-medium text-slate-900">{o.name}</span>
                <Badge tone="blue">{o.slug}</Badge>
              </div>
              <div className="mt-3 flex gap-3 text-sm">
                <Link href={`/settings/users?org_id=${o.id}`} className="text-brand hover:underline">Users</Link>
                <Link href={`/settings?org_id=${o.id}`} className="text-brand hover:underline">Settings</Link>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
