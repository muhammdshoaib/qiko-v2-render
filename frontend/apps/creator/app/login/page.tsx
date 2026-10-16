"use client";
import { useEffect, useState } from "react";
import { useAppDispatch } from "@/store/hooks";
import { setAuth } from "@/store/slices/authSlice";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Loader2, Eye, EyeOff, AlertCircle } from "lucide-react";
import { Link } from "@/lib/wouter";
import { toast } from "sonner";
import { loginAvatar } from "@/lib/avatarApi";
import { waitForApi } from "@/lib/wait-for-api";
import { ConsentSettingsButton } from "@/components/consent/ConsentUI";
import {
  AUTH_BUTTON,
  AUTH_INPUT,
  AUTH_LABEL,
  AUTH_MUTED,
  AuthLogo,
  AuthShell,
} from "@/components/auth/auth-shell";

export default function Login() {
  const dispatch = useAppDispatch();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [totp, setTotp] = useState("");
  // Revealed only once the server says this account has 2FA, so the common case stays a 2-field form.
  const [twoFactorRequired, setTwoFactorRequired] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [apiReady, setApiReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void waitForApi().then((ready) => {
      if (!cancelled) setApiReady(ready);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setIsLoading(true);

    try {
      const ready = apiReady || (await waitForApi());
      if (!ready) {
        setErrorMessage("The server is still starting. Wait 20 seconds, then sign in again.");
        return;
      }
      setApiReady(true);
      const res = await loginAvatar({ email, password, totp: totp.trim() || undefined });

      if (res?.data?.token) {
        // The session lives in an httpOnly cookie; nothing usable is returned to the client.
        dispatch(setAuth({ token: res.data.token, userInfo: (res?.data?.user as never) ?? null }));
        toast.success("Welcome back!");
        window.location.href = "/studio";
      }
    } catch (error: unknown) {
      const errorMsg = error instanceof Error ? error.message : "Login failed. Please try again.";
      // POST /auth/login wants the 2FA code in the same request, so a 2FA account fails until the
      // code is supplied. Reveal the field and ask for it instead of dead-ending the user.
      if (/2fa|two-factor|totp|authenticator/i.test(errorMsg)) {
        setTwoFactorRequired(true);
        const prompt = totp.trim()
          ? "That code was not accepted. Try the current code from your authenticator, or a backup code."
          : "This account has two-factor authentication. Enter the code from your authenticator app.";
        setErrorMessage(prompt);
        toast.message(prompt);
      } else if (/502|503|504|starting up|waking/i.test(errorMsg)) {
        const prompt = "The server is still starting. Wait 20 seconds, then sign in again.";
        setErrorMessage(prompt);
        toast.error(prompt);
      } else {
        setErrorMessage(errorMsg);
        toast.error(errorMsg);
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <AuthShell>
      <CardHeader className="space-y-1 text-center">
        <AuthLogo />
        <CardTitle className="text-2xl font-bold tracking-tight text-slate-900">Welcome back</CardTitle>
        <CardDescription className={AUTH_MUTED}>
          {apiReady ? "Server is ready. Sign in to continue." : "Starting the server. You can enter your details now."}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          {errorMessage && (
            <div className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-3">
              <AlertCircle className="mt-0.5 size-5 shrink-0 text-red-600" />
              <p className="text-sm text-red-700">{errorMessage}</p>
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="email" className={AUTH_LABEL}>
              Email
            </Label>
            <Input
              id="email"
              type="email"
              placeholder={"you" + "@" + "example.com"}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className={AUTH_INPUT}
            />
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label htmlFor="password" className={AUTH_LABEL}>
                Password
              </Label>
              <Link
                href="/forgot-password"
                className="text-xs font-medium text-indigo-600 transition-colors hover:text-indigo-700"
              >
                Forgot password?
              </Link>
            </div>
            <div className="relative">
              <Input
                id="password"
                type={showPassword ? "text" : "password"}
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className={`${AUTH_INPUT} pr-10`}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                aria-label={showPassword ? "Hide password" : "Show password"}
                className="absolute right-0 top-1/2 flex size-11 -translate-y-1/2 items-center justify-center text-slate-400 transition-colors hover:text-slate-700 sm:size-9"
              >
                {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
            </div>
          </div>

          {twoFactorRequired && (
            <div className="space-y-2">
              <Label htmlFor="totp" className={AUTH_LABEL}>
                Authenticator or backup code
              </Label>
              <Input
                id="totp"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={64}
                autoFocus
                placeholder="6-digit code"
                value={totp}
                onChange={(e) => setTotp(e.target.value)}
                className={AUTH_INPUT}
              />
              <p className={`text-xs ${AUTH_MUTED}`}>Lost your device? Use one of your saved backup codes.</p>
            </div>
          )}

          <Button type="submit" disabled={isLoading} className={AUTH_BUTTON}>
            {isLoading ? (
              <>
                <Loader2 className="mr-2 size-4 animate-spin" />
                {apiReady ? "Signing in..." : "Starting server, then signing in..."}
              </>
            ) : (
              "Sign in"
            )}
          </Button>
        </form>

        <div className="mt-6 text-center">
          <p className={`text-sm ${AUTH_MUTED}`}>
            Don&apos;t have an account?{" "}
            <Link href="/onboarding" className="font-medium text-indigo-600 transition-colors hover:text-indigo-700">
              Sign up
            </Link>
          </p>
        </div>

        <nav aria-label="Legal" className={`mt-4 flex flex-wrap justify-center gap-x-3 gap-y-2 text-xs ${AUTH_MUTED}`}>
          <a href="/terms" className="hover:text-slate-800">
            Terms
          </a>
          <a href="/privacy" className="hover:text-slate-800">
            Privacy
          </a>
          <a href="/cookies" className="hover:text-slate-800">
            Cookies
          </a>
          <ConsentSettingsButton className="hover:text-slate-800" />
        </nav>
      </CardContent>
    </AuthShell>
  );
}
