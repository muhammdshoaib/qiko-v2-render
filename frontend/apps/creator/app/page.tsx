"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Target, Zap, Shield, Sparkles, Cpu, Server, Database, Lock, Plug, Activity } from "lucide-react";

const WHY = [
  { icon: Target, title: "Accurate", desc: "Grounded in your own data, decisions, and judgment—not generic training data." },
  { icon: Zap, title: "Low Latency", desc: "Optimised for your specific use case instead of generic everything-models." },
  { icon: Shield, title: "Secure & Private", desc: "Data stays in a dedicated environment; on-prem or VPC deployments available." },
  { icon: Sparkles, title: "On-Brand", desc: "Tone, style, and behaviour that match you or your company perfectly." },
];
const STEPS = [
  { n: "01", title: "Describe your digital worker", desc: "Start in plain English. Tell Qiko what your worker should do, who it helps, and how it should behave." },
  { n: "02", title: "Upload your expertise data", desc: "Share documents, transcripts, decision logs, and knowledge. Qiko trains your worker on your unique expertise." },
  { n: "03", title: "Qiko deploys with GPT-5", desc: "We configure your worker with GPT-5, set up knowledge training, integrate APIs, and handle all infrastructure." },
  { n: "04", title: "Launch and earn", desc: "We deploy your worker behind secure APIs and a hosted interface so you can sell access as a subscription." },
];
const HANDLES = [
  { icon: Cpu, title: "Model Selection & Optimisation", desc: "Best-fit base AI models (e.g. Claude, GPT, or custom models such as Llama, Mistral) sized to your use case." },
  { icon: Server, title: "GPU & Infra Orchestration", desc: "Automatic allocation of GPU capacity via partners, with monitoring and scaling baked in." },
  { icon: Database, title: "Data Pipelines & RAG", desc: "We design retrieval and training pipelines so your model can use your documents and systems reliably." },
  { icon: Lock, title: "Security & Isolation", desc: "Isolated deployments, encryption, and optional on-prem / private cloud setups for strict compliance." },
  { icon: Plug, title: "APIs & Integration", desc: "Your model ships with documented APIs and webhooks so you can embed it into your app from day one." },
  { icon: Activity, title: "Monitoring & Iteration", desc: "We track performance and feedback so your digital twin gets sharper over time." },
];
const WHO = [
  { title: "Recruiters", desc: "Who want an AI that screens and pitches like they do." },
  { title: "Travel & Lifestyle Experts", desc: "Who want an assistant that knows their taste." },
  { title: "Sales Trainers", desc: "Who want an AI that coaches reps in their methodology." },
  { title: "Niche Consultants", desc: "Who want to package their knowledge as a subscription." },
];
const TRUSTED = ["Recruitment", "Travel", "Sales Training", "Consulting"];

function Eyebrow({ children }: { children: React.ReactNode }) {
  return <p className="text-xs font-semibold tracking-[0.2em] text-[#6366F1] mb-4">{children}</p>;
}

export default function LandingPage() {
  const router = useRouter();
  const go = () => router.push("/onboarding");
  const [input, setInput] = useState("");

  return (
    <div className="min-h-screen bg-[#050810] text-white overflow-x-hidden relative">
      {/* Ambient orbs */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute w-[600px] h-[600px] rounded-full opacity-25" style={{ background: "radial-gradient(circle,#6366F1 0%,transparent 70%)", top: "-8%", left: "15%", filter: "blur(90px)" }} />
        <div className="absolute w-[500px] h-[500px] rounded-full opacity-20" style={{ background: "radial-gradient(circle,#22D3EE 0%,transparent 70%)", top: "20%", right: "8%", filter: "blur(90px)" }} />
      </div>

      {/* Nav — floating glass-card, matching the live site exactly */}
      <header className="fixed top-0 inset-x-0 z-50">
        <div className="mx-3 sm:mx-4 mt-3 sm:mt-4 md:mx-8">
          <nav className="glass-card px-4 sm:px-6 py-3 sm:py-4 flex items-center justify-between max-w-6xl mx-auto">
            <a href="/" className="flex items-center gap-2 group">
              <img src="/qiko-logo.webp" alt="Go to Qiko homepage" className="h-8 sm:h-10 w-auto transition-all duration-300 group-hover:scale-105" />
            </a>
            <div className="hidden md:flex items-center gap-8 text-sm text-slate-300">
              <a href="#" className="text-white">Home</a>
              <a href="#pricing" className="hover:text-white">Pricing</a>
              <a href="#why" className="hover:text-white">About</a>
              <a href="#enterprise" className="hover:text-white">Enterprise</a>
            </div>
            <div className="flex items-center gap-3">
              <button onClick={() => router.push("/login")} className="text-slate-300 hover:text-white text-sm font-medium px-4 py-2 rounded-full">Sign in</button>
              <button onClick={go} className="bg-gradient-to-r from-[#6366F1] to-[#A855F7] text-white text-sm font-medium px-5 py-2 rounded-full shadow-lg shadow-[#6366F1]/25">Get started</button>
            </div>
          </nav>
        </div>
      </header>

      {/* Hero */}
      <section className="relative pt-36 pb-16 px-4">
        <div className="relative z-10 max-w-4xl mx-auto text-center">
          <h1 className="text-5xl md:text-7xl font-black mb-6 leading-[1.05]" style={{ fontFamily: "Satoshi, sans-serif", fontWeight: 900 }}>
            Build and sell your own <span style={{ background: "linear-gradient(135deg,#6366F1,#22D3EE)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>digital worker.</span>
          </h1>
          <p className="text-lg md:text-xl text-slate-300 mb-10 max-w-2xl mx-auto leading-relaxed">
            You bring the niche expertise. Qiko handles models, GPUs and security so you can launch a production ready digital worker.
          </p>
          <div className="relative max-w-xl mx-auto group">
            <div className="absolute -inset-[1px] rounded-2xl opacity-70 group-hover:opacity-100 transition-opacity" style={{ background: "linear-gradient(135deg,#6366F1,#22D3EE,#A855F7,#6366F1)", backgroundSize: "300% 300%" }} />
            <div className="relative bg-[#0a0f1a] rounded-2xl p-6 text-left">
              <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="I am a real estate agent..." className="w-full bg-transparent text-white text-lg outline-none placeholder:text-slate-500 mb-4" />
              <div className="flex justify-end">
                <button onClick={go} className="bg-gradient-to-r from-[#6366F1] to-[#22D3EE] text-white font-semibold px-6 py-2.5 rounded-full inline-flex items-center gap-2 shadow-lg shadow-[#6366F1]/30">Start Building <ArrowRight className="w-4 h-4" /></button>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Trusted */}
      <section className="relative z-10 px-4 pb-20">
        <p className="text-center text-sm text-slate-500 mb-5">Trusted by creators in</p>
        <div className="flex flex-wrap justify-center gap-x-10 gap-y-3 text-slate-400 font-medium">
          {TRUSTED.map((t) => <span key={t}>{t}</span>)}
        </div>
      </section>

      {/* Why digital workers */}
      <section id="why" className="relative z-10 px-4 py-20 max-w-6xl mx-auto">
        <div className="text-center mb-14">
          <Eyebrow>WHY DIGITAL WORKERS</Eyebrow>
          <h2 className="text-3xl md:text-5xl font-bold mb-4" style={{ fontFamily: "Satoshi, sans-serif" }}>Generic AI is smart. Your digital worker is <span className="text-[#22D3EE]">you</span>.</h2>
          <p className="text-slate-400 max-w-2xl mx-auto">Deploy a digital worker in minutes. As your business grows, train custom models on your proprietary data and own your competitive advantage.</p>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {WHY.map((w) => (
            <div key={w.title} className="glass-card p-6">
              <div className="w-10 h-10 rounded-lg grid place-items-center mb-4" style={{ background: "#6366F120", boxShadow: "0 0 20px #6366F130" }}><w.icon className="w-5 h-5 text-[#6366F1]" /></div>
              <h3 className="font-semibold mb-1">{w.title}</h3>
              <p className="text-sm text-slate-400">{w.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section className="relative z-10 px-4 py-20 max-w-6xl mx-auto">
        <div className="text-center mb-14">
          <Eyebrow>HOW IT WORKS</Eyebrow>
          <h2 className="text-3xl md:text-5xl font-bold mb-4" style={{ fontFamily: "Satoshi, sans-serif" }}>From idea to revenue-ready digital worker</h2>
          <p className="text-slate-400">Four simple steps to launch your AI-powered digital worker and start earning.</p>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {STEPS.map((s) => (
            <div key={s.n} className="glass-card p-6">
              <div className="text-3xl font-bold mb-3" style={{ background: "linear-gradient(135deg,#6366F1,#22D3EE)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>{s.n}</div>
              <h3 className="font-semibold mb-1">{s.title}</h3>
              <p className="text-sm text-slate-400">{s.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Creator success story */}
      <section className="relative z-10 px-4 py-20 max-w-6xl mx-auto">
        <div className="text-center mb-12">
          <Eyebrow>CREATOR SUCCESS STORY</Eyebrow>
          <h2 className="text-3xl md:text-5xl font-bold max-w-3xl mx-auto" style={{ fontFamily: "Satoshi, sans-serif" }}>
            Turn your niche expertise into a revenue-generating digital worker.
          </h2>
        </div>
        <div className="grid lg:grid-cols-2 gap-8 items-start">
          <div>
            <div className="flex items-center gap-3 mb-5">
              <div className="w-12 h-12 rounded-full grid place-items-center text-lg font-bold" style={{ background: "linear-gradient(135deg,#6366F1,#22D3EE)" }}>A</div>
              <div><p className="font-semibold">Alex</p><p className="text-sm text-slate-400">French Villa Expert</p></div>
            </div>
            <p className="text-slate-300 mb-4 leading-relaxed">Alex has spent a decade curating the best French villas for high-end travellers. With Qiko, they described their ideal assistant in plain English, uploaded their villa notes, client preferences, and past recommendations, and let Qiko handle the models and GPUs.</p>
            <p className="text-slate-400 mb-6 leading-relaxed">Alex now licenses their knowledge to users wanting to buy or rent a villa in France. They help them find the perfect property based on their unique and expert knowledge 24/7.</p>
            <div className="grid grid-cols-3 gap-4 mb-6">
              {[["1 day", "Time to first model"], ["Sub-second", "Response time"], ["Per agency", "Revenue model"]].map(([v, l]) => (
                <div key={l} className="glass-card p-4">
                  <p className="text-xl font-bold text-[#22D3EE]">{v}</p><p className="text-xs text-slate-500 mt-1">{l}</p>
                </div>
              ))}
            </div>
            <div className="flex flex-wrap gap-2">
              {["Digital Twin", "Earn While You Sleep", "Full Control"].map((t) => (
                <span key={t} className="text-xs px-3 py-1 rounded-full bg-[#6366F1]/10 border border-[#6366F1]/30 text-[#a5b4fc]">{t}</span>
              ))}
            </div>
          </div>
          <div className="relative bg-[#0a0f1a] border border-white/10 rounded-2xl p-5">
            <div className="flex items-center gap-3 pb-4 border-b border-white/5 mb-4">
              <div className="w-9 h-9 rounded-full grid place-items-center text-sm font-bold" style={{ background: "linear-gradient(135deg,#6366F1,#22D3EE)" }}>A</div>
              <div><p className="text-sm font-semibold">Alex.AI</p><p className="text-xs text-[#22D3EE]">French Villa Expert • Online</p></div>
            </div>
            <div className="space-y-3 text-sm">
              <div className="flex justify-end"><div className="bg-[#6366F1] text-white rounded-2xl rounded-br-sm px-3.5 py-2 max-w-[85%]">Hi Alex, I&apos;m looking for a villa in Provence for a family reunion next summer. We&apos;ll be 12 people.</div></div>
              <div className="flex justify-start"><div className="bg-[#141a28] text-slate-200 rounded-2xl rounded-bl-sm px-3.5 py-2 max-w-[85%]">Lovely! Provence is perfect for family gatherings. A few questions to find your ideal property:</div></div>
              <div className="flex justify-start"><div className="bg-[#141a28] text-slate-200 rounded-2xl rounded-bl-sm px-3.5 py-2 max-w-[85%]">Do you prefer the Luberon valley (charming hilltop villages, lavender fields) or closer to the coast near Saint-Rémy?</div></div>
              <div className="flex justify-end"><div className="bg-[#6366F1] text-white rounded-2xl rounded-br-sm px-3.5 py-2 max-w-[85%]">Luberon sounds magical. We have toddlers so fenced pool is essential.</div></div>
              <div className="flex justify-start"><div className="bg-[#141a28] text-slate-200 rounded-2xl rounded-bl-sm px-3.5 py-2 max-w-[85%]">Perfect choice. For the Luberon with child-safe pools, I&apos;d recommend Mas de Bonnieux or Domaine des Oliviers—both have enclosed gardens near Gordes. Shall I compare their chef and concierge options?</div></div>
            </div>
          </div>
        </div>
      </section>

      {/* What Qiko handles */}
      <section id="enterprise" className="relative z-10 px-4 py-20 max-w-6xl mx-auto">
        <div className="text-center mb-14">
          <Eyebrow>WE DO THE HARD WORK</Eyebrow>
          <h2 className="text-3xl md:text-5xl font-bold mb-4" style={{ fontFamily: "Satoshi, sans-serif" }}>What Qiko handles for you</h2>
          <p className="text-slate-400 max-w-2xl mx-auto">Qiko is everything between your expertise and a production-ready LLM business—handled for you.</p>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {HANDLES.map((h) => (
            <div key={h.title} className="glass-card p-6">
              <div className="w-10 h-10 rounded-lg grid place-items-center mb-4" style={{ background: "#22D3EE18", boxShadow: "0 0 20px #22D3EE22" }}><h.icon className="w-5 h-5 text-[#22D3EE]" /></div>
              <h3 className="font-semibold mb-1">{h.title}</h3>
              <p className="text-sm text-slate-400">{h.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Who it's for */}
      <section className="relative z-10 px-4 py-20 max-w-6xl mx-auto">
        <div className="text-center mb-14">
          <Eyebrow>BUILT FOR CREATORS</Eyebrow>
          <h2 className="text-3xl md:text-5xl font-bold" style={{ fontFamily: "Satoshi, sans-serif" }}>Who Qiko is for</h2>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {WHO.map((w) => (
            <div key={w.title} className="bg-gradient-to-b from-[#0a0f1a] to-[#0a0f1a]/40 border border-white/5 rounded-xl p-6">
              <h3 className="font-semibold mb-2 text-[#22D3EE]">{w.title}</h3>
              <p className="text-sm text-slate-400">{w.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Final CTA */}
      <section id="pricing" className="relative z-10 px-4 py-24">
        <div className="max-w-2xl mx-auto text-center relative">
          <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[300px] rounded-full opacity-25 pointer-events-none" style={{ background: "radial-gradient(circle,#6366F1 0%,transparent 70%)", filter: "blur(60px)" }} />
          <h2 className="text-3xl md:text-5xl font-bold mb-4 relative" style={{ fontFamily: "Satoshi, sans-serif" }}>Ready to build your digital worker?</h2>
          <p className="text-slate-400 mb-8 relative">Tell Qiko what you do. We'll design, deploy, and host your digital worker so you can start selling it.</p>
          <button onClick={go} className="relative bg-gradient-to-r from-[#6366F1] via-[#A855F7] to-[#22D3EE] text-white font-semibold px-10 py-4 rounded-full text-lg shadow-2xl shadow-[#6366F1]/40 inline-flex items-center">
            Create my digital worker <ArrowRight className="w-5 h-5 ml-2" />
          </button>
        </div>
      </section>

      {/* Footer */}
      <footer className="relative z-10 border-t border-white/5 px-6 py-12">
        <div className="max-w-6xl mx-auto grid sm:grid-cols-3 gap-8">
          <div>
            <img src="/qiko-logo.webp" alt="Qiko" className="h-7 w-auto mb-4" />
            <p className="text-sm text-slate-500 max-w-xs">Turn your deep expertise into scalable, secure AI products. Qiko handles the models, GPUs, and infrastructure so you can focus on what you know best.</p>
          </div>
          <div>
            <h4 className="font-semibold mb-3 text-sm">Product</h4>
            <ul className="space-y-2 text-sm text-slate-400">
              <li><a href="#" className="hover:text-white">Home</a></li>
              <li><a href="#why" className="hover:text-white">About</a></li>
              <li><a href="#enterprise" className="hover:text-white">Enterprise</a></li>
              <li><a href="#pricing" className="hover:text-white">Pricing</a></li>
            </ul>
          </div>
          <div>
            <h4 className="font-semibold mb-3 text-sm">Company</h4>
            <ul className="space-y-2 text-sm text-slate-400">
              <li><a href="mailto:support@qiko.ai" className="hover:text-white">Contact</a></li>
              <li><a href="#" className="hover:text-white">Terms and Conditions</a></li>
            </ul>
          </div>
        </div>
        <p className="text-center text-xs text-slate-600 mt-10">© 2026 Qiko. All rights reserved.</p>
      </footer>
    </div>
  );
}
