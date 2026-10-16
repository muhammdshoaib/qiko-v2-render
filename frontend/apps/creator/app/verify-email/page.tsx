"use client";
import { useEffect, useState } from "react";
import { useLocation } from "@/lib/wouter";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { verifySignupEmail } from "@/lib/api";
import { COOKIES_RELEASE_ID, PRIVACY_RELEASE_ID, TERMS_RELEASE_ID } from "@/lib/consent/consent-record";
import {
  AUTH_BUTTON,
  AUTH_INPUT,
  AUTH_LABEL,
  AUTH_MUTED,
  AuthLogo,
  AuthShell,
} from "@/components/auth/auth-shell";

export default function VerifyEmailPage() {
  const [, setLocation] = useLocation();
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
    setBusy(true);
    setError(null);
    try {
      const result = await verifySignupEmail({
        email,
        code,
        password,
        accept_policies: acceptedPolicies,
        terms_release_id: TERMS_RELEASE_ID,
        privacy_release_id: PRIVACY_RELEASE_ID,
        cookies_release_id: COOKIES_RELEASE_ID,
      });
      setLocation(result.worker_id ? "/creating" : "/dashboard");
    } catch {
      setError("Verification failed. Check the code or request a new signup email.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell backHref="/login" backLabel="Back to sign in">
      <CardHeader className="space-y-1 text-center">
        <AuthLogo />
        <CardTitle className="text-2xl font-bold tracking-tight text-slate-900">Verify your email</CardTitle>
        <CardDescription className={AUTH_MUTED}>Enter the code from your email and choose a password.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="verify-email" className={AUTH_LABEL}>
            Email
          </Label>
          <Input
            id="verify-email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className={AUTH_INPUT}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="verify-code" className={AUTH_LABEL}>
            Verification code
          </Label>
          <Input
            id="verify-code"
            inputMode="numeric"
            maxLength={6}
            value={code}
            onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))}
            className={AUTH_INPUT}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="verify-password" className={AUTH_LABEL}>
            Choose password
          </Label>
          <Input
            id="verify-password"
            type="password"
            autoComplete="new-password"
            minLength={8}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className={AUTH_INPUT}
          />
        </div>
        <label className="flex items-start gap-3 text-sm text-slate-600">
          <input
            type="checkbox"
            className="mt-1 size-4 shrink-0 accent-indigo-600"
            checked={acceptedPolicies}
            onChange={(event) => setAcceptedPolicies(event.target.checked)}
          />
          <span>
            I accept the{" "}
            <a className="text-indigo-600 underline" href="/terms" target="_blank" rel="noreferrer">
              Terms
            </a>
            ,{" "}
            <a className="text-indigo-600 underline" href="/privacy" target="_blank" rel="noreferrer">
              Privacy Policy
            </a>
            , and{" "}
            <a className="text-indigo-600 underline" href="/cookies" target="_blank" rel="noreferrer">
              Cookie Policy
            </a>
            .
          </span>
        </label>
        {error && (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        )}
        <Button
          className={AUTH_BUTTON}
          disabled={busy || !email || code.length !== 6 || password.length < 8 || !acceptedPolicies}
          onClick={verify}
        >
          {busy ? "Verifying..." : "Verify email"}
        </Button>
      </CardContent>
    </AuthShell>
  );
}
