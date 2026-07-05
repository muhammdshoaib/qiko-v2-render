"use client";
// Auth slice shim: V2 uses httpOnly cookies (set by /auth/login), so these are no-op action
// creators kept only so ported pages compile unchanged. useAppDispatch() returns a no-op.
export interface UserInfo {
  id?: string;
  email?: string;
  name?: string;
  user_name?: string;
  [key: string]: unknown;
}

export const setAuth = (payload: unknown) => ({ type: "auth/setAuth", payload });
export const setCalendlyToken = (payload: unknown) => ({ type: "auth/setCalendlyToken", payload });
export const logout = () => ({ type: "auth/logout" });
