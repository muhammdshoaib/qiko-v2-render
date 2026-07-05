"use client";

import { useState } from "react";
import QRCode from "qrcode";
import { ShieldCheck } from "lucide-react";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { twofaSetup, twofaVerify } from "@/lib/api";

export default function SecurityPage() {
  const [secret, setSecret] = useState<string | null>(null);
  const [qr, setQr] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function start() {
    setBusy(true); setError(null);
    try {
      const r = await twofaSetup();
      setSecret(r.secret);
      setQr(await QRCode.toDataURL(r.provisioning_uri, { width: 192, margin: 1 }));
    } finally {
      setBusy(false);
    }
  }
  async function verify() {
    setBusy(true); setError(null);
    try { await twofaVerify(secret!, code); setEnabled(true); }
    catch { setError("Invalid code — try the current 6 digits from your app."); }
    finally { setBusy(false); }
  }

  return (
    <AppShell title="Security">
      <div className="mx-auto max-w-md space-y-6">
        <Card className="border-border/50 bg-card/90 shadow-lg">
          <CardHeader className="space-y-1">
            <div className="flex items-center gap-2">
              <div className="flex size-9 items-center justify-center rounded-lg bg-primary/15 text-primary">
                <ShieldCheck className="size-5" />
              </div>
              <div>
                <CardTitle className="flex items-center gap-2">
                  Set up Google Authenticator
                  {enabled && <Badge variant="success">Enabled</Badge>}
                </CardTitle>
                <CardDescription className="mt-1">
                  Scan the QR code with Google Authenticator, then enter the 6-digit code to finish setup.
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-5">
            {enabled ? (
              <div className="flex items-center gap-2 text-sm text-success">
                <ShieldCheck className="size-4" /> 2FA is now active on your account.
              </div>
            ) : !secret ? (
              <Button onClick={start} disabled={busy} className="w-full">{busy ? "Preparing..." : "Enable 2FA"}</Button>
            ) : (
              <>
                {qr && (
                  <div className="flex justify-center rounded-xl border border-border/40 bg-secondary/20 p-4">
                    <img src={qr} alt="Google Authenticator QR code" className="size-48 rounded-md" />
                  </div>
                )}
                <div className="flex flex-col items-center gap-3">
                  <Label htmlFor="code" className="text-sm font-medium">Verification code</Label>
                  <Input id="code" inputMode="numeric" maxLength={6} placeholder="123456" autoFocus
                    className="w-32 text-center text-lg tracking-[0.3em]"
                    value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />
                </div>
                {error && <p className="text-center text-sm text-destructive">{error}</p>}
                <Button onClick={verify} disabled={code.length !== 6 || busy} className="w-full">
                  {busy ? "Verifying..." : "Verify & complete setup"}
                </Button>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
