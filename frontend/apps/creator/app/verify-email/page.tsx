"use client";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { verifySignupEmail } from "@/lib/api";
import { COOKIES_RELEASE_ID, PRIVACY_RELEASE_ID, TERMS_RELEASE_ID } from "@/lib/consent/consent-record";

export default function VerifyEmailPage() {
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [acceptedPolicies, setAcceptedPolicies] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setEmail(params.get("email") ?? "");
    setCode(params.get("code") ?? "");
  }, []);
  async function verify() {
    setBusy(true); setError(null);
    try { await verifySignupEmail({ email, code, password, accept_policies: acceptedPolicies,
      terms_release_id: TERMS_RELEASE_ID, privacy_release_id: PRIVACY_RELEASE_ID,
      cookies_release_id: COOKIES_RELEASE_ID }); window.location.assign("/login"); }
    catch { setError("Verification failed. Check the code or request a new signup email."); }
    finally { setBusy(false); }
  }
  return <main className="flex min-h-screen items-center justify-center bg-[#050810] p-4 text-white"><section className="w-full max-w-md space-y-5 rounded-2xl border border-slate-800 bg-slate-900/70 p-6"><img src="/qiko-logo-email.png" alt="Qiko" className="mx-auto h-12 w-[120px] object-contain" /><h1 className="text-center text-2xl font-semibold">Verify your email</h1><div><Label htmlFor="verify-email">Email</Label><Input id="verify-email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} /></div><div><Label htmlFor="verify-code">Verification code</Label><Input id="verify-code" inputMode="numeric" maxLength={6} value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))} /></div><div><Label htmlFor="verify-password">Choose password</Label><Input id="verify-password" type="password" autoComplete="new-password" minLength={8} value={password} onChange={(event) => setPassword(event.target.value)} /></div><label className="flex items-start gap-3 text-sm text-slate-300"><input type="checkbox" className="mt-1 h-4 w-4" checked={acceptedPolicies} onChange={(event) => setAcceptedPolicies(event.target.checked)} /><span>I accept the <a className="text-cyan-400 underline" href="/terms" target="_blank">Terms</a>, <a className="text-cyan-400 underline" href="/privacy" target="_blank">Privacy Policy</a>, and <a className="text-cyan-400 underline" href="/cookies" target="_blank">Cookie Policy</a>.</span></label>{error && <p role="alert" className="text-sm text-red-400">{error}</p>}<Button className="min-h-11 w-full" disabled={busy || !email || code.length !== 6 || password.length < 8 || !acceptedPolicies} onClick={verify}>{busy ? "Verifying..." : "Verify email"}</Button></section></main>;
}
