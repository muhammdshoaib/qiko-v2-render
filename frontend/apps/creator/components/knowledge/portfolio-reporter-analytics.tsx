"use client";

import { InvestorsAnalytics } from "./investors-analytics";
import { PORTFOLIO_ANALYTICS_BUBBLES } from "./portfolio-reporter-data";

const PORTFOLIO_BUBBLE_POS: Record<string, { x: number; y: number }> = {
  concentration: { x: 28, y: 36 },
  regional: { x: 58, y: 28 },
  income: { x: 78, y: 48 },
  pipeline: { x: 48, y: 62 },
  "empty-gap": { x: 22, y: 68 },
};

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
      description="Insight card patterns from holdings — concentration, regional mix, income, and hard walls on empty portfolios."
      kpis={{
        strongestLift: "412",
        strongestHint: "Concentration cards written",
        evidenceSources: "4",
        evidenceHint: "Portfolios, app, finance inputs",
      }}
    />
  );
}
