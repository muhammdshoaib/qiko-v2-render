"use client";
import { useState, useEffect } from "react";
import { useLocation } from "@/lib/wouter";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/_core/hooks/useAuth";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Loader2, ArrowLeft, AlertCircle } from "lucide-react";
import { Link } from "@/lib/wouter";
import { toast } from "sonner";
import { forgotPasswordAvatar } from "@/lib/avatarApi";

export default function ForgotPassword() {
  const [, setLocation] = useLocation();
  const { isAuthenticated, loading, user } = useAuth();
  const [email, setEmail] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // useEffect(() => {
  //   if (!loading && isAuthenticated) setLocation("/dashboard");
  // }, [loading, isAuthenticated, setLocation]);

  useEffect(() => {
    if (!loading && user?.email && !email) {
      setEmail(String(user.email));
    }
  }, [loading, user?.email, email]);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#050810] flex items-center justify-center">
        <div className="text-slate-400">Loading...</div>
      </div>
    );
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setIsLoading(true);

    try {
      await forgotPasswordAvatar(email);
      toast.success("Check your email for the verification code.");
      setLocation(`/reset-password?email=${encodeURIComponent(email)}`);
    } catch (error: any) {
      console.error("Forgot password error:", error);
      const errorMsg = error.message || "Failed to send reset email. Please try again.";
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
            <div className="mx-auto mb-4">
              <span className="text-3xl font-bold bg-gradient-to-r from-purple-400 to-cyan-400 bg-clip-text text-transparent">
                Qiko
              </span>
            </div>
            <CardTitle className="text-2xl text-white">
              {isAuthenticated ? "Change password?" : "Forgot password?"}
            </CardTitle>
            <CardDescription className="text-slate-400">
              { isAuthenticated ? `We’ll send a verification code to ${user?.email}
 to reset your password.` : "Enter your email and we'll send you a verification code to reset your password"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
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
                    placeholder="you@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    disabled={isAuthenticated}
                    className="bg-slate-800/50 border-slate-700 text-white placeholder:text-slate-500 focus:border-cyan-500 focus:ring-cyan-500/20"
                  />
                </div>

                <Button
                  type="submit"
                  disabled={isLoading}
                  className="w-full bg-gradient-to-r from-purple-600 to-cyan-600 hover:from-purple-500 hover:to-cyan-500 text-white border-0"
                >
                  {isLoading ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      Sending...
                    </>
                  ) : (
                    "Send verification code"
                  )}
                </Button>
              </form>

            {!isAuthenticated && (
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
