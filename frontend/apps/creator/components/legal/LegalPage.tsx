import type { ReactNode } from "react";
import { ConsentSettingsButton } from "@/components/consent/ConsentUI";

export function LegalSection({ heading, children }: { heading: string; children: ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="text-xl font-semibold text-white">{heading}</h2>
      <div className="space-y-3 text-sm leading-relaxed text-slate-300">{children}</div>
    </section>
  );
}

export function LegalPage({
  title,
  lastUpdated,
  intro,
  children,
}: {
  title: string;
  lastUpdated: string;
  intro?: ReactNode;
  children: ReactNode;
}) {
  const links = [
    { href: "/terms", label: "Terms of Service" },
    { href: "/privacy", label: "Privacy Policy" },
    { href: "/cookies", label: "Cookie Policy" },
  ];

  return (
    <div className="min-h-screen bg-[#050810] text-slate-300">
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-purple-500/10 rounded-full blur-3xl" />
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-cyan-500/10 rounded-full blur-3xl" />
      </div>

      <div className="relative z-10 mx-auto w-full max-w-4xl px-4 py-10 sm:px-6 sm:py-16">
        <header className="mb-10">
          <a
            href="/"
            className="mb-8 inline-flex items-center gap-2 text-sm text-slate-400 transition-colors hover:text-white"
          >
            <span aria-hidden>&larr;</span> Back to home
          </a>
          <div className="mb-4">
            <img
              src="/qiko-logo.webp"
              alt="Qiko"
              width={160}
              height={48}
              className="h-10 w-auto object-contain"
            />
          </div>
          <h1 className="text-3xl font-bold text-white sm:text-4xl">{title}</h1>
          <p className="mt-2 text-sm text-slate-500">Effective date: {lastUpdated}</p>
          {intro ? <div className="mt-4 text-sm leading-relaxed text-slate-300">{intro}</div> : null}
        </header>

        <main className="space-y-8">{children}</main>

        <footer className="mt-12 border-t border-slate-800 pt-6 text-sm text-slate-500">
          <p>
            Questions? Contact us at{" "}
            <a href="mailto:support%40qiko.ai" className="text-cyan-400 hover:text-cyan-300">
              support{"@"}qiko.ai
            </a>
            .
          </p>
          <nav className="mt-4 flex flex-wrap gap-x-6 gap-y-2">
            {links.map((l) => (
              <a key={l.href} href={l.href} className="text-slate-400 transition-colors hover:text-white">
                {l.label}
              </a>
            ))}
            <ConsentSettingsButton className="text-slate-400" />
          </nav>
        </footer>
      </div>
    </div>
  );
}
