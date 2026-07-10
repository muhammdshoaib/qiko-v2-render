"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

// Exact HTML extracted from the live stage.qiko.ai deployment (qiko-frontend's
// client/src/new-site/content/home.ts, itself "auto-generated from wireframe").
// Kept byte-for-byte so styling/spacing/gradients match the real site exactly,
// same pattern the real site uses (`dangerouslySetInnerHTML` + a data-action
// click-delegation root, see ActionDelegator below).
const HOME_HTML = `<main>

    
    <section style="position:relative;max-width:1200px;margin:0 auto;padding:60px 24px 58px;">
      <div style="position:absolute;inset:0;overflow:hidden;pointer-events:none;z-index:0;">
        <div style="position:absolute;top:-120px;left:-80px;width:520px;height:520px;border-radius:50%;background:radial-gradient(circle,rgba(34,160,245,.22),transparent 65%);animation:qfloat 13s ease-in-out infinite;"></div>
        <div style="position:absolute;top:40px;right:-120px;width:560px;height:560px;border-radius:50%;background:radial-gradient(circle,rgba(168,85,247,.2),transparent 65%);animation:qfloat2 16s ease-in-out infinite;"></div>
        <div style="position:absolute;inset:0;background-image:linear-gradient(#0e1830 1px,transparent 1px),linear-gradient(90deg,#0e1830 1px,transparent 1px);background-size:46px 46px;opacity:.35;mask-image:radial-gradient(circle at 50% 30%,#000,transparent 75%);-webkit-mask-image:radial-gradient(circle at 50% 30%,#000,transparent 75%);"></div>
      </div>
      <div class="q-hero" style="position:relative;z-index:1;display:grid;grid-template-columns:1.05fr .95fr;gap:54px;align-items:center;">
        <div>
          <h1 style="font-size:clamp(38px,5.2vw,62px);font-weight:700;letter-spacing:-.03em;line-height:1.03;margin:0 0 22px;">AI now decides which businesses get found. <span style="background:linear-gradient(115deg,#22D3EE,#4F8FF7 50%,#A855F7);-webkit-background-clip:text;background-clip:text;color:transparent;">Find out if yours is one of them.</span></h1>
          <p style="font-size:18px;line-height:1.6;color:#AEB9C9;max-width:54ch;margin:0 0 30px;">Qiko shows you how AI engines see your brand today, then helps you become visible, understood, and ready for a world where AI does the searching.</p>
          <div style="display:flex;flex-wrap:wrap;gap:14px;align-items:center;">
            <a data-action="goAudit" role="button" tabindex="0" style="cursor:pointer;display:inline-flex;align-items:center;gap:8px;font-size:15.5px;font-weight:700;color:#fff;text-decoration:none;background:linear-gradient(115deg,#22D3EE,#4F8FF7 55%,#6E73F2);padding:15px 26px;border-radius:999px;box-shadow:0 14px 38px -12px rgba(79,143,247,.75);">Run your free assessment <span>&#8594;</span></a>
            <a data-action="goSignal" role="button" tabindex="0" style="display:inline-flex;align-items:center;gap:8px;font-size:15.5px;font-weight:600;color:#E8EEF6;text-decoration:none;background:rgba(255,255,255,.04);border:1px solid #283349;padding:15px 24px;border-radius:999px;cursor:pointer;">Explore Signal</a>
          </div>
          <p style="font-family:'Geist Mono',monospace;font-size:12.5px;color:#6B7689;margin:18px 0 0;">One free assessment to get started</p>
        </div>
        
        <div style="position:relative;">
          <div style="position:absolute;inset:-1px;border-radius:22px;background:linear-gradient(140deg,rgba(34,211,238,.5),rgba(168,85,247,.4));filter:blur(22px);opacity:.45;"></div>
          <div style="position:relative;background:linear-gradient(165deg,#0d1526,#0a1120);border:1px solid #1d2942;border-radius:20px;padding:22px;box-shadow:0 40px 80px -30px rgba(0,0,0,.8);">
            <div style="display:flex;align-items:center;gap:11px;margin-bottom:18px;">
              <span style="width:34px;height:34px;border-radius:10px;background:linear-gradient(135deg,#0e3a4a,#10324a);display:grid;place-items:center;border:1px solid #1d4253;"><svg width="17" height="17" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="8.5" stroke="#34d399" stroke-width="2"></circle><line x1="12" y1="12" x2="12" y2="7.5" stroke="#34d399" stroke-width="2" stroke-linecap="round"></line><line x1="12" y1="12" x2="15.5" y2="13.5" stroke="#34d399" stroke-width="2" stroke-linecap="round"></line></svg></span>
              <div><b style="display:block;font-size:14.5px;letter-spacing:-.01em;">Qiko Signal</b><small style="font-size:11.5px;color:#7f93a8;">Your business visibility health</small></div>
            </div>
            <div style="display:flex;gap:12px;">
              <div style="flex:1;background:#0f1c30;border:1px solid #1e2e48;border-radius:14px;padding:15px;display:flex;gap:13px;align-items:center;">
                <div style="width:62px;height:62px;border-radius:50%;background:conic-gradient(#7C8CFF 54%,#1c2c44 0);display:grid;place-items:center;flex:0 0 auto;"><i style="width:46px;height:46px;border-radius:50%;background:#0f1c30;display:grid;place-items:center;font-style:normal;font-weight:700;font-size:18px;color:#fff;">54</i></div>
                <div><b style="display:block;font-size:13px;letter-spacing:.04em;color:#fff;">SEO</b><small style="font-size:11px;color:#7f93a8;">Traditional search</small><span style="font-family:'Geist Mono',monospace;font-size:10.5px;color:#9fb3c8;display:block;margin-top:5px;">You 54 &middot; Target 75</span></div>
              </div>
              <div style="flex:1;background:#0f1c30;border:1px solid #1e2e48;border-radius:14px;padding:15px;display:flex;gap:13px;align-items:center;">
                <div style="width:62px;height:62px;border-radius:50%;background:conic-gradient(#34d399 64%,#1c2c44 0);display:grid;place-items:center;flex:0 0 auto;"><i style="width:46px;height:46px;border-radius:50%;background:#0f1c30;display:grid;place-items:center;font-style:normal;font-weight:700;font-size:18px;color:#fff;">64</i></div>
                <div><b style="display:block;font-size:13px;letter-spacing:.04em;color:#fff;">AIO</b><small style="font-size:11px;color:#7f93a8;">AI search</small><span style="font-family:'Geist Mono',monospace;font-size:10.5px;color:#9fb3c8;display:block;margin-top:5px;">You 64 &middot; Target 80</span></div>
              </div>
            </div>
            <p style="border-left:3px solid #34d399;padding:7px 0 7px 13px;color:#cfe0ee;font-size:13px;margin:18px 0 8px;font-style:italic;">AI recommends you for 64% of tracked queries &mdash; invisible for the high-intent searches that win deals.</p>
            <div>
              <div style="display:flex;justify-content:space-between;align-items:center;border-top:1px solid #1d2942;padding:10px 0;font-size:12.5px;color:#a7b8c9;"><span>Problem search &middot; competitors recommended</span><span style="font-family:'Geist Mono',monospace;font-weight:700;color:#f0726a;">38%</span></div>
              <div style="display:flex;justify-content:space-between;align-items:center;border-top:1px solid #1d2942;padding:10px 0;font-size:12.5px;color:#a7b8c9;"><span>Feature search &middot; capability not attributed</span><span style="font-family:'Geist Mono',monospace;font-weight:700;color:#f0b249;">55%</span></div>
              <div style="display:flex;justify-content:space-between;align-items:center;border-top:1px solid #1d2942;padding:10px 0;font-size:12.5px;color:#a7b8c9;"><span>Brand search &middot; AI knows who you are</span><span style="font-family:'Geist Mono',monospace;font-weight:700;color:#34d399;">92%</span></div>
            </div>
          </div>
        </div>
      </div>
    </section>

    
    <section id="signal-section" style="max-width:1200px;margin:0 auto;padding:54px 24px;scroll-margin-top:96px;">
      <div style="font-size:12.5px;font-weight:600;letter-spacing:.18em;text-transform:uppercase;background:linear-gradient(100deg,#2DD4DA,#A855F7);-webkit-background-clip:text;background-clip:text;color:transparent;margin-bottom:14px;text-align:center;">Qiko Signal</div>
      <h2 style="font-size:clamp(30px,4vw,44px);font-weight:700;letter-spacing:-.025em;line-height:1.08;margin:0 0 18px;max-width:18ch;margin-left:auto;margin-right:auto;text-align:center;">See your brand the way AI does.</h2>
      <p style="font-size:17px;line-height:1.65;color:#AEB9C9;max-width:66ch;margin:0 auto 40px;text-align:center;">Signal runs your website or brand through the engines people now ask first &mdash; ChatGPT, Gemini, Claude and Perplexity. You get a clear visibility score, what AI says about you next to your competitors, and a short list of the highest-impact fixes across SEO and AI optimisation (AIO).</p>
      <div class="q-3col" style="display:grid;grid-template-columns:repeat(3,1fr);gap:18px;">
        <div style="background:linear-gradient(165deg,#0c1422,#0a1018);border:1px solid #18223a;border-radius:18px;padding:26px;">
          <div style="width:48px;height:48px;border-radius:13px;background:linear-gradient(150deg,rgba(34,211,238,.24),rgba(79,143,247,.05));border:1px solid rgba(45,212,218,.22);display:grid;place-items:center;margin-bottom:18px;position:relative;"><span style="position:absolute;width:22px;height:22px;border-radius:50%;border:2.5px solid #22D3EE;left:11px;top:11px;"></span><span style="position:absolute;width:8px;height:8px;border-radius:50%;background:#A855F7;right:11px;bottom:11px;"></span></div>
          <b style="display:block;font-size:17px;margin-bottom:7px;">Know your score</b><span style="font-size:14.5px;color:#9aa6b8;line-height:1.55;">One number for how visible and accurate you are across AI search.</span>
        </div>
        <div style="background:linear-gradient(165deg,#0c1422,#0a1018);border:1px solid #18223a;border-radius:18px;padding:26px;">
          <div style="width:48px;height:48px;border-radius:13px;background:linear-gradient(150deg,rgba(79,143,247,.24),rgba(110,115,242,.05));border:1px solid rgba(79,143,247,.26);display:grid;place-items:center;margin-bottom:18px;position:relative;"><span style="position:absolute;width:20px;height:20px;border-radius:5px;border:2.5px solid #4F8FF7;left:9px;top:9px;"></span><span style="position:absolute;width:20px;height:20px;border-radius:5px;background:rgba(168,85,247,.5);right:9px;bottom:9px;"></span></div>
          <b style="display:block;font-size:17px;margin-bottom:7px;">See the gap</b><span style="font-size:14.5px;color:#9aa6b8;line-height:1.55;">Where AI recommends competitors instead of you, and exactly why.</span>
        </div>
        <div style="background:linear-gradient(165deg,#0c1422,#0a1018);border:1px solid #18223a;border-radius:18px;padding:26px;">
          <div style="width:48px;height:48px;border-radius:13px;background:linear-gradient(150deg,rgba(168,85,247,.24),rgba(79,143,247,.05));border:1px solid rgba(168,85,247,.26);display:grid;place-items:center;margin-bottom:18px;position:relative;"><span style="position:absolute;width:0;height:0;border-left:11px solid transparent;border-right:11px solid transparent;border-bottom:18px solid #A855F7;left:13px;top:9px;"></span><span style="position:absolute;width:10px;height:10px;border-radius:50%;background:#22D3EE;right:10px;bottom:11px;"></span></div>
          <b style="display:block;font-size:17px;margin-bottom:7px;">Act on it</b><span style="font-size:14.5px;color:#9aa6b8;line-height:1.55;">Prioritised fixes you can ship this week &mdash; not a 60-page report.</span>
        </div>
      </div>
      <p style="font-size:16px;font-weight:600;color:#E8EEF6;margin:34px auto 0;text-align:center;max-width:60ch;">Strong visibility is the foundation. Here is what it unlocks.</p>
    </section>

    
    <section id="journey-section" style="position:relative;padding:54px 24px;overflow:hidden;scroll-margin-top:96px;">
      <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:900px;height:400px;background:radial-gradient(ellipse,rgba(79,143,247,.1),transparent 70%);pointer-events:none;"></div>
      <div style="position:relative;max-width:1200px;margin:0 auto;">
        <div style="font-size:12.5px;font-weight:600;letter-spacing:.18em;text-transform:uppercase;color:#7fdce6;margin-bottom:14px;text-align:center;">The Qiko journey</div>
        <h2 style="font-size:clamp(30px,4vw,44px);font-weight:700;letter-spacing:-.025em;line-height:1.08;margin:0 0 16px;text-align:center;">Visibility is step one.</h2>
        <p style="font-size:17px;line-height:1.65;color:#AEB9C9;max-width:64ch;margin:0 auto 54px;text-align:center;">Getting seen by AI is where it starts. Being represented accurately &mdash; and eventually transacted with &mdash; is where it goes. Qiko takes you along that path at your pace.</p>
        <div class="q-jwrap" style="position:relative;">
          <div class="q-jline" style="position:absolute;top:36px;left:12%;right:12%;height:2px;background:linear-gradient(90deg,#22D3EE,#4F8FF7,#A855F7);opacity:.5;z-index:0;"></div>
          <div class="q-journey" style="display:flex;align-items:stretch;gap:0;position:relative;z-index:1;">
          <div style="flex:1;position:relative;z-index:1;padding:0 14px;">
            <div style="width:72px;height:72px;border-radius:20px;background:linear-gradient(150deg,#0d2a38,#0c1a2c);border:1px solid #1c4254;display:grid;place-items:center;margin-bottom:20px;box-shadow:0 0 40px -8px rgba(34,211,238,.45);"><span style="width:24px;height:24px;border-radius:50%;border:3px solid #22D3EE;position:relative;"><span style="position:absolute;inset:5px;border-radius:50%;background:#22D3EE;"></span></span></div>
            <span style="display:inline-flex;align-items:center;gap:6px;font-family:'Geist Mono',monospace;font-size:11px;color:#34d399;border:1px solid #1c4a36;background:rgba(20,60,42,.4);padding:4px 10px;border-radius:999px;margin-bottom:12px;"><span style="width:6px;height:6px;border-radius:50%;background:#34d399;"></span>Live now</span>
            <b style="display:block;font-size:19px;margin:6px 0 8px;">Be seen</b>
            <span style="font-size:14.5px;color:#9aa6b8;line-height:1.55;">Signal makes sure AI engines can find, read, and cite your brand.</span>
            <div style="font-family:'Geist Mono',monospace;font-size:11px;color:#6B7689;margin-top:14px;">STEP 01</div>
          </div>
          <div style="flex:1;position:relative;z-index:1;padding:0 14px;">
            <div style="width:72px;height:72px;border-radius:20px;background:linear-gradient(150deg,#16243f,#0c1626);border:1px solid #25345a;display:grid;place-items:center;margin-bottom:20px;box-shadow:0 0 40px -8px rgba(79,143,247,.4);"><span style="width:24px;height:24px;border-radius:7px;border:3px solid #4F8FF7;position:relative;"><span style="position:absolute;inset:5px;border-radius:3px;background:#4F8FF7;"></span></span></div>
            <span style="display:inline-flex;align-items:center;gap:6px;font-family:'Geist Mono',monospace;font-size:11px;color:#34d399;border:1px solid #1c4a36;background:rgba(20,60,42,.4);padding:4px 10px;border-radius:999px;margin-bottom:12px;"><span style="width:6px;height:6px;border-radius:50%;background:#34d399;"></span>Available now</span>
            <b style="display:block;font-size:19px;margin:6px 0 8px;">Be understood</b>
            <span style="font-size:14.5px;color:#9aa6b8;line-height:1.55;">Structure your knowledge, guardrails, and processes so AI represents you accurately &mdash; not whatever it guesses.</span>
            <div style="font-family:'Geist Mono',monospace;font-size:11px;color:#6B7689;margin-top:14px;">STEP 02</div>
          </div>
          <div style="flex:1;position:relative;z-index:1;padding:0 14px;">
            <div style="width:72px;height:72px;border-radius:20px;background:linear-gradient(150deg,#241a3d,#130f24);border:1px solid #3a2a5c;display:grid;place-items:center;margin-bottom:20px;box-shadow:0 0 40px -8px rgba(168,85,247,.4);"><span style="width:0;height:0;border-left:13px solid transparent;border-right:13px solid transparent;border-bottom:22px solid #A855F7;"></span></div>
            <span style="display:inline-flex;align-items:center;gap:6px;font-family:'Geist Mono',monospace;font-size:11px;color:#c79bff;border:1px solid #3a2a5c;background:rgba(50,30,80,.4);padding:4px 10px;border-radius:999px;margin-bottom:12px;"><span style="width:6px;height:6px;border-radius:50%;background:#A855F7;"></span>On the horizon</span>
            <b style="display:block;font-size:19px;margin:6px 0 8px;">Be acted on</b>
            <span style="font-size:14.5px;color:#9aa6b8;line-height:1.55;">As agents start to transact directly, the businesses already structured for it win. You will be ready.</span>
            <div style="font-family:'Geist Mono',monospace;font-size:11px;color:#6B7689;margin-top:14px;">STEP 03</div>
          </div>
        </div>
        </div>
      </div>
    </section>

    
    <section id="labs-section" style="max-width:1200px;margin:0 auto;padding:54px 24px;scroll-margin-top:96px;">
      <div style="font-size:12.5px;font-weight:600;letter-spacing:.18em;text-transform:uppercase;color:#7fdce6;margin-bottom:14px;text-align:center;">Get started</div>
      <h2 style="font-size:clamp(30px,4vw,44px);font-weight:700;letter-spacing:-.025em;line-height:1.08;margin:0 0 38px;text-align:center;">Two ways to work with Qiko.</h2>
      <div class="q-2col" style="display:grid;grid-template-columns:1fr 1fr;gap:20px;">
        <div style="position:relative;background:linear-gradient(165deg,#0e1830,#0b1322);border:1px solid #26406e;border-radius:20px;padding:34px;overflow:hidden;">
          <div style="position:absolute;top:-60px;right:-40px;width:200px;height:200px;border-radius:50%;background:radial-gradient(circle,rgba(34,211,238,.18),transparent 70%);"></div>
          <div style="position:relative;">
            <div style="font-family:'Geist Mono',monospace;font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:#7fdce6;margin-bottom:14px;">Self-serve</div>
            <h3 style="font-size:23px;font-weight:700;letter-spacing:-.02em;margin:0 0 12px;">Start with Signal</h3>
            <p style="font-size:15px;color:#9aa6b8;line-height:1.6;margin:0 0 26px;max-width:42ch;">Run a free assessment, see where you stand, and subscribe to track and improve your AI visibility over time. Best if you want to act now and move fast.</p>
            <a data-action="goAudit" role="button" tabindex="0" style="cursor:pointer;display:inline-flex;align-items:center;gap:8px;font-size:15px;font-weight:700;color:#fff;text-decoration:none;background:linear-gradient(115deg,#22D3EE,#4F8FF7 55%,#6E73F2);padding:13px 22px;border-radius:999px;box-shadow:0 12px 32px -12px rgba(79,143,247,.7);">Run your free assessment <span>&#8594;</span></a>
          </div>
        </div>
        <div style="background:linear-gradient(165deg,#0c1422,#0a1018);border:1px solid #18223a;border-radius:20px;padding:34px;">
          <div style="font-family:'Geist Mono',monospace;font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:#c79bff;margin-bottom:14px;">Enterprise</div>
          <h3 style="font-size:23px;font-weight:700;letter-spacing:-.02em;margin:0 0 12px;">Build with Qiko Labs</h3>
          <p style="font-size:15px;color:#9aa6b8;line-height:1.6;margin:0 0 26px;max-width:42ch;">For enterprises that want custom AI workers and agentic workflows without managing models, infrastructure, or security. We build it on Qiko, primed for what comes next.</p>
          <a data-action="goLabs" role="button" tabindex="0" style="display:inline-flex;align-items:center;gap:8px;font-size:15px;font-weight:600;color:#E8EEF6;text-decoration:none;background:rgba(255,255,255,.04);border:1px solid #283349;padding:13px 22px;border-radius:999px;cursor:pointer;">Build with Qiko Labs <span>&#8594;</span></a>
        </div>
      </div>
    </section>

    
    <section id="under-the-hood" style="max-width:1200px;margin:0 auto;padding:54px 24px;scroll-margin-top:96px;">
      <div style="font-size:12.5px;font-weight:600;letter-spacing:.18em;text-transform:uppercase;color:#7fdce6;margin-bottom:14px;text-align:center;">Under the hood</div>
      <h2 style="font-size:clamp(30px,4vw,44px);font-weight:700;letter-spacing:-.025em;line-height:1.08;margin:0 0 16px;text-align:center;">Serious infrastructure, quietly handled.</h2>
      <p style="font-size:17px;line-height:1.65;color:#AEB9C9;max-width:64ch;margin:0 auto 38px;text-align:center;">Everything Qiko ships sits on enterprise-grade foundations so you do not have to build them. Multiple frontier models, your data isolated and encrypted, hosted in your region.</p>
      <div class="q-4col" style="display:grid;grid-template-columns:repeat(2,1fr);gap:18px;">
        <div style="display:flex;gap:18px;background:linear-gradient(165deg,#0c1422,#0a1018);border:1px solid #18223a;border-radius:18px;padding:26px;">
          <div style="flex:0 0 auto;width:46px;height:46px;border-radius:12px;background:linear-gradient(150deg,rgba(34,211,238,.24),rgba(79,143,247,.05));border:1px solid rgba(45,212,218,.22);position:relative;"><span style="position:absolute;width:13px;height:13px;border-radius:50%;background:#22D3EE;left:9px;top:16px;"></span><span style="position:absolute;width:13px;height:13px;border-radius:50%;border:2px solid #A855F7;left:18px;top:11px;"></span><span style="position:absolute;width:13px;height:13px;border-radius:50%;border:2px solid #4F8FF7;left:23px;top:20px;"></span></div>
          <div><b style="display:block;font-size:16px;margin-bottom:6px;">Multi-model by design</b><span style="font-size:14px;color:#9aa6b8;line-height:1.55;">We route across leading models rather than betting on one.</span></div>
        </div>
        <div style="display:flex;gap:18px;background:linear-gradient(165deg,#0c1422,#0a1018);border:1px solid #18223a;border-radius:18px;padding:26px;">
          <div style="flex:0 0 auto;width:46px;height:46px;border-radius:12px;background:linear-gradient(150deg,rgba(79,143,247,.24),rgba(110,115,242,.05));border:1px solid rgba(79,143,247,.26);position:relative;"><span style="position:absolute;width:18px;height:22px;border-radius:4px 4px 7px 7px;border:2.5px solid #4F8FF7;left:14px;top:13px;"></span><span style="position:absolute;width:8px;height:8px;border-radius:50%;background:#A855F7;left:19px;top:20px;"></span></div>
          <div><b style="display:block;font-size:16px;margin-bottom:6px;">Your data, isolated</b><span style="font-size:14px;color:#9aa6b8;line-height:1.55;">Encrypted, region-hosted, never blended with anyone else's.</span></div>
        </div>
        <div style="display:flex;gap:18px;background:linear-gradient(165deg,#0c1422,#0a1018);border:1px solid #18223a;border-radius:18px;padding:26px;">
          <div style="flex:0 0 auto;width:46px;height:46px;border-radius:12px;background:linear-gradient(150deg,rgba(168,85,247,.24),rgba(79,143,247,.05));border:1px solid rgba(168,85,247,.26);position:relative;"><span style="position:absolute;width:14px;height:14px;border-radius:50%;border:2.5px solid #A855F7;left:8px;top:16px;"></span><span style="position:absolute;width:14px;height:14px;border-radius:50%;border:2.5px solid #22D3EE;left:22px;top:16px;"></span></div>
          <div><b style="display:block;font-size:16px;margin-bottom:6px;">Cross-examined, not guessed</b><span style="font-size:14px;color:#9aa6b8;line-height:1.55;">Every finding is challenged by multiple models before it reaches you.</span></div>
        </div>
        <div style="display:flex;gap:18px;background:linear-gradient(165deg,#0c1422,#0a1018);border:1px solid #18223a;border-radius:18px;padding:26px;">
          <div style="flex:0 0 auto;width:46px;height:46px;border-radius:12px;background:linear-gradient(150deg,rgba(34,211,238,.24),rgba(79,143,247,.05));border:1px solid rgba(45,212,218,.22);position:relative;"><span style="position:absolute;width:10px;height:10px;background:#22D3EE;left:10px;top:18px;"></span><span style="position:absolute;width:10px;height:10px;border:2px solid #A855F7;left:24px;top:11px;"></span><span style="position:absolute;width:10px;height:10px;border:2px solid #4F8FF7;left:24px;top:25px;"></span></div>
          <div><b style="display:block;font-size:16px;margin-bottom:6px;">Built to extend</b><span style="font-size:14px;color:#9aa6b8;line-height:1.55;">The platform that audits your visibility hosts the workers you build next.</span></div>
        </div>
      </div>
      <p style="font-size:16px;font-weight:600;color:#E8EEF6;margin:34px auto 0;text-align:center;max-width:60ch;">Those same foundations are what make you ready for what comes next.</p>
    </section>

    
    <section style="position:relative;padding:60px 24px;overflow:hidden;">
      <div style="position:absolute;top:0;right:-100px;width:600px;height:600px;border-radius:50%;background:radial-gradient(circle,rgba(168,85,247,.16),transparent 65%);pointer-events:none;animation:qfloat2 18s ease-in-out infinite;"></div>
      <div style="position:relative;max-width:1000px;margin:0 auto;text-align:center;">
        <div style="font-size:12.5px;font-weight:600;letter-spacing:.18em;text-transform:uppercase;background:linear-gradient(100deg,#2DD4DA,#A855F7);-webkit-background-clip:text;background-clip:text;color:transparent;margin-bottom:18px;">The bigger picture</div>
        <h2 style="font-size:clamp(30px,4.2vw,48px);font-weight:700;letter-spacing:-.03em;line-height:1.1;margin:0 auto 22px;max-width:20ch;">The web is becoming a place where AI agents act on your behalf.</h2>
        <p style="font-size:18px;line-height:1.7;color:#AEB9C9;max-width:62ch;margin:0 auto;">Today people ask AI for recommendations. Soon agents will research, compare, and transact with each other directly. The businesses that are discoverable and structured now are the ones that get chosen then. Longer term, Qiko becomes a marketplace of specialised intelligence you can tap on demand. Getting visible today is how you get there.</p>
      </div>
    </section>

    
    <section style="position:relative;max-width:1200px;margin:0 auto;padding:30px 24px 100px;">
      <div style="position:relative;border-radius:26px;border:1px solid #1f2c48;background:linear-gradient(160deg,#0f1830,#0a1020);overflow:hidden;padding:64px 48px;text-align:center;">
        <div style="position:absolute;inset:0;background-image:linear-gradient(#13203a 1px,transparent 1px),linear-gradient(90deg,#13203a 1px,transparent 1px);background-size:42px 42px;opacity:.4;mask-image:radial-gradient(circle at 50% 40%,#000,transparent 72%);-webkit-mask-image:radial-gradient(circle at 50% 40%,#000,transparent 72%);"></div>
        <div style="position:relative;">
          <div style="font-size:12.5px;font-weight:600;letter-spacing:.18em;text-transform:uppercase;color:#7fdce6;margin-bottom:16px;">Find out where you stand</div>
          <h2 style="font-size:clamp(32px,4.5vw,52px);font-weight:700;letter-spacing:-.03em;line-height:1.05;margin:0 auto 16px;max-width:16ch;">See how AI sees your business.</h2>
          <p style="font-size:18px;color:#AEB9C9;margin:0 auto 32px;max-width:46ch;">It takes one scan to find out. Start free.</p>
          <div style="display:flex;flex-wrap:wrap;gap:14px;justify-content:center;">
            <a data-action="goAudit" role="button" tabindex="0" style="cursor:pointer;display:inline-flex;align-items:center;gap:8px;font-size:15.5px;font-weight:700;color:#fff;text-decoration:none;background:linear-gradient(115deg,#22D3EE,#4F8FF7 55%,#6E73F2);padding:15px 28px;border-radius:999px;box-shadow:0 14px 38px -12px rgba(79,143,247,.75);">Run your free assessment <span>&#8594;</span></a>
            <a data-action="goLabs" role="button" tabindex="0" style="display:inline-flex;align-items:center;gap:8px;font-size:15.5px;font-weight:600;color:#E8EEF6;text-decoration:none;background:rgba(255,255,255,.04);border:1px solid #283349;padding:15px 26px;border-radius:999px;cursor:pointer;">Talk to Qiko Labs</a>
          </div>
        </div>
      </div>
    </section>
</main>`;

const dropdownItem: React.CSSProperties = {
  display: "block", padding: "9px 12px", borderRadius: 9, fontSize: 14, color: "#cdd7e3",
  textDecoration: "none", cursor: "pointer",
};

/** Nav -- ported 1:1 from the live site's client/src/new-site/components/Nav.tsx.
 * Sign in / Get started / Signal / Labs targets are adapted to this app's actual routes
 * (the real site links to separate /signal, /labs marketing pages this app doesn't have). */
function Nav({
  onSignal, onLabs, onAbout, onSignIn, onGetStarted,
  sigHow, sigCheck, sigPricing, labBuild, labHow, labWhy,
}: {
  onSignal: () => void; onLabs: () => void; onAbout: () => void;
  onSignIn: () => void; onGetStarted: () => void;
  sigHow: () => void; sigCheck: () => void; sigPricing: () => void;
  labBuild: () => void; labHow: () => void; labWhy: () => void;
}) {
  const [menu, setMenu] = useState<"signal" | "labs" | null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const closeMobileAnd = (fn: () => void) => () => { setMobileOpen(false); fn(); };

  return (
    <header style={{ position: "sticky", top: 0, zIndex: 80, padding: "16px 24px", background: "linear-gradient(#06080F 60%,rgba(6,8,15,0))" }}>
      <nav style={{
        maxWidth: 1200, margin: "0 auto", display: "flex", alignItems: "center", gap: 20,
        background: "rgba(13,18,32,.7)", backdropFilter: "blur(16px)", WebkitBackdropFilter: "blur(16px)",
        border: "1px solid #1a2336", borderRadius: 999, padding: "11px 13px 11px 22px",
      }}>
        <a onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })} style={{ display: "flex", alignItems: "center", textDecoration: "none", cursor: "pointer", flex: "0 0 auto" }}>
          <img src="/qiko-logo.webp" alt="Qiko" style={{ height: 30, width: "auto", display: "block" }} />
        </a>

        <div style={{ alignItems: "center", gap: 6, margin: "0 auto" }} className="hidden md:flex">
          <a onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })} style={{ fontSize: 14.5, fontWeight: 500, color: "#E6ECF5", textDecoration: "none", padding: "8px 14px", borderRadius: 999, cursor: "pointer" }}>Home</a>

          <div style={{ position: "relative", display: "flex", alignItems: "center" }}
               onMouseEnter={() => setMenu("signal")} onMouseLeave={() => setMenu(null)}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 14.5, fontWeight: 500, color: "#9aa6b8", padding: "8px 14px", borderRadius: 999, userSelect: "none" }}>
              Signal <span style={{ fontSize: 8, opacity: 0.65 }}>&#9660;</span>
            </span>
            {menu === "signal" && (
              <div style={{ position: "absolute", top: "100%", left: "50%", transform: "translateX(-50%)", paddingTop: 11, zIndex: 90 }}>
                <div style={{ background: "rgba(13,18,32,.97)", backdropFilter: "blur(16px)", WebkitBackdropFilter: "blur(16px)", border: "1px solid #1a2336", borderRadius: 14, padding: 7, minWidth: 206, boxShadow: "0 24px 48px -18px rgba(0,0,0,.7)" }}>
                  <a onClick={onSignal} style={dropdownItem}>Overview</a>
                  <a onClick={sigHow} style={dropdownItem}>How it works</a>
                  <a onClick={sigCheck} style={dropdownItem}>What we check</a>
                  <a onClick={sigPricing} style={dropdownItem}>Pricing</a>
                </div>
              </div>
            )}
          </div>

          <div style={{ position: "relative", display: "flex", alignItems: "center" }}
               onMouseEnter={() => setMenu("labs")} onMouseLeave={() => setMenu(null)}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 14.5, fontWeight: 500, color: "#9aa6b8", padding: "8px 14px", borderRadius: 999, userSelect: "none" }}>
              Labs <span style={{ fontSize: 8, opacity: 0.65 }}>&#9660;</span>
            </span>
            {menu === "labs" && (
              <div style={{ position: "absolute", top: "100%", left: "50%", transform: "translateX(-50%)", paddingTop: 11, zIndex: 90 }}>
                <div style={{ background: "rgba(13,18,32,.97)", backdropFilter: "blur(16px)", WebkitBackdropFilter: "blur(16px)", border: "1px solid #1a2336", borderRadius: 14, padding: 7, minWidth: 206, boxShadow: "0 24px 48px -18px rgba(0,0,0,.7)" }}>
                  <a onClick={onLabs} style={dropdownItem}>Overview</a>
                  <a onClick={labBuild} style={dropdownItem}>What we build</a>
                  <a onClick={labHow} style={dropdownItem}>How it works</a>
                  <a onClick={labWhy} style={dropdownItem}>Why Labs</a>
                </div>
              </div>
            )}
          </div>

          <a onClick={onAbout} style={{ fontSize: 14.5, fontWeight: 500, color: "#9aa6b8", textDecoration: "none", padding: "8px 14px", borderRadius: 999, cursor: "pointer" }}>About</a>
        </div>

        <div style={{ alignItems: "center", gap: 10, flex: "0 0 auto" }} className="hidden md:flex">
          <a onClick={onSignIn} style={{ fontSize: 14.5, fontWeight: 600, color: "#D6DEEA", textDecoration: "none", padding: "9px 8px", cursor: "pointer" }}>Sign in</a>
          <a onClick={onGetStarted} style={{ display: "inline-flex", alignItems: "center", gap: 7, fontSize: 14.5, fontWeight: 700, color: "#fff", textDecoration: "none", background: "linear-gradient(115deg,#22D3EE,#4F8FF7 55%,#6E73F2)", padding: "11px 20px", borderRadius: 999, boxShadow: "0 10px 30px -10px rgba(79,143,247,.7)", cursor: "pointer" }}>
            Get started <span style={{ fontSize: 15 }}>&#8594;</span>
          </a>
        </div>

        <button type="button" onClick={() => setMobileOpen((v) => !v)} aria-label="Menu" className="flex md:hidden"
          style={{ marginLeft: "auto", flex: "0 0 auto", alignItems: "center", justifyContent: "center", width: 42, height: 42, borderRadius: 12, background: "rgba(255,255,255,.05)", border: "1px solid #283349", cursor: "pointer", padding: 0 }}>
          <span style={{ position: "relative", display: "block", width: 18, height: 12 }}>
            <span style={{ position: "absolute", top: 0, left: 0, width: "100%", height: 2, background: "#E6ECF5", borderRadius: 2 }} />
            <span style={{ position: "absolute", top: 5, left: 0, width: "100%", height: 2, background: "#E6ECF5", borderRadius: 2 }} />
            <span style={{ position: "absolute", top: 10, left: 0, width: "100%", height: 2, background: "#E6ECF5", borderRadius: 2 }} />
          </span>
        </button>
      </nav>

      {mobileOpen && (
        <div style={{ maxWidth: 1200, margin: "10px auto 0", background: "rgba(13,18,32,.97)", backdropFilter: "blur(16px)", WebkitBackdropFilter: "blur(16px)", border: "1px solid #1a2336", borderRadius: 18, padding: 10, boxShadow: "0 24px 48px -18px rgba(0,0,0,.7)" }}>
          <a onClick={closeMobileAnd(() => window.scrollTo({ top: 0, behavior: "smooth" }))} style={{ display: "block", padding: "12px 14px", borderRadius: 10, fontSize: 15, fontWeight: 500, color: "#E6ECF5", textDecoration: "none", cursor: "pointer" }}>Home</a>
          <a onClick={closeMobileAnd(onSignal)} style={{ display: "block", padding: "12px 14px", borderRadius: 10, fontSize: 15, fontWeight: 500, color: "#E6ECF5", textDecoration: "none", cursor: "pointer" }}>Signal</a>
          <a onClick={closeMobileAnd(onLabs)} style={{ display: "block", padding: "12px 14px", borderRadius: 10, fontSize: 15, fontWeight: 500, color: "#E6ECF5", textDecoration: "none", cursor: "pointer" }}>Labs</a>
          <a onClick={closeMobileAnd(onAbout)} style={{ display: "block", padding: "12px 14px", borderRadius: 10, fontSize: 15, fontWeight: 500, color: "#E6ECF5", textDecoration: "none", cursor: "pointer" }}>About</a>
          <div style={{ height: 1, background: "#1a2336", margin: "8px 6px" }} />
          <a onClick={closeMobileAnd(onSignIn)} style={{ display: "block", padding: "12px 14px", borderRadius: 10, fontSize: 15, fontWeight: 600, color: "#D6DEEA", textDecoration: "none", cursor: "pointer" }}>Sign in</a>
          <a onClick={closeMobileAnd(onGetStarted)} style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 7, marginTop: 6, fontSize: 15, fontWeight: 700, color: "#fff", textDecoration: "none", background: "linear-gradient(115deg,#22D3EE,#4F8FF7 55%,#6E73F2)", padding: "13px 20px", borderRadius: 12, cursor: "pointer" }}>
            Get started <span>&#8594;</span>
          </a>
        </div>
      )}
    </header>
  );
}

/** Footer -- ported 1:1 from the live site's client/src/new-site/components/Footer.tsx. */
function Footer({ onSignal, onLabs, onAbout, onSignIn, onGetStarted }: {
  onSignal: () => void; onLabs: () => void; onAbout: () => void; onSignIn: () => void; onGetStarted: () => void;
}) {
  const linkStyle: React.CSSProperties = { display: "block", fontSize: 14, color: "#9aa6b8", textDecoration: "none", marginBottom: 11, cursor: "pointer" };
  const label: React.CSSProperties = { fontFamily: "'Geist Mono',monospace", fontSize: 11, letterSpacing: ".12em", textTransform: "uppercase", color: "#5a6679", marginBottom: 16 };
  return (
    <footer style={{ borderTop: "1px solid #11192b", background: "#070a12" }}>
      <div className="grid grid-cols-2 sm:grid-cols-[1.4fr_1fr_1fr_1fr]" style={{ maxWidth: 1200, margin: "0 auto", padding: "54px 24px 40px", gap: 34 }}>
        <div className="col-span-2 sm:col-span-1">
          <div style={{ display: "flex", alignItems: "center", marginBottom: 14 }}>
            <img src="/qiko-logo.webp" alt="Qiko" style={{ height: 28, width: "auto", display: "block" }} />
          </div>
          <p style={{ fontSize: 14, color: "#6B7689", lineHeight: 1.6, maxWidth: "32ch", margin: 0 }}>
            Be visible, understood, and ready for a world where AI does the searching.
          </p>
        </div>
        <div>
          <div style={label}>Product</div>
          <a onClick={onSignal} style={linkStyle}>Signal</a>
          <a onClick={onLabs} style={linkStyle}>Labs</a>
        </div>
        <div>
          <div style={label}>Company</div>
          <a onClick={onAbout} style={linkStyle}>About</a>
          <a onClick={onLabs} style={linkStyle}>Contact</a>
        </div>
        <div>
          <div style={label}>Account</div>
          <a onClick={onSignIn} style={linkStyle}>Sign in</a>
          <a onClick={onGetStarted} style={linkStyle}>Get started</a>
        </div>
      </div>
      <div style={{ maxWidth: 1200, margin: "0 auto", padding: "20px 24px 34px", borderTop: "1px solid #11192b", fontFamily: "'Geist Mono',monospace", fontSize: 11.5, color: "#4f5a6d" }}>
        &copy; {new Date().getFullYear()} Qiko
      </div>
    </footer>
  );
}

const ACTION_KEYS = new Set(["goAudit", "goSignal", "goLabs"]);

export default function LandingPage() {
  const router = useRouter();
  const rootRef = useRef<HTMLDivElement>(null);

  const scrollTo = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });

  const goAudit = () => router.push("/onboarding");
  const goSignal = () => scrollTo("signal-section");
  const goLabs = () => scrollTo("labs-section");
  const goAbout = () => scrollTo("under-the-hood");
  const goSignIn = () => router.push("/login");
  const goGetStarted = () => router.push("/onboarding");

  // Real site's dropdown sub-items each go to a distinct part of a separate /signal or /labs
  // page we don't have. Mapped to the closest distinct on-page equivalent instead of collapsing
  // every item in a menu onto the same handler.
  const sigHow = () => scrollTo("journey-section");
  const sigCheck = () => scrollTo("under-the-hood");
  const sigPricing = () => router.push("/onboarding");
  const labBuild = () => scrollTo("under-the-hood");
  const labHow = () => scrollTo("journey-section");
  const labWhy = () => window.open("mailto:support@qiko.ai?subject=Qiko%20Labs", "_blank");

  // Same click-delegation pattern as the live site's ActionDelegator: the inner HTML block
  // carries data-action="goAudit"/"goSignal"/"goLabs" attributes we wire up here rather than
  // duplicating the markup as JSX (keeps it byte-identical to the deployed source).
  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const actionFns: Record<string, () => void> = { goAudit, goSignal, goLabs };
    const onClick = (e: MouseEvent) => {
      const target = (e.target as HTMLElement).closest("[data-action]") as HTMLElement | null;
      if (!target) return;
      const action = target.getAttribute("data-action");
      if (!action || !ACTION_KEYS.has(action)) return;
      e.preventDefault();
      actionFns[action]?.();
    };
    root.addEventListener("click", onClick);
    return () => root.removeEventListener("click", onClick);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      ref={rootRef}
      style={{
        background: "radial-gradient(1000px 600px at 82% -8%,rgba(34,160,245,.07),transparent 62%),radial-gradient(900px 560px at 8% 12%,rgba(168,85,247,.055),transparent 60%),#06080F",
        color: "#F4F7FB",
        fontFamily: "Geist,ui-sans-serif,system-ui,sans-serif",
        minHeight: "100vh",
        overflowX: "clip",
        WebkitFontSmoothing: "antialiased",
        lineHeight: 1.5,
      }}
    >
      <Nav onSignal={goSignal} onLabs={goLabs} onAbout={goAbout} onSignIn={goSignIn} onGetStarted={goGetStarted}
           sigHow={sigHow} sigCheck={sigCheck} sigPricing={sigPricing} labBuild={labBuild} labHow={labHow} labWhy={labWhy} />
      <div suppressHydrationWarning dangerouslySetInnerHTML={{ __html: HOME_HTML }} />
      <Footer onSignal={goSignal} onLabs={goLabs} onAbout={goAbout} onSignIn={goSignIn} onGetStarted={goGetStarted} />
    </div>
  );
}
