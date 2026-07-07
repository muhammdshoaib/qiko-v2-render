"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight, BarChart3, BrainCircuit, ShieldCheck, Zap,
  Search, MessageSquare, Eye, Target, Rocket,
} from "lucide-react";

const PILLARS = [
  {
    icon: Search, title: "SEO", subtitle: "Traditional search", color: "text-blue-400",
    description: "Technical health, structured data, and on-page signals that determine how Google and Bing rank your pages.",
  },
  {
    icon: MessageSquare, title: "AEO", subtitle: "Answer engines", color: "text-teal-400",
    description: "Content structure and authority signals that improve how AI assistants cite your brand as the direct answer.",
  },
  {
    icon: BrainCircuit, title: "GEO", subtitle: "Generative AI search", color: "text-purple-400",
    description: "Entity clarity and knowledge-graph alignment that shape how ChatGPT, Gemini, Claude, and Perplexity reference your brand.",
  },
];

const JOURNEY = [
  { step: "01", status: "Live now", title: "Be seen", desc: "Signal makes sure AI engines can find, read, and cite your brand." },
  { step: "02", status: "Available now", title: "Be understood", desc: "Structure your knowledge, guardrails, and processes so AI represents you accurately, not whatever it guesses." },
  { step: "03", status: "On the horizon", title: "Be acted on", desc: "As agents start to transact directly, the businesses already structured for it win. You will be ready." },
];

const FOUNDATIONS = [
  { icon: BrainCircuit, title: "Multi-model by design", desc: "We route across leading models rather than betting on one." },
  { icon: ShieldCheck, title: "Your data, isolated", desc: "Encrypted, region-hosted, never blended with anyone else's." },
  { icon: Eye, title: "Cross-examined, not guessed", desc: "Every finding is challenged by multiple models before it reaches you." },
  { icon: Zap, title: "Built to extend", desc: "The platform that audits your visibility hosts the digital workers you build next." },
];

const WHY = [
  { icon: Target, title: "Know your score", desc: "One number for how visible and accurate you are across AI search." },
  { icon: BarChart3, title: "See the gap", desc: "Where AI recommends competitors instead of you, and exactly why." },
  { icon: Rocket, title: "Act on it", desc: "Prioritised fixes you can ship this week, not a 60-page report." },
];

function Eyebrow({ children }: { children: React.ReactNode }) {
  return <p className="text-xs font-semibold tracking-[0.2em] text-[#6366F1] mb-4 text-center uppercase">{children}</p>;
}

export default function LandingPage() {
  const router = useRouter();
  const goApp = () => router.push("/onboarding");
  const [url, setUrl] = useState("");

  function runAssessment() {
    const params = url.trim() ? `?url=${encodeURIComponent(url.trim())}` : "";
    router.push(`/onboarding${params}`);
  }

  return (
    <div className="min-h-screen bg-[#050810] text-white overflow-x-hidden relative">
      {/* Ambient orbs */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute w-[600px] h-[600px] rounded-full opacity-25" style={{ background: "radial-gradient(circle,#6366F1 0%,transparent 70%)", top: "-8%", left: "15%", filter: "blur(90px)" }} />
        <div className="absolute w-[500px] h-[500px] rounded-full opacity-20" style={{ background: "radial-gradient(circle,#22D3EE 0%,transparent 70%)", top: "20%", right: "8%", filter: "blur(90px)" }} />
      </div>

      {/* Nav */}
      <header className="fixed top-0 inset-x-0 z-50">
        <div className="mx-3 sm:mx-4 mt-3 sm:mt-4 md:mx-8">
          <nav className="glass-card px-4 sm:px-6 py-3 sm:py-4 flex items-center justify-between max-w-6xl mx-auto">
            <a href="/" className="flex items-center gap-2 group">
              <img src="/qiko-logo.webp" alt="Go to Qiko homepage" className="h-8 sm:h-10 w-auto transition-all duration-300 group-hover:scale-105" />
            </a>
            <div className="hidden md:flex items-center gap-8 text-sm text-slate-300">
              <a href="#" className="text-white">Home</a>
              <a href="#signal" className="hover:text-white">Signal</a>
              <a href="#labs" className="hover:text-white">Labs</a>
              <a href="#about" className="hover:text-white">About</a>
            </div>
            <div className="flex items-center gap-3">
              <button onClick={() => router.push("/login")} className="text-slate-300 hover:text-white text-sm font-medium px-4 py-2 rounded-full">Sign in</button>
              <button onClick={goApp} className="bg-gradient-to-r from-[#6366F1] to-[#22D3EE] text-white text-sm font-medium px-5 py-2 rounded-full shadow-lg shadow-[#6366F1]/25 inline-flex items-center gap-1.5">
                Get started <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </nav>
        </div>
      </header>

      {/* Hero */}
      <section className="relative pt-36 pb-16 px-4">
        <div className="relative z-10 max-w-6xl mx-auto grid lg:grid-cols-2 gap-10 items-center">
          <div>
            <h1 className="text-4xl md:text-6xl font-black mb-6 leading-[1.1]" style={{ fontFamily: "Satoshi, sans-serif", fontWeight: 900 }}>
              AI now decides which businesses get found.{" "}
              <span style={{ background: "linear-gradient(135deg,#6366F1,#22D3EE)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
                Find out if yours is one of them.
              </span>
            </h1>
            <p className="text-lg text-slate-300 mb-8 max-w-xl leading-relaxed">
              Qiko shows you how AI engines see your brand today, then helps you become visible, understood, and ready for a world where AI does the searching.
            </p>
            <div className="flex flex-wrap items-center gap-3 mb-3">
              <div className="flex items-center gap-2 flex-1 min-w-[240px] max-w-sm">
                <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="yourcompany.com"
                  className="flex-1 bg-white/5 border border-white/10 rounded-full px-4 py-2.5 text-sm text-white outline-none placeholder:text-slate-500 focus:border-[#6366F1]/50" />
              </div>
              <button onClick={runAssessment} className="bg-gradient-to-r from-[#6366F1] to-[#22D3EE] text-white font-semibold px-6 py-2.5 rounded-full inline-flex items-center gap-2 shadow-lg shadow-[#6366F1]/30 whitespace-nowrap">
                Run your free assessment <ArrowRight className="w-4 h-4" />
              </button>
              <button onClick={() => router.push("/dashboard")} className="glass-card text-slate-200 font-medium px-6 py-2.5 rounded-full whitespace-nowrap">Explore Signal</button>
            </div>
            <p className="text-xs text-slate-500">One free assessment to get started</p>
          </div>

          {/* Signal preview card */}
          <div className="glass-card p-5 sm:p-6">
            <div className="flex items-center gap-3 mb-5">
              <div className="w-9 h-9 rounded-lg grid place-items-center bg-[#22D3EE]/15"><Eye className="w-4 h-4 text-[#22D3EE]" /></div>
              <div><p className="font-semibold text-sm">Qiko Signal</p><p className="text-xs text-slate-500">Your business visibility health</p></div>
            </div>
            <div className="grid grid-cols-2 gap-3 mb-5">
              <div className="bg-white/5 rounded-xl p-4">
                <p className="text-2xl font-bold text-[#6366F1]">54</p>
                <p className="text-xs font-medium mt-1">SEO</p>
                <p className="text-[11px] text-slate-500">Traditional search</p>
                <p className="text-[11px] text-slate-500">You 54 · Target 75</p>
              </div>
              <div className="bg-white/5 rounded-xl p-4">
                <p className="text-2xl font-bold text-[#22D3EE]">64</p>
                <p className="text-xs font-medium mt-1">AIO</p>
                <p className="text-[11px] text-slate-500">AI search</p>
                <p className="text-[11px] text-slate-500">You 64 · Target 80</p>
              </div>
            </div>
            <div className="border-l-2 border-[#22D3EE] pl-3 mb-4">
              <p className="text-xs text-slate-300 italic">AI recommends you for 64% of tracked queries. Invisible for the high-intent searches that win deals.</p>
            </div>
            <div className="space-y-2 text-xs">
              <div className="flex justify-between"><span className="text-slate-400">Problem search · competitors recommended</span><span className="text-red-400 font-medium">38%</span></div>
              <div className="flex justify-between"><span className="text-slate-400">Feature search · capability not attributed</span><span className="text-amber-400 font-medium">55%</span></div>
              <div className="flex justify-between"><span className="text-slate-400">Brand search · AI knows who you are</span><span className="text-emerald-400 font-medium">92%</span></div>
            </div>
          </div>
        </div>
      </section>

      {/* See your brand the way AI does */}
      <section id="signal" className="relative z-10 px-4 py-20 max-w-6xl mx-auto">
        <div className="text-center mb-14">
          <Eyebrow>Qiko Signal</Eyebrow>
          <h2 className="text-3xl md:text-5xl font-bold mb-4" style={{ fontFamily: "Satoshi, sans-serif" }}>See your brand the way AI does.</h2>
          <p className="text-slate-400 max-w-2xl mx-auto">
            Signal runs your website or brand through the engines people now ask first, ChatGPT, Gemini, Claude and Perplexity. You get a clear visibility score, what AI says about you next to your competitors, and a short list of the highest-impact fixes across SEO and AI optimisation (AIO).
          </p>
        </div>
        <div className="grid sm:grid-cols-3 gap-4">
          {WHY.map((w) => (
            <div key={w.title} className="glass-card p-6">
              <div className="w-10 h-10 rounded-lg grid place-items-center mb-4" style={{ background: "#6366F120", boxShadow: "0 0 20px #6366F130" }}><w.icon className="w-5 h-5 text-[#6366F1]" /></div>
              <h3 className="font-semibold mb-1">{w.title}</h3>
              <p className="text-sm text-slate-400">{w.desc}</p>
            </div>
          ))}
        </div>
        <p className="text-center text-sm text-slate-500 mt-10">Strong visibility is the foundation. Here is what it unlocks.</p>
      </section>

      {/* The Qiko journey */}
      <section className="relative z-10 px-4 py-20 max-w-6xl mx-auto">
        <div className="text-center mb-14">
          <Eyebrow>The Qiko journey</Eyebrow>
          <h2 className="text-3xl md:text-5xl font-bold mb-4" style={{ fontFamily: "Satoshi, sans-serif" }}>Visibility is step one.</h2>
          <p className="text-slate-400 max-w-2xl mx-auto">
            Getting seen by AI is where it starts. Being represented accurately, and eventually transacted with, is where it goes. Qiko takes you along that path at your pace.
          </p>
        </div>
        <div className="grid sm:grid-cols-3 gap-4">
          {JOURNEY.map((j) => (
            <div key={j.step} className="glass-card p-6">
              <span className="inline-block text-[10px] font-semibold uppercase tracking-wider px-2 py-1 rounded-full bg-[#22D3EE]/10 text-[#22D3EE] mb-4">{j.status}</span>
              <div className="text-2xl font-bold mb-2" style={{ background: "linear-gradient(135deg,#6366F1,#22D3EE)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>{j.step}</div>
              <h3 className="font-semibold mb-1">{j.title}</h3>
              <p className="text-sm text-slate-400">{j.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Two ways to work with Qiko */}
      <section className="relative z-10 px-4 py-20 max-w-6xl mx-auto">
        <div className="text-center mb-14">
          <Eyebrow>Get started</Eyebrow>
          <h2 className="text-3xl md:text-5xl font-bold" style={{ fontFamily: "Satoshi, sans-serif" }}>Two ways to work with Qiko.</h2>
        </div>
        <div className="grid md:grid-cols-2 gap-5">
          <div className="glass-card p-8">
            <p className="text-xs font-semibold uppercase tracking-wider text-[#22D3EE] mb-3">Self-serve</p>
            <h3 className="text-xl font-bold mb-3">Start with Signal</h3>
            <p className="text-sm text-slate-400 mb-6">Run a free assessment, see where you stand, and subscribe to track and improve your AI visibility over time. Best if you want to act now and move fast.</p>
            <button onClick={runAssessment} className="text-sm font-semibold text-[#22D3EE] inline-flex items-center gap-1.5">Run your free assessment <ArrowRight className="w-3.5 h-3.5" /></button>
          </div>
          <div className="glass-card p-8">
            <p className="text-xs font-semibold uppercase tracking-wider text-[#6366F1] mb-3">Enterprise</p>
            <h3 className="text-xl font-bold mb-3">Build with Qiko Labs</h3>
            <p className="text-sm text-slate-400 mb-6">For enterprises that want custom AI workers and agentic workflows without managing models, infrastructure, or security. We build it on Qiko, primed for what comes next.</p>
            <a href="mailto:labs@qiko.ai" className="text-sm font-semibold text-[#6366F1] inline-flex items-center gap-1.5">Build with Qiko Labs <ArrowRight className="w-3.5 h-3.5" /></a>
          </div>
        </div>
      </section>

      {/* Three pillars */}
      <section id="labs" className="relative z-10 px-4 py-20 max-w-6xl mx-auto">
        <div className="text-center mb-14">
          <Eyebrow>One platform, three pillars</Eyebrow>
          <h2 className="text-3xl md:text-5xl font-bold mb-4" style={{ fontFamily: "Satoshi, sans-serif" }}>SEO + AEO + GEO</h2>
          <p className="text-slate-400 max-w-2xl mx-auto">Traditional search, answer engines, and generative AI index the web differently. Qiko audits all three, so every score is cross-validated rather than single-provider guesswork.</p>
        </div>
        <div className="grid sm:grid-cols-3 gap-4">
          {PILLARS.map((p) => (
            <div key={p.title} className="glass-card p-6">
              <div className="w-10 h-10 rounded-lg grid place-items-center mb-4 bg-white/5"><p.icon className={`w-5 h-5 ${p.color}`} /></div>
              <h3 className="font-semibold mb-1">{p.title}</h3>
              <p className={`text-xs font-medium uppercase tracking-wider mb-3 ${p.color}`}>{p.subtitle}</p>
              <p className="text-sm text-slate-400">{p.description}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Under the hood */}
      <section id="about" className="relative z-10 px-4 py-20 max-w-6xl mx-auto">
        <div className="text-center mb-14">
          <Eyebrow>Under the hood</Eyebrow>
          <h2 className="text-3xl md:text-5xl font-bold mb-4" style={{ fontFamily: "Satoshi, sans-serif" }}>Serious infrastructure, quietly handled.</h2>
          <p className="text-slate-400 max-w-2xl mx-auto">Everything Qiko ships sits on enterprise-grade foundations so you do not have to build them. Multiple frontier models, your data isolated and encrypted, hosted in your region.</p>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {FOUNDATIONS.map((f) => (
            <div key={f.title} className="glass-card p-6">
              <div className="w-10 h-10 rounded-lg grid place-items-center mb-4" style={{ background: "#22D3EE18", boxShadow: "0 0 20px #22D3EE22" }}><f.icon className="w-5 h-5 text-[#22D3EE]" /></div>
              <h3 className="font-semibold mb-1">{f.title}</h3>
              <p className="text-sm text-slate-400">{f.desc}</p>
            </div>
          ))}
        </div>
        <p className="text-center text-sm text-slate-500 mt-10">Those same foundations are what make you ready for what comes next.</p>
      </section>

      {/* The bigger picture */}
      <section className="relative z-10 px-4 py-20 max-w-3xl mx-auto text-center">
        <Eyebrow>The bigger picture</Eyebrow>
        <h2 className="text-3xl md:text-5xl font-bold mb-4" style={{ fontFamily: "Satoshi, sans-serif" }}>
          The web is becoming a place where AI agents act on your behalf.
        </h2>
        <p className="text-slate-400 leading-relaxed">
          Today people ask AI for recommendations. Soon agents will research, compare, and transact with each other directly. The businesses that are discoverable and structured now are the ones that get chosen then. Longer term, Qiko becomes a marketplace of specialised intelligence you can tap on demand. Getting visible today is how you get there.
        </p>
      </section>

      {/* Final CTA */}
      <section className="relative z-10 px-4 py-24">
        <div className="max-w-2xl mx-auto text-center relative">
          <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[300px] rounded-full opacity-25 pointer-events-none" style={{ background: "radial-gradient(circle,#6366F1 0%,transparent 70%)", filter: "blur(60px)" }} />
          <p className="text-xs font-semibold tracking-[0.2em] text-[#6366F1] mb-4 uppercase relative">Find out where you stand</p>
          <h2 className="text-3xl md:text-5xl font-bold mb-4 relative" style={{ fontFamily: "Satoshi, sans-serif" }}>See how AI sees your business.</h2>
          <p className="text-slate-400 mb-8 relative">It takes one scan to find out. Start free.</p>
          <div className="flex flex-wrap justify-center gap-3 relative">
            <button onClick={runAssessment} className="bg-gradient-to-r from-[#6366F1] via-[#A855F7] to-[#22D3EE] text-white font-semibold px-8 py-3.5 rounded-full inline-flex items-center gap-2 shadow-2xl shadow-[#6366F1]/40">
              Run your free assessment <ArrowRight className="w-4 h-4" />
            </button>
            <a href="mailto:labs@qiko.ai" className="glass-card text-white font-medium px-8 py-3.5 rounded-full">Talk to Qiko Labs</a>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="relative z-10 border-t border-white/5 px-6 py-12">
        <div className="max-w-6xl mx-auto grid sm:grid-cols-4 gap-8">
          <div className="sm:col-span-2">
            <img src="/qiko-logo.webp" alt="Qiko" className="h-7 w-auto mb-4" />
            <p className="text-sm text-slate-500 max-w-xs">Be visible, understood, and ready for a world where AI does the searching.</p>
          </div>
          <div>
            <h4 className="font-semibold mb-3 text-sm">Product</h4>
            <ul className="space-y-2 text-sm text-slate-400">
              <li><a href="#signal" className="hover:text-white">Signal</a></li>
              <li><a href="#labs" className="hover:text-white">Labs</a></li>
            </ul>
          </div>
          <div>
            <h4 className="font-semibold mb-3 text-sm">Company</h4>
            <ul className="space-y-2 text-sm text-slate-400">
              <li><a href="#about" className="hover:text-white">About</a></li>
              <li><a href="mailto:support@qiko.ai" className="hover:text-white">Contact</a></li>
            </ul>
          </div>
        </div>
        <p className="text-center text-xs text-slate-600 mt-10">© {new Date().getFullYear()} Qiko</p>
      </footer>
    </div>
  );
}
