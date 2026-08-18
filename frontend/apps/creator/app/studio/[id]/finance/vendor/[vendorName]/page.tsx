"use client";

import { useParams } from "next/navigation";
import { useMemo } from "react";
import { ArrowLeft } from "lucide-react";
import { useRouter } from "next/navigation";
import { useFinance } from "@/components/finance/finance-context";
import { ExpenseList } from "@/components/finance/expense-list";
import { allExpenses, formatCurrency } from "@/components/finance/utils";

function Field({ label, value }: { label: string; value?: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-white/[0.06] p-3" style={{ background: "oklch(0.16 0.02 250)" }}>
      <p className="text-[10px] font-medium uppercase tracking-wider text-white/45">{label}</p>
      <p className="mt-1 text-sm font-semibold text-white/90">{value ?? "-"}</p>
    </div>
  );
}

export default function VendorPage() {
  const params = useParams<{ vendorName: string }>();
  const router = useRouter();
  const { agentId, analytics } = useFinance();
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
    <div className="space-y-6 p-4">
      <button
        type="button"
        onClick={() => router.push(`/studio/${agentId}/finance`)}
        className="inline-flex items-center gap-1 text-xs text-white/55 hover:text-white/80"
      >
        <ArrowLeft className="h-3.5 w-3.5" /> Back to dashboard
      </button>

      <h1 className="text-lg font-semibold text-white">{vendorName}</h1>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Field label="Total gross" value={formatCurrency(totalGross)} />
        <Field label="Total nett" value={formatCurrency(totalNett)} />
        <Field label="Invoices" value={invoiceCount} />
        <Field label="Properties" value={propertyCount} />
      </div>

      <div className="rounded-xl border border-white/[0.06] p-4" style={{ background: "oklch(0.16 0.02 250)" }}>
        <ExpenseList filter={{ vendorName }} title="Vendor invoices" />
      </div>
    </div>
  );
}
