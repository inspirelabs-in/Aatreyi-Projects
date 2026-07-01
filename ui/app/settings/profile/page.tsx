"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Me } from "@/lib/types";
import { Badge, ErrorBox, Section, Spinner } from "@/components/ui";
import { logout } from "@/lib/auth";

export default function ProfilePage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { api.me().then(setMe).catch((e) => setError(String(e))); }, []);

  if (error) return <ErrorBox error={error} />;
  if (!me) return <Spinner />;

  const Row = ({ label, value }: { label: string; value: React.ReactNode }) => (
    <div className="flex items-center justify-between border-b border-edge py-3 last:border-0">
      <span className="text-sm text-slate-500">{label}</span>
      <span className="text-sm font-medium text-slate-800">{value}</span>
    </div>
  );

  return (
    <Section title="Your account">
      <div className="max-w-lg">
        <Row label="Name" value={me.name || "—"} />
        <Row label="Email" value={me.email || "—"} />
        <Row label="Organization" value={me.org_slug || "—"} />
        <Row label="Role" value={me.is_platform_admin ? <Badge tone="amber">Platform Admin</Badge> : <Badge>Member</Badge>} />
        <div className="pt-4">
          <button onClick={() => { logout(); router.replace("/login"); }}
            className="rounded-lg border border-edge bg-panel px-4 py-2 text-sm font-medium text-slate-700 transition hover:border-red-300 hover:text-red-600">
            Log out
          </button>
        </div>
      </div>
    </Section>
  );
}
