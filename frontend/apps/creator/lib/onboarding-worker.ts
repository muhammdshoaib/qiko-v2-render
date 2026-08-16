export interface OnboardingWorkerDraftInput {
  fullName?: string;
  professionalTitle?: string;
  location?: string;
  headline?: string;
  tone?: string;
  industry?: string;
  categories?: readonly string[];
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

export interface OnboardingWorkerSignup {
  name: string;
  title: string;
  location: string;
  about: string;
  tone: string;
  industry: string;
  expertise: string;
  main_goal: string;
  knowledge: string;
}

export type OnboardingWorkerConfig = Omit<OnboardingWorkerSignup, "name" | "knowledge"> & {
  full_name: string;
};

export interface OnboardingWorkerDraft {
  signup: OnboardingWorkerSignup;
  config: OnboardingWorkerConfig;
}

const MAX_KNOWLEDGE_LENGTH = 4_000;

function trim(value?: string): string {
  return value?.trim() ?? "";
}

function buildKnowledge(input: OnboardingWorkerDraftInput): string {
  const sections: readonly [string, string | undefined][] = [
    ["Headline", input.headline],
    ["Professional background", input.professionalBackground],
    ["Credentials", input.credentials],
    ["Achievements", input.achievements],
    ["Additional guidance", input.additionalGuidance],
    ["Common mistakes", input.commonMistakes],
    ["Frameworks", input.frameworks],
    ["Stakeholder balance", input.stakeholderBalance],
    ["Boundaries", input.boundaries],
    ["Common tasks", input.commonTasks],
    ["Example Q&A", input.exampleQA],
  ];

  return sections
    .map(([label, value]) => {
      const text = trim(value);
      return text ? `${label}: ${text}` : "";
    })
    .filter(Boolean)
    .join("\n\n")
    .slice(0, MAX_KNOWLEDGE_LENGTH)
    .trimEnd();
}

export function buildOnboardingWorkerDraft(
  input: OnboardingWorkerDraftInput,
): OnboardingWorkerDraft {
  const name = trim(input.fullName);
  const title = trim(input.professionalTitle);
  const location = trim(input.location);
  const about = [input.professionalBackground, input.credentials, input.achievements]
    .map(trim)
    .filter(Boolean)
    .join("\n\n");
  const tone = trim(input.tone);
  const industry = trim(input.industry);
  const expertise = (input.categories ?? [])
    .map((category) => category.trim())
    .filter(Boolean)
    .join(", ");
  const mainGoal = trim(input.headline);
  const knowledge = buildKnowledge(input);

  return {
    signup: {
      name,
      title,
      location,
      about,
      tone,
      industry,
      expertise,
      main_goal: mainGoal,
      knowledge,
    },
    config: {
      full_name: name,
      title,
      location,
      about,
      tone,
      industry,
      expertise,
      main_goal: mainGoal,
    },
  };
}
