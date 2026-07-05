"use client";
import { useEffect, useState } from "react";
import { useLocation } from "@/lib/wouter";
import { CheckCircle2, Mail } from "lucide-react";
import { Button } from "@/components/ui/button";

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
    <div className="min-h-screen bg-[#050810] flex items-center justify-center p-4">
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-purple-500/10 rounded-full blur-3xl" />
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-cyan-500/10 rounded-full blur-3xl" />
      </div>

      <div className="relative z-10 w-full max-w-2xl">
        <div className="rounded-2xl border border-slate-800 bg-slate-900/50 backdrop-blur-sm px-6 py-10 md:px-10 md:py-12 text-center">
          <div className="relative mx-auto mb-8 flex h-36 w-36 items-center justify-center rounded-full bg-gradient-to-br from-purple-500/20 to-cyan-500/20 ring-1 ring-slate-700/70">
            <Mail className="h-16 w-16 text-cyan-300" />
            <div className="absolute -right-1 -top-1 rounded-full bg-emerald-500 p-1.5 shadow-lg shadow-emerald-500/30">
              <CheckCircle2 className="h-5 w-5 text-white" />
            </div>
          </div>

          <h1 className="text-3xl font-semibold text-white mb-4">Congratulations</h1>
          <p className="mx-auto max-w-xl text-slate-300 text-lg leading-8">
          Your account has been created successfully. Next, we’ll ask you a few quick questions to set up your workspace and create your first Digital Worker.
          </p>
          <p className="mt-4 text-slate-400">
          Redirecting to onboarding in <span className="text-cyan-300 font-semibold">{secondsLeft}s</span>.
          </p>


          <div className="mt-8 flex items-center justify-center gap-3">
            <Button
              className="min-w-[200px] bg-gradient-to-r from-purple-600 to-cyan-600 text-white border-0"
              onClick={() => setLocation("/onboarding")}
            >
              Start onboarding
            </Button>
            {/* <Button
              className="min-w-[200px] bg-gradient-to-r from-purple-400 to-cyan-600 text-white border-0"
              onClick={() => setLocation("/login")}
            >
              Login
            </Button> */}
          </div>

          
          <div className="space-y-3 text-slate-300 text-2xl leading-9 mt-10">
            <h2 className="text-white font-semibold text-2xl">Having trouble?</h2>
            <p className="text-slate-300 text-lg">
              Contact us at{" "}
              <a href="mailto:team@qiko.com" className="text-cyan-300 hover:text-cyan-200 transition-colors">
                support@qiko.ai
              </a>
            </p>
          </div>

        </div>
      </div>
    </div>
  );
}
