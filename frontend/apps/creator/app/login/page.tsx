"use client";
import { useState } from "react";
import { useLocation } from "@/lib/wouter";
import { useAppDispatch } from "@/store/hooks";
import { setAuth } from "@/store/slices/authSlice";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Loader2, Eye, EyeOff, ArrowLeft, AlertCircle } from "lucide-react";
import { Link } from "@/lib/wouter";
import { toast } from "sonner";
import { loginAvatar } from "@/lib/avatarApi";
import { ConsentSettingsButton } from "@/components/consent/ConsentUI";

export default function Login() {
  const dispatch = useAppDispatch();
  const [, setLocation] = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [totp, setTotp] = useState("");
  // Revealed only once the server says this account has 2FA, so the common case stays a 2-field form.
  const [twoFactorRequired, setTwoFactorRequired] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setIsLoading(true);

    try {
      const res = await loginAvatar({ email, password, totp: totp.trim() || undefined });

      if (res?.data?.token) {
        // The session lives in an httpOnly cookie; nothing usable is returned to the client.
        dispatch(setAuth({ token: res.data.token, userInfo: (res?.data?.user as never) ?? null }));
        toast.success("Welcome back!");
        window.location.href = "/dashboard";
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
      } else {
        setErrorMessage(errorMsg);
        toast.error(errorMsg);
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#050810] flex items-center justify-center p-4">
      {/* Background gradient effects */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-purple-500/10 rounded-full blur-3xl" />
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-cyan-500/10 rounded-full blur-3xl" />
      </div>

      <div className="relative z-10 w-full max-w-md">
        {/* Back to home */}
        <Link href="/" className="inline-flex items-center gap-2 text-slate-400 hover:text-white mb-8 transition-colors">
          <ArrowLeft className="w-4 h-4" />
          Back to home
        </Link>

        <Card className="bg-slate-900/50 border-slate-800 backdrop-blur-sm">
          <CardHeader className="text-center">
            <img
              src="/qiko-logo-email.png"
              alt="Qiko"
              width={120}
              height={48}
              className="mx-auto mb-4 h-12 w-[120px] object-contain"
            />
            <CardTitle className="text-2xl text-white">Welcome back</CardTitle>
            <CardDescription className="text-slate-400">
              Sign in to your account to continue
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Error message display */}
              {errorMessage && (
                <div className="flex items-start gap-3 p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
                  <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                  <p className="text-red-400 text-sm">{errorMessage}</p>
                </div>
              )}

              <div className="space-y-2">
                <Label htmlFor="email" className="text-slate-300">Email</Label>
                <Input
                  id="email"
                  type="email"
                  placeholder={"you" + "@" + "example.com"}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="bg-slate-800/50 border-slate-700 text-white placeholder:text-slate-500 focus:border-cyan-500 focus:ring-cyan-500/20"
                />
              </div>
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label htmlFor="password" className="text-slate-300">Password</Label>
                  <Link href="/forgot-password" className="text-xs text-cyan-400 hover:text-cyan-300 transition-colors">
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
                    className="bg-slate-800/50 border-slate-700 text-white placeholder:text-slate-500 focus:border-cyan-500 focus:ring-cyan-500/20 pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                    className="absolute right-0 top-1/2 flex size-11 -translate-y-1/2 items-center justify-center text-slate-400 transition-colors hover:text-white sm:size-9"
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              {twoFactorRequired && (
                <div className="space-y-2">
                  <Label htmlFor="totp" className="text-slate-300">Authenticator or backup code</Label>
                  <Input
                    id="totp"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    maxLength={64}
                    autoFocus
                    placeholder="6-digit code"
                    value={totp}
                    onChange={(e) => setTotp(e.target.value)}
                    className="bg-slate-800/50 border-slate-700 text-white placeholder:text-slate-500 focus:border-cyan-500 focus:ring-cyan-500/20"
                  />
                  <p className="text-xs text-slate-500">
                    Lost your device? Use one of your saved backup codes.
                  </p>
                </div>
              )}

              <Button
                type="submit"
                disabled={isLoading}
                className="min-h-11 w-full border-0 bg-gradient-to-r from-purple-600 to-cyan-600 text-white sm:min-h-9"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Signing in...
                  </>
                ) : (
                  "Sign in"
                )}
              </Button>
            </form>

            <div className="mt-6 text-center">
              <p className="text-slate-400 text-sm">
                Don't have an account?{" "}
                <Link href="/onboarding" className="text-cyan-400 hover:text-cyan-300 transition-colors">
                  Sign up
                </Link>
              </p>
            </div>

            <nav aria-label="Legal" className="mt-4 flex flex-wrap justify-center gap-x-3 gap-y-2 text-xs text-slate-500">
              <a href="/terms" className="hover:text-slate-300">Terms</a>
              <a href="/privacy" className="hover:text-slate-300">Privacy</a>
              <a href="/cookies" className="hover:text-slate-300">Cookies</a>
              <ConsentSettingsButton className="hover:text-slate-300" />
            </nav>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
