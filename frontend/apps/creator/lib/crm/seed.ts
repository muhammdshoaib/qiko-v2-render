import type { CrmState } from "./types";
import { EMPTY_CHANNEL_RUNS } from "./channels";
import { EMPTY_RUNS } from "./workflows";

export const OWNERS = ["Maya Chen", "James Whitaker", "Sara Okonkwo"] as const;

export const SEED: CrmState = {
  companies: [
    { id: "albemarle", name: "Albemarle", sector: "Investment office", location: "London", owner: "Maya Chen", website: "albemarle.example", summary: "Family office reviewing a governed intelligence layer for existing investor and admin workflows. Sample lead for the walkthrough." },
    { id: "northbridge", name: "Northbridge Capital", sector: "Private credit", location: "Manchester", owner: "James Whitaker", website: "northbridge.example", summary: "Credit team evaluating worker coverage for origination follow-up." },
    { id: "harrow", name: "Harrow Street Partners", sector: "Property advisory", location: "Edinburgh", owner: "Sara Okonkwo", website: "harrowstreet.example", summary: "Advisory firm comparing Qiko to a generic CRM chatbot." },
    { id: "lumen", name: "Lumen Court Residences", sector: "Developer", location: "Birmingham", owner: "Maya Chen", website: "lumencourt.example", summary: "Developer ops lead who wants commercial visibility without a new finance stack." },
    { id: "oakridge", name: "Oakridge Advisory", sector: "Wealth", location: "Leeds", owner: "James Whitaker", website: "oakridge.example", summary: "Early inbound from a webinar. Not yet qualified." },
    { id: "pinnacle", name: "Pinnacle Estates Group", sector: "Asset manager", location: "London", owner: "Sara Okonkwo", website: "pinnacle.example", summary: "Live customer on an annual platform commitment." },
    { id: "westferry", name: "Westferry Holdings", sector: "Holdco", location: "Canary Wharf", owner: "Maya Chen", website: "westferry.example", summary: "Introduced last month. Conversation stalled after first call." },
  ],
  contacts: [
    { id: "c1", companyId: "albemarle", name: "Helena Ward", role: "Operating partner", email: "helena.ward@albemarle.example", phone: "+44 20 7946 0101" },
    { id: "c2", companyId: "albemarle", name: "Tom Ellis", role: "Head of technology", email: "tom.ellis@albemarle.example", phone: "+44 20 7946 0102" },
    { id: "c3", companyId: "northbridge", name: "Priya Shah", role: "Origination lead", email: "priya.shah@northbridge.example", phone: "+44 161 496 0200" },
    { id: "c4", companyId: "harrow", name: "Callum Reid", role: "Managing partner", email: "callum.reid@harrowstreet.example", phone: "+44 131 496 0300" },
    { id: "c5", companyId: "lumen", name: "Nadia Brooks", role: "Commercial director", email: "nadia.brooks@lumencourt.example", phone: "+44 121 496 0400" },
    { id: "c6", companyId: "oakridge", name: "Owen Blake", role: "Analyst", email: "owen.blake@oakridge.example", phone: "+44 113 496 0500" },
    { id: "c7", companyId: "pinnacle", name: "Ruth Adeyemi", role: "COO", email: "ruth.adeyemi@pinnacle.example", phone: "+44 20 7946 0600" },
    { id: "c8", companyId: "westferry", name: "Daniel Cho", role: "Chief of staff", email: "daniel.cho@westferry.example", phone: "+44 20 7946 0700" },
  ],
  opportunities: [
    { id: "o-alb", companyId: "albemarle", title: "Intelligence layer pilot", value: 180000, expectedRevenue: 144000, estimatedCost: 42000, owner: "Maya Chen", stage: "in_discussion", nextStep: "Send draft proposal", lastActivityAt: daysAgo(8), createdAt: daysAgo(21) },
    { id: "o-nb", companyId: "northbridge", title: "Origination workers", value: 96000, expectedRevenue: 72000, owner: "James Whitaker", stage: "proposal_sent", nextStep: "Walk through proposal appendix", lastActivityAt: daysAgo(3), createdAt: daysAgo(18) },
    { id: "o-hs", companyId: "harrow", title: "Advisory workspace", value: 72000, expectedRevenue: 54000, owner: "Sara Okonkwo", stage: "negotiation", nextStep: "Confirm commercial terms", lastActivityAt: daysAgo(2), createdAt: daysAgo(30) },
    { id: "o-lc", companyId: "lumen", title: "Ops visibility pack", value: 54000, expectedRevenue: 54000, owner: "Maya Chen", stage: "confirmed", nextStep: "Kickoff scheduling", lastActivityAt: daysAgo(1), createdAt: daysAgo(40) },
    { id: "o-or", companyId: "oakridge", title: "Webinar inbound", value: 36000, expectedRevenue: 18000, owner: "James Whitaker", stage: "cold_lead", nextStep: "Qualify budget and timeline", lastActivityAt: daysAgo(5), createdAt: daysAgo(5) },
    { id: "o-pe", companyId: "pinnacle", title: "Annual platform", value: 120000, expectedRevenue: 120000, owner: "Sara Okonkwo", stage: "charged", nextStep: "Quarterly review", lastActivityAt: daysAgo(4), createdAt: daysAgo(200) },
    { id: "o-wf", companyId: "westferry", title: "Holdco introduction", value: 84000, expectedRevenue: 42000, owner: "Maya Chen", stage: "contacted", nextStep: "Book second conversation", lastActivityAt: daysAgo(12), createdAt: daysAgo(16) },
  ],
  invoices: [
    { id: "i1", companyId: "pinnacle", opportunityId: "o-pe", number: "QIK-1042", amount: 30000, paidAmount: 30000, status: "paid", dueDate: daysAgo(-20), issuedAt: daysAgo(40) },
    { id: "i2", companyId: "pinnacle", opportunityId: "o-pe", number: "QIK-1088", amount: 30000, paidAmount: 10000, status: "partial", dueDate: daysAgo(-10), issuedAt: daysAgo(12) },
    { id: "i3", companyId: "lumen", opportunityId: "o-lc", number: "QIK-1101", amount: 18000, paidAmount: 0, status: "unpaid", dueDate: daysAgo(-3), issuedAt: daysAgo(6) },
    { id: "i4", companyId: "harrow", opportunityId: "o-hs", number: "QIK-1094", amount: 12000, paidAmount: 0, status: "overdue", dueDate: daysAgo(6), issuedAt: daysAgo(20) },
    { id: "i5", companyId: "northbridge", opportunityId: "o-nb", number: "QIK-1110", amount: 8000, paidAmount: 0, status: "unpaid", dueDate: daysAgo(-14), issuedAt: daysAgo(2) },
  ],
  commitments: [
    { id: "cm1", companyId: "pinnacle", title: "Platform subscription", cadence: "Quarterly", amount: 30000, nextDate: daysAgo(-45) },
    { id: "cm2", companyId: "lumen", title: "Pilot retainer", cadence: "Monthly", amount: 6000, nextDate: daysAgo(-12) },
    { id: "cm3", companyId: "harrow", title: "Implementation support", cadence: "One-off then monthly", amount: 4000, nextDate: daysAgo(-8) },
  ],
  tasks: [
    { id: "t3", companyId: "northbridge", opportunityId: "o-nb", title: "Review proposal appendix with Priya", owner: "James Whitaker", dueDate: daysAgo(-2), priority: "normal", status: "open", source: "manual" },
    { id: "t4", companyId: "harrow", opportunityId: "o-hs", title: "Notify owner of overdue invoice QIK-1094", owner: "Sara Okonkwo", dueDate: daysAgo(-1), priority: "high", status: "open", source: "agent", suggestedAction: "Invoice overdue. Notify account owner?" },
    { id: "t5", companyId: "lumen", opportunityId: "o-lc", title: "Schedule kickoff", owner: "Maya Chen", dueDate: daysAgo(-4), priority: "normal", status: "open", source: "manual" },
    { id: "t6", companyId: "pinnacle", opportunityId: "o-pe", title: "Prepare quarterly review notes", owner: "Sara Okonkwo", dueDate: daysAgo(-10), priority: "low", status: "done", source: "manual" },
    { id: "t7", companyId: "oakridge", opportunityId: "o-or", title: "Qualify webinar inbound", owner: "James Whitaker", dueDate: daysAgo(-3), priority: "normal", status: "open", source: "manual" },
  ],
  activities: [
    { id: "a1", companyId: "albemarle", opportunityId: "o-alb", at: daysAgo(8), kind: "human", title: "Working session", detail: "Helena asked how Intent Monitor stays off the investor app. Tom wants a written boundary." },
    { id: "a2", companyId: "albemarle", opportunityId: "o-alb", at: daysAgo(8), kind: "agent", title: "Suggestion logged", detail: "No meaningful activity for 8 days. Follow-up suggested." },
    { id: "a3", companyId: "harrow", opportunityId: "o-hs", at: daysAgo(2), kind: "human", title: "Commercial call", detail: "Callum said the proposal is directionally accepted, pending payment terms." },
    { id: "a4", companyId: "harrow", opportunityId: "o-hs", at: daysAgo(2), kind: "agent", title: "Stage review suggested", detail: "Meeting notes indicate proposal acceptance. Review stage update." },
    { id: "a5", companyId: "lumen", opportunityId: "o-lc", at: daysAgo(1), kind: "system", title: "Invoice issued", detail: "QIK-1101 issued. Due in 3 days at time of issue." },
    { id: "a6", companyId: "westferry", opportunityId: "o-wf", at: daysAgo(12), kind: "human", title: "Intro call", detail: "Daniel asked for a second conversation after internal review. None booked." },
    { id: "a7", companyId: "pinnacle", opportunityId: "o-pe", at: daysAgo(4), kind: "agent", title: "Follow-up email", detail: "Follow-up email approved and sent. Prototype only — no mail was delivered." },
    { id: "a8", companyId: "northbridge", opportunityId: "o-nb", at: daysAgo(3), kind: "human", title: "Proposal sent", detail: "Appendix covering origination workers shared with Priya." },
  ],
  suggestions: [
    { id: "s1", companyId: "albemarle", opportunityId: "o-alb", message: "No meaningful activity for 8 days. Follow-up suggested.", actionLabel: "Create follow-up task", action: "follow_up", applied: false },
    { id: "s2", companyId: "harrow", opportunityId: "o-hs", message: "Meeting notes indicate proposal acceptance. Review stage update.", actionLabel: "Move to Confirmed", action: "stage_review", applied: false },
    { id: "s3", companyId: "lumen", opportunityId: "o-lc", message: "Invoice due in 3 days. Notify account owner?", actionLabel: "Notify owner (mock)", action: "invoice_nudge", applied: false },
    { id: "s4", companyId: "pinnacle", opportunityId: "o-pe", message: "Follow-up email approved and sent.", actionLabel: "View activity", action: "email_sent", applied: true },
  ],
  workflowEvents: [],
  workflowRuns: EMPTY_RUNS,
  channelRuns: EMPTY_CHANNEL_RUNS,
  channelMessages: [],
  emailDraft: null,
};

function daysAgo(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() - days);
  date.setHours(9, 30, 0, 0);
  return date.toISOString();
}
