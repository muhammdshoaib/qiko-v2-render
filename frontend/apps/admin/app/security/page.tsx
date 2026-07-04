"use client";

import { useState } from "react";
import { ShieldCheck } from "lucide-react";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { twofaSetup, twofaVerify } from "@/lib/api";

export default function SecurityPage() {
  const [secret, setSecret] = useState<string | null>(null);
  const [uri, setUri] = useState("");
  const [code, setCode] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function start() {
    setBusy(true); setError(null);
    try { const r = await twofaSetup(); setSecret(r.secret); setUri(r.provisioning_uri); }
    finally { setBusy(false); }
  }
  async function verify() {
    setBusy(true); setError(null);
    try { await twofaVerify(secret!, code); setEnabled(true); }
    catch { setError("Invalid code — try the current 6 digits from your app."); }
    finally { setBusy(false); }
  }

  return (
    <AppShell title="Security">
      <div className="mx-auto max-w-lg space-y-6">
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <CardTitle>Two-factor authentication</CardTitle>
              {enabled && <Badge variant="success">Enabled</Badge>}
            </div>
            <CardDescription>Protect your admin account with a TOTP authenticator app.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {enabled ? (
              <div className="flex items-center gap-2 text-sm text-success">
                <ShieldCheck className="size-4" /> 2FA is now active on your account.
              </div>
            ) : !secret ? (
              <Button onClick={start} disabled={busy}>{busy ? "Preparing…" : "Enable 2FA"}</Button>
            ) : (
              <>
                <div className="space-y-1.5">
                  <Label>1. Add this secret to your authenticator</Label>
                  <code className="block break-all rounded-md border border-border bg-muted px-3 py-2 text-xs">{secret}</code>
                  <p className="break-all text-xs text-muted-foreground">{uri}</p>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="code">2. Enter the 6-digit code</Label>
                  <Input id="code" inputMode="numeric" maxLength={6} placeholder="123456"
                    value={code} onChange={(e) => setCode(e.target.value)} />
                </div>
                {error && <p className="text-sm text-destructive">{error}</p>}
                <Button onClick={verify} disabled={code.length !== 6 || busy}>Verify & enable</Button>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
