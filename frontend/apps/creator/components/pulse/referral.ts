import type { ReferralStatus } from "@/lib/brain/referral-store";

export const REFERRAL_ID = "o-referral";
export const REFERRAL_EVIDENCE_ID = "c-referral";

export const REFERRAL = {
  id: REFERRAL_ID,
  title: "Referral reachout recommendation",
  insight: "An investor viewed Lombe House repeatedly. The Intelligence Worker flagged that as interest. From that intelligence, Qiko recommends a referral reachout.",
  why: [
    "Labelled sample of investor-app activity: the same person opened Lombe House several times.",
    "That pattern is an intent signal for Joseph Mews admin — not a message to the investor.",
    "The Intelligence Worker clustered the activity. It did not email, WhatsApp, or create a CRM deal.",
  ],
  caution: "This is a labelled sample of the intent-signal worker, not the live admin feed, and not a conversion or revenue forecast.",
  action: "Write a recommendation to company intelligence: a person should decide on a referral reachout for this Lombe House intent.",
  expectedOutput: [
    "A short brief: this investor is showing intent on Lombe House, so a referral reachout is the suggested next action.",
    "The brief is for a person. Pulse does not send the reachout.",
    "Hard wall: Pulse will not send WhatsApp or email, and will not create a CRM deal.",
  ],
  uses: 2,
  minutes: 25,
  usesLabel: "Times this insight was reused to brief someone",
  minutesLabel: "Minutes saved per briefing",
  measurement: "If this were production, you would check whether a person completed the Lombe House referral reachout. This prototype does not measure that.",
  estimatedNote: "Estimated benefit uses labelled assumptions (2 briefings × 25 minutes × an hourly rate). It is not a recorded result.",
  captured: {
    approved: [
      "Human decision: approved.",
      "Pattern captured: repeat views on Lombe House were treated as intent, and a referral reachout was the recommended action.",
      "Recommended reachout brief written to company intelligence.",
    ],
    rejected: [
      "Human decision: declined.",
      "The Lombe House intent stays visible on Investors.",
      "The referral reachout brief was not written.",
    ],
  },
  futureUse: {
    approved: "A later briefing could reuse this recorded Lombe House intent. That reuse is described here — the worker does not update itself automatically.",
    rejected: "Later recommendations should not treat a Lombe House referral reachout as agreed. That constraint is now on the record — it is not an automatic model update.",
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

export function isDecided(status: ReferralStatus) {
  return status === "approved" || status === "rejected";
}

export function statusLabel(status: ReferralStatus) {
  if (status === "approved") return "On the record";
  if (status === "rejected") return "Declined";
  if (status === "exploring") return "Exploring";
  if (status === "deferred") return "Deferred";
  return "Awaiting a decision";
}

export function statusTone(status: ReferralStatus): "good" | "warn" | "blue" | "bad" | "" {
  if (status === "approved") return "good";
  if (status === "rejected") return "bad";
  if (status === "exploring" || status === "deferred") return "blue";
  return "warn";
}

export function decisionLabel(status: ReferralStatus) {
  if (status === "approved") return "Approved. The recommendation was written to company intelligence.";
  if (status === "rejected") return "Declined. The insight stays; the action was not written.";
  if (status === "exploring") return "Not decided yet. You are reviewing the labelled walkthrough.";
  if (status === "deferred") return "Deferred. The recommendation stays open. Nothing was written.";
  return "Not decided yet.";
}

export function conversationStage(status: ReferralStatus) {
  if (status === "approved") return { stage: "On the record", tone: "good" as const };
  if (status === "rejected") return { stage: "Declined", tone: "bad" as const };
  if (status === "exploring") return { stage: "Exploring", tone: "blue" as const };
  if (status === "deferred") return { stage: "Deferred", tone: "blue" as const };
  return { stage: "Insight ready", tone: "warn" as const };
}

export function destinationLabel(status: ReferralStatus) {
  if (status === "approved") return "Investors block · Company intelligence · Pulse activity";
  if (status === "rejected") return "Insight stays on Investors. The action was not written.";
  if (status === "deferred") return "Not written yet. Deferred for a later decision.";
  return "Not written yet.";
}

export const CLAUDE_STEPS = [
  {
    id: 0 as const,
    title: "Open the insight",
    prompt: "What did the Intelligence Worker notice about Lombe House?",
    reply: REFERRAL.insight,
  },
  {
    id: 1 as const,
    title: "Ask for context",
    prompt: "Why is a referral reachout recommended from that?",
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
    reply: "Approval writes the recommendation to the shared record. Rejection leaves the Lombe House intent in place and writes nothing. Neither choice sends outreach.",
  },
];
