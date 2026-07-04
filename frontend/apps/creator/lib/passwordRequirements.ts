export interface PasswordRequirement {
  met: boolean;
  text: string;
}

/** Checklist used on Sign up, Reset password, and Onboarding. */
export function getPasswordRequirements(password: string): PasswordRequirement[] {
  return [
    { met: password.length >= 8, text: "At least 8 characters" },
    { met: /[A-Z]/.test(password), text: "One uppercase letter" },
    { met: /[a-z]/.test(password), text: "One lowercase letter" },
    { met: /[0-9]/.test(password), text: "One number" },
    { met: /[^A-Za-z0-9]/.test(password), text: "One special character" },
  ];
}

export function arePasswordRequirementsMet(password: string): boolean {
  return getPasswordRequirements(password).every((req) => req.met);
}
