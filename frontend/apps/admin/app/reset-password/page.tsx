"use client";

import { Suspense } from "react";

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<ResetPasswordSkeleton />}>
      <ResetPasswordForm />
    </Suspense>
  );
}

function ResetPasswordSkeleton() {
  return (
    <div className="flex min-h-screen items-center justify-center px-4 bg-background">
      <div className="h-96 w-full max-w-md animate-pulse rounded-xl bg-card/50" />
    </div>
  );
}

import { useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Eye, EyeOff } from "lucide-react";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label } from "@qiko/ui";
import { resetPassword } from "@/lib/api";

function ResetPasswordForm() {
  const searchParams = useSearchParams();
  const email = searchParams?.get("email") ?? "";

  const [otp, setOtp] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);

    if (otp.length !== 6) {
      setError("Please enter the 6-digit code from your email.");
      setLoading(false);
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      setLoading(false);
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match.");
      setLoading(false);
      return;
    }

    try {
      await resetPassword(email, otp, password);
      setSuccess(true);
    } catch {
      setError("Failed to reset password. The code may be invalid or expired.");
    } finally {
      setLoading(false);
    }
  }

  if (!email) {
    return (
      <div className="flex min-h-screen items-center justify-center px-4 bg-background">
        <Card className="w-full max-w-md bg-card/90 border-border/50">
          <CardHeader className="text-center">
            <CardTitle>Reset Password</CardTitle>
            <CardDescription>No email address was provided.</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              <Link href="/forgot-password" className="text-primary hover:underline">Request a new code</Link>
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (success) {
    return (
      <div className="flex min-h-screen items-center justify-center px-4 bg-background">
        <Card className="w-full max-w-md bg-card/90 border-border/50">
          <CardHeader className="text-center">
            <CardTitle>Password reset</CardTitle>
            <CardDescription>Your admin password has been updated.</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              <Link href="/login" className="text-primary hover:underline">Sign in with your new password</Link>
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4 bg-background">
      <Card className="w-full max-w-md bg-card/90 border-border/50">
        <CardHeader className="text-center">
          <img
            src="/qiko-logo.webp"
            alt="Qiko"
            width={120}
            height={48}
            className="mx-auto mb-3 h-12 w-[120px] object-contain"
          />
          <CardTitle>Reset admin password</CardTitle>
          <CardDescription>Enter the one-time code from your email and choose a new password.</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={onSubmit}>
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" value={email} disabled />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="otp">One-time code</Label>
              <Input
                id="otp"
                inputMode="numeric"
                maxLength={6}
                value={otp}
                onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))}
                placeholder="123456"
                required
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">New password</Label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="At least 8 characters"
                  className="pr-10"
                  required
                  minLength={8}
                />
                <button
                  type="button"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  className="absolute inset-y-0 right-0 flex items-center pr-3 text-muted-foreground hover:text-foreground transition-colors"
                  onClick={() => setShowPassword((v) => !v)}
                >
                  {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="confirm">Confirm password</Label>
              <Input
                id="confirm"
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                placeholder="Re-enter password"
                required
              />
            </div>
            {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? "Resetting..." : "Reset password"}
            </Button>
          </form>
          <p className="mt-4 text-xs text-muted-foreground">
            Back to <Link href="/login" className="text-primary hover:underline">sign in</Link>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
