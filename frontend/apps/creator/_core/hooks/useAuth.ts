"use client";
// Auth state for ported pages (onboarding/signup/password flows). Auth is cookie-based (httpOnly) in
// V2, so the client can't read the token directly; instead we resolve the session via GET /auth/me.
// Previously this was a stub that hard-coded isAuthenticated:false, which wrongly bounced already
// authenticated users to the email/password step in onboarding (QIK-305).
import { useCallback, useEffect, useState } from "react";
import { logout as apiLogout, probeSession } from "@/lib/api";

type AuthUser = { id: string; email: string; name?: string };

export function useAuth() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const u = await probeSession(); // { id, email, role } or null when anonymous (never redirects)
      setUser(u ? { id: u.id, email: u.email } : null);
    } catch {
      setUser(null); // treat any failure as signed out
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const logout = useCallback(async () => {
    try {
      await apiLogout();
    } finally {
      setUser(null);
    }
  }, []);

  return { isAuthenticated: !!user, loading, user, refresh, logout };
}
