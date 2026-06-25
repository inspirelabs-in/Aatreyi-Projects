"use client";

import React, { useState } from "react";

export function Card({ title, children, className = "" }: { title?: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-edge bg-panel p-4 shadow-card ${className}`}>
      {title && <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">{title}</h3>}
      {children}
    </div>
  );
}

export function Stat({ label, value, sub, info }: { label: string; value: React.ReactNode; sub?: React.ReactNode; info?: string }) {
  return (
    <div className="rounded-xl border border-edge bg-panel p-4 shadow-card">
      <div className="flex items-center text-xs uppercase tracking-wide text-slate-500">
        {label}
        {info && <InfoTooltip text={info} />}
      </div>
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

export function InfoTooltip({ text }: { text: string }) {
  const [show, setShow] = useState(false);
  return (
    <span className="relative inline-flex">
      <button
        type="button"
        onMouseEnter={() => setShow(true)}
        onMouseLeave={() => setShow(false)}
        onClick={() => setShow((s) => !s)}
        className="ml-1 inline-flex h-4 w-4 cursor-pointer items-center justify-center rounded-full bg-slate-100 text-[10px] font-bold text-slate-400 hover:bg-slate-200 focus:outline-none"
        aria-label="More info"
      >
        i
      </button>
      {show && (
        <span className="absolute bottom-full left-1/2 z-20 mb-2 w-56 -translate-x-1/2 rounded-lg border border-edge bg-white px-3 py-2 text-xs leading-snug text-slate-600 shadow-lg">
          {text}
        </span>
      )}
    </span>
  );
}

export function Collapsible({
  title,
  children,
  defaultOpen = true,
}: {
  title: React.ReactNode;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-xl border border-edge bg-panel shadow-card">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-slate-50"
      >
        <span className="text-sm font-semibold uppercase tracking-wide text-slate-500">{title}</span>
        <svg
          className={`h-4 w-4 flex-shrink-0 text-slate-400 transition-transform duration-200 ${open ? "rotate-180" : ""}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && <div className="border-t border-edge px-4 pb-4 pt-3">{children}</div>}
    </div>
  );
}
