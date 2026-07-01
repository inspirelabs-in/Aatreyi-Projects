"use client";

import React, { useRef, useState } from "react";

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
  const [coords, setCoords] = useState({ top: 0, left: 0 });
  const btnRef = useRef<HTMLButtonElement>(null);

  function openTooltip() {
    if (btnRef.current) {
      const r = btnRef.current.getBoundingClientRect();
      setCoords({ top: r.top - 8, left: r.left + r.width / 2 });
      setShow(true);
    }
  }

  return (
    <span className="inline-flex">
      <button
        ref={btnRef}
        type="button"
        onMouseEnter={openTooltip}
        onMouseLeave={() => setShow(false)}
        onClick={() => (show ? setShow(false) : openTooltip())}
        className="ml-1 inline-flex h-4 w-4 cursor-pointer items-center justify-center rounded-full bg-slate-100 text-[10px] font-bold text-slate-400 hover:bg-slate-200 focus:outline-none"
        aria-label="More info"
      >
        i
      </button>
      {show && (
        <span
          style={{
            position: "fixed",
            top: coords.top,
            left: coords.left,
            transform: "translate(-50%, -100%)",
            zIndex: 9999,
          }}
          className="w-56 rounded-lg border border-edge bg-white px-3 py-2 text-xs leading-snug text-slate-600 shadow-lg"
        >
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

export function PageHeader({ title, subtitle, actions }: {
  title: React.ReactNode; subtitle?: React.ReactNode; actions?: React.ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-xl font-bold tracking-tight text-slate-900">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Section({ title, desc, actions, children }: {
  title?: React.ReactNode; desc?: React.ReactNode; actions?: React.ReactNode; children: React.ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-edge bg-panel p-5 shadow-card">
      {(title || actions) && (
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            {title && <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">{title}</h3>}
            {desc && <p className="mt-1 text-xs text-slate-500">{desc}</p>}
          </div>
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="rounded-xl border border-dashed border-edge bg-field/50 px-6 py-10 text-center">
      <p className="text-sm font-medium text-slate-600">{title}</p>
      {hint && <p className="mt-1 text-xs text-slate-400">{hint}</p>}
    </div>
  );
}

export function Tabs({ tabs, active, onChange }: {
  tabs: { key: string; label: React.ReactNode }[]; active: string; onChange: (k: string) => void;
}) {
  return (
    <div className="mb-4 inline-flex rounded-lg border border-edge bg-field p-1">
      {tabs.map((t) => (
        <button key={t.key} onClick={() => onChange(t.key)}
          className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
            active === t.key ? "bg-white text-brand shadow-sm" : "text-slate-500 hover:text-slate-800"
          }`}>{t.label}</button>
      ))}
    </div>
  );
}

export function Pagination({ page, pageCount, onPage }: {
  page: number; pageCount: number; onPage: (p: number) => void;
}) {
  if (pageCount <= 1) return null;
  return (
    <div className="flex items-center justify-center gap-2 pt-2">
      <button disabled={page === 0} onClick={() => onPage(Math.max(0, page - 1))}
        className="rounded-md border border-edge bg-panel px-3 py-1.5 text-sm text-slate-700 transition hover:bg-slate-50 disabled:opacity-40">← Prev</button>
      {Array.from({ length: pageCount }).map((_, i) => (
        <button key={i} onClick={() => onPage(i)}
          className={`h-8 w-8 rounded-md text-sm transition ${i === page ? "bg-brand font-medium text-white" : "border border-edge bg-panel text-slate-600 hover:bg-slate-50"}`}>{i + 1}</button>
      ))}
      <button disabled={page >= pageCount - 1} onClick={() => onPage(Math.min(pageCount - 1, page + 1))}
        className="rounded-md border border-edge bg-panel px-3 py-1.5 text-sm text-slate-700 transition hover:bg-slate-50 disabled:opacity-40">Next →</button>
    </div>
  );
}
