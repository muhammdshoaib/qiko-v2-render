"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2, Mic, PhoneOff } from "lucide-react";
import { Button, cn } from "@qiko/ui";
import { getVapiCredentials } from "@/lib/api";

// In-chat voice call (QIK-319), aligned to V1's WorkerCallView: the Vapi web SDK runs client-side
// with the worker's PUBLIC key + assistant id (both non-secret). Only rendered once VAPI is connected
// for this worker. The SDK is imported dynamically so it never loads during SSR (it touches browser
// APIs at construction). Answers come from the worker's own Vapi assistant.
type Status = "idle" | "connecting" | "active" | "error";

// The Vapi web SDK is loosely typed for its event bus; a narrow local shape keeps us off `any`.
type VapiClient = {
  on: (event: string, cb: (arg?: unknown) => void) => void;
  start: (assistantId: string) => Promise<unknown>;
  stop: () => void;
};

export function WorkerVoiceCall({ id }: { id: string }) {
  const creds = useQuery({ queryKey: ["vapi-credentials", id], queryFn: () => getVapiCredentials(id) });
  const [status, setStatus] = useState<Status>("idle");
  const [speaking, setSpeaking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const vapiRef = useRef<VapiClient | null>(null);

  useEffect(() => () => { try { vapiRef.current?.stop(); } catch { /* already stopped */ } }, []);

  // Only offer voice once this worker has VAPI connected (Connections > Voice). Disconnected/loading
  // workers show no controls, per the acceptance criteria.
  if (!creds.data?.vapi_credentials_added || !creds.data.vapi_public_key || !creds.data.vapi_assistant_id) {
    return null;
  }

  async function start() {
    setError(null);
    setStatus("connecting");
    try {
      const { default: Vapi } = await import("@vapi-ai/web");
      const vapi = new Vapi(creds.data!.vapi_public_key) as unknown as VapiClient;
      vapiRef.current = vapi;
      vapi.on("call-start", () => setStatus("active"));
      vapi.on("call-end", () => { setStatus("idle"); setSpeaking(false); });
      vapi.on("speech-start", () => setSpeaking(true));
      vapi.on("speech-end", () => setSpeaking(false));
      vapi.on("error", () => { setError("The voice call ran into a problem. Please try again."); setStatus("error"); });
      await vapi.start(creds.data!.vapi_assistant_id);
    } catch {
      setError("Couldn't start the call. Allow microphone access and try again.");
      setStatus("error");
    }
  }

  function end() {
    try { vapiRef.current?.stop(); } catch { /* already stopped */ }
    setStatus("idle");
    setSpeaking(false);
  }

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-muted/50 p-3">
      <div className="flex items-center gap-2 text-sm">
        <span className={cn("flex size-8 items-center justify-center rounded-full",
          status === "active" ? "bg-emerald-50 text-emerald-700" : "bg-muted text-slate-400")}>
          <Mic className="size-4" />
        </span>
        <span className="text-slate-600">
          {status === "active" ? (speaking ? "Worker is speaking..." : "Listening...")
            : status === "connecting" ? "Connecting..."
              : "Talk to this worker by voice"}
        </span>
      </div>
      <div className="ml-auto">
        {status === "active" ? (
          <Button type="button" variant="destructive" size="sm" onClick={end} className="gap-1.5">
            <PhoneOff className="size-4" /> End call
          </Button>
        ) : status === "connecting" ? (
          <Button type="button" size="sm" disabled className="gap-1.5">
            <Loader2 className="size-4 animate-spin" /> Connecting...
          </Button>
        ) : (
          <Button type="button" size="sm" onClick={start} className="gap-1.5">
            <Mic className="size-4" /> Start voice call
          </Button>
        )}
      </div>
      {error && <p role="alert" className="w-full text-xs text-destructive">{error}</p>}
    </div>
  );
}
