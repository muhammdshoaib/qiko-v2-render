import { formatMoney } from "./format";
import type { ChannelId, CrmState, DemoUserId, Invoice, Opportunity } from "./types";

export const FINANCIAL_FIELDS = [
  "value",
  "expectedRevenue",
  "estimatedCost",
  "invoiceAmount",
  "paidAmount",
  "pipelineTotal",
] as const;

export type FinancialField = (typeof FINANCIAL_FIELDS)[number];

export const DEMO_USERS: Record<DemoUserId, {
  id: DemoUserId;
  name: string;
  role: string;
  finance: boolean;
}> = {
  maya: { id: "maya", name: "Maya Chen", role: "Account owner", finance: true },
  owen: { id: "owen", name: "Owen Blake", role: "Analyst", finance: false },
};

export const CHANNELS: Record<ChannelId, {
  id: ChannelId;
  label: string;
  allowsFinance: boolean;
}> = {
  claude: { id: "claude", label: "Claude", allowsFinance: true },
  "slack-sales": { id: "slack-sales", label: "Slack #sales-pipeline", allowsFinance: false },
  "slack-revenue": { id: "slack-revenue", label: "Slack #revenue", allowsFinance: true },
  email: { id: "email", label: "Email", allowsFinance: false },
};

export type AccessDecision = {
  operational: boolean;
  financial: boolean;
  deniedBy: "channel" | "user" | null;
  reason: string | null;
};

export type ProjectedOpportunity = {
  companyId: string;
  companyName: string;
  title: string;
  owner: string;
  stage: Opportunity["stage"];
  nextStep: string;
  lastActivityAt: string;
  value?: number;
  expectedRevenue?: number;
  estimatedCost?: number;
};

export type ProjectedInvoice = {
  companyName: string;
  number: string;
  status: Invoice["status"];
  dueDate: string;
  amount?: number;
};

export function authorize(userId: DemoUserId, channel: ChannelId): AccessDecision {
  const user = DEMO_USERS[userId];
  const surface = CHANNELS[channel];
  if (user.finance && surface.allowsFinance) {
    return { operational: true, financial: true, deniedBy: null, reason: null };
  }
  if (!surface.allowsFinance) {
    return {
      operational: true,
      financial: false,
      deniedBy: "channel",
      reason: "Financial fields are not permitted in this channel.",
    };
  }
  return {
    operational: true,
    financial: false,
    deniedBy: "user",
    reason: "This operator is not authorised for financial fields.",
  };
}

function omitFinance<T extends Record<string, unknown>>(record: T, allow: boolean): T {
  if (allow) return record;
  const next = { ...record };
  for (const key of FINANCIAL_FIELDS) {
    delete next[key];
  }
  return next;
}

export function projectOpportunity(
  state: CrmState,
  companyId: string,
  access: AccessDecision,
): ProjectedOpportunity | null {
  const company = state.companies.find((item) => item.id === companyId);
  const opportunity = state.opportunities.find((item) => item.companyId === companyId);
  if (!company || !opportunity) return null;
  const raw: ProjectedOpportunity = {
    companyId: company.id,
    companyName: company.name,
    title: opportunity.title,
    owner: opportunity.owner,
    stage: opportunity.stage,
    nextStep: opportunity.nextStep,
    lastActivityAt: opportunity.lastActivityAt,
    value: opportunity.value,
    expectedRevenue: opportunity.expectedRevenue,
    estimatedCost: opportunity.estimatedCost,
  };
  return omitFinance(raw, access.financial);
}

export function projectOpenPipeline(state: CrmState, access: AccessDecision) {
  const open = state.opportunities.filter((item) => item.stage !== "charged");
  const total = open.reduce((sum, item) => sum + item.value, 0);
  const invoices: ProjectedInvoice[] = state.invoices
    .filter((item) => item.status !== "paid")
    .map((item) => {
      const row: ProjectedInvoice = {
        companyName: state.companies.find((company) => company.id === item.companyId)?.name ?? "Unknown",
        number: item.number,
        status: item.status,
        dueDate: item.dueDate,
      };
      if (access.financial) row.amount = item.amount;
      return row;
    });
  return omitFinance({ invoices, pipelineTotal: total, count: open.length }, access.financial);
}

export function hasRestrictedValue(text: string) {
  return /£?\s?180,?000|£?\s?42,?000|£?\s?144,?000|£?\s?522,?000|180000|42000/.test(text);
}

export function moneyOrHidden(value: number | undefined, access: AccessDecision) {
  if (!access.financial || value == null) return null;
  return formatMoney(value);
}
