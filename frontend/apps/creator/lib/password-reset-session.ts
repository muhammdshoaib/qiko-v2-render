export const PASSWORD_RESET_EMAIL_SESSION_KEY = "qiko.password-reset.email";

type SessionStorage = {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
};

type WindowLike = {
  readonly sessionStorage: SessionStorage;
};

export function getPasswordResetSessionStorage(windowLike: WindowLike): SessionStorage | null {
  try {
    return windowLike.sessionStorage;
  } catch {
    return null;
  }
}

export function normalisePasswordResetEmail(email: string): string {
  return email.trim().toLowerCase();
}

export function storePasswordResetEmail(storage: SessionStorage | null, email: string): string {
  const normalisedEmail = normalisePasswordResetEmail(email);
  if (storage === null) return normalisedEmail;
  try {
    if (normalisedEmail) {
      storage.setItem(PASSWORD_RESET_EMAIL_SESSION_KEY, normalisedEmail);
    } else {
      storage.removeItem(PASSWORD_RESET_EMAIL_SESSION_KEY);
    }
  } catch {
    // Browser privacy settings can disable session storage; the reset flow must still continue.
  }
  return normalisedEmail;
}

export function resolvePasswordResetEmail(
  queryEmail: string | null,
  storage: Pick<SessionStorage, "getItem"> | null,
): string {
  const normalisedQueryEmail = normalisePasswordResetEmail(queryEmail ?? "");
  if (normalisedQueryEmail) return normalisedQueryEmail;
  if (storage === null) return "";
  try {
    return normalisePasswordResetEmail(storage.getItem(PASSWORD_RESET_EMAIL_SESSION_KEY) ?? "");
  } catch {
    return "";
  }
}

export function clearPasswordResetEmail(storage: Pick<SessionStorage, "removeItem"> | null): void {
  if (storage === null) return;
  try {
    storage.removeItem(PASSWORD_RESET_EMAIL_SESSION_KEY);
  } catch {
    // Cleanup is best effort and must not hide a successful password reset.
  }
}
