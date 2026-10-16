"use client";
import { useEffect, useState } from "react";
import { useLocation } from "@/lib/wouter";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Loader2 } from "lucide-react";
import { Link } from "@/lib/wouter";
import { toast } from "sonner";
import { signupAvatar } from "@/lib/avatarApi";
import { ConsentSettingsButton } from "@/components/consent/ConsentUI";
import { COOKIES_RELEASE_ID, PRIVACY_RELEASE_ID, TERMS_RELEASE_ID } from "@/lib/consent/consent-record";
import {
  AUTH_BUTTON,
  AUTH_INPUT,
  AUTH_LABEL,
  AUTH_MUTED,
  AuthLogo,
  AuthShell,
} from "@/components/auth/auth-shell";

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
    <AuthShell>
      <CardHeader className="space-y-1 text-center">
        <AuthLogo />
        <CardTitle className="text-2xl font-bold tracking-tight text-slate-900">Create your account</CardTitle>
        <CardDescription className={AUTH_MUTED}>Start building your AI expert today</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="name" className={AUTH_LABEL}>
              Full Name
            </Label>
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
              className={`${AUTH_INPUT} ${fieldErrors.name ? "border-red-500" : ""}`}
            />
            {fieldErrors.name && <p className="text-xs text-red-600">{fieldErrors.name}</p>}
          </div>
          <div className="space-y-2">
            <Label htmlFor="email" className={AUTH_LABEL}>
              Email
            </Label>
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
              className={`${AUTH_INPUT} ${fieldErrors.email ? "border-red-500" : ""}`}
            />
            {fieldErrors.email && <p className="text-xs text-red-600">{fieldErrors.email}</p>}
          </div>

          <div className="flex items-start gap-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
            <input
              id="policy-acceptance"
              type="checkbox"
              required
              checked={acceptedPolicies}
              onChange={(event) => setAcceptedPolicies(event.target.checked)}
              className="mt-0.5 size-4 shrink-0 accent-indigo-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
            />
            <label htmlFor="policy-acceptance" className="text-xs leading-5 text-slate-600">
              I confirm that I am authorised to bind my organisation, agree to the{" "}
              <a href="/terms" target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline">
                Terms of Service
              </a>
              {", and acknowledge the "}
              <a href="/privacy" target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline">
                Privacy Policy
              </a>
              .
            </label>
          </div>

          <Button type="submit" disabled={isLoading || !acceptedPolicies} className={AUTH_BUTTON}>
            {isLoading ? (
              <>
                <Loader2 className="mr-2 size-4 animate-spin" />
                Creating account...
              </>
            ) : (
              "Create account"
            )}
          </Button>
        </form>

        <div className="mt-6 text-center">
          <p className={`text-sm ${AUTH_MUTED}`}>
            Already have an account?{" "}
            <Link href="/login" className="font-medium text-indigo-600 transition-colors hover:text-indigo-700">
              Sign in
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
