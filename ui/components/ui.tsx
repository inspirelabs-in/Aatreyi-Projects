import React from "react";

export function Card({ title, children, className = "" }: { title?: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-edge bg-panel p-4 shadow-card ${className}`}>
      {title && <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">{title}</h3>}
      {children}
    </div>
  );
}

export function Stat({ label, value, sub }: { label: string; value: React.ReactNode; sub?: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-edge bg-panel p-4 shadow-card">
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-slate-900">{value ?? "—"}</div>
      {sub != null && <div className="mt-1 text-sm text-slate-500">{sub}</div>}
    </div>
  );
}

export function Badge({ children, tone = "slate" }: { children: React.ReactNode; tone?: "slate" | "green" | "red" | "blue" | "amber" }) {
  const tones: Record<string, string> = {
    slate: "bg-slate-100 text-slate-700 ring-1 ring-inset ring-slate-200",
    green: "bg-green-50 text-green-700 ring-1 ring-inset ring-green-200",
    red: "bg-red-50 text-red-700 ring-1 ring-inset ring-red-200",
    blue: "bg-blue-50 text-blue-700 ring-1 ring-inset ring-blue-200",
    amber: "bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-200",
  };
  return <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ${tones[tone]}`}>{children}</span>;
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return <div className="py-12 text-center text-slate-400">{label}</div>;
}

export function ErrorBox({ error }: { error: string }) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
      {error}
      <div className="mt-1 text-xs text-red-500">Is the API running at NEXT_PUBLIC_API_BASE?</div>
    </div>
  );
}
