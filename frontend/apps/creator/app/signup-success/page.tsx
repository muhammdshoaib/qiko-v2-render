"use client";
import { useEffect, useState } from "react";
import { useLocation } from "@/lib/wouter";
import { CheckCircle2, Mail } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AUTH_BUTTON } from "@/components/auth/auth-shell";

export default function SignUpSuccess() {
  const [, setLocation] = useLocation();
  const [secondsLeft, setSecondsLeft] = useState(10);

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      setSecondsLeft((prev) => {
        if (prev <= 1) {
          window.clearInterval(intervalId);
          setLocation("/onboarding");
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => window.clearInterval(intervalId);
  }, [setLocation]);

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-slate-50 p-4">
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
        <div className="absolute -left-24 top-0 h-[28rem] w-[28rem] rounded-full bg-indigo-100/70 blur-3xl" />
        <div className="absolute -right-20 bottom-0 h-[24rem] w-[24rem] rounded-full bg-sky-100/60 blur-3xl" />
      </div>

      <div className="relative z-10 w-full max-w-2xl">
        <div className="rounded-2xl border border-slate-200 bg-white px-6 py-10 text-center shadow-[0_8px_30px_-12px_rgba(15,23,42,0.12)] md:px-10 md:py-12">
          <div className="relative mx-auto mb-8 flex h-36 w-36 items-center justify-center rounded-full bg-indigo-50 ring-1 ring-indigo-100">
            <Mail className="size-16 text-indigo-600" />
            <div className="absolute -right-1 -top-1 rounded-full bg-emerald-500 p-1.5 shadow-sm">
              <CheckCircle2 className="size-5 text-white" />
            </div>
          </div>

          <h1 className="mb-4 text-3xl font-semibold text-slate-900">Congratulations</h1>
          <p className="mx-auto max-w-xl text-lg leading-8 text-slate-600">
            Your account has been created successfully. Next, we&apos;ll ask you a few quick questions to set up your
            workspace and create your first Digital Worker.
          </p>
          <p className="mt-4 text-slate-500">
            Redirecting to onboarding in <span className="font-semibold text-indigo-600">{secondsLeft}s</span>.
          </p>

          <div className="mt-8 flex flex-col items-stretch justify-center gap-3 sm:flex-row sm:items-center">
            <Button
              className={`${AUTH_BUTTON} sm:min-w-[200px] sm:w-auto`}
              onClick={() => setLocation("/onboarding")}
            >
              Start onboarding
            </Button>
          </div>

          <div className="mt-10 space-y-3 text-slate-600">
            <h2 className="text-2xl font-semibold text-slate-900">Having trouble?</h2>
            <p className="text-lg">
              Contact us at{" "}
              <a href="mailto:support@qiko.ai" className="text-indigo-600 transition-colors hover:text-indigo-700">
                support@qiko.ai
              </a>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
