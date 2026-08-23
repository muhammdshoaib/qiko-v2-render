"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { FinanceMonthlyTrend } from "@/lib/api";
import { useFinance } from "./finance-context";
import { EXPENSE_COLOR, INCOME_COLOR, PROFIT_COLOR, formatCompact, formatCurrency } from "./utils";

export function MonthlyTrendsChart({ data, height = 240 }: { data: FinanceMonthlyTrend[]; height?: number }) {
  const { currency } = useFinance();
  if (data.length === 0) return <p className="text-xs text-white/45">No monthly data available.</p>;

  const chartData = data.map((d) => ({
    ...d,
    label: new Date(`${d.month}-01T00:00:00Z`).toLocaleString("en-GB", { month: "short", year: "numeric" }),
  }));

  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
          <XAxis dataKey="label" tick={{ fill: "#64748b", fontSize: 11 }} />
          <YAxis tick={{ fill: "#64748b", fontSize: 11 }} tickFormatter={(v) => formatCompact(Number(v), currency)} />
          <Tooltip
            contentStyle={{ background: "#0f1220", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 8, fontSize: 12, color: "#e2e8f0" }}
            formatter={(v) => formatCurrency(Number(v), currency)}
          />
          <Bar dataKey="income" name="Income" fill={INCOME_COLOR} radius={[4, 4, 0, 0]} />
          <Bar dataKey="expenses" name="Expenses" fill={EXPENSE_COLOR} radius={[4, 4, 0, 0]} />
          <Bar dataKey="netProfit" name="Net Profit" fill={PROFIT_COLOR} radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
