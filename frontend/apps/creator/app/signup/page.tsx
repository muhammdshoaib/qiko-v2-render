"use client";
import { useEffect, useState } from "react";
import { useLocation } from "@/lib/wouter";
// import { trpc } from "@/lib/trpc";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Loader2, ArrowLeft } from "lucide-react";
import { Link } from "@/lib/wouter";
import { toast } from "sonner";
import { signupAvatar } from "@/lib/avatarApi";
import { ConsentSettingsButton } from "@/components/consent/ConsentUI";
import { COOKIES_RELEASE_ID, PRIVACY_RELEASE_ID, TERMS_RELEASE_ID } from "@/lib/consent/consent-record";

export default function SignUp() {
  const [, setLocation] = useLocation();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [fieldErrors, setFieldErrors] = useState<{ name?: string; email?: string }>({});
  const [acceptedPolicies, setAcceptedPolicies] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const inviteToken =
    typeof window === "undefined"
      ? undefined
      : new URLSearchParams(window.location.search).get("invite") ?? undefined;

  useEffect(() => {
    if (!inviteToken) {
      setLocation("/onboarding");
    }
  }, [inviteToken, setLocation]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFieldErrors({});

    if (!acceptedPolicies) {
      toast.error("You must confirm your authority and acknowledge the Terms and Privacy Policy");
      return;
    }

    setIsLoading(true);

    try {
      const normalizedEmail = email.trim().toLowerCase();
      await signupAvatar({
        user_name: name,
        email: normalizedEmail,
        invite_token: inviteToken,
        terms_release_id: TERMS_RELEASE_ID,
        privacy_release_id: PRIVACY_RELEASE_ID,
        cookies_release_id: COOKIES_RELEASE_ID,
      });

      toast.success("Check your email to verify your account");
      setLocation(`/verify-email?email=${encodeURIComponent(normalizedEmail)}`);
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
                  placeholder={"you" + "@" + "example.com"}
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

              <div className="flex items-start gap-3 rounded-lg border border-slate-700 bg-slate-900/60 p-3">
                <input
                  id="policy-acceptance"
                  type="checkbox"
                  required
                  checked={acceptedPolicies}
                  onChange={(event) => setAcceptedPolicies(event.target.checked)}
                  className="mt-0.5 size-4 shrink-0 accent-cyan-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300"
                />
                <label htmlFor="policy-acceptance" className="text-xs leading-5 text-slate-300">
                  I confirm that I am authorised to bind my organisation, agree to the{" "}
                  <a href="/terms" target="_blank" rel="noreferrer" className="text-cyan-400 hover:underline">Terms of Service</a>
                  {", and acknowledge the "}
                  <a href="/privacy" target="_blank" rel="noreferrer" className="text-cyan-400 hover:underline">Privacy Policy</a>.
                </label>
              </div>

              <Button
                type="submit"
                disabled={isLoading || !acceptedPolicies}
                className="min-h-11 w-full border-0 bg-gradient-to-r from-purple-600 to-cyan-600 text-white sm:min-h-9"
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
