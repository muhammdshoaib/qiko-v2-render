export type LiveCapture = {
  block: "investor-app" | "properties";
  initials: string;
  worker: string;
  text: string;
};

export const LIVE_CAPTURES: LiveCapture[] = [
  { block: "investor-app", initials: "IW", worker: "Intelligence Worker", text: "Lombe House / Derby repeat views flagged as intent" },
  { block: "properties", initials: "PI", worker: "Property Insights", text: "412 concentration cards written across advised investors" },
  { block: "investor-app", initials: "IW", worker: "Intelligence Worker", text: "Quiet listings recorded — two developments, no new intent in 7 days" },
  { block: "properties", initials: "PI", worker: "Property Insights", text: "3,104 advised portfolios received a grounded insight card" },
  { block: "investor-app", initials: "IW", worker: "Intelligence Worker", text: "Referral reachout recommended from Lombe House intent" },
  { block: "properties", initials: "PI", worker: "Property Insights", text: "2,140 client holdings read — not Joseph Mews stock" },
  { block: "investor-app", initials: "IW", worker: "Intelligence Worker", text: "Intent signal captured from investor-app views. No email sent." },
  { block: "properties", initials: "PI", worker: "Property Insights", text: "Empty portfolios skipped — no invented cards" },
];
