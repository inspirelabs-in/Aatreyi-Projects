"use client";

import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

// Shared brand palette for all charts.
export const PALETTE = ["#2563eb", "#7c3aed", "#16a34a", "#f59e0b", "#06b6d4", "#e11d48", "#0ea5e9", "#a855f7"];

const AXIS = { stroke: "#94a3b8", fontSize: 11 };
const GRID = "#eef2f7";

function ChartFrame({ height = 220, children }: { height?: number; children: React.ReactElement }) {
  // Explicit pixel height on ResponsiveContainer — height="100%" collapses to 0
  // inside grid/flex parents (the "charts not showing" bug).
  return (
    <div style={{ width: "100%", minHeight: height }}>
      <ResponsiveContainer width="100%" height={height}>{children}</ResponsiveContainer>
    </div>
  );
}

export function AreaTrend({ data, x, y, color = PALETTE[0], height }: {
  data: any[]; x: string; y: string; color?: string; height?: number;
}) {
  return (
    <ChartFrame height={height}>
      <AreaChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: -12 }}>
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
    </ChartFrame>
  );
}

export function LineTrend({ data, x, y, color = PALETTE[2], height }: {
  data: any[]; x: string; y: string; color?: string; height?: number;
}) {
  return (
    <ChartFrame height={height}>
      <LineChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: -12 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey={x} tick={AXIS} tickLine={false} axisLine={false} minTickGap={24} />
        <YAxis tick={AXIS} tickLine={false} axisLine={false} width={44} />
        <Tooltip contentStyle={{ borderRadius: 10, border: "1px solid #e5e7eb", fontSize: 12 }} />
        <Line type="monotone" dataKey={y} stroke={color} strokeWidth={2} dot={false} />
      </LineChart>
    </ChartFrame>
  );
}

export function BarBreakdown({ data, x, y, color = PALETTE[1], height }: {
  data: any[]; x: string; y: string; color?: string; height?: number;
}) {
  return (
    <ChartFrame height={height}>
      <BarChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: -12 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey={x} tick={AXIS} tickLine={false} axisLine={false} />
        <YAxis tick={AXIS} tickLine={false} axisLine={false} width={44} />
        <Tooltip contentStyle={{ borderRadius: 10, border: "1px solid #e5e7eb", fontSize: 12 }} cursor={{ fill: "#f8fafc" }} />
        <Bar dataKey={y} radius={[6, 6, 0, 0]}>
          {data.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}
        </Bar>
      </BarChart>
    </ChartFrame>
  );
}

export function Donut({ data, nameKey, valueKey, height = 220 }: {
  data: any[]; nameKey: string; valueKey: string; height?: number;
}) {
  return (
    <div className="flex items-center gap-4">
      <div style={{ width: 160, minHeight: height }}>
        <ResponsiveContainer width={160} height={height}>
          <PieChart>
            <Pie data={data} dataKey={valueKey} nameKey={nameKey} cx="50%" cy="50%"
                 innerRadius={48} outerRadius={72} paddingAngle={2} stroke="none">
              {data.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}
            </Pie>
            <Tooltip contentStyle={{ borderRadius: 10, border: "1px solid #e5e7eb", fontSize: 12 }} />
          </PieChart>
        </ResponsiveContainer>
      </div>
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
