"use client";

import { useEffect, useRef, useState } from "react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Pie, PieChart,
  Tooltip, XAxis, YAxis,
} from "recharts";

// Shared brand palette for all charts.
export const PALETTE = ["#2563eb", "#7c3aed", "#16a34a", "#f59e0b", "#06b6d4", "#e11d48", "#0ea5e9", "#a855f7"];

const AXIS = { stroke: "#94a3b8", fontSize: 11 };
const GRID = "#eef2f7";

// recharts' <ResponsiveContainer> renders nothing in this Next 16 / Turbopack
// setup (its ResizeObserver never reports a positive size, so no <svg> is ever
// drawn — only sibling legends showed). We measure the parent width ourselves and
// pass an explicit numeric width+height to each chart, which always renders.
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

export function AreaTrend({ data, x, y, color = PALETTE[0], height = 220 }: {
  data: any[]; x: string; y: string; color?: string; height?: number;
}) {
  const [ref, w] = useWidth();
  return (
    <div ref={ref} style={{ width: "100%", height }}>
      {w > 0 && (
        <AreaChart width={w} height={height} data={data} margin={{ top: 6, right: 8, bottom: 0, left: -12 }}>
          <defs>
            <linearGradient id={`grad-${y}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.28} />
              <stop offset="100%" stopColor={color} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey={x} tick={AXIS} tickLine={false} axisLine={false} minTickGap={24} />
          <YAxis tick={AXIS} tickLine={false} axisLine={false} width={44} />
          <Tooltip contentStyle={{ borderRadius: 10, border: "1px solid #e5e7eb", fontSize: 12 }} />
          <Area type="monotone" dataKey={y} stroke={color} strokeWidth={2} fill={`url(#grad-${y})`} />
        </AreaChart>
      )}
    </div>
  );
}

export function LineTrend({ data, x, y, color = PALETTE[2], height = 220 }: {
  data: any[]; x: string; y: string; color?: string; height?: number;
}) {
  const [ref, w] = useWidth();
  return (
    <div ref={ref} style={{ width: "100%", height }}>
      {w > 0 && (
        <LineChart width={w} height={height} data={data} margin={{ top: 6, right: 8, bottom: 0, left: -12 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey={x} tick={AXIS} tickLine={false} axisLine={false} minTickGap={24} />
          <YAxis tick={AXIS} tickLine={false} axisLine={false} width={44} />
          <Tooltip contentStyle={{ borderRadius: 10, border: "1px solid #e5e7eb", fontSize: 12 }} />
          <Line type="monotone" dataKey={y} stroke={color} strokeWidth={2} dot={false} />
        </LineChart>
      )}
    </div>
  );
}

export function BarBreakdown({ data, x, y, color = PALETTE[1], height = 220 }: {
  data: any[]; x: string; y: string; color?: string; height?: number;
}) {
  const [ref, w] = useWidth();
  return (
    <div ref={ref} style={{ width: "100%", height }}>
      {w > 0 && (
        <BarChart width={w} height={height} data={data} margin={{ top: 6, right: 8, bottom: 0, left: -12 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey={x} tick={AXIS} tickLine={false} axisLine={false} />
          <YAxis tick={AXIS} tickLine={false} axisLine={false} width={44} />
          <Tooltip contentStyle={{ borderRadius: 10, border: "1px solid #e5e7eb", fontSize: 12 }} cursor={{ fill: "#f8fafc" }} />
          <Bar dataKey={y} radius={[6, 6, 0, 0]}>
            {data.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}
          </Bar>
        </BarChart>
      )}
    </div>
  );
}

export function Donut({ data, nameKey, valueKey, height = 220 }: {
  data: any[]; nameKey: string; valueKey: string; height?: number;
}) {
  const size = Math.min(height, 180);
  return (
    <div className="flex items-center gap-4">
      <PieChart width={size} height={size}>
        <Pie data={data} dataKey={valueKey} nameKey={nameKey} cx="50%" cy="50%"
             innerRadius={size * 0.3} outerRadius={size * 0.46} paddingAngle={2} stroke="none">
          {data.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}
        </Pie>
        <Tooltip contentStyle={{ borderRadius: 10, border: "1px solid #e5e7eb", fontSize: 12 }} />
      </PieChart>
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
