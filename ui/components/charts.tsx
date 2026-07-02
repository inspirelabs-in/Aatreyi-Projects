"use client";

// Dependency-free inline-SVG charts. recharts (2.12.7) is unusable in this Next 16
// / Turbopack production build — ResponsiveContainer renders no <svg> at all, and
// rendering charts directly crashes ("t is not a function" + NaN SVG paths). These
// hand-rolled SVG equivalents always render and carry no runtime dependency.
import { useEffect, useRef, useState } from "react";

export const PALETTE = ["#2563eb", "#7c3aed", "#16a34a", "#f59e0b", "#06b6d4", "#e11d48", "#0ea5e9", "#a855f7"];

const GRID = "#eef2f7";
const LABEL = "#94a3b8";

function useWidth(): [React.RefObject<HTMLDivElement>, number] {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => setW(el.clientWidth);
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

function niceLabels<T>(items: T[], max: number): { item: T; i: number }[] {
  const n = items.length;
  if (n <= max) return items.map((item, i) => ({ item, i }));
  const step = Math.ceil(n / max);
  return items.map((item, i) => ({ item, i })).filter(({ i }) => i % step === 0 || i === n - 1);
}

// ── Line / Area trend ────────────────────────────────────────────────────────
function TrendChart({ data, x, y, color, height, fill }: {
  data: any[]; x: string; y: string; color: string; height: number; fill: boolean;
}) {
  const [ref, w] = useWidth();
  const padL = 40, padR = 10, padT = 10, padB = 22;
  const H = height;
  const vals = data.map((d) => Number(d[y]) || 0);
  const min = Math.min(...vals), max = Math.max(...vals);
  const span = max - min || 1;
  const n = data.length;
  const innerW = Math.max(w - padL - padR, 1);
  const innerH = Math.max(H - padT - padB, 1);
  const px = (i: number) => padL + (n <= 1 ? innerW / 2 : (i / (n - 1)) * innerW);
  const py = (v: number) => padT + innerH - ((v - min) / span) * innerH;
  const line = vals.map((v, i) => `${px(i)},${py(v)}`).join(" ");
  const area = `M ${px(0)},${padT + innerH} ` + vals.map((v, i) => `L ${px(i)},${py(v)}`).join(" ") +
    ` L ${px(n - 1)},${padT + innerH} Z`;
  const yTicks = [max, (max + min) / 2, min];
  return (
    <div ref={ref} style={{ width: "100%", height: H }}>
      {w > 0 && (
        <svg width={w} height={H} role="img">
          {yTicks.map((v, i) => {
            const gy = py(v);
            return (
              <g key={i}>
                <line x1={padL} y1={gy} x2={w - padR} y2={gy} stroke={GRID} />
                <text x={padL - 6} y={gy + 3} textAnchor="end" fontSize={10} fill={LABEL}>
                  {Math.round(v).toLocaleString()}
                </text>
              </g>
            );
          })}
          {fill && <path d={area} fill={color} opacity={0.12} />}
          <polyline points={line} fill="none" stroke={color} strokeWidth={2}
            strokeLinejoin="round" strokeLinecap="round" />
          {niceLabels(data, 6).map(({ item, i }) => (
            <text key={i} x={px(i)} y={H - 6} textAnchor="middle" fontSize={10} fill={LABEL}>
              {String(item[x])}
            </text>
          ))}
        </svg>
      )}
    </div>
  );
}

export function AreaTrend({ data, x, y, color = PALETTE[0], height = 220 }: {
  data: any[]; x: string; y: string; color?: string; height?: number;
}) {
  return <TrendChart data={data} x={x} y={y} color={color} height={height} fill />;
}

export function LineTrend({ data, x, y, color = PALETTE[2], height = 220 }: {
  data: any[]; x: string; y: string; color?: string; height?: number;
}) {
  return <TrendChart data={data} x={x} y={y} color={color} height={height} fill={false} />;
}

// ── Bar breakdown ────────────────────────────────────────────────────────────
export function BarBreakdown({ data, x, y, height = 220 }: {
  data: any[]; x: string; y: string; color?: string; height?: number;
}) {
  const [ref, w] = useWidth();
  const padL = 40, padR = 10, padT = 10, padB = 30;
  const H = height;
  const vals = data.map((d) => Number(d[y]) || 0);
  const max = Math.max(...vals, 1);
  const n = data.length;
  const innerW = Math.max(w - padL - padR, 1);
  const innerH = Math.max(H - padT - padB, 1);
  const gap = 10;
  const bw = Math.max((innerW - gap * n) / Math.max(n, 1), 2);
  const yTicks = [max, max / 2, 0];
  return (
    <div ref={ref} style={{ width: "100%", height: H }}>
      {w > 0 && (
        <svg width={w} height={H} role="img">
          {yTicks.map((v, i) => {
            const gy = padT + innerH - (v / max) * innerH;
            return (
              <g key={i}>
                <line x1={padL} y1={gy} x2={w - padR} y2={gy} stroke={GRID} />
                <text x={padL - 6} y={gy + 3} textAnchor="end" fontSize={10} fill={LABEL}>{Math.round(v)}</text>
              </g>
            );
          })}
          {data.map((d, i) => {
            const bh = (Number(d[y]) || 0) / max * innerH;
            const bx = padL + gap / 2 + i * (bw + gap);
            const by = padT + innerH - bh;
            return (
              <g key={i}>
                <rect x={bx} y={by} width={bw} height={bh} rx={4} fill={PALETTE[i % PALETTE.length]} />
                <text x={bx + bw / 2} y={H - 8} textAnchor="middle" fontSize={10} fill={LABEL}>
                  {String(d[x]).length > 10 ? String(d[x]).slice(0, 9) + "…" : String(d[x])}
                </text>
              </g>
            );
          })}
        </svg>
      )}
    </div>
  );
}

// ── Donut ────────────────────────────────────────────────────────────────────
function arcPath(cx: number, cy: number, rOut: number, rIn: number, a0: number, a1: number): string {
  const pt = (r: number, a: number) => [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  const [x0, y0] = pt(rOut, a0), [x1, y1] = pt(rOut, a1);
  const [x2, y2] = pt(rIn, a1), [x3, y3] = pt(rIn, a0);
  const large = a1 - a0 > Math.PI ? 1 : 0;
  return `M ${x0} ${y0} A ${rOut} ${rOut} 0 ${large} 1 ${x1} ${y1} L ${x2} ${y2} A ${rIn} ${rIn} 0 ${large} 0 ${x3} ${y3} Z`;
}

export function Donut({ data, nameKey, valueKey, height = 220 }: {
  data: any[]; nameKey: string; valueKey: string; height?: number;
}) {
  const size = Math.min(height, 176);
  const cx = size / 2, cy = size / 2, rOut = size * 0.46, rIn = size * 0.3;
  const total = data.reduce((s, d) => s + (Number(d[valueKey]) || 0), 0) || 1;
  let angle = -Math.PI / 2;
  const segs = data.map((d, i) => {
    const frac = (Number(d[valueKey]) || 0) / total;
    const a0 = angle, a1 = angle + frac * Math.PI * 2;
    angle = a1;
    return { d: arcPath(cx, cy, rOut, rIn, a0, Math.max(a1 - 0.01, a0)), color: PALETTE[i % PALETTE.length], i };
  });
  return (
    <div className="flex items-center gap-4">
      <svg width={size} height={size} role="img" className="flex-shrink-0">
        {segs.map((s) => <path key={s.i} d={s.d} fill={s.color} />)}
      </svg>
      <ul className="space-y-1.5 text-sm">
        {data.map((d, i) => (
          <li key={i} className="flex items-center gap-2 text-slate-600">
            <span className="h-2.5 w-2.5 rounded-sm" style={{ background: PALETTE[i % PALETTE.length] }} />
            <span className="capitalize">{d[nameKey]}</span>
            <span className="ml-auto font-medium text-slate-900">{d[valueKey]}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
