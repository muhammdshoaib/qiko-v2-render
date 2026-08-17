import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";


const avatarApiSource = readFileSync(resolve(process.cwd(), "lib/avatarApi.ts"), "utf8");
const apiSource = readFileSync(resolve(process.cwd(), "lib/api.ts"), "utf8");
const onboardingSource = readFileSync(resolve(process.cwd(), "app/onboarding/page.tsx"), "utf8");

function sourceBetween(source: string, startMarker: string, endMarker: string): string {
  const start = source.indexOf(startMarker);
  const end = source.indexOf(endMarker, start);
  assert.ok(start >= 0, `missing source marker: ${startMarker}`);
  assert.ok(end > start, `missing source marker after ${startMarker}: ${endMarker}`);
  return source.slice(start, end);
}

const signupAvatarSource = sourceBetween(
  avatarApiSource,
  "export async function signupAvatar",
  "export async function forgotPasswordAvatar",
);
const addAvatarKnowledgeSource = sourceBetween(
  avatarApiSource,
  "export async function addAvatarKnowledge",
  "export async function loginAvatar",
);
const accountCreationSource = sourceBetween(
  onboardingSource,
  "const handleCreateAccount = async () =>",
  "const specializations =",
);
const authenticatedCreationSource = sourceBetween(
  onboardingSource,
  "async function runCreateAvatarAndKnowledge",
  "const validateAccountForm =",
);
const verifySignupEmailSource = sourceBetween(
  apiSource,
  "export const verifySignupEmail",
  "// Auth",
);


test("anonymous onboarding uses the canonical worker draft helper", () => {
  assert.match(onboardingSource, /buildOnboardingWorkerDraft/);
});

test("anonymous worker signup sends the bounded draft but AI Visibility omits it", () => {
  assert.ok((signupAvatarSource.match(/\bonboarding_worker\b/g) || []).length >= 2);
  assert.match(
    accountCreationSource,
    /onboarding_worker\s*:\s*wizardData\.industry\s*===\s*["']ai_visibility["']\s*\?\s*undefined\s*:\s*draft\.signup/,
  );
});

test("authenticated onboarding requires a separate profile save before best-effort knowledge", () => {
  assert.match(avatarApiSource, /export async function saveAvatarProfile/);
  const saveAvatarProfileSource = sourceBetween(
    avatarApiSource,
    "export async function saveAvatarProfile",
    "export async function addAvatarKnowledge",
  );
  assert.match(saveAvatarProfileSource, /\/agents\/[^"'`]*\$\{[^}]+\}[^"'`]*\/config/);
  assert.match(saveAvatarProfileSource, /method:\s*["']PUT["']/);
  assert.match(saveAvatarProfileSource, /patch/);

  const createCall = authenticatedCreationSource.indexOf("await createAvatar");
  const profileCall = authenticatedCreationSource.indexOf("await saveAvatarProfile");
  const knowledgeTry = authenticatedCreationSource.indexOf("try {", profileCall);
  const knowledgeCall = authenticatedCreationSource.indexOf("await addAvatarKnowledge", profileCall);
  const knowledgeCatch = authenticatedCreationSource.indexOf("catch", knowledgeCall);
  assert.ok(createCall >= 0);
  assert.ok(profileCall > createCall);
  assert.ok(knowledgeTry > profileCall);
  assert.ok(knowledgeCall > knowledgeTry);
  assert.ok(knowledgeCatch > knowledgeCall);
  assert.match(authenticatedCreationSource, /await saveAvatarProfile\([^;]*draft\.config\)/);
});

test("authenticated knowledge passes the full canonical draft to the created worker", () => {
  assert.match(addAvatarKnowledgeSource, /\/knowledge\/ingest/);
  assert.match(addAvatarKnowledgeSource, /agent_id\s*:/);
  assert.match(
    authenticatedCreationSource,
    /await addAvatarKnowledge\((?=[^;]*\bagentId\b)(?=[^;]*draft\.signup\.knowledge)[^;]*\)/s,
  );
  assert.doesNotMatch(addAvatarKnowledgeSource, /\/agents\/[^"'`]*\/config/);
  assert.doesNotMatch(addAvatarKnowledgeSource, /method:\s*["']PUT["']/);
  assert.doesNotMatch(addAvatarKnowledgeSource, /\bpatch\b/);
});

test("verifySignupEmail exposes the optional worker id in its response type", () => {
  assert.match(
    verifySignupEmailSource,
    /request<\{[^}]*user_id:\s*string;[^}]*email:\s*string;[^}]*worker_id\?:\s*string;?[^}]*\}>/s,
  );
});
