import { BLOCKS } from "./drilldown-data";
import type { PulseNav } from "./route";

const WALL =
  "Nothing is sent outbound. WhatsApp, email, and CRM stay blocked. A person decides.";
const SAMPLE = "Labelled sample — not a live model, and not live Claude.";

function has(q: string, ...needles: string[]) {
  return needles.some((needle) => q.includes(needle));
}

export function parseBrainNav(question: string): Partial<PulseNav> | null {
  const q = question.trim().toLowerCase();
  if (!/^(open|show|go to|take me to)\b/.test(q)) return null;
  if (has(q, "property insights")) {
    return { block: "properties", worker: "property-insights", pane: "conversations", detail: null, focus: null };
  }
  if (has(q, "intelligence worker", "intent")) {
    return { block: "investors", worker: "intent-intelligence", pane: "conversations", detail: null, focus: null };
  }
  if (has(q, "properties", "portfolio")) {
    return { block: "properties", worker: null, pane: "overview", detail: null, focus: null };
  }
  if (has(q, "investor")) {
    return { block: "investors", worker: null, pane: "overview", detail: null, focus: null };
  }
  if (has(q, "pulse", "company intelligence", "home")) {
    return { block: null, worker: null, detail: null, focus: "record", sheet: null };
  }
  return null;
}

function composeReply(question: string, nav: Partial<PulseNav> | null): string {
  const q = question.trim().toLowerCase();

  if (nav) {
    if (nav.worker === "property-insights") {
      return `Opening **Property Insights**.\n\n${BLOCKS.properties.summary}\n\n${WALL}\n\n_${SAMPLE}_`;
    }
    if (nav.worker === "intent-intelligence") {
      return `Opening the **Intelligence Worker** on Investors.\n\n${BLOCKS.investors.summary}\n\n${WALL}\n\n_${SAMPLE}_`;
    }
    if (nav.block === "properties") {
      return `Opening **Properties**.\n\n${BLOCKS.properties.summary}\n\n${WALL}\n\n_${SAMPLE}_`;
    }
    if (nav.block === "investors") {
      return `Opening **Investors**.\n\n${BLOCKS.investors.summary}\n\n${WALL}\n\n_${SAMPLE}_`;
    }
    return `Back on **Pulse** — company intelligence.\n\n${WALL}\n\n_${SAMPLE}_`;
  }

  if (has(q, "whatsapp", "email", "sms") || (has(q, "send", "outreach", "contact", "message") && has(q, "investor", "client", "crm", "whatsapp", "email"))) {
    return [
      "**Hard wall.** Pulse recommends only.",
      WALL,
      "The Intelligence Worker can flag intent (Lombe House is the worked example). A person still writes any reachout. Property Insights writes cards into each investor’s app — it does not message them, and it does not give buy/sell advice.",
      `_${SAMPLE}_`,
    ].join("\n\n");
  }

  if (has(q, "crm")) {
    return [
      "**Client CRM is not connected.**",
      "A hand-off would stay a planned next step. This prototype does not create CRM records or deals.",
      WALL,
      `_${SAMPLE}_`,
    ].join("\n\n");
  }

  if (has(q, "lombe", "lombay", "derby", "referral", "high-intent", "high intent")) {
    return [
      "**Lombe House** is the worked example on Investors.",
      "28 high-intent investors in the labelled sample. Repeat views flagged interest. From that intelligence, a **referral reachout** is recommended — awaiting a person. Nothing was sent.",
      "8 other recommended reachouts are already on the record this quarter. Pulse sent none of them.",
      WALL,
      `_${SAMPLE}_`,
    ].join("\n\n");
  }

  if (has(q, "quiet", "7-day", "7 day", "gap")) {
    return [
      "**Quiet developments** sit on Investors.",
      "Two listings had no new investor-app views in 7 days. Written to the activity feed. No investor email was sent.",
      "Absence of attention is also knowledge. It is not a chase list.",
      WALL,
      `_${SAMPLE}_`,
    ].join("\n\n");
  }

  if (has(q, "concentration", "diverse", "diversif", "london")) {
    return [
      "**412 concentration cards** this month.",
      "Joseph Mews advises these investors. Property Insights read each client’s portfolio. 412 received a concentration card: three or more holdings in one city. London is the largest cluster.",
      "Example in the app: “You have 3 properties in London; this portfolio is not diverse.” That is a grounded note — not advice to buy or sell.",
      WALL,
      `_${SAMPLE}_`,
    ].join("\n\n");
  }

  if (has(q, "holding", "stock", "portfolio", "propert", "insight", "3,104", "3104", "2,140", "2140")) {
    return [
      "**Properties is not Joseph Mews stock.**",
      BLOCKS.properties.summary,
      "- **4,180** advised investors (illustrative)",
      "- **3,104** portfolios with enough holdings to ground at least one card this month",
      "- **2,140** client holdings read",
      "- **412** concentration cards",
      "Empty portfolios get no invented card. Contacting a client stays blocked.",
      WALL,
      `_${SAMPLE}_`,
    ].join("\n\n");
  }

  if (has(q, "worker", "intent", "reachout", "intelligence worker")) {
    return [
      "Two workers sit on Pulse.",
      "**Intelligence Worker** — intent signals and reachouts on the Investors block. It can recommend. It cannot send.",
      "**Property Insights** — reads each advised investor’s portfolio and writes grounded cards into their app. Counts sit on Properties.",
      WALL,
      `_${SAMPLE}_`,
    ].join("\n\n");
  }

  if (has(q, "investor", "4,180", "4180", "4,000", "4000", "register")) {
    return [
      `**Investors.** ${BLOCKS.investors.summary}`,
      "28 high-intent in the labelled sample. Lombe House is the worked example. 8 reachouts already on the record this quarter; 1 still needs a person.",
      WALL,
      `_${SAMPLE}_`,
    ].join("\n\n");
  }

  if (has(q, "pulse", "company brain", "company intelligence", "what do you know", "help")) {
    return [
      "I answer from **labelled Pulse knowledge** — Investors, Properties, the two workers, and what is already on the record.",
      "Ask about Lombe House intent, reachouts, portfolio insights, or concentration cards. Say *open Investors* or *open Properties* to jump there.",
      WALL,
      `_${SAMPLE}_`,
    ].join("\n\n");
  }

  return [
    "I only answer from **labelled Pulse knowledge** — not a live model.",
    "Try **Investors**, **Properties**, **Lombe House**, **concentration cards**, or **quiet listings**. Say *open Investors* to jump to a block.",
    WALL,
    `_${SAMPLE}_`,
  ].join("\n\n");
}

export async function askCompanyBrain(
  question: string,
  onNav?: (next: Partial<PulseNav>) => void,
): Promise<string> {
  await new Promise((resolve) => setTimeout(resolve, 420));
  const nav = parseBrainNav(question);
  if (nav && onNav) onNav(nav);
  return composeReply(question, nav);
}
