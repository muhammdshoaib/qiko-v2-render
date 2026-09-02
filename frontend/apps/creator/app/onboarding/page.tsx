"use client";
import { useState, useEffect } from "react";
import { useLocation } from "@/lib/wouter";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { toast } from "sonner";
import { buildOnboardingWorkerDraft } from "@/lib/onboarding-worker";
import { startCheckout } from "@/lib/api";
import {
  ArrowRight,
  ArrowLeft,
  Sparkles,
  Zap,
  Brain,
  Check,
  Crown,
  Loader2,
  CreditCard,
  X,
  User,
  Mail,
  Plane,
  Building2,
  Briefcase,
  Heart,
  Scale,
  TrendingUp,
  ChevronDown,
  ChevronUp,
  Wifi,
  WifiOff,
  Search,
  Activity,
} from "lucide-react";
import { addAvatarKnowledge, createAvatar, createSignalWorker, saveAvatarProfile, signupAvatar, getSubscriptionPlans, type SubscriptionPlan } from "@/lib/avatarApi";
import { COOKIES_RELEASE_ID, PRIVACY_RELEASE_ID, TERMS_RELEASE_ID } from "@/lib/consent/consent-record";
import { useAuth } from "@/_core/hooks/useAuth";
import { useAppSelector } from "@/store/hooks";
import { motion } from "framer-motion";
import { BRAND_TEXT } from "@/constants/brand";
import PlanRecommendation from "./PlanRecommendation";

// ─── Constants (replacing @shared/types) ─────────────────────────────
const TOTAL_STEPS = 6;

const INDUSTRY_OPTIONS = [
  {
    value: "financial_analyst",
    title: "Financial Analyst",
    description: "AI financial analyst that monitors markets, evaluates investment opportunities, builds financial strategies, and generates detailed reports",
    active: true,
    features: ["Market monitoring", "Investment research", "Strategy development", "Performance analysis"],
  },
  { value: "travel_leisure", title: "Travel & Leisure", description: "Golf, luxury trips, concierge", features: ["Golf packages", "Itineraries", "VIP access"], active: true },
  { value: "real_estate", title: "Real Estate", description: "Sales, lettings, investment", features: ["Listings", "Valuations", "Viewings"], active: true },
  { value: "financial_services", title: "Financial Services", description: "Advisory, wealth, banking", features: ["Portfolio", "Compliance", "Reports"], active: true },
  { value: "healthcare", title: "Healthcare", description: "Clinics, patient support", features: ["Appointments", "FAQs", "Triage"], active: true },
  { value: "legal", title: "Legal", description: "Law firms, contracts", features: ["Intake", "Documents", "Scheduling"], active: true },
  { value: "wealth_management", title: "Wealth Management", description: "HNW, family offices", features: ["Advisory", "Reporting", "Onboarding"], active: true },
  { value: "ai_visibility", title: "AI Visibility (Qiko Signal)", description: "Track how visible your brand is across AI engines", features: ["Brand", "Category", "Problem", "Feature", "Comparison"], active: true },
  { value: "other", title: "Other", description: "Custom use cases", features: ["Flexible"], active: true },
];

const SPECIALIZATION_CATEGORIES = ["Sales", "Lettings", "Investment", "Valuations", "Property management", "New build", "International", "Commercial", "Rural", "Other"];
const TRAVEL_SPECIALIZATION_CATEGORIES = ["Golf travel", "Luxury itineraries", "VIP access", "Group travel", "Corporate travel", "Destination weddings", "Adventure travel", "Cruises", "Other"];
const WEALTH_SPECIALIZATION_CATEGORIES = ["Portfolio management", "Estate planning", "Tax optimization", "Family office", "Impact investing", "Art & collectibles", "Other"];

const TONE_OPTIONS = [
  { value: "professional", label: "Professional" },
  { value: "friendly", label: "Friendly & approachable" },
  { value: "Casual", label: "Relaxed & conversational" },
  { value: "Expert", label: "Authoritative & confident" },
  { value: "empathetic", label: "Warm & empathetic" },
];

// ─── Types ───────────────────────────────────────────────────────────
type SubscriptionType = "gpt_wrapper" | "custom_model" | "premium";

interface WizardData {
  industry?: string;
  // Qiko Signal (AI Visibility) config
  signal_brand?: string;
  signal_domain?: string;
  signal_competitors?: string[];
  signal_query_sets?: Record<string, string[]>;
  fullName?: string;
  location?: string;
  professionalTitle?: string;
  headline?: string;
  categories?: string[];
  tone?: string;
  additionalGuidance?: string;
  professionalBackground?: string;
  credentials?: string;
  achievements?: string;
  commonMistakes?: string;
  frameworks?: string;
  stakeholderBalance?: string;
  boundaries?: string;
  commonTasks?: string;
  exampleQA?: string;
}

interface AssessmentData {
  nicheLevel: number;
  privacyImportance: number;
  needsOffline: boolean;
  conversationVolume: number;
}

interface AccountData {
  fullName: string;
  email: string;
}

interface AccountFieldErrors {
  fullName?: string;
  email?: string;
}

interface Recommendation {
  type: SubscriptionType;
  reasons: string[];
  confidence: number;
}

// ─── Industry icons ───────────────────────────────────────────────────
const INDUSTRY_ICONS: Record<string, React.ReactNode> = {
  financial_analyst: <Search className="w-6 h-6" />,
  travel_leisure: <Plane className="w-6 h-6" />,
  real_estate: <Building2 className="w-6 h-6" />,
  financial_services: <Briefcase className="w-6 h-6" />,
  healthcare: <Heart className="w-6 h-6" />,
  legal: <Scale className="w-6 h-6" />,
  wealth_management: <TrendingUp className="w-6 h-6" />,
  ai_visibility: <Activity className="w-6 h-6" />,
  other: <Sparkles className="w-6 h-6" />,
};

function getSpecializationsForIndustry(industry?: string): readonly string[] {
  switch (industry) {
    case "travel_leisure":
      return TRAVEL_SPECIALIZATION_CATEGORIES;
    case "wealth_management":
      return WEALTH_SPECIALIZATION_CATEGORIES;
    default:
      return SPECIALIZATION_CATEGORIES;
  }
}

function getRecommendation(data: AssessmentData): Recommendation {
  let customScore = 0;

  if (data.nicheLevel > 70) {
    customScore += 40;
  } else if (data.nicheLevel > 40) {
    customScore += 20;
  }
  if (data.privacyImportance > 70) {
    customScore += 30;
  } else if (data.privacyImportance > 40) {
    customScore += 15;
  }
  if (data.needsOffline) {
    customScore += 20;
  }
  if (data.conversationVolume > 70) {
    customScore += 10;
  }
  if (customScore >= 50) {
    return {
      type: "custom_model",
      reasons: [],
      confidence: Math.min(customScore, 95),
    };
  }
  return {
    type: "custom_model",
    reasons: [],
    confidence: 100 - customScore,
  };
}

// ─── Shared UI ───────────────────────────────────────────────────────
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

function TrainingSection({
  title,
  description,
  isOpen,
  onToggle,
  children,
  filled,
}: {
  title: string;
  description: string;
  isOpen: boolean;
  onToggle: () => void;
  children: React.ReactNode;
  filled?: boolean;
}) {
  return (
    <div className="rounded-2xl border border-white/[0.06] bg-white/[0.015] overflow-hidden">
      <button type="button" onClick={onToggle} className="w-full flex items-center justify-between p-5 text-left transition-colors hover:bg-white/[0.03] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500">
        <div className="flex items-center gap-3">
          {filled && (
            <div className="w-5 h-5 rounded-full bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center">
              <Check className="w-3 h-3 text-emerald-400" />
            </div>
          )}
          <div>
            <h3 className="font-medium text-white">{title}</h3>
            <p className="text-sm text-slate-500 mt-0.5">{description}</p>
          </div>
        </div>
        {isOpen ? <ChevronUp className="w-5 h-5 text-slate-400 flex-shrink-0" /> : <ChevronDown className="w-5 h-5 text-slate-400 flex-shrink-0" />}
      </button>
      {isOpen && <div className="px-5 pb-5 space-y-4 border-t border-white/5 pt-4">{children}</div>}
    </div>
  );
}

export default function Onboarding() {
  const [, setLocation] = useLocation();
  const { isAuthenticated, loading: authLoading, refresh } = useAuth();
  const isLoggedIn = !!isAuthenticated;
  const subscription = useAppSelector((state) => state?.auth?.subscription);
  const subscribed = subscription?.subscribed;
  const hasSubscription =
    subscribed === true ||
    subscribed === "true" ||
    (!!subscription && (subscription?.status === "active" || subscription?.status === "trialing"));

  const [step, setStep] = useState(1);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [checkoutLoading, setCheckoutLoading] = useState<SubscriptionType | null>(null);

  const [wizardData, setWizardData] = useState<WizardData>({});
  const [assessment, setAssessment] = useState<AssessmentData>({
    nicheLevel: 50,
    privacyImportance: 50,
    needsOffline: false,
    conversationVolume: 50,
  });
  const [account, setAccount] = useState<AccountData>({
    fullName: "",
    email: "",
  });
  const [accountFieldErrors, setAccountFieldErrors] = useState<AccountFieldErrors>({});
  const [selectedPlan, setSelectedPlan] = useState<SubscriptionType | null>(null);
  const [selectedPlanDetails, setSelectedPlanDetails] = useState<SubscriptionPlan | null>(null);
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({
    tone: false,
    background: false,
    frameworks: false,
    services: false,
  });
  const [plans, setPlans] = useState<SubscriptionPlan[]>([]);
  const [plansLoading, setPlansLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setPlansLoading(true);
    getSubscriptionPlans()
      .then((list) => {
        if (!cancelled) setPlans(Array.isArray(list) ? list : []);
      })
      .catch(() => {
        if (!cancelled) setPlans([]);
      })
      .finally(() => {
        if (!cancelled) setPlansLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  const recommendation = getRecommendation(assessment);
  const effectiveTotal = isLoggedIn ? TOTAL_STEPS - 1 : TOTAL_STEPS;
  const totalDots = effectiveTotal;
  const displayStep = isLoggedIn && step >= 5 ? step - 1 : step;
  const onboardingReturnTo = (() => {
    if (typeof window === "undefined") return null;
    const params = new URLSearchParams(window.location.search);
    const value = params.get("returnTo");
    if (!value) return null;
    // Only allow app-internal paths to avoid accidental external redirects.
    if (!value.startsWith("/")) return null;
    return value;
  })();
  
  const handleCloseOnboarding = () => {
    if (onboardingReturnTo) {
      setLocation(onboardingReturnTo);
      return;
    }
    if (isLoggedIn) {
      setLocation("/workers");
      return;
    }
    if (typeof window === "undefined") {
      setLocation("/");
      return;
    }

    const landingPageUrl = "/";
    window.location.href = landingPageUrl;
  };

  const updateWizard = <K extends keyof WizardData>(field: K, value: WizardData[K]) => {
    setWizardData((prev) => ({ ...prev, [field]: value }));
  };

  const handleCategoryToggle = (category: string) => {
    const current = wizardData.categories || [];
    const updated = current.includes(category) ? current.filter((c) => c !== category) : [...current, category];
    updateWizard("categories", updated);
  };

  const handleNext = () => {
    if (step === 1 && !wizardData.industry) {
      toast.error("Please select an industry to continue");
      return;
    }
    if (step === 2) {
      if (!wizardData.fullName?.trim()) {
        toast.error("Please enter your worker's name");
        return;
      }
      if (!wizardData.location?.trim()) {
        toast.error("Please enter your location");
        return;
      }
      if (!wizardData.professionalTitle?.trim()) {
        toast.error("Please enter your professional title");
        return;
      }
      if (!wizardData.headline?.trim()) {
        toast.error("Please describe what you help clients with");
        return;
      }
    }
    // User already has subscription: skip plan step, go straight to creating worker
    if (step === 3 && hasSubscription) {
      runCreateAvatarAndKnowledge(recommendation.type);
      return;
    }
    setStep((prev) => Math.min(prev + 1, TOTAL_STEPS));
  };

  const handleBack = () => {  
    if (step === 5) {
      setStep(3);
      return
    }
    setStep((prev) => Math.max(prev - 1, 1));
  }

  const handleSelectPlan = async (plan: SubscriptionType, planDetails: SubscriptionPlan) => {
    setSelectedPlan(plan);
    setSelectedPlanDetails(planDetails);

    // Wait for the session to resolve before deciding; otherwise an already authenticated user could
    // be wrongly sent to the email/password step while GET /auth/me is still in flight (QIK-305).
    if (authLoading) return;

    if (!isLoggedIn) {
      setAccount((prev) => ({ ...prev, fullName: prev.fullName || wizardData.fullName || "" }));
      setStep(6);
      return;
    }
    if (hasSubscription) {
      await runCreateAvatarAndKnowledge(plan);
      return;
    }
    // Logged in but no subscription: create avatar, then redirect to dashboard; checkout API runs after they land on dashboard
    await runCreateAvatarAndKnowledge(plan, true);
  };

  const handleDemoMode = async (plan: SubscriptionType) => {
    setSelectedPlan(plan);
    // Same session-still-resolving guard as handleSelectPlan (QIK-305): don't route an authenticated
    // user to the email/password step while GET /auth/me is in flight.
    if (authLoading) return;
    if (isLoggedIn) {
      await runCreateAvatarAndKnowledge(plan);
    } else {
      setAccount((prev) => ({ ...prev, fullName: prev.fullName || wizardData.fullName || "" }));
      setStep(6);
    }
  };

  async function runCreateAvatarAndKnowledge(plan: SubscriptionType, redirectToDashboardForCheckout = false) {

    setIsSubmitting(true);
    try {

      // AI Visibility (Qiko Signal) workers use a dedicated create endpoint.
      if (wizardData.industry === "ai_visibility") {
        const signalName =
          wizardData.signal_brand?.trim() ||
          wizardData.fullName?.trim() ||
          wizardData.professionalTitle?.trim() ||
          "Signal Worker";
        await createSignalWorker({
          agent_name: signalName,
          signal_brand: wizardData.signal_brand?.trim() || undefined,
          signal_domain: wizardData.signal_domain?.trim() || undefined,
          signal_competitors: wizardData.signal_competitors?.length
            ? wizardData.signal_competitors
            : undefined,
          signal_query_sets: wizardData.signal_query_sets,
        });
        if (redirectToDashboardForCheckout) {
          setLocation("/dashboard");
        } else {
          setLocation("/creating");
        }
        return;
      }

      const draft = buildOnboardingWorkerDraft(wizardData);
      const name = draft.signup.name || draft.signup.title || "My AI Assistant";
      const avatarRes = await createAvatar({ agent_name: name });
      const agentId = avatarRes?.data?.agent_unique_id;

      if (!agentId) throw new Error("Avatar created but no agent id returned");
      await saveAvatarProfile(agentId, draft.config);
      try {
        await addAvatarKnowledge(agentId, draft.signup.knowledge);
        toast.success("Worker knowledge added successfully.");
      } catch (knowledgeError) {
        const msg = knowledgeError instanceof Error ? knowledgeError.message : "Knowledge save failed";
        toast.warning(msg + " You can add training later.");
      }

      if (redirectToDashboardForCheckout) {
        setLocation("/dashboard");
      } else {
        setLocation("/creating");
      }
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Failed to save. Please try again.";
      toast.error(message);
      setIsSubmitting(false);
    }
  }

  const validateAccountForm = (): boolean => {
    setAccountFieldErrors({});
    if (!account.fullName.trim()) {
      toast.error("Please enter your full name");
      return false;
    }
    if (!account.email.trim()) {
      toast.error("Please enter your email");
      return false;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(account.email)) {
      toast.error("Please enter a valid email address");
      return false;
    }
    if (!selectedPlan) {
      toast.error("Please select a plan first");
      return false;
    }
    return true;
  };

  const handleCreateAccount = async () => {
    if (!validateAccountForm()) return;
    setIsSubmitting(true);
    try {
      setAccountFieldErrors({});
      const draft = buildOnboardingWorkerDraft(wizardData);
      await signupAvatar({
        user_name: account.fullName,
        email: account.email,
        onboarding_worker: wizardData.industry === "ai_visibility" ? undefined : draft.signup,
        terms_release_id: TERMS_RELEASE_ID,
        privacy_release_id: PRIVACY_RELEASE_ID,
        cookies_release_id: COOKIES_RELEASE_ID,
      });
      if (selectedPlanDetails && selectedPlanDetails.key && selectedPlanDetails.price_id && selectedPlanDetails.amount > 0) {
        try {
          const checkout = await startCheckout(selectedPlanDetails.key, selectedPlanDetails.price_id);
          if (checkout?.url) {
            window.location.href = checkout.url;
            return;
          }
        } catch (checkoutErr) {
          const msg = checkoutErr instanceof Error ? checkoutErr.message : "Checkout unavailable";
          toast.error(`${msg}. You can complete payment from Billing after verifying your email.`);
        }
      }
      setLocation(`/verify-email?email=${encodeURIComponent(account.email)}`);
      return;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Sign up failed. Please try again.";
      const validationErrors =
        err && typeof err === "object" && "validationErrors" in err
          ? (err as { validationErrors?: Record<string, string[]> }).validationErrors
          : undefined;

      if (validationErrors) {
        setAccountFieldErrors({
          fullName: validationErrors.user_name?.[0],
          email: validationErrors.email?.[0],
        });
      }

      if (typeof message === "string" && /already|registered|exists/i.test(message)) {
        toast.error("This email or username is already registered. Please sign in instead.");
      } else {
        toast.error(message);
      }
      setIsSubmitting(false);
    }
  };

  const specializations = getSpecializationsForIndustry(wizardData.industry);

  const toggleSection = (key: string) => {
    setOpenSections((prev) => ({ ...prev, [key]: !prev[key] }));
  };
  
  return (
    <div className="min-h-screen bg-[#050810] text-white relative overflow-hidden">
      {/* Animated gradient background - matching landing page */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        {/* Large floating orbs with neon glow */}
        <div 
          className="absolute w-[600px] h-[600px] rounded-full opacity-30"
          style={{
            background: 'radial-gradient(circle, #6366F1 0%, transparent 70%)',
            top: '-10%',
            left: '20%',
            filter: 'blur(80px)',
            animation: 'float1 12s ease-in-out infinite',
          }}
        />
        <div 
          className="absolute w-[500px] h-[500px] rounded-full opacity-25"
          style={{
            background: 'radial-gradient(circle, #22D3EE 0%, transparent 70%)',
            top: '40%',
            right: '5%',
            filter: 'blur(80px)',
            animation: 'float2 10s ease-in-out infinite',
          }}
        />
        <div 
          className="absolute w-[400px] h-[400px] rounded-full opacity-20"
          style={{
            background: 'radial-gradient(circle, #A855F7 0%, transparent 70%)',
            bottom: '10%',
            left: '10%',
            filter: 'blur(80px)',
            animation: 'float3 14s ease-in-out infinite',
          }}
        />
        {/* Grid overlay for depth */}
        <div 
          className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage: `
              linear-gradient(rgba(99, 102, 241, 0.3) 1px, transparent 1px),
              linear-gradient(90deg, rgba(99, 102, 241, 0.3) 1px, transparent 1px)
            `,
            backgroundSize: '60px 60px',
          }}
        />
      </div>


      {/* Header */}
      <header className="fixed top-0 left-0 right-0 z-50 bg-[#050810]/60 backdrop-blur-xl border-b border-white/5">
        {/* {JSON.stringify(wizardData)} */}
        <div className="container mx-auto flex h-16 items-center justify-between px-4">
          {/* {JSON.stringify(wizardData)} */}
          <div className="flex items-center gap-3">
            <img 
              src="/qiko-logo.webp" 
              alt={BRAND_TEXT}
              className="h-8 w-auto"
              style={{ filter: 'drop-shadow(0 0 10px rgba(99, 102, 241, 0.5))' }}
            />
          </div>
          
          <span className="text-xs font-medium text-slate-400 sm:hidden">Step {displayStep}/{totalDots}</span>

          <div className="hidden items-center gap-2 sm:flex">
            {Array.from({ length: totalDots }, (_, i) => i + 1).map((s) => (
              <div
                key={s}
                className={`h-2 rounded-full transition-all duration-300 ${
                  s === displayStep
                    ? "w-8 bg-gradient-to-r from-[#6366F1] to-[#22D3EE] shadow-lg shadow-[#6366F1]/50"
                    : s < displayStep
                      ? "w-2 bg-[#6366F1]/50"
                      : "w-2 bg-white/20"
                }`}
              />
            ))}
          </div>
          
          {/* Cancel/Close button */}
          <Button
            variant="ghost"
            size="icon"
            onClick={handleCloseOnboarding}
            className="text-slate-400 hover:text-white hover:bg-white/10"
          >
            <X className="h-5 w-5" />
          </Button>
        </div>
      </header>
      
      <main className="container relative z-10 mx-auto flex max-w-2xl flex-col justify-center overflow-x-hidden px-4" style={{ minHeight: "calc(100vh - 64px)", paddingTop: "80px", paddingBottom: "24px" }}>
        {/* Step 1: Choose Industry */}
        {step === 1 && (
          <div className="space-y-4 animate-in fade-in slide-in-from-right-4 duration-300">
            <div className="text-center space-y-2">
              <StepBadge current={1} total={effectiveTotal} />
              <GradientHeading>Choose your industry</GradientHeading>
              <p className="text-slate-400 text-sm">This determines which features and specializations your AI worker will have</p>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {INDUSTRY_OPTIONS.map((industry) => (
                <button
                  type="button"
                  key={industry.value}
                  disabled={!industry.active}
                  aria-pressed={wizardData.industry === industry.value}
                  className={`relative flex w-full items-center gap-3 p-3 rounded-xl border text-left transition-all ${
                    !industry.active ? "opacity-40 cursor-not-allowed" : "cursor-pointer hover:border-[#6366F1]/50"
                  } ${
                    wizardData.industry === industry.value
                      ? "border-[#6366F1] bg-[#6366F1]/10 ring-1 ring-[#6366F1]"
                      : "border-white/10 bg-[#0a0f1a]/60"
                  }`}
                  onClick={() => industry.active && updateWizard("industry", industry.value)}
                >
                  <div
                    className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 ${
                      wizardData.industry === industry.value ? "bg-[#6366F1] text-white" : "bg-white/5 text-slate-400"
                    }`}
                  >
                    {INDUSTRY_ICONS[industry.value]}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="font-medium text-white text-sm">{industry.title}</span>
                      {!industry.active && (
                        <Badge className="bg-white/5 text-slate-500 border-white/10 text-[10px] px-1.5 py-0">Soon</Badge>
                      )}
                      {/* {industry.value === "travel_leisure" && (
                        <Badge className="bg-cyan-500/10 text-cyan-400 border-cyan-500/30 text-[10px] px-1.5 py-0">Featured</Badge>
                      )} */}
                    </div>
                    <p className="text-xs text-slate-500 mt-0.5 line-clamp-1">{industry.description}</p>
                  </div>
                  {wizardData.industry === industry.value && <Check className="w-4 h-4 text-[#6366F1] flex-shrink-0" />}
                </button>
              ))}
            </div>
            {wizardData.industry && (() => {
              const selected = INDUSTRY_OPTIONS.find((i) => i.value === wizardData.industry);
              return selected?.active ? (
                <div className="flex flex-wrap gap-1.5 justify-center">
                  {selected.features.map((f) => (
                    <span key={f} className="text-xs px-2.5 py-1 rounded-full bg-[#6366F1]/10 text-[#818CF8] border border-[#6366F1]/20">
                      {f}
                    </span>
                  ))}
                </div>
              ) : null;
            })()}
            {wizardData.industry === "ai_visibility" && (
              <div className="space-y-3 rounded-xl border border-[#22D3EE]/30 bg-[#22D3EE]/5 p-4 text-left">
                <div className="flex items-center gap-2 text-[#22D3EE]">
                  <Activity className="w-4 h-4" />
                  <span className="font-semibold text-sm">Qiko Signal setup</span>
                </div>
                <p className="text-xs text-slate-400">
                  Tell us what to track. We&apos;ll measure how visible your brand is across AI engines.
                </p>
                <div className="space-y-1.5">
                  <Label htmlFor="signal_brand" className="text-xs text-slate-300">Brand name</Label>
                  <Input
                    id="signal_brand"
                    value={wizardData.signal_brand || ""}
                    onChange={(e) => updateWizard("signal_brand", e.target.value)}
                    placeholder="e.g., Qiko"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="signal_domain" className="text-xs text-slate-300">Website domain</Label>
                  <Input
                    id="signal_domain"
                    value={wizardData.signal_domain || ""}
                    onChange={(e) => updateWizard("signal_domain", e.target.value)}
                    placeholder="e.g., qiko.ai"
                  />
                </div>
              </div>
            )}
            <Button
              onClick={handleNext}
              disabled={!wizardData.industry || isSubmitting}
              className="w-full h-12 bg-gradient-to-r from-[#6366F1] to-[#22D3EE] text-white font-semibold rounded-xl shadow-lg shadow-[#6366F1]/30 hover:shadow-[#6366F1]/50 disabled:opacity-40 disabled:hover:scale-100"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                  Loading...
                </>
              ) : (
                <>
                  Continue
                  <ArrowRight className="ml-2 h-5 w-5" />
                </>
              )}
            </Button>
          </div>
        )}


        {/* Step 2: Your Identity */}
        {step === 2 && (
          <div className="space-y-4 animate-in fade-in slide-in-from-right-4 duration-300">
            <div className="text-center space-y-2">
              <StepBadge current={2} total={effectiveTotal} />
              <GradientHeading>Tell us about your worker</GradientHeading>
              <p className="text-slate-400 text-sm">Your AI worker will represent your expertise to clients</p>
            </div>
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label htmlFor="worker-name" className="text-slate-300 text-xs font-medium">Your worker&apos;s name *</Label>
                  <Input
                    id="worker-name"
                    value={wizardData.fullName || ""}
                    onChange={(e) => updateWizard("fullName", e.target.value)}
                    placeholder="e.g., James Wilson"
                    required
                    className="h-10 bg-[#0a0f1a]/80 border-white/10 text-white text-sm placeholder:text-slate-500 rounded-lg focus:border-[#6366F1] focus:ring-[#6366F1]/20"
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="worker-location" className="text-slate-300 text-xs font-medium">Location *</Label>
                  <Input
                    id="worker-location"
                    value={wizardData.location || ""}
                    onChange={(e) => updateWizard("location", e.target.value)}
                    placeholder="e.g., Dubai, UAE"
                    required
                    className="h-10 bg-[#0a0f1a]/80 border-white/10 text-white text-sm placeholder:text-slate-500 rounded-lg focus:border-[#6366F1] focus:ring-[#6366F1]/20"
                  />
                </div>
              </div>
              <div className="space-y-1">
                <Label htmlFor="worker-title" className="text-slate-300 text-xs font-medium">Professional title *</Label>
                <Input
                  id="worker-title"
                  value={wizardData.professionalTitle || ""}
                  onChange={(e) => updateWizard("professionalTitle", e.target.value)}
                  placeholder="e.g., Golf Travel Specialist, Wealth Fund Manager"
                  className="h-10 bg-[#0a0f1a]/80 border-white/10 text-white text-sm placeholder:text-slate-500 rounded-lg focus:border-[#6366F1] focus:ring-[#6366F1]/20"
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="worker-headline" className="text-slate-300 text-xs font-medium">I help clients with... *</Label>
                <Textarea
                  id="worker-headline"
                  value={wizardData.headline || ""}
                  onChange={(e) => updateWizard("headline", e.target.value)}
                  placeholder="e.g., Planning luxury golf trips to Scotland and Ireland with VIP tee-time access"
                  rows={2}
                  className="bg-[#0a0f1a]/80 border-white/10 text-white text-sm placeholder:text-slate-500 rounded-lg focus:border-[#6366F1] focus:ring-[#6366F1]/20"
                />
              </div>
              {/* <div className="space-y-2">
                <Label className="text-slate-300 text-xs font-medium">
                  Specializations <span className="text-slate-500">(select all that apply)</span>
                </Label>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-1.5 max-h-[200px] overflow-y-auto pr-1">
                  {specializations.map((cat) => (
                    <label
                      key={cat}
                      className={`flex items-center gap-2 px-2.5 py-2 rounded-lg border cursor-pointer transition-all ${
                        (wizardData.categories || []).includes(cat)
                          ? "border-[#6366F1]/50 bg-[#6366F1]/10"
                          : "border-white/5 bg-[#0a0f1a]/40 hover:border-white/10"
                      }`}
                    >
                      <Checkbox
                        checked={(wizardData.categories || []).includes(cat)}
                        onCheckedChange={() => handleCategoryToggle(cat)}
                        className="border-white/20 data-[state=checked]:bg-[#6366F1] data-[state=checked]:border-[#6366F1] h-3.5 w-3.5"
                      />
                      <span className="text-xs text-slate-300 line-clamp-1">{cat}</span>
                    </label>
                  ))}
                </div>
              </div> */}
            </div>
            <div className="flex gap-3">
              <Button variant="outline" onClick={handleBack} className="flex-1 h-11 bg-transparent border border-white/20 text-white hover:bg-white/5 hover:border-white/30 rounded-xl font-medium">
                <ArrowLeft className="mr-2 h-4 w-4" />
                Back
              </Button>
              <Button
                onClick={handleNext}
                disabled={
                  isSubmitting ||
                  !wizardData.fullName?.trim() ||
                  !wizardData.location?.trim() ||
                  !wizardData.professionalTitle?.trim() ||
                  !wizardData.headline?.trim()
                }
                className="flex-1 h-11 bg-gradient-to-r from-[#6366F1] to-[#22D3EE] text-white font-semibold rounded-xl shadow-lg shadow-[#6366F1]/30 hover:shadow-[#6366F1]/50 disabled:opacity-40"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Loading...
                  </>
                ) : (
                  <>
                    Continue
                    <ArrowRight className="ml-2 h-4 w-4" />
                  </>
                )}
              </Button>
            </div>
          </div>
        )}

        {/* Step 3: Train Your Worker */}
        {step === 3 && (
          <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-300">
            <div className="text-center space-y-3">
              <StepBadge current={3} total={effectiveTotal} />
              <GradientHeading>Train your worker</GradientHeading>
              <p className="text-slate-400 text-lg">
                The more detail you provide, the better your AI will represent you.
                <br />
                <span className="text-sm text-slate-500">All sections are optional - you can come back to this later.</span>
              </p>
            </div>
            <div className="space-y-3">
              <TrainingSection title="Communication Style" description="How should your AI worker speak to clients?" isOpen={openSections.tone} onToggle={() => toggleSection("tone")} filled={!!wizardData.tone}>
                <div className="space-y-3">
                  <Label className="text-slate-300 text-sm">Tone</Label>
                  <RadioGroup value={wizardData.tone || ""} onValueChange={(v) => updateWizard("tone", v)} className="grid grid-cols-2 gap-2">
                    {TONE_OPTIONS.map((opt) => (
                      <label key={opt.value} className={`flex items-center gap-2 p-3 rounded-lg border cursor-pointer transition-all ${wizardData.tone === opt.value ? "border-[#6366F1]/50 bg-[#6366F1]/10" : "border-white/5 hover:border-white/10"}`}>
                        <RadioGroupItem value={opt.value} className="border-white/20 text-[#6366F1]" />
                        <span className="text-sm text-slate-300">{opt.label}</span>
                      </label>
                    ))}
                  </RadioGroup>
                </div>
                <div className="space-y-2">
                  <Label className="text-slate-300 text-sm">Additional guidance</Label>
                  <Textarea value={wizardData.additionalGuidance || ""} onChange={(e) => updateWizard("additionalGuidance", e.target.value)} placeholder="e.g., Always be warm but professional." rows={3} className="bg-white/5 border-white/10 text-white placeholder:text-slate-500 rounded-xl" />
                </div>
              </TrainingSection>
              <TrainingSection title="Background & Credentials" description="Your professional story, qualifications, and achievements" isOpen={openSections.background} onToggle={() => toggleSection("background")} filled={!!(wizardData.professionalBackground || wizardData.credentials || wizardData.achievements)}>
                <div className="space-y-2">
                  <Label className="text-slate-300 text-sm">Professional background</Label>
                  <Textarea value={wizardData.professionalBackground || ""} onChange={(e) => updateWizard("professionalBackground", e.target.value)} placeholder="Tell us about your career journey..." rows={4} className="bg-white/5 border-white/10 text-white placeholder:text-slate-500 rounded-xl" />
                </div>
                <div className="space-y-2">
                  <Label className="text-slate-300 text-sm">Credentials & certifications</Label>
                  <Textarea value={wizardData.credentials || ""} onChange={(e) => updateWizard("credentials", e.target.value)} placeholder="e.g., CFA Level III, IATA certified" rows={2} className="bg-white/5 border-white/10 text-white placeholder:text-slate-500 rounded-xl" />
                </div>
                <div className="space-y-2">
                  <Label className="text-slate-300 text-sm">Key achievements</Label>
                  <Textarea value={wizardData.achievements || ""} onChange={(e) => updateWizard("achievements", e.target.value)} placeholder="e.g., Managed $50M+ in client portfolios" rows={2} className="bg-white/5 border-white/10 text-white placeholder:text-slate-500 rounded-xl" />
                </div>
              </TrainingSection>
              <TrainingSection title="Thinking & Boundaries" description="How you make decisions and what your limits are" isOpen={openSections.frameworks} onToggle={() => toggleSection("frameworks")} filled={!!(wizardData.frameworks || wizardData.boundaries)}>
                <div className="space-y-2">
                  <Label className="text-slate-300 text-sm">Common mistakes you help clients avoid</Label>
                  <Textarea value={wizardData.commonMistakes || ""} onChange={(e) => updateWizard("commonMistakes", e.target.value)} placeholder="e.g., Booking peak season without checking calendars..." rows={3} className="bg-white/5 border-white/10 text-white placeholder:text-slate-500 rounded-xl" />
                </div>
                <div className="space-y-2">
                  <Label className="text-slate-300 text-sm">Your frameworks & decision-making approach</Label>
                  <Textarea value={wizardData.frameworks || ""} onChange={(e) => updateWizard("frameworks", e.target.value)} placeholder="e.g., I always assess risk tolerance first..." rows={3} className="bg-white/5 border-white/10 text-white placeholder:text-slate-500 rounded-xl" />
                </div>
                <div className="space-y-2">
                  <Label className="text-slate-300 text-sm">Boundaries - what should your AI NOT do?</Label>
                  <Textarea value={wizardData.boundaries || ""} onChange={(e) => updateWizard("boundaries", e.target.value)} placeholder="e.g., Never give specific financial advice" rows={2} className="bg-white/5 border-white/10 text-white placeholder:text-slate-500 rounded-xl" />
                </div>
              </TrainingSection>
              <TrainingSection title="Services & Examples" description="What your worker does and example conversations" isOpen={openSections.services} onToggle={() => toggleSection("services")} filled={!!(wizardData.commonTasks || wizardData.exampleQA)}>
                <div className="space-y-2">
                  <Label className="text-slate-300 text-sm">Common tasks your worker should handle</Label>
                  <Textarea value={wizardData.commonTasks || ""} onChange={(e) => updateWizard("commonTasks", e.target.value)} placeholder="e.g., Answer questions, create itineraries" rows={3} className="bg-white/5 border-white/10 text-white placeholder:text-slate-500 rounded-xl" />
                </div>
                <div className="space-y-2">
                  <Label className="text-slate-300 text-sm">Example Q&A</Label>
                  <Textarea value={wizardData.exampleQA || ""} onChange={(e) => updateWizard("exampleQA", e.target.value)} placeholder="Q: Your question here? A: Your answer here." rows={4} className="bg-white/5 border-white/10 text-white placeholder:text-slate-500 rounded-xl" />
                </div>
              </TrainingSection>
            </div>
            <div className="flex gap-4">
              <Button variant="outline" onClick={handleBack} className="flex-1 h-14 bg-transparent border border-white/20 text-white hover:bg-white/5 hover:border-white/30 rounded-xl font-medium">
                <ArrowLeft className="mr-2 h-5 w-5" />
                Back
              </Button>
              <Button
                onClick={handleNext}
                disabled={isSubmitting}
                className="flex-1 h-14 bg-gradient-to-r from-[#6366F1] to-[#22D3EE] text-white font-semibold rounded-xl shadow-lg shadow-[#6366F1]/30 hover:shadow-[#6366F1]/50"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                    Loading...
                  </>
                ) : (
                  <>
                    Continue
                    <ArrowRight className="ml-2 h-5 w-5" />
                  </>
                )}
              </Button>
            </div>
          </div>
        )}

        {/* Step 4: Quick Assessment */}
        {step === 4 && (
          <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-300">
            <>
            <div className="text-center space-y-3">
              <StepBadge current={4} total={effectiveTotal} />
              <GradientHeading>Quick Assessment</GradientHeading>
              <p className="text-slate-400 text-lg">Help us recommend the best plan for you</p>
            </div>
            <div className="space-y-6">
              <div className="space-y-4 p-5 rounded-2xl bg-[#0a0f1a]/60 border border-white/5">
                <div className="flex justify-between items-center">
                  <Label className="text-white font-medium">How specialized is your expertise?</Label>
                  <Badge className={assessment.nicheLevel > 66 ? "bg-[#22D3EE]/20 text-[#22D3EE] border-[#22D3EE]/30" : assessment.nicheLevel > 33 ? "bg-[#6366F1]/20 text-[#818CF8] border-[#6366F1]/30" : "bg-slate-500/20 text-slate-400 border-slate-500/30"}>
                    {assessment.nicheLevel > 66 ? "Specialized" : assessment.nicheLevel > 33 ? "Moderate" : "General"}
                  </Badge>
                </div>
                <Slider value={[assessment.nicheLevel]} onValueChange={([v]) => setAssessment((prev) => ({ ...prev, nicheLevel: v }))} max={100} step={1} className="[&_[role=slider]]:bg-gradient-to-r [&_[role=slider]]:from-[#6366F1] [&_[role=slider]]:to-[#22D3EE] [&_[role=slider]]:border-0 [&_[role=slider]]:shadow-lg [&_[role=slider]]:shadow-[#6366F1]/50" />
                <div className="flex justify-between text-xs text-slate-500"><span>General knowledge</span><span>Highly specialized</span></div>
              </div>
              <div className="space-y-4 p-5 rounded-2xl bg-[#0a0f1a]/60 border border-white/5">
                <div className="flex justify-between items-center">
                  <Label className="text-white font-medium">How important is data privacy?</Label>
                  <Badge className={assessment.privacyImportance > 66 ? "bg-[#22D3EE]/20 text-[#22D3EE] border-[#22D3EE]/30" : assessment.privacyImportance > 33 ? "bg-[#6366F1]/20 text-[#818CF8] border-[#6366F1]/30" : "bg-slate-500/20 text-slate-400 border-slate-500/30"}>
                    {assessment.privacyImportance > 66 ? "Critical" : assessment.privacyImportance > 33 ? "Important" : "Flexible"}
                  </Badge>
                </div>
                <Slider value={[assessment.privacyImportance]} onValueChange={([v]) => setAssessment((prev) => ({ ...prev, privacyImportance: v }))} max={100} step={1} className="[&_[role=slider]]:bg-gradient-to-r [&_[role=slider]]:from-[#6366F1] [&_[role=slider]]:to-[#22D3EE] [&_[role=slider]]:border-0 [&_[role=slider]]:shadow-lg [&_[role=slider]]:shadow-[#6366F1]/50" />
                <div className="flex justify-between text-xs text-slate-500"><span>Not a concern</span><span>Absolutely critical</span></div>
              </div>
              <div className="flex items-center justify-between p-5 rounded-2xl bg-[#0a0f1a]/60 border border-white/5">
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 rounded-xl flex items-center justify-center" style={{ background: assessment.needsOffline ? "rgba(34,211,238,0.2)" : "rgba(99,102,241,0.1)", boxShadow: assessment.needsOffline ? "0 0 20px rgba(34,211,238,0.3)" : "none" }}>
                    {assessment.needsOffline ? <WifiOff className="h-6 w-6 text-[#22D3EE]" /> : <Wifi className="h-6 w-6 text-slate-400" />}
                  </div>
                  <div>
                    <Label className="text-white font-medium">Need offline access?</Label>
                    <p className="text-sm text-slate-500">Run AI without internet connection</p>
                  </div>
                </div>
                <Switch checked={assessment.needsOffline} onCheckedChange={(v) => setAssessment((prev) => ({ ...prev, needsOffline: v }))} className="data-[state=checked]:bg-gradient-to-r data-[state=checked]:from-[#6366F1] data-[state=checked]:to-[#22D3EE]" />
              </div>
              <div className="space-y-4 p-5 rounded-2xl bg-[#0a0f1a]/60 border border-white/5">
                <div className="flex justify-between items-center">
                  <Label className="text-white font-medium">Expected conversation volume?</Label>
                  <Badge className={assessment.conversationVolume > 66 ? "bg-[#22D3EE]/20 text-[#22D3EE] border-[#22D3EE]/30" : assessment.conversationVolume > 33 ? "bg-[#6366F1]/20 text-[#818CF8] border-[#6366F1]/30" : "bg-slate-500/20 text-slate-400 border-slate-500/30"}>
                    {assessment.conversationVolume > 66 ? "High" : assessment.conversationVolume > 33 ? "Moderate" : "Low"}
                  </Badge>
                </div>
                <Slider value={[assessment.conversationVolume]} onValueChange={([v]) => setAssessment((prev) => ({ ...prev, conversationVolume: v }))} max={100} step={1} className="[&_[role=slider]]:bg-gradient-to-r [&_[role=slider]]:from-[#6366F1] [&_[role=slider]]:to-[#22D3EE] [&_[role=slider]]:border-0 [&_[role=slider]]:shadow-lg [&_[role=slider]]:shadow-[#6366F1]/50" />
                <div className="flex justify-between text-xs text-slate-500"><span>Just a few</span><span>Hundreds per month</span></div>
              </div>
            </div>
            </>
            
            <div className="flex gap-4">
              <Button variant="outline" onClick={handleBack} className="flex-1 h-14 bg-transparent border border-white/20 text-white hover:bg-white/5 hover:border-white/30 rounded-xl font-medium">
                <ArrowLeft className="mr-2 h-5 w-5" />
                Back
              </Button>
              <Button onClick={handleNext} disabled={isSubmitting} className="flex-1 h-14 bg-gradient-to-r from-[#6366F1] to-[#22D3EE] hover:from-[#818CF8] hover:to-[#22D3EE] text-white font-semibold rounded-xl shadow-lg shadow-[#6366F1]/30 hover:shadow-[#6366F1]/50 transition-all hover:scale-[1.02]">
                {hasSubscription ? "Continue" : "Purchase Plan"}
                <ArrowRight className="ml-2 h-5 w-5" />
              </Button>
            </div>
          </div>
        )}

        {/* Step 5: Plan Recommendation */}
        {step === 5 && (
          hasSubscription ? (
            <>
              <div className="text-center space-y-3">
                <StepBadge current={4} total={effectiveTotal} />
                <GradientHeading>You're all set</GradientHeading>
                <p className="text-slate-400 text-lg">You already have an active plan</p>
              </div>
              <motion.div
                className="w-full max-w-md mx-auto"
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4 }}
              >
                <div className="relative rounded-2xl border border-white/10 bg-gradient-to-b from-[#0f172a]/95 to-[#0f172a]/80 p-8 lg:p-10 text-center shadow-xl shadow-[#6366F1]/5">
                  <div className="absolute inset-0 rounded-2xl bg-gradient-to-br from-[#6366F1]/10 via-transparent to-[#22D3EE]/10 pointer-events-none" />
                  <div className="absolute -top-12 left-1/2 -translate-x-1/2 w-24 h-24 rounded-full bg-[#6366F1]/20 blur-2xl" />
                  <motion.div
                    className="relative mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-full bg-gradient-to-br from-[#6366F1] to-[#22D3EE] shadow-lg shadow-[#6366F1]/30"
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    transition={{ type: "spring", stiffness: 200, damping: 15, delay: 0.1 }}
                  >
                    <Check className="h-10 w-10 text-white stroke-[2.5]" />
                  </motion.div>
                  <motion.p
                    className="relative text-slate-400 text-sm lg:text-base max-w-sm mx-auto"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.25 }}
                  >
                    Continue to create your worker.
                  </motion.p>
                </div>
              </motion.div>
            </>
          ): (
          <PlanRecommendation
            effectiveTotal={effectiveTotal}
            displayStep={isLoggedIn ? 5 : 5}
            recommendation={recommendation}
            plans={plans}
            plansLoading={plansLoading}
            checkoutLoading={checkoutLoading}
            isSubmitting={isSubmitting}
            handleSelectPlan={handleSelectPlan}
            handleDemoMode={handleDemoMode}
            handleBack={handleBack}
          />  
        ))} 


        {/* Step 6: Account Creation (non–logged-in only) */}
        {step === 6 && !isLoggedIn && (
          <Step6AccountCreation
            effectiveTotal={effectiveTotal}
            account={account}
            setAccount={setAccount}
            accountFieldErrors={accountFieldErrors}
            selectedPlan={selectedPlan}
            selectedPlanDetails={selectedPlanDetails}
            isSubmitting={isSubmitting}
            handleCreateAccount={handleCreateAccount}
            handleBack={handleBack}
            setStep={setStep}
            setLocation={setLocation}
          />
        )}


      </main>

      {/* CSS Animations */}
      <style>{`
        @keyframes float1 {
          0%, 100% { transform: translate(0, 0) scale(1); }
          33% { transform: translate(30px, -30px) scale(1.05); }
          66% { transform: translate(-20px, 20px) scale(0.95); }
        }
        @keyframes float2 {
          0%, 100% { transform: translate(0, 0) scale(1); }
          33% { transform: translate(-40px, 20px) scale(1.1); }
          66% { transform: translate(30px, -40px) scale(0.9); }
        }
        @keyframes float3 {
          0%, 100% { transform: translate(0, 0) scale(1); }
          50% { transform: translate(50px, -30px) scale(1.05); }
        }
        @keyframes gradient-shift {
          0% { background-position: 0% 50%; }
          50% { background-position: 100% 50%; }
          100% { background-position: 0% 50%; }
        }
      `}</style>
    </div>
  );
}

// ─── Sub-components ───────────────────────────────────────────────────

function Step6PlanSummary({
  selectedPlan,
  selectedPlanDetails,
}: {
  selectedPlan: SubscriptionType;
  selectedPlanDetails: SubscriptionPlan | null;
}) {
  const fallbackName = selectedPlan === "gpt_wrapper" ? "Basic AI Model" : "Premium";
  const fallbackPrice = selectedPlan === "gpt_wrapper" ? "$20/month" : "$49/month";

  const name = selectedPlanDetails?.name || fallbackName;
  const amount = selectedPlanDetails?.amount;
  const display = typeof selectedPlanDetails?.display_price === "string" ? selectedPlanDetails.display_price.trim() : "";
  const price = display
    ? (display === "Custom Pricing" ? display : `${display}/month`)
    : typeof amount === "number" && Number.isFinite(amount) && amount > 0
      ? `$${(amount / 100).toFixed(amount % 100 === 0 ? 0 : 2)}/month`
      : fallbackPrice;

  const isCustomModel = selectedPlan === "custom_model";
  const isPremium = selectedPlan === "premium";
  return (
    <div className="p-4 rounded-xl bg-[#6366F1]/10 border border-[#6366F1]/30 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ background: isCustomModel ? "rgba(34,211,238,0.2)" : isPremium ? "rgba(245,158,11,0.2)" : "rgba(99,102,241,0.2)" }}>
          {isCustomModel ? <Brain className="h-5 w-5 text-[#22D3EE]" /> : isPremium ? <Crown className="h-5 w-5 text-amber-400" /> : <Zap className="h-5 w-5 text-[#6366F1]" />}
        </div>
        <div>
          <p className="text-white font-medium">{name}</p>
          <p className="text-sm text-slate-400">{price}</p>
        </div>
      </div>
    </div>
  );
}

function Step6AccountCreation({
  effectiveTotal,
  account,
  setAccount,
  accountFieldErrors,
  selectedPlan,
  selectedPlanDetails,
  isSubmitting,
  handleCreateAccount,
  handleBack,
  setStep,
  setLocation,
}: {
  effectiveTotal: number;
  account: AccountData;
  setAccount: React.Dispatch<React.SetStateAction<AccountData>>;
  accountFieldErrors: AccountFieldErrors;
  selectedPlan: SubscriptionType | null;
  selectedPlanDetails: SubscriptionPlan | null;
  isSubmitting: boolean;
  handleCreateAccount: () => void;
  handleBack: () => void;
  setStep: (s: number) => void;
  setLocation: (path: string) => void;
}) {
  const [acceptedPolicies, setAcceptedPolicies] = useState(false);

  return (
    <div className="space-y-8 animate-in fade-in slide-in-from-right-4 duration-300">
      <div className="text-center space-y-3">
        <StepBadge current={effectiveTotal} total={effectiveTotal} />
        <GradientHeading>Create Your Account</GradientHeading>
        <p className="text-slate-400 text-lg">Almost there! Set up your account to access your AI worker</p>
      </div>
      {/* {JSON.stringify(selectedPlan)} */}
      {selectedPlan && (
        <Step6PlanSummary selectedPlan={selectedPlan} selectedPlanDetails={selectedPlanDetails} />
      )}
      <div className="space-y-5">
        <div className="space-y-2">
          <Label htmlFor="fullName" className="text-slate-300 text-sm font-medium">Full Name</Label>
          <div className="relative">
            <User className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-slate-500" />
            <Input id="fullName" placeholder="John Smith" value={account.fullName} onChange={(e) => setAccount((prev) => ({ ...prev, fullName: e.target.value }))} className={`h-14 pl-12 bg-[#0a0f1a]/80 border-white/10 text-white placeholder:text-slate-500 rounded-xl focus:border-[#6366F1] focus:ring-[#6366F1]/20 ${accountFieldErrors.fullName ? "border-red-500" : ""}`} />
          </div>
          {accountFieldErrors.fullName && (
            <p className="text-xs text-red-400">{accountFieldErrors.fullName}</p>
          )}
        </div>
        <div className="space-y-2">
          <Label htmlFor="email" className="text-slate-300 text-sm font-medium">Email Address</Label>
          <div className="relative">
            <Mail className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-slate-500" />
            <Input id="email" type="email" placeholder={"john" + "@" + "example.com"} value={account.email} onChange={(e) => setAccount((prev) => ({ ...prev, email: e.target.value }))} className={`h-14 pl-12 bg-[#0a0f1a]/80 border-white/10 text-white placeholder:text-slate-500 rounded-xl focus:border-[#6366F1] focus:ring-[#6366F1]/20 ${accountFieldErrors.email ? "border-red-500" : ""}`} />
          </div>
          {accountFieldErrors.email && (
            <p className="text-xs text-red-400">{accountFieldErrors.email}</p>
          )}
        </div>
        <div className="flex items-start gap-3 rounded-xl border border-white/10 bg-[#0a0f1a]/80 p-4">
          <input
            id="onboarding-policy-acceptance"
            type="checkbox"
            required
            checked={acceptedPolicies}
            onChange={(event) => setAcceptedPolicies(event.target.checked)}
            className="mt-0.5 size-4 shrink-0 accent-cyan-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300"
          />
          <label htmlFor="onboarding-policy-acceptance" className="text-xs leading-5 text-slate-300">
            I confirm that I am authorised to bind my organisation, agree to the{" "}
            <a href="/terms" target="_blank" rel="noreferrer" className="text-[#22D3EE] hover:underline">Terms of Service</a>
            {", and acknowledge the "}
            <a href="/privacy" target="_blank" rel="noreferrer" className="text-[#22D3EE] hover:underline">Privacy Policy</a>.
          </label>
        </div>
      </div>
      <div className="space-y-4">
        <Button onClick={handleCreateAccount} disabled={isSubmitting || !acceptedPolicies} className="w-full h-14 bg-gradient-to-r from-[#6366F1] to-[#22D3EE] text-white font-semibold rounded-xl shadow-lg shadow-[#6366F1]/30 hover:shadow-[#6366F1]/50">
          {isSubmitting ? <><Loader2 className="mr-2 h-5 w-5 animate-spin" />Creating your account...</> : <>Create Account & Continue<ArrowRight className="ml-2 h-5 w-5" /></>}
        </Button>
        <Button variant="ghost" onClick={handleBack} disabled={isSubmitting} className="w-full text-slate-500 hover:text-slate-300">
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to plan selection
        </Button>
      </div>
      <p className="text-center text-sm text-slate-500">
        Already have an account?{" "}
        <button onClick={() => setLocation("/login")} className="text-[#22D3EE] hover:underline">Sign in</button>
      </p>
    </div>
  );
}
