"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Me, OrgSettings } from "@/lib/types";
import { Badge, Card, ErrorBox, Spinner } from "@/components/ui";

const TARGET_OPTIONS = [5, 10, 20, 35, 50];

export default function SettingsPage() {
  const [me, setMe] = useState<Me | null>(null);
  const [settings, setSettings] = useState<OrgSettings | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  async function load() {
    try {
      const [m, s] = await Promise.all([api.me(), api.orgSettings()]);
      setMe(m);
      setSettings(s);
    } catch (e) {
      setError(String(e));
    }
  }
  useEffect(() => { load(); }, []);

  async function save(patch: { auto_approve_content?: boolean; daily_target_posts?: number | null }) {
    setSaving(true);
    setSaved(false);
    try {
      const updated = await api.updateOrgSettings(patch);
      setSettings(updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 1500);
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  if (error) return <ErrorBox error={error} />;
  if (settings === null || me === null) return <Spinner />;

  const target = settings.daily_target_posts;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-semibold text-slate-900">Organization Settings</h1>
        {me.org_slug && <Badge tone="blue">{me.org_slug}</Badge>}
        {me.is_platform_admin && <Badge tone="amber">Platform Admin</Badge>}
      </div>

      <Card title="Auto Approve Content">
        <p className="mb-3 text-sm text-slate-600">
          When <b>on</b>, generated content is automatically approved into the publishing queue.
          When <b>off</b>, content stays <b>Pending</b> for manual approve/reject in each channel's review queue.
        </p>
        <button
          disabled={saving}
          onClick={() => save({ auto_approve_content: !settings.auto_approve_content })}
          className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition disabled:opacity-50 ${
            settings.auto_approve_content ? "bg-green-600 text-white hover:bg-green-700" : "bg-slate-200 text-slate-700 hover:bg-slate-300"
          }`}>
          {settings.auto_approve_content ? "Enabled — auto-approving" : "Disabled — manual review"}
        </button>
      </Card>

      <Card title="Daily Target Posts (deals channels)">
        <p className="mb-3 text-sm text-slate-600">
          How many execution slots the Strategy Agent creates per day for deals channels. The agent still
          distributes posts intelligently (audience activity, competitor trends, engagement, diversity, posting
          windows) — this only sets the count. <b>Default</b> keeps the current behavior (50: 25 loot / 25 single).
        </p>
        <div className="flex flex-wrap gap-2">
          <button
            disabled={saving}
            onClick={() => save({ daily_target_posts: null })}
            className={`rounded-lg border px-3 py-1.5 text-sm transition disabled:opacity-50 ${
              target == null ? "border-brand bg-blue-50 font-medium text-brand" : "border-edge bg-white text-slate-600 hover:bg-slate-50"
            }`}>
            Default
          </button>
          {TARGET_OPTIONS.map((n) => (
            <button
              key={n}
              disabled={saving}
              onClick={() => save({ daily_target_posts: n })}
              className={`rounded-lg border px-3 py-1.5 text-sm transition disabled:opacity-50 ${
                target === n ? "border-brand bg-blue-50 font-medium text-brand" : "border-edge bg-white text-slate-600 hover:bg-slate-50"
              }`}>
              {n}
            </button>
          ))}
        </div>
        <p className="mt-2 text-xs text-slate-500">
          Current: <b>{target == null ? "Default (50)" : `${target} posts/day`}</b>
          {saved && <span className="ml-2 text-green-600">✓ saved</span>}
        </p>
      </Card>
    </div>
  );
}
