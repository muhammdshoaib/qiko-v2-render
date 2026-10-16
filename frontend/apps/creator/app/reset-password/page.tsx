"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useRoute, Link } from "@/lib/wouter";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { InputOTP, InputOTPGroup, InputOTPSlot } from "@/components/ui/input-otp";
import { Loader2, Eye, EyeOff, AlertCircle, Check } from "lucide-react";
import { toast } from "sonner";
import { resetPasswordAvatar } from "@/lib/avatarApi";
import { arePasswordRequirementsMet, getPasswordRequirements } from "@/lib/passwordRequirements";
import {
  clearPasswordResetEmail,
  getPasswordResetSessionStorage,
  resolvePasswordResetEmail,
} from "@/lib/password-reset-session";
import {
  AUTH_BUTTON,
  AUTH_INPUT,
  AUTH_LABEL,
  AUTH_MUTED,
  AuthLogo,
  AuthShell,
} from "@/components/auth/auth-shell";

export default function ResetPassword() {
  const router = useRouter();
  const [, pathParams] = useRoute("/reset-password/:otp");
  const pathOtp = pathParams?.otp ?? "";
  const queryParams = typeof window !== "undefined" ? new URLSearchParams(window.location.search) : null;
  const queryOtp = queryParams?.get("otp") ?? queryParams?.get("token") ?? "";
  const queryEmail = queryParams?.get("email") ?? null;
  const initialOtp = pathOtp || queryOtp;

  const [email, setEmail] = useState("");
  const [emailResolved, setEmailResolved] = useState(false);
  const [otp, setOtp] = useState(initialOtp);
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (initialOtp) setOtp(initialOtp);
  }, [initialOtp]);
  useEffect(() => {
    if (typeof window === "undefined") return;
    const storage = getPasswordResetSessionStorage(window);
    const resolvedEmail = resolvePasswordResetEmail(queryEmail, storage);
    if (resolvedEmail) {
      setEmail(resolvedEmail);
    } else {
      router.replace("/forgot-password");
    }
    setEmailResolved(true);
  }, [queryEmail, router]);

  if (!emailResolved || !email) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <div className="text-slate-500">Loading...</div>
      </div>
    );
  }

  const passwordRequirements = getPasswordRequirements(password);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    if (password !== confirmPassword) {
      toast.error("Passwords do not match");
      return;
    }

    if (!arePasswordRequirementsMet(password)) {
      toast.error("Please meet all password requirements");
      return;
    }

    if (!otp) {
      setErrorMessage("Please enter the verification code.");
      return;
    }

    setIsLoading(true);

    try {
      await resetPasswordAvatar({
        email,
        otp,
        password,
      });
      const storage = getPasswordResetSessionStorage(window);
      clearPasswordResetEmail(storage);
      setSuccess(true);
      toast.success("Password reset successfully. You can now sign in with your new password.");
    } catch (error: unknown) {
      console.error("Reset password error:", error);
      const errorMsg =
        error instanceof Error ? error.message : "Failed to reset password. Please try again.";
      setErrorMessage(errorMsg);
      toast.error(errorMsg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <AuthShell backHref="/login" backLabel="Back">
      <CardHeader className="space-y-1 text-center">
        <AuthLogo />
        <CardTitle className="text-2xl font-bold tracking-tight text-slate-900">Reset your password</CardTitle>
        {!success && (
          <CardDescription className={AUTH_MUTED}>
            We have sent a one-time code to the provided email address. Please check your email and enter the code
            below.
          </CardDescription>
        )}
      </CardHeader>
      <CardContent>
        {success ? (
          <div className="space-y-4">
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4">
              <p className="text-center text-sm text-emerald-800">
                Your password has been reset. You can now sign in with your new password.
              </p>
            </div>
            <Link href="/login">
              <Button className={AUTH_BUTTON}>Sign in</Button>
            </Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="w-full space-y-4">
            {errorMessage && (
              <div className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-3">
                <AlertCircle className="mt-0.5 size-5 shrink-0 text-red-600" />
                <p className="text-sm text-red-700">{errorMessage}</p>
              </div>
            )}

            <div className="w-full space-y-2">
              <Label htmlFor="email" className={`${AUTH_LABEL} block`}>
                Email
              </Label>
              <Input
                id="email"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                disabled
                className={`w-full ${AUTH_INPUT}`}
              />
            </div>

            <div className="w-full space-y-2">
              <Label className={`${AUTH_LABEL} block`}>Enter 6-digit authentication code</Label>
              <InputOTP
                maxLength={6}
                value={otp}
                onChange={(val) => setOtp(val.replace(/\D/g, ""))}
                inputMode="numeric"
                containerClassName="justify-start gap-2 w-full"
              >
                <InputOTPGroup className="gap-2 [&>div]:border-slate-200 [&>div]:bg-white [&>div]:text-slate-900 [&>div[data-active=true]]:border-indigo-400 [&>div[data-active=true]]:ring-2 [&>div[data-active=true]]:ring-indigo-300/40">
                  <InputOTPSlot index={0} className="h-9 w-15 rounded-lg border text-lg font-mono tabular-nums" />
                  <InputOTPSlot index={1} className="h-9 w-15 rounded-lg border text-lg font-mono tabular-nums" />
                  <InputOTPSlot index={2} className="h-9 w-15 rounded-lg border text-lg font-mono tabular-nums" />
                  <InputOTPSlot index={3} className="h-9 w-15 rounded-lg border text-lg font-mono tabular-nums" />
                  <InputOTPSlot index={4} className="h-9 w-15 rounded-lg border text-lg font-mono tabular-nums" />
                  <InputOTPSlot index={5} className="h-9 w-15 rounded-lg border text-lg font-mono tabular-nums" />
                </InputOTPGroup>
              </InputOTP>
            </div>

            <div className="w-full space-y-2">
              <Label htmlFor="password" className={`${AUTH_LABEL} block`}>
                New password
              </Label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className={`w-full pr-10 ${AUTH_INPUT}`}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-0 top-1/2 flex size-11 -translate-y-1/2 items-center justify-center text-slate-400 transition-colors hover:text-slate-700 sm:right-3 sm:size-9"
                >
                  {showPassword ? <Eye className="size-4" /> : <EyeOff className="size-4" />}
                </button>
              </div>
              {password && (
                <div className="mt-2 space-y-1">
                  {passwordRequirements.map((req, i) => (
                    <div
                      key={i}
                      className={`flex items-center gap-2 text-xs ${req.met ? "text-emerald-600" : "text-slate-500"}`}
                    >
                      <Check className={`size-3 ${req.met ? "opacity-100" : "opacity-30"}`} />
                      {req.text}
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="w-full space-y-2">
              <Label htmlFor="confirmPassword" className={`${AUTH_LABEL} block`}>
                Confirm password
              </Label>
              <Input
                id="confirmPassword"
                type={showPassword ? "text" : "password"}
                placeholder="••••••••"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                className={`w-full ${AUTH_INPUT} ${
                  confirmPassword && password !== confirmPassword ? "border-red-500" : ""
                }`}
              />
              {confirmPassword && password !== confirmPassword && (
                <p className="text-xs text-red-600">Passwords do not match</p>
              )}
            </div>

            <Button
              type="submit"
              disabled={isLoading || password !== confirmPassword || otp.length !== 6}
              className={AUTH_BUTTON}
            >
              {isLoading ? (
                <>
                  <Loader2 className="mr-2 size-4 animate-spin" />
                  Resetting...
                </>
              ) : (
                "Reset Password"
              )}
            </Button>
          </form>
        )}

        {!success && (
          <div className="mt-6 text-center">
            <p className={`text-sm ${AUTH_MUTED}`}>
              Remember your password?{" "}
              <Link href="/login" className="font-medium text-indigo-600 transition-colors hover:text-indigo-700">
                Sign in
              </Link>
            </p>
          </div>
        )}
      </CardContent>
    </AuthShell>
  );
}
