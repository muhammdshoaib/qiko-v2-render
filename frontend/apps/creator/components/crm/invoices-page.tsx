"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { formatDate, formatMoney, invoiceTone } from "@/lib/crm/format";
import { useCrm } from "@/lib/crm/store";
import type { InvoiceStatus } from "@/lib/crm/types";
import { Button } from "@qiko/ui";
import { toast } from "sonner";
import { PrototypeBadge } from "./prototype-badge";
import { WORKFLOW_IDS } from "@/lib/crm/workflows";

const FILTERS: { id: "all" | InvoiceStatus; label: string }[] = [
  { id: "all", label: "All" },
  { id: "unpaid", label: "Unpaid" },
  { id: "partial", label: "Partial" },
  { id: "overdue", label: "Overdue" },
  { id: "paid", label: "Paid" },
];

export function CrmInvoicesPage() {
  const crm = useCrm();
  const [filter, setFilter] = useState<(typeof FILTERS)[number]["id"]>("all");
  const invoices = useMemo(
    () => crm.invoices.filter((item) => filter === "all" || item.status === filter),
    [crm.invoices, filter],
  );
  const upcoming = crm.commitments;

  return (
    <div className="space-y-6">
      <p className="text-sm text-slate-400">
        Invoice amounts are sample records. <PrototypeBadge className="ml-1 align-middle" /> No payments are processed.
      </p>

      <section className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-4">
        <h2 className="text-sm font-semibold text-white">Recurring commercial commitments</h2>
        {upcoming.length === 0 ? (
          <p className="mt-4 text-sm text-slate-400">No commitments on file.</p>
        ) : (
          <ul className="mt-3 divide-y divide-white/[0.05]">
            {upcoming.map((item) => (
              <li key={item.id} className="flex items-center justify-between py-3 text-sm">
                <div>
                  <Link href={`/crm/companies/${item.companyId}`} className="text-white hover:underline">{crm.companyById(item.companyId)?.name}</Link>
                  <p className="text-xs text-slate-400">{item.title} · {item.cadence}</p>
                </div>
                <div className="text-right">
                  <p className="text-white">{formatMoney(item.amount)}</p>
                  <p className="text-xs text-slate-500">Next {formatDate(item.nextDate)}</p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <div className="flex flex-wrap gap-2">
        {FILTERS.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => setFilter(item.id)}
            className={`rounded-lg px-3 py-2 text-sm ${filter === item.id ? "bg-white/[0.08] text-white" : "text-slate-400 hover:text-white"}`}
          >
            {item.label}
          </button>
        ))}
      </div>

      <section className="overflow-x-auto rounded-2xl border border-white/[0.06]">
        {invoices.length === 0 ? (
          <p className="px-4 py-10 text-sm text-slate-400">No invoices in this filter.</p>
        ) : (
          <table className="min-w-full text-left text-sm">
            <thead className="sticky top-0 bg-[#0b0f18] text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3 font-medium">Invoice</th>
                <th className="px-4 py-3 font-medium">Customer</th>
                <th className="px-4 py-3 font-medium">Due</th>
                <th className="px-4 py-3 font-medium">Amount</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.05]">
              {invoices.map((invoice) => (
                <tr key={invoice.id}>
                  <td className="px-4 py-3 text-white">{invoice.number}</td>
                  <td className="px-4 py-3">
                    <Link href={`/crm/companies/${invoice.companyId}`} className="text-indigo-300 hover:underline">
                      {crm.companyById(invoice.companyId)?.name}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-slate-300">{formatDate(invoice.dueDate)}</td>
                  <td className="px-4 py-3 text-slate-200">
                    {formatMoney(invoice.amount)}
                    {invoice.status === "partial" && (
                      <span className="block text-xs text-amber-300">Paid {formatMoney(invoice.paidAmount)}</span>
                    )}
                  </td>
                  <td className={`px-4 py-3 capitalize ${invoiceTone(invoice.status)}`}>{invoice.status}</td>
                  <td className="px-4 py-3">
                    {invoice.id === WORKFLOW_IDS.invoiceId && crm.workflowRuns.find((run) => run.id === "invoice")?.status === "idle" && (
                      <Button type="button" size="sm" variant="outline" onClick={() => toast.message(crm.runInvoiceWorkflow())}>
                        Monitor (prototype)
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
