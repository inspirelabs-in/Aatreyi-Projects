import Link from "next/link";
import { BRAND } from "@/lib/brand";
import { Logo, LogoMark } from "@/components/Logo";

const AGENTS = [
  { icon: "🧬", name: "Channel DNA", desc: "Profiles your niche, tone, best hours and top topics from real post history." },
  { icon: "🔍", name: "Competitor Intelligence", desc: "Finds & scrapes rival channels, benchmarks ER, surfaces gaps and trends." },
  { icon: "📊", name: "Analytics", desc: "Tracks subscribers, engagement and churn in near-real-time." },
  { icon: "🧭", name: "Strategy", desc: "Plans an executable daily schedule — when, what, and why for every slot." },
  { icon: "✍️", name: "Content", desc: "Scrapes, ranks and writes each post with one CTA, then queues it for approval." },
];

export default function Landing() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-white via-ink to-white">
      {/* top bar */}
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
        <Logo size={32} />
        <Link href="/login"
          className="rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-700">
          Sign in
        </Link>
      </header>

      {/* hero */}
      <section className="mx-auto max-w-4xl px-6 pb-16 pt-14 text-center">
        <span className="inline-flex items-center gap-2 rounded-full border border-edge bg-white px-3 py-1 text-xs font-medium text-slate-500 shadow-sm">
          <span className="h-1.5 w-1.5 rounded-full bg-green-500" /> Autonomous · multi-tenant · always-on
        </span>
        <h1 className="mt-6 text-4xl font-extrabold tracking-tight text-slate-900 sm:text-5xl">
          Grow your Telegram channel<br className="hidden sm:block" /> on autopilot with <span className="bg-gradient-to-r from-brand to-violet-600 bg-clip-text text-transparent">{BRAND.name}</span>
        </h1>
        <p className="mx-auto mt-5 max-w-2xl text-lg text-slate-600">{BRAND.blurb}</p>
        <div className="mt-8 flex items-center justify-center gap-3">
          <Link href="/login"
            className="rounded-xl bg-brand px-6 py-3 text-sm font-semibold text-white shadow-md transition hover:bg-blue-700">
            Get started →
          </Link>
          <a href="#agents"
            className="rounded-xl border border-edge bg-white px-6 py-3 text-sm font-semibold text-slate-700 shadow-sm transition hover:bg-slate-50">
            See the agents
          </a>
        </div>
      </section>

      {/* agents grid */}
      <section id="agents" className="mx-auto max-w-6xl px-6 pb-20">
        <h2 className="mb-2 text-center text-sm font-semibold uppercase tracking-wider text-slate-400">The agent pipeline</h2>
        <p className="mb-8 text-center text-xl font-bold text-slate-800">Five agents, one autonomous loop</p>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {AGENTS.map((a) => (
            <div key={a.name} className="rounded-2xl border border-edge bg-white p-5 shadow-card transition hover:shadow-md">
              <div className="text-2xl">{a.icon}</div>
              <h3 className="mt-3 font-semibold text-slate-900">{a.name}</h3>
              <p className="mt-1 text-sm text-slate-500">{a.desc}</p>
            </div>
          ))}
          <div className="flex flex-col items-start justify-center rounded-2xl border border-brand/20 bg-gradient-to-br from-blue-50 to-violet-50 p-5">
            <LogoMark size={36} />
            <h3 className="mt-3 font-semibold text-slate-900">…and you just approve</h3>
            <p className="mt-1 text-sm text-slate-600">Every post lands in a review queue — or auto-publishes when you enable it.</p>
            <Link href="/login" className="mt-4 text-sm font-semibold text-brand hover:underline">Launch the app →</Link>
          </div>
        </div>
      </section>

      <footer className="border-t border-edge py-8 text-center text-xs text-slate-400">
        © {BRAND.name} — {BRAND.tagline}
      </footer>
    </div>
  );
}
