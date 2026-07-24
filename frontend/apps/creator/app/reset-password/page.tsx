"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useRoute, Link } from "@/lib/wouter";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { InputOTP, InputOTPGroup, InputOTPSlot } from "@/components/ui/input-otp";
import { Loader2, Eye, EyeOff, ArrowLeft, AlertCircle, Check } from "lucide-react";
import { toast } from "sonner";
import { resetPasswordAvatar } from "@/lib/avatarApi";
import { useAuth } from "@/_core/hooks/useAuth";
import { useAppDispatch } from "@/store/hooks";
import { setAuth, type UserInfo } from "@/store/slices/authSlice";
import { arePasswordRequirementsMet, getPasswordRequirements } from "@/lib/passwordRequirements";
import {
  clearPasswordResetEmail,
  getPasswordResetSessionStorage,
  resolvePasswordResetEmail,
} from "@/lib/password-reset-session";

export default function ResetPassword() {
  const router = useRouter();
  const dispatch = useAppDispatch();
  const [, pathParams] = useRoute("/reset-password/:otp");
  const { isAuthenticated, loading } = useAuth();
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

  if (loading || !emailResolved || !email) {
    return (
      <div className="min-h-screen bg-[#050810] flex items-center justify-center">
        <div className="text-slate-400">Loading...</div>
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
      const result = await resetPasswordAvatar({
        email,
        otp,
        password,
      });

      const token = result.data?.token;
      const user = result.data?.user;
      if (token) {
        const userInfo: UserInfo | null = user
          ? ({
              ...user,
              id: user.id != null ? String(user.id) : undefined,
              name: user.user_name,
            } as UserInfo)
          : null;

        // If user is already logged in, keep them logged in with the new token.
        // `setAuth` persists to localStorage (`qiko_session_token` + `qiko_user_info`).
        if (isAuthenticated) {
          dispatch(setAuth({ token, userInfo }));
        }
      }
      const storage = getPasswordResetSessionStorage(window);
      clearPasswordResetEmail(storage);
      setSuccess(true);
      toast.success(
        isAuthenticated
          ? "Password reset successfully."
          : "Password reset successfully. You can now sign in with your new password.",
      );
    } catch (error: any) {
      console.error("Reset password error:", error);
      const errorMsg = error.message || "Failed to reset password. Please try again.";
      setErrorMessage(errorMsg);
      toast.error(errorMsg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#050810] flex items-center justify-center p-4">
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-purple-500/10 rounded-full blur-3xl" />
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-cyan-500/10 rounded-full blur-3xl" />
      </div>

      <div className="relative z-10 w-full max-w-md">
        <Link href="/login" className="inline-flex items-center gap-2 text-slate-400 hover:text-white mb-8 transition-colors">
          <ArrowLeft className="w-4 h-4" />
          Back
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
            <CardTitle className="text-2xl text-white">Reset your password</CardTitle>
            {!success && (
              <CardDescription className="text-slate-400">
                We have sent a one-time code to the provided email address. Please check your email and enter the code below.
              </CardDescription>
            )}
          </CardHeader>
          <CardContent>
            {success ? (
              <div className="space-y-4">
                {isAuthenticated ? (<div className="p-4 bg-green-500/10 border border-green-500/30 rounded-lg">
                    <p className="text-green-400 text-sm text-center">
                      Your password has been reset.
                    </p>
                  </div>): (
                  <div className="p-4 bg-green-500/10 border border-green-500/30 rounded-lg">
                    <p className="text-green-400 text-sm text-center">
                      Your password has been reset. You can now sign in with your new password.
                    </p>
                  </div>
                )}
                { !isAuthenticated && <Link href="/login">
                  <Button className="w-full bg-gradient-to-r from-purple-600 to-cyan-600 hover:from-purple-500 hover:to-cyan-500 text-white border-0">
                    Sign in
                  </Button>
                </Link>}
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="space-y-4 w-full">
                {errorMessage && (
                  <div className="flex items-start gap-3 p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
                    <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                    <p className="text-red-400 text-sm">{errorMessage}</p>
                  </div>
                )}

                <div className="space-y-2 w-full">
                  <Label htmlFor="email" className="text-slate-300 block">Email</Label>
                  <Input
                    id="email"
                    type="email"
                    placeholder="you@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    disabled={true}
                    className="w-full bg-slate-800/50 border-slate-700 text-white placeholder:text-slate-500 focus:border-cyan-500 focus:ring-cyan-500/20"
                  />
                </div>

                <div className="space-y-2 w-full">
                  <Label className="text-slate-300 block">Enter 6-digit authentication code</Label>
                  <InputOTP
                    maxLength={6}
                    value={otp}
                    onChange={(val) => setOtp(val.replace(/\D/g, ""))}
                    inputMode="numeric"
                    containerClassName="justify-start gap-2 w-full"
                  >
                    <InputOTPGroup className="gap-2 [&>div]:border-slate-600 [&>div]:bg-slate-800/50 [&>div]:text-white [&>div[data-active=true]]:border-cyan-500 [&>div[data-active=true]]:ring-2 [&>div[data-active=true]]:ring-cyan-500/20">
                      <InputOTPSlot index={0} className="h-9 w-15 rounded-lg border text-lg font-mono tabular-nums" />
                      <InputOTPSlot index={1} className="h-9 w-15 rounded-lg border text-lg font-mono tabular-nums" />
                      <InputOTPSlot index={2} className="h-9 w-15 rounded-lg border text-lg font-mono tabular-nums" />
                      <InputOTPSlot index={3} className="h-9 w-15 rounded-lg border text-lg font-mono tabular-nums" />
                      <InputOTPSlot index={4} className="h-9 w-15 rounded-lg border text-lg font-mono tabular-nums" />
                      <InputOTPSlot index={5} className="h-9 w-15 rounded-lg border text-lg font-mono tabular-nums" />
                    </InputOTPGroup>
                  </InputOTP>
                </div>

                <div className="space-y-2 w-full">
                  <Label htmlFor="password" className="text-slate-300 block">New password</Label>
                  <div className="relative">
                    <Input
                      id="password"
                      type={showPassword ? "text" : "password"}
                      placeholder="••••••••"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      required
                      className="w-full bg-slate-800/50 border-slate-700 text-white placeholder:text-slate-500 focus:border-cyan-500 focus:ring-cyan-500/20 pr-10"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white transition-colors"
                    >
                      {showPassword ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
                    </button>
                  </div>
                  {password && (
                    <div className="mt-2 space-y-1">
                      {passwordRequirements.map((req, i) => (
                        <div
                          key={i}
                          className={`flex items-center gap-2 text-xs ${req.met ? "text-green-400" : "text-slate-500"}`}
                        >
                          <Check className={`w-3 h-3 ${req.met ? "opacity-100" : "opacity-30"}`} />
                          {req.text}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="space-y-2 w-full">
                  <Label htmlFor="confirmPassword" className="text-slate-300 block">Confirm password</Label>
                  <Input
                    id="confirmPassword"
                    type={showPassword ? "text" : "password"}
                    placeholder="••••••••"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    required
                    className={`w-full bg-slate-800/50 border-slate-700 text-white placeholder:text-slate-500 focus:border-cyan-500 focus:ring-cyan-500/20 ${
                      confirmPassword && password !== confirmPassword ? "border-red-500" : ""
                    }`}
                  />
                  {confirmPassword && password !== confirmPassword && (
                    <p className="text-xs text-red-400">Passwords do not match</p>
                  )}
                </div>

                <Button
                  type="submit"
                  disabled={isLoading || password !== confirmPassword || otp.length !== 6}
                  className="w-full bg-gradient-to-r from-purple-600 to-cyan-600 hover:from-purple-500 hover:to-cyan-500 text-white border-0"
                >
                  {isLoading ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      Resetting...
                    </>
                  ) : (
                    "Reset Password"
                  )}
                </Button>
              </form>
            )}

            {!success && !isAuthenticated && (
              <div className="mt-6 text-center">
                <p className="text-slate-400 text-sm">
                  Remember your password?{" "}
                  <Link href="/login" className="text-cyan-400 hover:text-cyan-300 transition-colors">
                    Sign in
                  </Link>
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
