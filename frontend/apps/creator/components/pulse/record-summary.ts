import type { FocusId, WorkerId } from "@/components/intelligence-layer/model";
import type { ApprovalStatus } from "@/lib/brain/store";
import type { ReferralStatus } from "@/lib/brain/referral-store";
import { BLOCKS, LEARNING_LABEL } from "./drilldown-data";

export type IntelAwaiting = {
  title: string;
  when: string;
  origin: FocusId;
};

export type GrowthCapture = {
  title: string;
  evidence: string;
};

export type GrowthPoint = {
  month: string;
  notes: number;
  awaiting?: boolean;
  captures: GrowthCapture[];
};

export function companyIntel(referral: ReferralStatus, _approval: ApprovalStatus) {
  const referralDecided = referral === "approved" || referral === "rejected";
  const investorOutcomes = BLOCKS.investors.outcomes.map((item) => {
    if (item.id === "o-referral") {
      if (referral === "approved") return { ...item, status: "recorded" as const };
      if (referral === "rejected") return { ...item, status: "held" as const };
    }
    return item;
  });
  const recorded = [
    ...investorOutcomes.filter((item) => item.status === "recorded"),
    ...BLOCKS.properties.outcomes.filter((item) => item.status === "recorded"),
  ];
  const awaiting = [
    ...investorOutcomes.filter((item) => item.status === "awaiting"),
    ...BLOCKS.properties.outcomes.filter((item) => item.status === "awaiting"),
  ];
  const learning = BLOCKS.investors.learnings[0];
  const learningState = referral === "approved" ? "rule" : referral === "rejected" ? "observed" : "proposed";
  const octNote = referral === "approved"
    ? "Reachout from Lombe House intent written. 3,104 portfolios received insights. 412 concentration cards."
    : referral === "rejected"
      ? "Reachout declined. Lombe House intent stays. 3,104 portfolios received insights. 412 concentration cards."
      : referral === "deferred"
        ? "Reachout deferred. 3,104 portfolios received insights. 412 concentration cards. Lombe House intent stays."
      : BLOCKS.investors.accumulation[3].note;

  const investorSignal = referral === "approved"
    ? "4,180 on the book. Lombe House reachout approved. 8 other reachouts already recorded."
    : referral === "rejected"
      ? "4,180 on the book. Lombe House reachout declined. 8 other reachouts stay recorded."
      : referral === "deferred"
        ? "4,180 on the book. Lombe House reachout deferred. 8 other reachouts stay recorded."
        : "4,180 on the book. 28 high-intent. 1 of 9 reachouts still needs a person (Lombe House).";

  const octCaptures: GrowthCapture[] = [
    { title: "3,104 portfolios received insights", evidence: "Property Insights read each advised investor’s holdings and wrote grounded cards into their app. Empty portfolios got no invented card." },
    { title: "2,140 client holdings read", evidence: "Properties those investors own. Input to insight generation — not Joseph Mews stock." },
    { title: "412 concentration cards", evidence: "Clients with 3+ holdings in one city. Example: “You have 3 properties in London; this portfolio is not diverse.”" },
    { title: "8 reachouts already on the record", evidence: "Recommended reachouts written after a person decided. Pulse sent none of them." },
    { title: "Lombe House intent captured", evidence: "Worked example from the 28 high-intent set. Labelled sample — not the live admin feed." },
  ];
  if (referral === "approved") {
    octCaptures.push({
      title: "Referral reachout recorded",
      evidence: "Approved. The recommendation was written to company intelligence. No outreach was sent.",
    });
  } else if (referral === "rejected") {
    octCaptures.push({
      title: "Referral reachout declined",
      evidence: "Declined. The Lombe House intent stays on Investors. The brief was not written.",
    });
  } else if (referral === "deferred") {
    octCaptures.push({
      title: "Decision deferred",
      evidence: "A person postponed the referral reachout. Nothing new was written to company intelligence.",
    });
  } else {
    octCaptures.push({
      title: "1 reachout awaiting a person",
      evidence: "The Lombe House referral reachout is not on the company record until someone approves or declines.",
    });
  }

  const growth: GrowthPoint[] = [
    {
      month: "Jul",
      notes: 3,
      captures: [
        { title: "Register described", evidence: "The labelled book of ~4,000 investors named. Not a live CRM count." },
        { title: "Client portfolios readable", evidence: "Advised investors’ holdings first readable by Property Insights." },
        { title: "Intent paths described", evidence: "Investor-app viewing paths named. No Lombe House pattern yet." },
      ],
    },
    {
      month: "Aug",
      notes: 5,
      captures: [
        { title: "First per-investor cards", evidence: "Property Insights wrote grounded cards into advised investors’ apps." },
        { title: "Grounded chat constrained", evidence: "Operator answers stay inside attached documents. Outbound contact stays blocked." },
        { title: "Pulse counts the pattern", evidence: "Insight generation writes in the app. Pulse shows how many clients received which insight type." },
      ],
    },
    {
      month: "Sep",
      notes: 7,
      captures: [
        { title: "Concentration across clients", evidence: "412 concentration cards counted as a pattern across advised investors, not one file." },
        { title: "First reachouts recorded", evidence: "A person decided. Pulse sent nothing." },
        { title: "Quiet listings recorded", evidence: "Absence of attention written to Investors." },
      ],
    },
    {
      month: "Oct",
      notes: referralDecided ? 12 : 11,
      awaiting: !referralDecided,
      captures: octCaptures,
    },
  ];
  const latestNotes = growth[growth.length - 1]?.notes ?? recorded.length;

  return {
    recordedCount: recorded.length,
    awaitingCount: awaiting.length,
    growthNotes: latestNotes,
    hubCaption: `${latestNotes} note${latestNotes === 1 ? "" : "s"}`,
    growth,
    blocks: [
      {
        id: "investor-app" as FocusId,
        name: "Investors",
        worker: "Intelligence Worker",
        workerId: "intent-intelligence" as WorkerId,
        signal: investorSignal,
      },
      {
        id: "properties" as FocusId,
        name: "Properties",
        worker: "Property Insights",
        workerId: "property-insights" as WorkerId,
        signal: "3,104 of 4,180 advised portfolios received insights. 412 concentration cards. 2,140 client holdings read.",
      },
    ],
    workers: [
      { id: "intent-intelligence" as WorkerId, name: "Intelligence Worker", writes: "Intent, attention, and reachouts across the register" },
      { id: "property-insights" as WorkerId, name: "Property Insights", writes: "Per-investor portfolio insights across advised clients" },
    ],
    timeline: [
      { month: "Jul", note: BLOCKS.investors.accumulation[0].note },
      { month: "Aug", note: BLOCKS.investors.accumulation[1].note },
      { month: "Sep", note: BLOCKS.investors.accumulation[2].note },
      { month: "Oct", note: octNote },
    ],
    latestLearning: {
      title: learning.title,
      evidence: learning.evidence,
      label: LEARNING_LABEL[learningState].label,
    },
    awaiting: awaiting.map((item): IntelAwaiting => ({
      title: item.title,
      when: item.when,
      origin: item.block === "investors" ? "investor-app" : "properties",
    })),
    recorded: recorded.map((item) => ({
      title: item.title,
      when: item.when,
      origin: item.block === "investors" ? "investor-app" as FocusId : "properties" as FocusId,
    })),
    sources: [
      { id: "knowledge" as FocusId, name: "Knowledge library", role: "Uploaded sources both workers may read" },
      { id: "chat" as FocusId, name: "Grounded chat", role: "Operator questions against attached documents" },
    ],
    hover: {
      record: `${latestNotes} notes on the company record — portfolio insights, concentration cards, intent, and reachouts. A count of what was written, not a score.${awaiting.length ? ` ${awaiting.length} still ${awaiting.length === 1 ? "needs" : "need"} a person.` : ""}`,
      "investor-app": `${investorSignal} Portfolio insights sit on Properties. Reachouts sit here.`,
      properties: "Joseph Mews advises these investors. Property Insights reads each client’s portfolio and writes their cards. 3,104 with insights. 412 concentration cards. Nobody is contacted.",
      "intent-intelligence": "Reads the investor book. Captures intent and recommends reachouts. Cannot contact an investor.",
      "property-insights": "Checks each advised investor’s portfolio, then writes grounded insight cards into their app. Cannot contact anyone, advise a trade, or move money.",
      knowledge: "Documents attached to the workers. Answers stay inside those files.",
      chat: "Operator questions against attached documents. Outbound contact stays blocked.",
    } as Record<FocusId, string>,
    referralDecided,
  };
}
