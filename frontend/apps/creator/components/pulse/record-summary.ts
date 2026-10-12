import type { FocusId, WorkerId } from "@/components/intelligence-layer/model";
import type { ApprovalStatus } from "@/lib/brain/store";
import type { ReferralStatus } from "@/lib/brain/referral-store";
import { BLOCKS, LEARNING_LABEL } from "./drilldown-data";

export type IntelAwaiting = {
  title: string;
  when: string;
  origin: FocusId;
};

export function companyIntel(referral: ReferralStatus, approval: ApprovalStatus) {
  const referralDecided = referral === "approved" || referral === "rejected";
  const investorOutcomes = BLOCKS.investors.outcomes.map((item) => {
    if (item.id === "o-referral") {
      if (referral === "approved") return { ...item, status: "recorded" as const };
      if (referral === "rejected") return { ...item, status: "held" as const };
    }
    if (item.id === "o-lombay") {
      if (approval === "approved") return { ...item, status: "recorded" as const };
      if (approval === "held") return { ...item, status: "held" as const };
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
    ? "Referral recommendation written to company intelligence."
    : referral === "rejected"
      ? "Referral recommendation declined. The insight stays on Investors."
      : BLOCKS.investors.accumulation[3].note;

  const investorSignal = referral === "approved"
    ? "Referral decision is on the record."
    : referral === "rejected"
      ? "Referral declined; the insight was kept."
      : "Referral recommendation awaiting a person.";

  return {
    recordedCount: recorded.length,
    awaitingCount: awaiting.length,
    hubCaption: `${recorded.length} recorded note${recorded.length === 1 ? "" : "s"}`,
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
        signal: "Expenditure drift noted. Payments stay blocked.",
      },
    ],
    workers: [
      { id: "intent-intelligence" as WorkerId, name: "Intelligence Worker", writes: "Investor attention and research" },
      { id: "property-insights" as WorkerId, name: "Property Insights", writes: "Income, spend, and risk notes" },
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
      record: `${recorded.length} recorded notes across Investors and Properties${awaiting.length ? `. ${awaiting.length} still ${awaiting.length === 1 ? "needs" : "need"} a person.` : "."}`,
      "investor-app": `${investorSignal} ${BLOCKS.investors.segments[0].signal}`,
      properties: `${BLOCKS.properties.segments[0].signal} Payments stay blocked.`,
      "intent-intelligence": "Clusters investor attention and answers from the knowledge library. Cannot contact an investor.",
      "property-insights": "Summarises income, spend, and risk from the finance cockpit. Cannot move money.",
      knowledge: "Documents attached to the workers. Answers stay inside those files.",
      chat: "Operator questions against attached documents. Outbound contact stays blocked.",
    } as Record<FocusId, string>,
    referralDecided,
  };
}
