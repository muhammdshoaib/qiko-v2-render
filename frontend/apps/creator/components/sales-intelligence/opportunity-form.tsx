"use client";

// Shared manual "add / edit an opportunity" form for the Sales Intelligence cockpit. Ported from
// Ali's OpportunityCreateView / OpportunityDetailView edit form and adapted to V2's API
// (createSalesOpportunity / updateSalesOpportunity). Pure controlled form: the parent owns the
// submit + loading state and decides where to route afterwards. Dark cockpit theme, labelled
// inputs throughout.
import { useState } from "react";
import { Loader2 } from "lucide-react";
import { Input, Select, Textarea } from "@/components/cockpit/controls";
import type {
  CreateSalesOpportunityInput, SalesOpportunity, UpdateSalesOpportunityInput,
} from "@/lib/api";

export type OpportunityFormValues = {
  title: string;
  buyer: string;
  reference: string;
  noticeType: string;
  country: string;
  category: string;
  estimatedValue: string;
  currency: string;
  deadlineAt: string;
  sourceUrl: string;
  securityClearance: string;
  framework: string;
  contractDuration: string;
  technology: string;
  extractionConfidence: string;
  contactName: string;
  contactEmail: string;
  contactPhone: string;
  linkUrl: string;
  linkDescription: string;
  executiveSummary: string;
  riskSummary: string;
  opportunitySummary: string;
  requirements: string;
  deliverables: string;
  qualificationScore: string;
  recommendation: string;
  confidence: string;
  aiReasoning: string;
  recommendations: string;
  notes: string;
};

export const EMPTY_OPPORTUNITY_FORM: OpportunityFormValues = {
  title: "", buyer: "", reference: "", noticeType: "", country: "", category: "",
  estimatedValue: "", currency: "GBP", deadlineAt: "", sourceUrl: "", securityClearance: "",
  framework: "", contractDuration: "", technology: "", extractionConfidence: "",
  contactName: "", contactEmail: "", contactPhone: "", linkUrl: "", linkDescription: "",
  executiveSummary: "", riskSummary: "", opportunitySummary: "", requirements: "", deliverables: "",
  qualificationScore: "", recommendation: "", confidence: "", aiReasoning: "", recommendations: "",
  notes: "",
};

function toDateInput(value?: string | null): string {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value.slice(0, 10);
  return d.toISOString().slice(0, 10);
}

// Pre-fill the edit form from an existing opportunity + its detail sections.
export function opportunityToForm(opp: SalesOpportunity): OpportunityFormValues {
  const ov = opp.detail?.overview;
  const sum = opp.detail?.summary;
  const q = opp.detail?.qualification;
  const contact = ov?.contacts?.[0];
  const link = ov?.links?.[0];
  const num = (v: number | null | undefined) => (v === null || v === undefined ? "" : String(v));
  const lines = (v: string[] | null | undefined) => (v ?? []).join("\n");
  return {
    title: opp.title ?? "",
    buyer: opp.buyer ?? ov?.buyer ?? "",
    reference: ov?.reference ?? "",
    noticeType: ov?.noticeType ?? "",
    country: opp.country ?? ov?.country ?? "",
    category: opp.category ?? ov?.category ?? "",
    estimatedValue: num(opp.estimatedValue ?? ov?.estimatedValue),
    currency: opp.currency ?? ov?.currency ?? "GBP",
    deadlineAt: toDateInput(opp.deadlineAt ?? ov?.deadlineAt),
    sourceUrl: opp.sourceUrl ?? ov?.sourceUrl ?? "",
    securityClearance: ov?.securityClearance ?? "",
    framework: ov?.framework ?? "",
    contractDuration: ov?.contractDuration ?? "",
    technology: ov?.technology ?? "",
    extractionConfidence: num(ov?.extractionConfidence),
    contactName: contact?.name ?? "",
    contactEmail: contact?.email ?? "",
    contactPhone: contact?.phone ?? "",
    linkUrl: link?.url ?? "",
    linkDescription: link?.description ?? "",
    executiveSummary: sum?.executiveSummary ?? "",
    riskSummary: sum?.riskSummary ?? "",
    opportunitySummary: sum?.opportunitySummary ?? "",
    requirements: lines(sum?.requirements),
    deliverables: lines(sum?.deliverables),
    qualificationScore: num(q?.overallScore ?? opp.qualificationScore),
    recommendation: q?.recommendation ?? opp.recommendation ?? "",
    confidence: num(q?.confidence ?? opp.confidence),
    aiReasoning: q?.aiReasoning ?? "",
    recommendations: lines(q?.recommendations),
    notes: opp.detail?.notes?.humanReviewNotes ?? opp.humanReviewNotes ?? "",
  };
}

const text = (v: string): string | null => (v.trim() ? v.trim() : null);
const number = (v: string): number | null => {
  const t = v.trim().replace(/,/g, "");
  if (!t) return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
};
const list = (v: string): string[] => v.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);

// Shared field mapping used by both create + update payloads.
function basePayload(v: OpportunityFormValues) {
  return {
    title: v.title.trim(),
    buyer: text(v.buyer),
    country: text(v.country),
    category: text(v.category),
    estimated_value: number(v.estimatedValue),
    currency: (v.currency.trim().toUpperCase().slice(0, 3)) || null,
    deadline_at: text(v.deadlineAt),
    source_url: text(v.sourceUrl),
    reference: text(v.reference),
    notice_type: text(v.noticeType),
    security_clearance: text(v.securityClearance),
    extraction_confidence: number(v.extractionConfidence),
    framework: text(v.framework),
    contract_duration: text(v.contractDuration),
    technology: text(v.technology),
    contacts: [{ name: text(v.contactName), email: text(v.contactEmail), phone: text(v.contactPhone) }],
    links: v.linkUrl.trim() ? [{ url: v.linkUrl.trim(), description: text(v.linkDescription) }] : [],
    executive_summary: text(v.executiveSummary),
    risk_summary: text(v.riskSummary),
    opportunity_summary: text(v.opportunitySummary),
    requirements: list(v.requirements),
    deliverables: list(v.deliverables),
    qualification_score: number(v.qualificationScore),
    recommendation: text(v.recommendation),
    confidence: number(v.confidence),
    ai_reasoning: text(v.aiReasoning),
    recommendations: list(v.recommendations),
    notes: text(v.notes),
  };
}

export function toCreatePayload(v: OpportunityFormValues): CreateSalesOpportunityInput {
  return { ...basePayload(v), source_key: "manual", source_name: "Manual Entry", run_qualification: true };
}

export function toUpdatePayload(v: OpportunityFormValues): UpdateSalesOpportunityInput {
  return basePayload(v);
}

function LabelledField({ id, label, children }: { id: string; label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">{label}</label>
      {children}
    </div>
  );
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return <h3 className="text-[13px] font-semibold text-foreground">{children}</h3>;
}

export function OpportunityForm({
  mode, initialValues, submitting, error, onSubmit, onCancel,
}: {
  mode: "create" | "edit";
  initialValues?: OpportunityFormValues;
  submitting: boolean;
  error?: string | null;
  onSubmit: (values: OpportunityFormValues) => void;
  onCancel: () => void;
}) {
  const [values, setValues] = useState<OpportunityFormValues>(initialValues ?? EMPTY_OPPORTUNITY_FORM);
  const [titleError, setTitleError] = useState(false);

  function set<K extends keyof OpportunityFormValues>(key: K, value: OpportunityFormValues[K]) {
    setValues((prev) => ({ ...prev, [key]: value }));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (submitting) return;
    if (!values.title.trim()) {
      setTitleError(true);
      return;
    }
    setTitleError(false);
    onSubmit(values);
  }

  const submitLabel = mode === "create"
    ? (submitting ? "Creating\u2026" : "Create opportunity")
    : (submitting ? "Saving\u2026" : "Save changes");

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {error && (
        <p role="alert" className="rounded-lg border border-red-500/20 bg-red-500/[0.06] px-3 py-2 text-[12px] text-red-300">
          {error}
        </p>
      )}

      <section className="space-y-4">
        <SectionHeading>Overview</SectionHeading>
        <LabelledField id="opp-title" label="Title *">
          <Input id="opp-title" value={values.title} onChange={(e) => set("title", e.target.value)}
            placeholder="Opportunity title" required aria-required="true"
            aria-invalid={titleError} disabled={submitting} />
          {titleError && <span className="text-[11px] text-red-400">Title is required.</span>}
        </LabelledField>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <LabelledField id="opp-buyer" label="Buyer / Agency">
            <Input id="opp-buyer" value={values.buyer} onChange={(e) => set("buyer", e.target.value)} disabled={submitting} />
          </LabelledField>
          <LabelledField id="opp-reference" label="Reference">
            <Input id="opp-reference" value={values.reference} onChange={(e) => set("reference", e.target.value)} disabled={submitting} />
          </LabelledField>
          <LabelledField id="opp-country" label="Country">
            <Input id="opp-country" value={values.country} onChange={(e) => set("country", e.target.value)} disabled={submitting} />
          </LabelledField>
          <LabelledField id="opp-category" label="Category">
            <Input id="opp-category" value={values.category} onChange={(e) => set("category", e.target.value)} disabled={submitting} />
          </LabelledField>
          <LabelledField id="opp-notice-type" label="Notice Type">
            <Input id="opp-notice-type" value={values.noticeType} onChange={(e) => set("noticeType", e.target.value)} disabled={submitting} />
          </LabelledField>
          <LabelledField id="opp-deadline" label="Deadline">
            <Input id="opp-deadline" type="date" value={values.deadlineAt} onChange={(e) => set("deadlineAt", e.target.value)} disabled={submitting} />
          </LabelledField>
          <LabelledField id="opp-value" label="Estimated Value">
            <Input id="opp-value" inputMode="decimal" value={values.estimatedValue}
              onChange={(e) => set("estimatedValue", e.target.value)} placeholder="e.g. 250000" disabled={submitting} />
          </LabelledField>
          <LabelledField id="opp-currency" label="Currency">
            <Input id="opp-currency" value={values.currency} onChange={(e) => set("currency", e.target.value)}
              maxLength={3} placeholder="GBP" disabled={submitting} />
          </LabelledField>
          <LabelledField id="opp-source-url" label="Source URL">
            <Input id="opp-source-url" type="url" value={values.sourceUrl} onChange={(e) => set("sourceUrl", e.target.value)}
              placeholder="https://" disabled={submitting} />
          </LabelledField>
          <LabelledField id="opp-security" label="Security Clearance">
            <Input id="opp-security" value={values.securityClearance} onChange={(e) => set("securityClearance", e.target.value)} disabled={submitting} />
          </LabelledField>
          <LabelledField id="opp-framework" label="Framework">
            <Input id="opp-framework" value={values.framework} onChange={(e) => set("framework", e.target.value)} disabled={submitting} />
          </LabelledField>
          <LabelledField id="opp-duration" label="Contract Duration">
            <Input id="opp-duration" value={values.contractDuration} onChange={(e) => set("contractDuration", e.target.value)} disabled={submitting} />
          </LabelledField>
          <LabelledField id="opp-technology" label="Technology">
            <Input id="opp-technology" value={values.technology} onChange={(e) => set("technology", e.target.value)} disabled={submitting} />
          </LabelledField>
          <LabelledField id="opp-extraction" label="Extraction Confidence (%)">
            <Input id="opp-extraction" inputMode="numeric" value={values.extractionConfidence}
              onChange={(e) => set("extractionConfidence", e.target.value)} disabled={submitting} />
          </LabelledField>
        </div>
      </section>

      <section className="space-y-4">
        <SectionHeading>Contact &amp; link</SectionHeading>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <LabelledField id="opp-contact-name" label="Contact Name">
            <Input id="opp-contact-name" value={values.contactName} onChange={(e) => set("contactName", e.target.value)} disabled={submitting} />
          </LabelledField>
          <LabelledField id="opp-contact-email" label="Contact Email">
            <Input id="opp-contact-email" type="email" value={values.contactEmail} onChange={(e) => set("contactEmail", e.target.value)} disabled={submitting} />
          </LabelledField>
          <LabelledField id="opp-contact-phone" label="Contact Phone">
            <Input id="opp-contact-phone" value={values.contactPhone} onChange={(e) => set("contactPhone", e.target.value)} disabled={submitting} />
          </LabelledField>
          <LabelledField id="opp-link-url" label="Link URL">
            <Input id="opp-link-url" type="url" value={values.linkUrl} onChange={(e) => set("linkUrl", e.target.value)}
              placeholder="https://" disabled={submitting} />
          </LabelledField>
          <LabelledField id="opp-link-desc" label="Link Description">
            <Input id="opp-link-desc" value={values.linkDescription} onChange={(e) => set("linkDescription", e.target.value)} disabled={submitting} />
          </LabelledField>
        </div>
      </section>

      <section className="space-y-4">
        <SectionHeading>Summary</SectionHeading>
        <LabelledField id="opp-exec-summary" label="Executive Summary">
          <Textarea id="opp-exec-summary" value={values.executiveSummary} onChange={(e) => set("executiveSummary", e.target.value)}
            className="min-h-20" disabled={submitting} />
        </LabelledField>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <LabelledField id="opp-risk-summary" label="Risk Summary">
            <Textarea id="opp-risk-summary" value={values.riskSummary} onChange={(e) => set("riskSummary", e.target.value)}
              className="min-h-20" disabled={submitting} />
          </LabelledField>
          <LabelledField id="opp-opportunity-summary" label="Opportunity Summary">
            <Textarea id="opp-opportunity-summary" value={values.opportunitySummary} onChange={(e) => set("opportunitySummary", e.target.value)}
              className="min-h-20" disabled={submitting} />
          </LabelledField>
          <LabelledField id="opp-requirements" label="Requirements (one per line)">
            <Textarea id="opp-requirements" value={values.requirements} onChange={(e) => set("requirements", e.target.value)}
              className="min-h-20" disabled={submitting} />
          </LabelledField>
          <LabelledField id="opp-deliverables" label="Deliverables (one per line)">
            <Textarea id="opp-deliverables" value={values.deliverables} onChange={(e) => set("deliverables", e.target.value)}
              className="min-h-20" disabled={submitting} />
          </LabelledField>
        </div>
      </section>

      <section className="space-y-4">
        <SectionHeading>Qualification</SectionHeading>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <LabelledField id="opp-score" label="Qualification Score (0-100)">
            <Input id="opp-score" inputMode="numeric" value={values.qualificationScore}
              onChange={(e) => set("qualificationScore", e.target.value)} disabled={submitting} />
          </LabelledField>
          <LabelledField id="opp-recommendation" label="Recommendation">
            <Select id="opp-recommendation" value={values.recommendation} onChange={(e) => set("recommendation", e.target.value)} disabled={submitting}>
              <option value="">Not set</option>
              <option value="Bid">Bid</option>
              <option value="Review">Review</option>
              <option value="No Bid">No Bid</option>
            </Select>
          </LabelledField>
          <LabelledField id="opp-confidence" label="Confidence (%)">
            <Input id="opp-confidence" inputMode="numeric" value={values.confidence}
              onChange={(e) => set("confidence", e.target.value)} disabled={submitting} />
          </LabelledField>
        </div>
        <LabelledField id="opp-ai-reasoning" label="AI Reasoning">
          <Textarea id="opp-ai-reasoning" value={values.aiReasoning} onChange={(e) => set("aiReasoning", e.target.value)}
            className="min-h-20" disabled={submitting} />
        </LabelledField>
        <LabelledField id="opp-recommendations" label="Recommendations (one per line)">
          <Textarea id="opp-recommendations" value={values.recommendations} onChange={(e) => set("recommendations", e.target.value)}
            className="min-h-20" disabled={submitting} />
        </LabelledField>
      </section>

      <section className="space-y-4">
        <SectionHeading>Notes</SectionHeading>
        <LabelledField id="opp-notes" label="Human Review Notes">
          <Textarea id="opp-notes" value={values.notes} onChange={(e) => set("notes", e.target.value.slice(0, 2000))}
            className="min-h-24" disabled={submitting} />
        </LabelledField>
      </section>

      <div className="flex items-center justify-end gap-3 border-t border-border pt-4">
        <button type="button" onClick={onCancel} disabled={submitting}
          className="rounded-lg border border-border px-4 py-2 text-[13px] font-semibold text-slate-700 hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 disabled:opacity-50">
          Cancel
        </button>
        <button type="submit" disabled={submitting}
          className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-500 px-4 py-2 text-[13px] font-semibold text-foreground hover:bg-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 disabled:opacity-50">
          {submitting && <Loader2 className="size-3.5 animate-spin" />}
          {submitLabel}
        </button>
      </div>
    </form>
  );
}
