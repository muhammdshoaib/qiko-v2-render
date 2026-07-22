"use client";
import { useState } from "react";
import { useLocation } from "@/lib/wouter";
// import { trpc } from "@/lib/trpc";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Loader2, Eye, EyeOff, ArrowLeft, Check } from "lucide-react";
import { Link } from "@/lib/wouter";
import { toast } from "sonner";
import { signupAvatar } from "@/lib/avatarApi";
import { arePasswordRequirementsMet, getPasswordRequirements } from "@/lib/passwordRequirements";

export default function SignUp() {
  const [, setLocation] = useLocation();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [fieldErrors, setFieldErrors] = useState<{ name?: string; email?: string }>({});
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFieldErrors({});
    
    if (password !== confirmPassword) {
      toast.error("Passwords do not match");
      return;
    }

    if (!arePasswordRequirementsMet(password)) {
      toast.error("Please meet all password requirements");
      return;
    }
    
    setIsLoading(true);

    try {
      const normalizedEmail = email.trim().toLowerCase();
      const response = await signupAvatar({
        user_name: name,
        email: normalizedEmail,
        password,
      });

      toast.success("Account created successfully!");
      setLocation("/signup-success");
    } catch (error: unknown) {
      console.error("Signup error:", error);
      const err = error as Error & { validationErrors?: Record<string, string[]> };
      const validationErrors = err?.validationErrors;
      if (validationErrors) {
        setFieldErrors({
          name: validationErrors.user_name?.[0],
          email: validationErrors.email?.[0],
        });
      }
      toast.error(err?.message || "Registration failed");
    } finally {
      setIsLoading(false);
    }
  };

  const passwordRequirements = getPasswordRequirements(password);

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
            <div className="mx-auto mb-4">
              <span className="text-3xl font-bold bg-gradient-to-r from-purple-400 to-cyan-400 bg-clip-text text-transparent">
                Qiko
              </span>
            </div>
            <CardTitle className="text-2xl text-white">Create your account</CardTitle>
            <CardDescription className="text-slate-400">
              Start building your AI expert today
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="name" className="text-slate-300">Full Name</Label>
                <Input
                  id="name"
                  type="text"
                  placeholder="John Doe"
                  value={name}
                  onChange={(e) => {
                    setName(e.target.value);
                    if (fieldErrors.name) setFieldErrors((prev) => ({ ...prev, name: undefined }));
                  }}
                  required
                  className={`bg-slate-800/50 border-slate-700 text-white placeholder:text-slate-500 focus:border-cyan-500 focus:ring-cyan-500/20 ${
                    fieldErrors.name ? "border-red-500" : ""
                  }`}
                />
                {fieldErrors.name && <p className="text-xs text-red-400">{fieldErrors.name}</p>}
              </div>
              <div className="space-y-2">
                <Label htmlFor="email" className="text-slate-300">Email</Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value.toLowerCase());
                    if (fieldErrors.email) setFieldErrors((prev) => ({ ...prev, email: undefined }));
                  }}
                  required
                  className={`bg-slate-800/50 border-slate-700 text-white placeholder:text-slate-500 focus:border-cyan-500 focus:ring-cyan-500/20 ${
                    fieldErrors.email ? "border-red-500" : ""
                  }`}
                />
                {fieldErrors.email && <p className="text-xs text-red-400">{fieldErrors.email}</p>}
              </div>
              <div className="space-y-2">
                <Label htmlFor="password" className="text-slate-300">Password</Label>
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
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white transition-colors"
                  >
                    {showPassword ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
                  </button>
                </div>
                {/* Password requirements */}
                {password && (
                  <div className="mt-2 space-y-1">
                    {passwordRequirements.map((req, i) => (
                      <div key={i} className={`flex items-center gap-2 text-xs ${req.met ? 'text-green-400' : 'text-slate-500'}`}>
                        <Check className={`w-3 h-3 ${req.met ? 'opacity-100' : 'opacity-30'}`} />
                        {req.text}
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <div className="space-y-2">
                <Label htmlFor="confirmPassword" className="text-slate-300">Confirm Password</Label>
                <Input
                  id="confirmPassword"
                  type={showPassword ? "text" : "password"}
                  placeholder="••••••••"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                  className={`bg-slate-800/50 border-slate-700 text-white placeholder:text-slate-500 focus:border-cyan-500 focus:ring-cyan-500/20 ${
                    confirmPassword && password !== confirmPassword ? 'border-red-500' : ''
                  }`}
                />
                {confirmPassword && password !== confirmPassword && (
                  <p className="text-xs text-red-400">Passwords do not match</p>
                )}
              </div>

              <Button
                type="submit"
                disabled={isLoading || password !== confirmPassword}
                className="w-full bg-gradient-to-r from-purple-600 to-cyan-600 text-white border-0"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Creating account...
                  </>
                ) : (
                  "Create account"
                )}
              </Button>
            </form>

            <div className="mt-6 text-center">
              <p className="text-slate-400 text-sm">
                Already have an account?{" "}
                <Link href="/login" className="text-cyan-400 hover:text-cyan-300 transition-colors">
                  Sign in
                </Link>
              </p>
            </div>

            <p className="mt-4 text-xs text-slate-500 text-center">
              By creating an account, you agree to our{" "}
              <a href="/terms" className="text-cyan-400 hover:underline">Terms of Service</a>
              {", "}
              <a href="/privacy" className="text-cyan-400 hover:underline">Privacy Policy</a>
              {" "}and{" "}
              <a href="/cookies" className="text-cyan-400 hover:underline">Cookie Policy</a>
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
