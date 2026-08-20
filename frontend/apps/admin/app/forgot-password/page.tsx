"use client";

import { useState } from "react";
import Link from "next/link";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label } from "@qiko/ui";
import { forgotPassword } from "@/lib/api";

export default function ForgotPasswordPage() {
  const creatorBaseUrl = process.env.NEXT_PUBLIC_CREATOR_BASE_URL || "/";
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setMessage(null);
    try {
      const normalisedEmail = email.trim().toLowerCase();
      await forgotPassword(normalisedEmail);
      window.location.assign(`/reset-password?email=${encodeURIComponent(normalisedEmail)}`);
    } catch {
      setMessage("Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4 bg-background">
      <Card className="w-full max-w-md bg-card/90 border-border/50">
        <CardHeader className="text-center">
          <Link href={creatorBaseUrl}>
            <img
              src="/qiko-logo.webp"
              alt="Qiko"
              width={120}
              height={48}
              className="mx-auto mb-3 h-12 w-[120px] object-contain"
            />
          </Link>
          <CardTitle>Forgot Password</CardTitle>
          <CardDescription>Enter your admin email to receive a one-time code.</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={onSubmit}>
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com" required />
            </div>
            {message && <p role="status" className="text-sm text-muted-foreground">{message}</p>}
            <Button type="submit" className="w-full" disabled={loading}>{loading ? "Sending..." : "Send one-time code"}</Button>
          </form>
          <p className="mt-4 text-xs text-muted-foreground">
            Back to <Link href="/login" className="text-primary hover:underline">sign in</Link>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
