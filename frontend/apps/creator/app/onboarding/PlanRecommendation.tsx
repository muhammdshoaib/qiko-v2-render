"use client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ArrowLeft, Brain, Check, CreditCard, Loader2 } from "lucide-react";
import type { SubscriptionPlan } from "@/lib/avatarApi";

type SubscriptionType = "gpt_wrapper" | "custom_model" | "premium";

interface Recommendation {
  type: SubscriptionType;
  reasons: string[];
  confidence: number;
}

function GradientHeading({ children }: { children: React.ReactNode }) {
  return (
    <h1
      className="text-3xl lg:text-4xl font-bold"
      style={{
        fontFamily: "Satoshi, sans-serif",
        background: "linear-gradient(135deg, #ffffff 0%, #6366F1 50%, #22D3EE 100%)",
        WebkitBackgroundClip: "text",
        WebkitTextFillColor: "transparent",
      }}
    >
      {children}
    </h1>
  );
}

function StepBadge({ current, total }: { current: number; total: number }) {
  return (
    <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-[#6366F1]/10 border border-[#6366F1]/30 mb-4 backdrop-blur-sm">
      <span className="w-2 h-2 rounded-full bg-[#22D3EE] animate-pulse shadow-lg shadow-[#22D3EE]/50" />
      <span className="text-sm text-[#22D3EE] font-medium">Step {current} of {total}</span>
    </div>
  );
}

interface PlanRecommendationProps {
  effectiveTotal: number;
  displayStep: number;
  recommendation: Recommendation;
  plans: SubscriptionPlan[];
  plansLoading: boolean;
  checkoutLoading: SubscriptionType | null;
  isSubmitting: boolean;
  handleSelectPlan: (plan: SubscriptionType) => void;
  handleDemoMode: (plan: SubscriptionType) => void;
  handleBack: () => void;
}

export default function PlanRecommendation({
  effectiveTotal,
  displayStep,
  recommendation,
  plans,
  plansLoading,
  checkoutLoading,
  isSubmitting,
  handleSelectPlan,
  handleDemoMode,
  handleBack,
}: PlanRecommendationProps) {
  // Change this one index to switch recommended plan source.
  const RECOMMENDED_PLAN_INDEX = 0;
  const planPrimary = plans[RECOMMENDED_PLAN_INDEX];
  const pricePrimary = planPrimary?.amount;
  const namePrimary = planPrimary?.name;
  const hasPrimaryPlanDetails =
    typeof pricePrimary === "number" &&
    Number.isFinite(pricePrimary) &&
    typeof namePrimary === "string" &&
    namePrimary.trim().length > 0;

  const recommendedFeatureReasons: string[] = Array.isArray((planPrimary as any)?.features)
    ? (planPrimary as any).features.filter(
        (f: unknown): f is string => typeof f === "string" && f.trim().length > 0
      )
    : [];

  if (plansLoading) {
    return (
      <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-300">
        <div className="text-center space-y-3">
          <StepBadge current={displayStep} total={effectiveTotal} />
          <GradientHeading>Our Recommendation</GradientHeading>
          <p className="text-slate-400 text-lg">Based on your answers, here&apos;s what we suggest</p>
        </div>
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <Card key={i} className="bg-[#0a0f1a]/80 border border-white/10 p-6">
              <div className="h-10 w-32 rounded bg-white/10 animate-pulse mb-4" />
              <div className="h-12 w-24 rounded bg-white/10 animate-pulse mb-6" />
              <div className="flex-1 space-y-3">
                {[1, 2, 3].map((j) => (
                  <div key={j} className="h-4 w-full rounded bg-white/10 animate-pulse" />
                ))}
              </div>
              <div className="h-10 w-full rounded bg-white/10 animate-pulse mt-6" />
            </Card>
          ))}
        </div>
        <Button variant="ghost" disabled className="w-full text-slate-500">
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to assessment
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-300">
      <div className="text-center space-y-3">
        <StepBadge current={displayStep} total={effectiveTotal} />
        <GradientHeading>Our Recommendation</GradientHeading>
        <p className="text-slate-400 text-lg">Based on your answers, here&apos;s what we suggest</p>
      </div>
      <div className="relative group">
        <div
          className="absolute -inset-[2px] rounded-2xl opacity-75"
          style={{
            background: "linear-gradient(135deg, #22D3EE, #6366F1, #A855F7, #22D3EE)",
            backgroundSize: "300% 300%",
            animation: "gradient-shift 4s ease infinite",
          }}
        />
        {hasPrimaryPlanDetails ? (
          <Card className="relative bg-[#0a0f1a] border-0 overflow-hidden">
            <div className="absolute top-0 right-0 px-4 py-2 text-xs font-semibold rounded-bl-xl" style={{ background: "linear-gradient(135deg, #6366F1, #22D3EE)" }}>
              Recommended for you
            </div>
            <CardHeader className="pt-10">
              <div className="flex items-center gap-4">
                <div className="w-14 h-14 rounded-xl flex items-center justify-center" style={{ background: "rgba(34,211,238,0.2)", boxShadow: "0 0 30px rgba(34,211,238,0.4)" }}>
                  <Brain className="h-7 w-7 text-[#22D3EE]" />
                </div>
                <div>
                  <CardTitle className="text-white text-2xl font-bold">{namePrimary}</CardTitle>
                  <CardDescription className="text-slate-400">Your own fine-tuned model</CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="text-4xl font-bold" style={{ background: "linear-gradient(135deg, #ffffff, #22D3EE)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
                {`$ ${pricePrimary}`}
                <span className="text-lg font-normal text-slate-500">/month</span>
              </div>
              <div className="space-y-3">
                <p className="text-sm text-slate-400 font-medium">Why we recommend this:</p>
                <ul className="space-y-3">
                  {recommendedFeatureReasons.map((reason, i) => (
                    <li key={i} className="flex items-start gap-3 text-sm text-slate-300">
                      <div className="w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5" style={{ background: "rgba(34,211,238,0.2)", boxShadow: "0 0 10px rgba(34,211,238,0.3)" }}>
                        <Check className="h-3 w-3 text-[#22D3EE]" />
                      </div>
                      {reason}
                    </li>
                  ))}
                </ul>
              </div>
              <Button onClick={() => handleSelectPlan(recommendation.type)} disabled={checkoutLoading !== null || isSubmitting} className="w-full h-14 bg-gradient-to-r from-[#6366F1] via-[#A855F7] to-[#22D3EE] text-white font-semibold text-lg rounded-xl shadow-lg shadow-[#6366F1]/30" style={{ backgroundSize: "200% 200%", animation: "gradient-shift 3s ease infinite" }}>
                {isSubmitting ? <Loader2 className="mr-2 h-5 w-5 animate-spin" /> : <CreditCard className="mr-2 h-5 w-5" />}
                {isSubmitting ? "Creating..." : "Subscribe Now"}
              </Button>
              {/* 
              <Button variant="ghost" onClick={() => handleDemoMode(recommendation.type)} disabled={checkoutLoading !== null || isSubmitting} className="w-full text-slate-500 hover:text-slate-300 text-sm">
                Skip payment (demo mode)
              </Button> */}
            </CardContent>
          </Card>
        ) : (
          <Card className="relative bg-[#0a0f1a] border-0 overflow-hidden">
            <div className="absolute top-0 right-0 px-4 py-2 text-xs font-semibold rounded-bl-xl" style={{ background: "linear-gradient(135deg, #6366F1, #22D3EE)" }}>
              Recommended for you
            </div>
            <CardHeader className="pt-10">
              <CardTitle className="text-white text-2xl font-bold">Plan details unavailable</CardTitle>
              <CardDescription className="text-slate-400">
                We are updating plan name and pricing. Please check back shortly.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button disabled className="w-full h-14 text-white font-semibold text-lg rounded-xl">
                Plan details are updating. Please check back shortly.
              </Button>
            </CardContent>
          </Card>
        )}
      </div>
      <Button variant="ghost" onClick={handleBack} className="w-full text-slate-500 hover:text-slate-300">
        <ArrowLeft className="mr-2 h-4 w-4" />
        Back to assessment
      </Button>
    </div>
  );
}

