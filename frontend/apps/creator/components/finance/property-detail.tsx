"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Button, DataTable, type Column, type SortOrder } from "@qiko/ui";
import type { FinanceProperty, FinanceUnitLedger } from "@/lib/api";
import { useFinance } from "./finance-context";
import { DrilldownFrame } from "./drilldown-frame";
import { ExpenseList } from "./expense-list";
import { MonthlyTrendsChart } from "./monthly-trends-chart";
import { formatCurrency } from "./utils";

function Field({ label, value, sub }: { label: string; value?: React.ReactNode; sub?: string }) {
  return (
    <div className="rounded-lg border border-white/[0.06] p-3" style={{ background: "oklch(0.16 0.02 250)" }}>
      <p className="text-[10px] font-medium uppercase tracking-wider text-white/45">{label}</p>
      <p className="mt-1 text-sm font-semibold text-white/90">{value ?? "-"}</p>
      {sub && <p className="mt-0.5 text-[10px] text-white/50">{sub}</p>}
    </div>
  );
}

export function PropertyDetail({ propertyRef, unitRef, from }: { propertyRef: string; unitRef?: string; from?: string | null }) {
  const { agentId, analytics } = useFinance();
  const router = useRouter();

  const property = useMemo(() => {
    const decoded = decodeURIComponent(propertyRef);
    return analytics?.properties?.find((p) =>
      p.propertyRef === decoded || p.propertyRef === propertyRef ||
      p.propertyId === decoded || p.propertyId === propertyRef ||
      p.name === decoded
    );
  }, [analytics, propertyRef]);

  if (!property) {
    return <div className="p-4 text-sm text-white/60">Property not found.</div>;
  }

  const unit = unitRef
    ? property.unitLedger?.find((u) =>
        u.unitRef === unitRef || u.unitRef === decodeURIComponent(unitRef) ||
        u.unitDescription === decodeURIComponent(unitRef)
      )
    : undefined;

  if (unit) {
    return (
      <UnitDetail property={property} unit={unit} onBack={() => {
        const back = `/studio/${agentId}/finance/property/${encodeURIComponent(propertyRef)}`;
        router.push(back);
      }} />
    );
  }

  return <PropertyOverview property={property} propertyRef={propertyRef} from={from} />;
}

function PropertyOverview({ property, propertyRef, from }: { property: FinanceProperty; propertyRef: string; from?: string | null }) {
  const { agentId, currency } = useFinance();
  const router = useRouter();
  const fromPortfolio = from === "portfolio";

  const [sort, setSort] = useState<keyof FinanceUnitLedger | "expenses">("income");
  const [order, setOrder] = useState<SortOrder>("desc");

  const units = useMemo(() => {
    const list = [...(property.unitLedger ?? [])];
    return list.sort((a, b) => {
      let av: unknown, bv: unknown;
      if (sort === "expenses") { av = a.totalGross; bv = b.totalGross; }
      else { av = (a as Record<string, unknown>)[sort]; bv = (b as Record<string, unknown>)[sort]; }
      if (typeof av === "number" && typeof bv === "number") return order === "asc" ? av - bv : bv - av;
      const as = String(av ?? ""), bs = String(bv ?? "");
      return order === "asc" ? as.localeCompare(bs) : bs.localeCompare(as);
    });
  }, [property, sort, order]);

  const unitColumns: Column<FinanceUnitLedger>[] = [
    { id: "unitRef", header: "Unit", rowHeader: true, sortable: true, cell: (u) => u.unitRef },
    { id: "unitDescription", header: "Description", sortable: true, cell: (u) => u.unitDescription },
    { id: "income", header: "Income", numeric: true, sortable: true, cell: (u) => formatCurrency(u.income, currency) },
    { id: "outstanding", header: "Outstanding", numeric: true, sortable: true, cell: (u) => formatCurrency(u.outstanding, currency) },
    { id: "totalGross", header: "Gross", numeric: true, sortable: true, cell: (u) => formatCurrency(u.totalGross, currency) },
    { id: "invoiceCount", header: "Invoices", numeric: true, sortable: true, cell: (u) => u.invoiceCount },
  ];

  const totalVendors = property.topVendors ?? [];
  const totalCategories = property.expenseCategories ?? [];

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <DrilldownFrame
        backLabel={fromPortfolio ? "Back to properties" : "Back to dashboard"}
        onBack={() => router.push(fromPortfolio ? `/studio/${agentId}/finance/breakdown?view=properties` : `/studio/${agentId}/finance`)}
        title={property.name || property.propertyRef || "Property"}
        subtitle={<p className="text-sm text-white/55">{`Property ${property.propertyRef ?? ""} - income, expenses, risk, and vendor mix for the selected period.`}</p>}
      >
        <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Field label="Reference" value={property.propertyRef} />
        <Field label="Income" value={formatCurrency(property.income, currency)} />
        <Field label="Expenses" value={formatCurrency(property.expenses, currency)} />
        <Field label="Net Profit" value={formatCurrency(property.netProfit, currency)} />
        <Field label="Margin" value={`${property.marginPercent ?? 0}%`} />
        <Field label="Outstanding" value={formatCurrency(property.outstanding, currency)} />
        <Field label="Risk" value={property.riskLevel ? `${property.riskLevel} (${property.riskScore ?? 0})` : undefined} />
        <Field label="Units" value={property.unitCount ?? property.unitLedger?.length} />
        <Field label="Invoices" value={property.invoiceCount} />
        <Field label="Vendors" value={property.vendorCount} />
      </div>

      <div className="rounded-xl border border-white/[0.06] p-4" style={{ background: "oklch(0.16 0.02 250)" }}>
        <h3 className="mb-3 text-sm font-semibold text-white/88">Monthly trends</h3>
        <MonthlyTrendsChart data={property.monthlyTrends ?? []} />
      </div>

      <div className="rounded-xl border border-white/[0.06] p-4" style={{ background: "oklch(0.16 0.02 250)" }}>
        <h3 className="mb-3 text-sm font-semibold text-white/88">Unit ledger</h3>
        <DataTable
          caption={`Units for ${property.name}`}
          rows={units}
          rowKey={(u) => u.unitRef ?? String(u.unitDescription)}
          columns={unitColumns}
          sort={sort}
          order={order}
          onSortChange={(s, o) => { setSort(s as typeof sort); setOrder(o); }}
          actions={(u) => (
            <Button
              variant="outline"
              size="sm"
              onClick={() => router.push(`/studio/${agentId}/finance/property/${encodeURIComponent(propertyRef)}?unit=${encodeURIComponent(u.unitRef ?? "")}${fromPortfolio ? "&from=portfolio" : ""}`)}
            >
              View
            </Button>
          )}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-white/[0.06] p-4" style={{ background: "oklch(0.16 0.02 250)" }}>
          <h3 className="mb-3 text-sm font-semibold text-white/88">Top vendors</h3>
          <ul className="space-y-2">
            {totalVendors.length === 0 && <p className="text-xs text-white/45">No vendor data.</p>}
            {totalVendors.slice(0, 10).map((v, i) => (
              <li key={i} className="flex items-center justify-between">
                <button
                  type="button"
                  onClick={() => router.push(`/studio/${agentId}/finance/vendor/${encodeURIComponent(v.vendorName)}`)}
                  className="text-left text-xs text-indigo-300 hover:underline"
                >
                  {v.vendorName}
                </button>
                <span className="text-xs text-white/62">{formatCurrency(v.amount, currency)}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="rounded-xl border border-white/[0.06] p-4" style={{ background: "oklch(0.16 0.02 250)" }}>
          <h3 className="mb-3 text-sm font-semibold text-white/88">Expense categories</h3>
          <ul className="space-y-2">
            {totalCategories.length === 0 && <p className="text-xs text-white/45">No category data.</p>}
            {totalCategories.slice(0, 10).map((c, i) => (
              <li key={i} className="flex items-center justify-between">
                <button
                  type="button"
                  onClick={() => router.push(`/studio/${agentId}/finance/expenditure?category=${encodeURIComponent(c.category)}`)}
                  className="text-left text-xs text-indigo-300 hover:underline"
                >
                  {c.category}
                </button>
                <span className="text-xs text-white/62">{formatCurrency(c.amount, currency)}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="rounded-xl border border-white/[0.06] p-4" style={{ background: "oklch(0.16 0.02 250)" }}>
        <ExpenseList filter={{ propertyRef: property.propertyRef ?? property.propertyId ?? "" }} title="Property expenses" />
      </div>
        </div>
      </DrilldownFrame>
    </div>
  );
}

function UnitDetail({ property, unit, onBack }: { property: FinanceProperty; unit: FinanceUnitLedger; onBack: () => void }) {
  const { currency } = useFinance();

  return (
    <DrilldownFrame
      backLabel={`Back to ${property.name || property.propertyRef || "property"}`}
      onBack={onBack}
      title={unit.unitRef || "Unit"}
      subtitle={unit.unitDescription}
    >
      <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Field label="Income" value={formatCurrency(unit.income, currency)} />
        <Field label="Outstanding" value={formatCurrency(unit.outstanding, currency)} />
        <Field label="Gross" value={formatCurrency(unit.totalGross, currency)} />
        <Field label="Invoices" value={unit.invoiceCount} />
      </div>

      <div className="rounded-xl border border-white/[0.06] p-4" style={{ background: "oklch(0.16 0.02 250)" }}>
        <ExpenseList
          filter={{ propertyRef: property.propertyRef ?? property.propertyId ?? "", unitRef: unit.unitRef ?? "" }}
          showSearch={false}
          hideProperty
          hideUnit
          hideViewUnitAction
          title="Unit expenses"
        />
      </div>
      </div>
    </DrilldownFrame>
  );
}
