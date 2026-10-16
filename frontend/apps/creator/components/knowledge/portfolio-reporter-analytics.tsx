"use client";

import type { HonestyKind } from "@/components/intelligence-layer/model";
import { InvestorsAnalytics } from "./investors-analytics";
import { PORTFOLIO_ANALYTICS_BUBBLES } from "./portfolio-reporter-data";

const PORTFOLIO_BUBBLE_POS: Record<string, { x: number; y: number }> = {
  concentration: { x: 28, y: 36 },
  regional: { x: 58, y: 28 },
  income: { x: 78, y: 48 },
  pipeline: { x: 48, y: 62 },
  "empty-gap": { x: 22, y: 68 },
};

const PORTFOLIO_BUSINESS_KPIS: { label: string; value: string; hint: string; honesty: HonestyKind }[] = [
  { label: "Portfolios with insights", value: "3,104", hint: "Cards written from holdings", honesty: "illustrative" },
  { label: "Concentration cards", value: "412", hint: "3+ holdings in one city", honesty: "illustrative" },
  { label: "Holdings read", value: "2,140", hint: "Input only — not JM stock", honesty: "illustrative" },
  { label: "Awaiting person", value: "41", hint: "Pipeline cards · human decision", honesty: "illustrative" },
];

export function PortfolioReporterAnalytics({ agentId }: { agentId?: string }) {
  return (
    <InvestorsAnalytics
      agentId={agentId}
      bubbles={PORTFOLIO_ANALYTICS_BUBBLES}
      bubblePositions={PORTFOLIO_BUBBLE_POS}
      hubId="concentration"
      skipLinkIds={["empty-gap"]}
      kicker="Portfolio Reporter · Analytics"
      title="What Portfolio Reporter knows"
      description="Commercial portfolio measures and evidence-backed insight cards. Every figure is Live, Pending integration, or Illustrative."
      businessKpis={PORTFOLIO_BUSINESS_KPIS}
    />
  );
}
