"use client";
import { useState, useEffect } from "react";
import { useLocation } from "@/lib/wouter";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/_core/hooks/useAuth";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Loader2, AlertCircle } from "lucide-react";
import { Link } from "@/lib/wouter";
import { toast } from "sonner";
import { forgotPasswordAvatar } from "@/lib/avatarApi";
import {
  getPasswordResetSessionStorage,
  normalisePasswordResetEmail,
  storePasswordResetEmail,
} from "@/lib/password-reset-session";
import {
  AUTH_BUTTON,
  AUTH_INPUT,
  AUTH_LABEL,
  AUTH_MUTED,
  AuthLogo,
  AuthShell,
} from "@/components/auth/auth-shell";

export default function ForgotPassword() {
  const [, setLocation] = useLocation();
  const { isAuthenticated, loading, user } = useAuth();
  const [email, setEmail] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (!loading && user?.email && !email) {
      setEmail(String(user.email));
    }
  }, [loading, user?.email, email]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <div className="text-slate-500">Loading...</div>
      </div>
    );
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setIsLoading(true);

    try {
      const normalisedEmail = normalisePasswordResetEmail(email);
      await forgotPasswordAvatar(normalisedEmail);
      const storage = getPasswordResetSessionStorage(window);
      storePasswordResetEmail(storage, normalisedEmail);
      toast.success("One-time code sent. Check your email and enter the code below.");
      setLocation(`/reset-password?email=${encodeURIComponent(normalisedEmail)}`);
    } catch (error: unknown) {
      console.error("Forgot password error:", error);
      const errorMsg =
        error instanceof Error ? error.message : "Failed to send reset email. Please try again.";
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
        <CardTitle className="text-2xl font-bold tracking-tight text-slate-900">
          {isAuthenticated ? "Change password?" : "Forgot password?"}
        </CardTitle>
        <CardDescription className={AUTH_MUTED}>
          {isAuthenticated
            ? `We'll send a one-time code to ${user?.email}.`
            : "Enter your email and we'll send you a one-time code."}
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
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              disabled={isAuthenticated}
              className={AUTH_INPUT}
            />
          </div>

          <Button type="submit" disabled={isLoading} className={AUTH_BUTTON}>
            {isLoading ? (
              <>
                <Loader2 className="mr-2 size-4 animate-spin" />
                Sending...
              </>
            ) : (
              "Send one-time code"
            )}
          </Button>
        </form>

        {!isAuthenticated && (
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
