import assert from "node:assert/strict";
import test from "node:test";

import { buildOnboardingWorkerDraft } from "../lib/onboarding-worker";


test("wizard data maps to one canonical signup and agent config draft", () => {
  const input = {
    fullName: "  Atlas Advisor  ",
    professionalTitle: "  Senior Wealth Strategist  ",
    location: "  London, UK  ",
    headline: "  I help families make clear long-term investment decisions.  ",
    tone: "professional",
    industry: "wealth_management",
    categories: ["Portfolio strategy", "Risk analysis"],
    additionalGuidance: "Explain trade-offs before making a recommendation.",
    professionalBackground: "  Fifteen years advising private clients.  ",
    credentials: "  CFA charterholder  ",
    achievements: "  Built an award-winning advisory practice.  ",
    commonMistakes: "Avoid chasing short-term performance.",
    frameworks: "Use goals, time horizon, liquidity, and risk tolerance.",
    stakeholderBalance: "Balance the needs of founders and beneficiaries.",
    boundaries: "Never promise returns or replace regulated advice.",
    commonTasks: "Compare allocations and explain portfolio risk.",
    exampleQA: "Q: How do you assess risk? A: Start with goals and capacity. " + "x".repeat(5_000),
  };
  const draft = buildOnboardingWorkerDraft(input);
  const signup = draft.signup as typeof draft.signup & { knowledge?: string };
  const { knowledge, ...signupProfile } = signup;
  const about = [
    "Fifteen years advising private clients.",
    "CFA charterholder",
    "Built an award-winning advisory practice.",
  ].join("\n\n");

  assert.deepEqual(signupProfile, {
    name: "Atlas Advisor",
    title: "Senior Wealth Strategist",
    location: "London, UK",
    about,
    tone: "professional",
    industry: "wealth_management",
    expertise: "Portfolio strategy, Risk analysis",
    main_goal: "I help families make clear long-term investment decisions.",
  });
  assert.deepEqual(draft.config, {
    full_name: "Atlas Advisor",
    title: "Senior Wealth Strategist",
    location: "London, UK",
    about,
    tone: "professional",
    industry: "wealth_management",
    expertise: "Portfolio strategy, Risk analysis",
    main_goal: "I help families make clear long-term investment decisions.",
  });
  assert.equal(signup.main_goal, "I help families make clear long-term investment decisions.");
  assert.ok(typeof knowledge === "string" && knowledge.length > 0);
  assert.ok(knowledge.length <= 4_000, `knowledge exceeded signup boundary: ${knowledge.length}`);
  for (const representativeValue of [
    "Explain trade-offs before making a recommendation.",
    "Avoid chasing short-term performance.",
    "Use goals, time horizon, liquidity, and risk tolerance.",
    "Balance the needs of founders and beneficiaries.",
    "Never promise returns or replace regulated advice.",
    "Compare allocations and explain portfolio risk.",
    "Q: How do you assess risk? A: Start with goals and capacity.",
  ]) {
    assert.ok(knowledge.includes(representativeValue), `knowledge omitted: ${representativeValue}`);
  }
});
