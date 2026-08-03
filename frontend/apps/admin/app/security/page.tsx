"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import QRCode from "qrcode";
import { ShieldCheck } from "lucide-react";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { authMe, regenerateBackupCodes, twofaSetup, twofaVerify } from "@/lib/api";

export default function SecurityPage() {
  const [secret, setSecret] = useState<string | null>(null);
  const [qr, setQr] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [currentCode, setCurrentCode] = useState("");
  const [backupCodes, setBackupCodes] = useState<string[]>([]);
  const me = useQuery({ queryKey: ["auth-me"], queryFn: authMe });
  const enabled = me.data?.user.twofa_enabled === true;
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // The admin requires 2FA, so an admin arriving here without it (typically auto-redirected by
  // AppShell) is auto-put into onboarding: kick off setup once so the QR is shown immediately.
  const autoStarted = useRef(false);
  useEffect(() => {
    if (me.data && !enabled && !autoStarted.current) {
      autoStarted.current = true;
      void start();
    }
    // start is a stable local function; the ref guard prevents re-invocation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me.data, enabled]);

  async function start() {
    setBusy(true); setError(null);
    try {
      const r = await twofaSetup();
      setSecret(r.secret);
      setQr(await QRCode.toDataURL(r.provisioning_uri, { width: 192, margin: 1 }));
    } catch {
      setError("2FA setup is unavailable. Please retry.");
    } finally {
      setBusy(false);
    }
  }
  async function regenerate() {
    setBusy(true); setError(null);
    try { const result = await regenerateBackupCodes(password, currentCode); setBackupCodes(result.backup_codes); }
    catch { setError("Backup code regeneration failed."); }
    finally { setBusy(false); }
  }
  async function verify() {
    setBusy(true); setError(null);
    try { const result = await twofaVerify(secret!, code, password, currentCode); setBackupCodes(result.backup_codes); }
    catch { setError("Verification failed. Check the current code or retry when the service is available."); }
    finally { setBusy(false); }
  }

  if (me.isLoading) return <AppShell title="Security"><p role="status" className="p-6 text-sm text-muted-foreground">Loading security status...</p></AppShell>;
  if (me.isError) return <AppShell title="Security"><p role="alert" className="p-6 text-sm text-destructive">Security status unavailable. <button className="underline" onClick={() => me.refetch()}>Retry</button></p></AppShell>;

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
                  {enabled
                    ? "Scan the QR code with Google Authenticator, then enter the 6-digit code to finish setup."
                    : "Two-factor authentication is required to access the admin. Scan the QR code with Google Authenticator, enter the 6-digit code, then sign back in."}
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-5">
            {error && <p role="alert" className="text-center text-sm text-destructive">{error}</p>}
            {backupCodes.length > 0 ? (
              <div className="space-y-4">
                <p role="alert" className="text-sm font-medium">Save these one-time backup codes now. They will not be shown again.</p>
                <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">{backupCodes.map((backupCode) => <li key={backupCode} className="rounded border p-2 font-mono text-sm">{backupCode}</li>)}</ul>
                <Button className="w-full" onClick={() => window.location.assign("/login")}>I&apos;ve saved these codes, sign in</Button>
              </div>
            ) : enabled ? (
              <div className="space-y-4">
                <div className="flex items-center gap-2 text-sm text-success"><ShieldCheck className="size-4" /> 2FA is active on your account.</div>
                <Label htmlFor="recovery-password">Current password</Label>
                <Input id="recovery-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
                <Label htmlFor="recovery-code">Current authenticator code</Label>
                <Input id="recovery-code" inputMode="numeric" maxLength={6} value={currentCode} onChange={(event) => setCurrentCode(event.target.value.replace(/\D/g, ""))} />
                <Button className="w-full" disabled={busy || !password || currentCode.length !== 6} onClick={regenerate}>Generate new backup codes</Button>
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
                <div className="space-y-2">
                  <Label htmlFor="password">Current password</Label>
                  <Input id="password" type="password" autoComplete="current-password" value={password}
                    onChange={(event) => setPassword(event.target.value)} />
                </div>
                {enabled && <div className="space-y-2">
                  <Label htmlFor="current-code">Current authenticator code</Label>
                  <Input id="current-code" inputMode="numeric" maxLength={6} value={currentCode}
                    onChange={(event) => setCurrentCode(event.target.value.replace(/\D/g, ""))} />
                </div>}
                <div className="flex flex-col items-center gap-3">
                  <Label htmlFor="code" className="text-sm font-medium">Verification code</Label>
                  <Input id="code" inputMode="numeric" maxLength={6} placeholder="123456" autoFocus
                    className="w-32 text-center text-lg tracking-[0.3em]"
                    value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />
                </div>
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
