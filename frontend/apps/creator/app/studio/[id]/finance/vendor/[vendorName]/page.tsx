"use client";

import { useParams, useRouter } from "next/navigation";
import { useMemo } from "react";
import { DrilldownFrame } from "@/components/finance/drilldown-frame";
import { useFinance } from "@/components/finance/finance-context";
import { ExpenseList } from "@/components/finance/expense-list";
import { allExpenses, formatCurrency } from "@/components/finance/utils";

function Field({ label, value }: { label: string; value?: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border p-3" style={{ background: "oklch(0.16 0.02 250)" }}>
      <p className="text-[10px] font-medium uppercase tracking-wider text-slate-400">{label}</p>
      <p className="mt-1 text-sm font-semibold text-foreground/90">{value ?? "-"}</p>
    </div>
  );
}

export default function VendorPage() {
  const params = useParams<{ vendorName: string }>();
  const router = useRouter();
  const { agentId, analytics, currency } = useFinance();
  const vendorName = decodeURIComponent(params.vendorName);

  const rows = useMemo(
    () => allExpenses(analytics).filter((e) => (e.supplierName ?? "").toLowerCase() === vendorName.toLowerCase()),
    [analytics, vendorName],
  );

  const totalGross = rows.reduce((sum, r) => sum + (r.gross ?? 0), 0);
  const totalNett = rows.reduce((sum, r) => sum + (r.nett ?? 0), 0);
  const invoiceCount = rows.length;
  const propertyCount = new Set(rows.map((r) => r.propertyRef)).size;

  return (
    <DrilldownFrame
      onBack={() => router.push(`/studio/${agentId}/finance`)}
      title={vendorName}
      subtitle={<p className="text-sm text-slate-500">{`${propertyCount} properties · ${invoiceCount} invoices - vendor spend profile and payment mix.`}</p>}
    >
      <div className="space-y-6">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Field label="Total gross" value={formatCurrency(totalGross, currency)} />
          <Field label="Total nett" value={formatCurrency(totalNett, currency)} />
          <Field label="Invoices" value={invoiceCount} />
          <Field label="Properties" value={propertyCount} />
        </div>
        <div className="rounded-xl border border-border p-4" style={{ background: "oklch(0.16 0.02 250)" }}>
          <ExpenseList filter={{ vendorName }} title="Vendor invoices" />
        </div>
      </div>
    </DrilldownFrame>
  );
}
