"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Check, Sparkles } from "lucide-react";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label, cn } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { createAgent, ingest } from "@/lib/api";

const STEPS = ["Name", "Knowledge", "Done"];

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [knowledge, setKnowledge] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function createWorker() {
    setBusy(true); setError(null);
    try {
      await createAgent(name);
      setStep(1);
    } catch { setError("Could not create worker (plan limit or permission)."); }
    finally { setBusy(false); }
  }

  async function addKnowledge() {
    setBusy(true);
    try {
      if (knowledge.trim()) await ingest(`onboarding-${Date.now()}`, knowledge);
      setStep(2);
    } finally { setBusy(false); }
  }

  return (
    <AppShell title="New worker">
      <div className="mx-auto max-w-lg space-y-6">
        <ol className="flex items-center gap-2">
          {STEPS.map((s, i) => (
            <li key={s} className="flex flex-1 items-center gap-2">
              <span className={cn("grid size-7 place-items-center rounded-full text-xs font-semibold",
                i < step ? "bg-primary text-primary-foreground" : i === step ? "bg-accent text-accent-foreground" : "bg-muted text-muted-foreground")}>
                {i < step ? <Check className="size-4" /> : i + 1}
              </span>
              <span className={cn("text-sm", i === step ? "font-medium" : "text-muted-foreground")}>{s}</span>
            </li>
          ))}
        </ol>

        {step === 0 && (
          <Card>
            <CardHeader><CardTitle>Name your worker</CardTitle>
              <CardDescription>Give your AI worker a recognizable name.</CardDescription></CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1.5"><Label>Worker name</Label>
                <Input placeholder="e.g. IDG Sales Assistant" value={name} onChange={(e) => setName(e.target.value)} /></div>
              {error && <p className="text-sm text-destructive">{error}</p>}
              <Button className="w-full" disabled={!name || busy} onClick={createWorker}>Continue</Button>
            </CardContent>
          </Card>
        )}

        {step === 1 && (
          <Card>
            <CardHeader><CardTitle>Add knowledge</CardTitle>
              <CardDescription>Paste text your worker should ground its answers in (optional).</CardDescription></CardHeader>
            <CardContent className="space-y-4">
              <textarea className="min-h-32 w-full rounded-md border border-input bg-background p-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                placeholder="e.g. Our company holds ISO 9001 certification valid through 2027…"
                value={knowledge} onChange={(e) => setKnowledge(e.target.value)} />
              <Button className="w-full" disabled={busy} onClick={addKnowledge}>{knowledge.trim() ? "Add & finish" : "Skip"}</Button>
            </CardContent>
          </Card>
        )}

        {step === 2 && (
          <Card>
            <CardContent className="flex flex-col items-center gap-4 py-10 text-center">
              <span className="grid size-12 place-items-center rounded-full bg-accent text-accent-foreground"><Sparkles className="size-6" /></span>
              <div><p className="text-lg font-semibold">Your worker is ready to train</p>
                <p className="text-sm text-muted-foreground">Mark it ready from the dashboard when you are set.</p></div>
              <Button onClick={() => router.push("/dashboard")}>Go to dashboard</Button>
            </CardContent>
          </Card>
        )}
      </div>
    </AppShell>
  );
}
