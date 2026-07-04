"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, MessageSquare, Globe, Shield, Clock } from "lucide-react";

const typingExamples = [
  "I am a golf travel specialist...",
  "I am a real estate advisor...",
  "I am a financial consultant...",
  "I am a fitness coach...",
  "I am a legal expert...",
  "I am a marketing strategist...",
];

const useCases = [
  { icon: MessageSquare, title: "Answer Questions", description: "Handle client inquiries automatically, even the tricky ones", color: "#6366F1" },
  { icon: Globe, title: "Never Miss a Lead", description: "Respond to prospects at 3am without lifting a finger", color: "#22D3EE" },
  { icon: Shield, title: "Sound Like You", description: "Your tone, your expertise, your way of explaining things", color: "#A855F7" },
  { icon: Clock, title: "Save Hours Daily", description: "Stop repeating yourself—let AI handle the routine stuff", color: "#EC4899" },
];

function useTypingAnimation(texts: string[], typingSpeed = 80, deletingSpeed = 40, pauseDuration = 2000) {
  const [displayText, setDisplayText] = useState("");
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isDeleting, setIsDeleting] = useState(false);
  useEffect(() => {
    const currentText = texts[currentIndex];
    const timeout = setTimeout(() => {
      if (!isDeleting) {
        if (displayText.length < currentText.length) setDisplayText(currentText.slice(0, displayText.length + 1));
        else setTimeout(() => setIsDeleting(true), pauseDuration);
      } else if (displayText.length > 0) setDisplayText(displayText.slice(0, -1));
      else { setIsDeleting(false); setCurrentIndex((p) => (p + 1) % texts.length); }
    }, isDeleting ? deletingSpeed : typingSpeed);
    return () => clearTimeout(timeout);
  }, [displayText, currentIndex, isDeleting, texts, typingSpeed, deletingSpeed, pauseDuration]);
  return displayText;
}

export default function LandingPage() {
  const router = useRouter();
  const [inputValue, setInputValue] = useState("");
  const [isFocused, setIsFocused] = useState(false);
  const animatedPlaceholder = useTypingAnimation(typingExamples);
  const getStarted = () => router.push("/onboarding");

  return (
    <div className="min-h-screen bg-[#050810] text-white overflow-x-hidden relative">
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute w-[600px] h-[600px] rounded-full opacity-30" style={{ background: "radial-gradient(circle, #6366F1 0%, transparent 70%)", top: "-10%", left: "20%", filter: "blur(80px)", animation: "float1 12s ease-in-out infinite" }} />
        <div className="absolute w-[500px] h-[500px] rounded-full opacity-25" style={{ background: "radial-gradient(circle, #22D3EE 0%, transparent 70%)", top: "30%", right: "10%", filter: "blur(80px)", animation: "float2 10s ease-in-out infinite" }} />
        <div className="absolute w-[400px] h-[400px] rounded-full opacity-20" style={{ background: "radial-gradient(circle, #A855F7 0%, transparent 70%)", bottom: "10%", left: "30%", filter: "blur(80px)", animation: "float3 14s ease-in-out infinite" }} />
        <div className="absolute inset-0 opacity-[0.03]" style={{ backgroundImage: "linear-gradient(rgba(99,102,241,0.3) 1px, transparent 1px), linear-gradient(90deg, rgba(99,102,241,0.3) 1px, transparent 1px)", backgroundSize: "60px 60px" }} />
      </div>

      <header className="fixed top-0 left-0 right-0 z-50 bg-[#050810]/60 backdrop-blur-xl border-b border-white/5">
        <div className="mx-auto flex items-center justify-between h-16 px-6 max-w-6xl">
          <img src="/qiko-logo.webp" alt="Qiko" className="h-8 w-auto" style={{ filter: "drop-shadow(0 0 10px rgba(99,102,241,0.5))" }} />
          <div className="flex items-center gap-3">
            <button onClick={() => router.push("/login")} className="text-slate-300 hover:text-white hover:bg-white/10 font-medium px-4 py-2 rounded-full transition-all">Sign in</button>
            <button onClick={getStarted} className="bg-gradient-to-r from-[#6366F1] to-[#A855F7] text-white font-medium px-5 py-2 rounded-full shadow-lg shadow-[#6366F1]/25 transition-all hover:shadow-[#6366F1]/40">Get started</button>
          </div>
        </div>
      </header>

      <section className="relative pt-32 pb-20 px-4">
        <div className="relative z-10 max-w-4xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-[#6366F1]/10 border border-[#6366F1]/30 mb-8 backdrop-blur-sm">
            <span className="w-2 h-2 rounded-full bg-[#22D3EE] animate-pulse shadow-lg shadow-[#22D3EE]/50" />
            <span className="text-sm text-[#22D3EE] font-medium">Now in Beta • Join 500+ creators</span>
          </div>
          <h1 className="text-5xl md:text-7xl font-bold mb-6 leading-tight" style={{ fontFamily: "Satoshi, sans-serif", background: "linear-gradient(135deg, #ffffff 0%, #6366F1 50%, #22D3EE 100%)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", textShadow: "0 0 80px rgba(99,102,241,0.5)" }}>
            Build Your AI Expert
          </h1>
          <p className="text-xl md:text-2xl text-slate-300 mb-12 max-w-2xl mx-auto leading-relaxed">
            Train a custom AI on your expertise. Answer clients <span className="text-[#22D3EE]">24/7</span> with your knowledge, your tone, your way.
          </p>

          <div className="relative max-w-xl mx-auto mb-8 group">
            <div className="absolute -inset-[1px] rounded-2xl opacity-75 group-hover:opacity-100 transition-opacity" style={{ background: "linear-gradient(135deg, #6366F1, #22D3EE, #A855F7, #6366F1)", backgroundSize: "300% 300%", animation: "gradient-shift 4s ease infinite" }} />
            <div className="relative bg-[#0a0f1a] rounded-2xl p-6">
              <div className="relative mb-4 text-left">
                <input type="text" value={inputValue} onChange={(e) => setInputValue(e.target.value)} onFocus={() => setIsFocused(true)} onBlur={() => setIsFocused(false)} className="w-full bg-transparent text-white text-lg outline-none" />
                {!inputValue && !isFocused && (
                  <div className="absolute top-0 left-0 pointer-events-none text-lg text-slate-400">
                    {animatedPlaceholder}
                    <span className="inline-block w-0.5 h-5 bg-[#6366F1] ml-0.5 animate-pulse align-middle" />
                  </div>
                )}
                {!inputValue && isFocused && <div className="absolute top-0 left-0 pointer-events-none text-lg text-slate-500">Type your profession...</div>}
              </div>
              <div className="flex items-center justify-end">
                <button onClick={getStarted} className="bg-gradient-to-r from-[#6366F1] to-[#22D3EE] text-white font-semibold px-6 py-2.5 rounded-full flex items-center gap-2 shadow-lg shadow-[#6366F1]/30 hover:shadow-[#6366F1]/50">
                  Start Building <ArrowRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="py-16 px-4 relative z-10">
        <div className="max-w-5xl mx-auto grid grid-cols-2 md:grid-cols-4 gap-4">
          {useCases.map((u) => (
            <div key={u.title} className="group relative bg-[#0a0f1a]/80 backdrop-blur-sm rounded-xl p-5 border border-white/5 hover:border-transparent transition-all overflow-hidden">
              <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity" style={{ background: `radial-gradient(circle at center, ${u.color}15 0%, transparent 70%)` }} />
              <div className="w-10 h-10 rounded-lg flex items-center justify-center mb-3 relative" style={{ background: `${u.color}20`, boxShadow: `0 0 20px ${u.color}30` }}>
                <u.icon className="w-5 h-5" style={{ color: u.color }} />
              </div>
              <h3 className="font-semibold text-white mb-1 relative">{u.title}</h3>
              <p className="text-sm text-slate-400 relative">{u.description}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="py-24 px-4 relative z-10">
        <div className="max-w-2xl mx-auto text-center relative">
          <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[300px] rounded-full opacity-30 pointer-events-none" style={{ background: "radial-gradient(circle, #6366F1 0%, transparent 70%)", filter: "blur(60px)" }} />
          <h2 className="text-3xl md:text-5xl font-bold mb-6 relative" style={{ fontFamily: "Satoshi, sans-serif" }}>
            Ready to Build Your <span className="text-[#22D3EE]">AI Expert</span>?
          </h2>
          <p className="text-slate-400 mb-8 text-lg relative">Train a custom AI on your knowledge. You decide.</p>
          <button onClick={getStarted} className="relative bg-gradient-to-r from-[#6366F1] via-[#A855F7] to-[#22D3EE] text-white font-semibold px-10 py-4 rounded-full text-lg shadow-2xl shadow-[#6366F1]/40 hover:shadow-[#6366F1]/60 inline-flex items-center" style={{ backgroundSize: "200% 200%", animation: "gradient-shift 3s ease infinite" }}>
            Get Started Free <ArrowRight className="w-5 h-5 ml-2" />
          </button>
        </div>
      </section>

      <style>{`
        @keyframes float1 { 0%,100%{transform:translate(0,0) scale(1);} 33%{transform:translate(30px,-30px) scale(1.05);} 66%{transform:translate(-20px,20px) scale(0.95);} }
        @keyframes float2 { 0%,100%{transform:translate(0,0) scale(1);} 33%{transform:translate(-40px,20px) scale(1.1);} 66%{transform:translate(30px,-40px) scale(0.9);} }
        @keyframes float3 { 0%,100%{transform:translate(0,0) scale(1);} 50%{transform:translate(50px,-30px) scale(1.05);} }
        @keyframes gradient-shift { 0%{background-position:0% 50%;} 50%{background-position:100% 50%;} 100%{background-position:0% 50%;} }
      `}</style>
    </div>
  );
}
