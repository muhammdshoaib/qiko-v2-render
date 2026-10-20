"use client";

import { InvestorsAnalytics } from "./investors-analytics";
import { PORTFOLIO_ANALYTICS_BUBBLES } from "./portfolio-reporter-data";

const PORTFOLIO_BUBBLE_POS: Record<string, { x: number; y: number }> = {
  concentration: { x: 46, y: 46 },
  regional: { x: 22, y: 28 },
  income: { x: 74, y: 30 },
  pipeline: { x: 70, y: 68 },
  "empty-gap": { x: 20, y: 66 },
};

export function PortfolioReporterAnalytics({ agentId }: { agentId?: string }) {
  return (
    <InvestorsAnalytics
      agentId={agentId}
      bubbles={PORTFOLIO_ANALYTICS_BUBBLES}
      bubblePositions={PORTFOLIO_BUBBLE_POS}
      hubId="concentration"
      skipLinkIds={["empty-gap"]}
      kicker="Knowledge block · Portfolio Reporter · Analytics"
      title="What Portfolio Reporter knows"
      description="Every bubble is something the block has learned. Size shows how often it is used. Click one to see the evidence."
      mapSubtitle={`Portfolio Reporter · ${PORTFOLIO_ANALYTICS_BUBBLES.length} patterns · click a bubble`}
    />
  );
}
