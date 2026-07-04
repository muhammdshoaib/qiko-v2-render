"use client";
// Minimal auth shim for ported pages. Auth is cookie-based (httpOnly) in V2; the client can't read
// the token, so isAuthenticated defaults false in public flows (onboarding/signup). refresh is a no-op.
export function useAuth() {
  return {
    isAuthenticated: false,
    loading: false,
    user: null as null | { id: string; email: string; name?: string },
    refresh: async () => {},
    logout: async () => {},
  };
}
