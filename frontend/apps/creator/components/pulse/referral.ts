import type { ReferralStatus } from "@/lib/brain/referral-store";

export const REFERRAL_ID = "o-referral";
export const REFERRAL_EVIDENCE_ID = "c-referral";

export const REFERRAL = {
  id: REFERRAL_ID,
  title: "Referral programme recommendation",
  insight: "In the labelled sample, investors who arrived via an existing investor reached a human review more often than portal-only views.",
  why: [
    "14 labelled past referrals in the sample pack.",
    "9 of those 14 reached a person. Portal-only sessions in the same pack did so about 3 times in 10.",
    "The Intelligence Worker clustered this from existing intent-signal paths. It did not email anyone.",
  ],
  caution: "These counts are a defined sample. They are not a live conversion rate, and they are not a revenue forecast.",
  action: "Write a recommendation to company intelligence: thank repeat investors who refer, then a person decides any outreach.",
  expectedOutput: [
    "A one-page brief: why referrals in the sample reached review more often.",
    "A suggested thank-you amount (£1,000) is Ed’s illustrative figure — not a predicted return.",
    "Hard wall: Pulse will not send WhatsApp or email, and will not create a CRM deal.",
  ],
  uses: 2,
  minutes: 25,
  usesLabel: "Times this insight was reused to brief someone",
  minutesLabel: "Minutes saved per briefing",
  measurement: "If this were production, you would compare next month’s referred sessions that reach review against this sample. This prototype does not measure that.",
  estimatedNote: "Estimated benefit uses labelled assumptions (2 briefings × 25 minutes × an hourly rate). It is not a recorded result.",
  captured: {
    approved: [
      "Human decision: approved.",
      "Pattern captured: referred arrivals in the sample reached review more often than portal-only views.",
      "Recommended thank-you brief written to company intelligence.",
    ],
    rejected: [
      "Human decision: declined.",
      "Insight retained on Investors.",
      "The thank-you brief was not written.",
    ],
  },
  futureUse: {
    approved: "A later briefing could reuse this recorded pattern. That reuse is described here — the worker does not update itself automatically.",
    rejected: "Later recommendations should not treat a thank-you programme as agreed. That constraint is now on the record — it is not an automatic model update.",
  },
  recordedResult: {
    pending: "No result has been recorded yet. The estimated benefit is an assumption, not an outcome.",
    approved: "Recorded: the recommendation was written to company intelligence. No outreach was sent. No conversion or revenue was recorded.",
    rejected: "Recorded: the recommendation was declined. Nothing was written. No conversion or revenue was recorded.",
  },
};

export function referralHours(uses = REFERRAL.uses, minutes = REFERRAL.minutes) {
  return (uses * minutes) / 60;
}

export function referralValue(rate: number, uses = REFERRAL.uses, minutes = REFERRAL.minutes) {
  return Math.round(referralHours(uses, minutes) * rate);
}

export function statusLabel(status: ReferralStatus) {
  if (status === "approved") return "On the record";
  if (status === "rejected") return "Declined";
  if (status === "exploring") return "Exploring";
  return "Awaiting a decision";
}

export function statusTone(status: ReferralStatus): "good" | "warn" | "blue" | "bad" | "" {
  if (status === "approved") return "good";
  if (status === "rejected") return "bad";
  if (status === "exploring") return "blue";
  return "warn";
}

export function decisionLabel(status: ReferralStatus) {
  if (status === "approved") return "Approved. The recommendation was written to company intelligence.";
  if (status === "rejected") return "Declined. The insight stays; the action was not written.";
  if (status === "exploring") return "Not decided yet. You are reviewing the labelled walkthrough.";
  return "Not decided yet.";
}

export function conversationStage(status: ReferralStatus) {
  if (status === "approved") return { stage: "On the record", tone: "good" as const };
  if (status === "rejected") return { stage: "Declined", tone: "bad" as const };
  if (status === "exploring") return { stage: "Exploring", tone: "blue" as const };
  return { stage: "Insight ready", tone: "warn" as const };
}

export function destinationLabel(status: ReferralStatus) {
  if (status === "approved") return "Investors block · Company intelligence · Pulse activity";
  if (status === "rejected") return "Insight stays on Investors. The action was not written.";
  return "Not written yet.";
}

export const CLAUDE_STEPS = [
  {
    id: 0 as const,
    title: "Open the insight",
    prompt: "What did the Intelligence Worker notice about referrals?",
    reply: REFERRAL.insight,
  },
  {
    id: 1 as const,
    title: "Ask for context",
    prompt: "Why is this recommended? Show the supporting sample.",
    reply: `${REFERRAL.why.join(" ")} ${REFERRAL.caution}`,
  },
  {
    id: 2 as const,
    title: "Explore the action",
    prompt: "What should we do with this?",
    reply: REFERRAL.action,
  },
  {
    id: 3 as const,
    title: "Review the expected output",
    prompt: "Show me what would be written if I approve.",
    reply: REFERRAL.expectedOutput.join(" "),
  },
  {
    id: 4 as const,
    title: "Confirm the action",
    prompt: "Write this to company intelligence if I approve. Do not contact an investor.",
    reply: "Approval writes the recommendation to the shared record. Rejection leaves the insight in place and writes nothing. Neither choice sends outreach.",
  },
];
