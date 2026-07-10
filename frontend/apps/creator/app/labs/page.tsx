"use client";

import { useRouter } from "next/navigation";
import { QikoNav, QikoFooter } from "@/components/QikoSiteChrome";
import LabsContactForm from "@/components/LabsContactForm";

// Exact HTML extracted from the live stage.qiko.ai deployment (qiko-frontend's
// client/src/new-site/content/labs.ts, itself "auto-generated from wireframe"), minus its
// #lb-contact section -- that one is rendered as real JSX below (see LabsPage), with
// LabsContactForm as a normal child instead of a portal into a raw-HTML placeholder node
// (the real site does the latter via createPortal; not worth the hydration-timing risk here).
const LABS_HTML = `<main data-labs-page="">

    
    <section style="position:relative;max-width:1200px;margin:0 auto;padding:60px 24px 58px;">
      <div style="position:absolute;inset:0;overflow:hidden;pointer-events:none;z-index:0;">
        <div style="position:absolute;top:-100px;left:-80px;width:520px;height:520px;border-radius:50%;background:radial-gradient(circle,rgba(168,85,247,.2),transparent 65%);animation:qfloat 14s ease-in-out infinite;"></div>
        <div style="position:absolute;top:60px;right:-120px;width:540px;height:540px;border-radius:50%;background:radial-gradient(circle,rgba(34,160,245,.16),transparent 65%);animation:qfloat2 17s ease-in-out infinite;"></div>
      </div>
      <div class="q-hero" style="position:relative;z-index:1;display:grid;grid-template-columns:1.05fr .95fr;gap:54px;align-items:center;">
        <div>
          <div style="display:inline-flex;align-items:center;gap:9px;font-size:12.5px;font-weight:600;letter-spacing:.16em;text-transform:uppercase;color:#c79bff;border:1px solid #3a2a5c;background:rgba(50,30,80,.32);padding:7px 14px;border-radius:999px;margin-bottom:24px;white-space:nowrap;">Qiko Labs</div>
          <h1 style="font-size:clamp(34px,4.6vw,54px);font-weight:700;letter-spacing:-.03em;line-height:1.05;margin:0 0 22px;">Custom AI workers, built on Qiko. <span style="background:linear-gradient(115deg,#A855F7,#4F8FF7 60%,#22D3EE);-webkit-background-clip:text;background-clip:text;color:transparent;">Owned by you.</span></h1>
          <p style="font-size:18px;line-height:1.6;color:#AEB9C9;max-width:56ch;margin:0 0 30px;">Labs designs and ships bespoke agentic workers and workflows for enterprises that want a specialist built on their own data and judgment &mdash; not another generic model. We handle the models, infrastructure, and security. You own the result.</p>
          <div style="display:flex;flex-wrap:wrap;gap:14px;align-items:center;">
            <a href="#lb-contact" style="display:inline-flex;align-items:center;gap:8px;font-size:15.5px;font-weight:700;color:#fff;text-decoration:none;background:linear-gradient(115deg,#A855F7,#6E73F2 55%,#4F8FF7);padding:15px 26px;border-radius:999px;box-shadow:0 14px 38px -12px rgba(168,85,247,.7);">Talk to Labs <span>&#8594;</span></a>
            <a href="#lb-build" style="display:inline-flex;align-items:center;gap:8px;font-size:15.5px;font-weight:600;color:#E8EEF6;text-decoration:none;background:rgba(255,255,255,.04);border:1px solid #283349;padding:15px 24px;border-radius:999px;">See what we build</a>
          </div>
        </div>
        
        <div style="position:relative;">
          <div style="position:absolute;inset:-1px;border-radius:22px;background:linear-gradient(140deg,rgba(168,85,247,.45),rgba(34,211,238,.35));filter:blur(22px);opacity:.4;"></div>
          <div style="position:relative;background:linear-gradient(165deg,#0d1526,#0a1120);border:1px solid #1d2942;border-radius:20px;padding:24px;box-shadow:0 40px 80px -30px rgba(0,0,0,.8);">
            <div style="font-family:'Geist Mono',monospace;font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:#6B7689;margin-bottom:16px;">Your Labs build</div>
            <div style="display:flex;align-items:center;gap:14px;background:#0f1c30;border:1px solid #1e2e48;border-radius:14px;padding:16px;margin-bottom:10px;">
              <span style="flex:0 0 auto;width:40px;height:40px;border-radius:11px;background:rgba(168,85,247,.14);position:relative;"><span style="position:absolute;width:0;height:0;border-left:9px solid transparent;border-right:9px solid transparent;border-bottom:15px solid #A855F7;left:11px;top:8px;"></span><span style="position:absolute;width:7px;height:7px;border-radius:50%;background:#22D3EE;left:16px;top:26px;"></span></span>
              <div style="flex:1;"><b style="display:block;font-size:14px;color:#fff;">The worker</b><small style="font-size:11.5px;color:#7f93a8;">Reads inputs &middot; applies your logic &middot; returns output</small></div>
            </div>
            <div style="display:flex;justify-content:center;color:#34465e;font-size:13px;margin:2px 0;">&#8595;</div>
            <div style="display:flex;align-items:center;gap:14px;background:#0f1c30;border:1px solid #1e2e48;border-radius:14px;padding:16px;margin-bottom:10px;">
              <span style="flex:0 0 auto;width:40px;height:40px;border-radius:11px;background:rgba(79,143,247,.14);position:relative;"><span style="position:absolute;width:18px;height:13px;border-radius:3px;border:2.5px solid #4F8FF7;left:11px;top:12px;"></span><span style="position:absolute;width:18px;height:3px;background:#A855F7;left:11px;top:12px;"></span></span>
              <div style="flex:1;"><b style="display:block;font-size:14px;color:#fff;">Your dashboard</b><small style="font-size:11.5px;color:#7f93a8;">Built for the task &mdash; not a generic chat box</small></div>
            </div>
            <div style="display:flex;justify-content:center;color:#34465e;font-size:13px;margin:2px 0;">&#8595;</div>
            <div style="display:flex;align-items:center;gap:14px;background:#0f1c30;border:1px solid #1e2e48;border-radius:14px;padding:16px;">
              <span style="flex:0 0 auto;width:40px;height:40px;border-radius:11px;background:rgba(34,211,238,.14);position:relative;"><span style="position:absolute;width:14px;height:14px;border-radius:50%;border:2.5px solid #22D3EE;left:9px;top:13px;"></span><span style="position:absolute;width:6px;height:6px;border-radius:50%;background:#A855F7;left:13px;top:17px;"></span></span>
              <div style="flex:1;"><b style="display:block;font-size:14px;color:#fff;">Your controls</b><small style="font-size:11.5px;color:#7f93a8;">Prompts, guardrails, rules &amp; knowledge &mdash; yours to tune</small></div>
            </div>
            <div style="margin-top:16px;text-align:center;font-family:'Geist Mono',monospace;font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:#5a6679;border-top:1px solid #1d2942;padding-top:14px;">Runs on the Qiko platform</div>
          </div>
        </div>
      </div>
    </section>

    
    <section id="lb-build" style="max-width:1200px;margin:0 auto;padding:54px 24px;scroll-margin-top:96px;">
      <div style="font-size:12.5px;font-weight:600;letter-spacing:.18em;text-transform:uppercase;background:linear-gradient(100deg,#A855F7,#22D3EE);-webkit-background-clip:text;background-clip:text;color:transparent;margin-bottom:14px;text-align:center;">What we build</div>
      <h2 style="font-size:clamp(30px,4vw,44px);font-weight:700;letter-spacing:-.025em;line-height:1.08;margin:0 0 18px;max-width:18ch;margin-left:auto;margin-right:auto;text-align:center;">Built for your problem, not off a shelf.</h2>
      <p style="font-size:17px;line-height:1.65;color:#AEB9C9;max-width:66ch;margin:0 auto 40px;text-align:center;">Every Labs worker is designed around your data, your decisions, and the way your team already works. It takes your inputs, applies your logic, and returns something your team can act on. Teams put Labs workers to work to:</p>
      <div class="q-3col" style="display:grid;grid-template-columns:repeat(3,1fr);gap:18px;">
        <div style="background:linear-gradient(165deg,#0c1422,#0a1018);border:1px solid #18223a;border-radius:18px;padding:24px;">
          <div style="width:44px;height:44px;border-radius:12px;background:linear-gradient(150deg,rgba(34,211,238,.24),rgba(79,143,247,.05));border:1px solid rgba(45,212,218,.22);position:relative;margin-bottom:16px;"><span style="position:absolute;width:14px;height:14px;border-radius:50%;border:2.5px solid #22D3EE;left:8px;top:8px;"></span><span style="position:absolute;width:14px;height:7px;border-radius:0 0 8px 8px;background:#A855F7;left:22px;top:22px;"></span></div>
          <b style="display:block;font-size:16.5px;margin-bottom:7px;">Decide which deals to chase</b><span style="font-size:14px;color:#9aa6b8;line-height:1.55;">Score incoming opportunities against your criteria and return clear bid / no-bid calls on a dashboard.</span>
        </div>
        <div style="background:linear-gradient(165deg,#0c1422,#0a1018);border:1px solid #18223a;border-radius:18px;padding:24px;">
          <div style="width:44px;height:44px;border-radius:12px;background:linear-gradient(150deg,rgba(79,143,247,.24),rgba(110,115,242,.05));border:1px solid rgba(79,143,247,.26);position:relative;margin-bottom:16px;"><span style="position:absolute;width:16px;height:20px;border-radius:3px;border:2.5px solid #4F8FF7;left:9px;top:11px;"></span><span style="position:absolute;width:8px;height:3px;background:#A855F7;left:13px;top:18px;"></span><span style="position:absolute;width:8px;height:3px;background:#A855F7;left:13px;top:24px;"></span></div>
          <b style="display:block;font-size:16.5px;margin-bottom:7px;">Respond to proposals faster</b><span style="font-size:14px;color:#9aa6b8;line-height:1.55;">Draft answers from your library of past responses, so your team edits instead of starting from blank.</span>
        </div>
        <div style="background:linear-gradient(165deg,#0c1422,#0a1018);border:1px solid #18223a;border-radius:18px;padding:24px;">
          <div style="width:44px;height:44px;border-radius:12px;background:linear-gradient(150deg,rgba(168,85,247,.24),rgba(79,143,247,.05));border:1px solid rgba(168,85,247,.26);position:relative;margin-bottom:16px;"><span style="position:absolute;width:18px;height:18px;border-radius:50%;border:2.5px solid #A855F7;left:9px;top:9px;"></span><span style="position:absolute;width:2.5px;height:7px;background:#22D3EE;border-radius:2px;left:17px;top:13px;"></span><span style="position:absolute;width:6px;height:2.5px;background:#22D3EE;border-radius:2px;left:17px;top:18px;"></span></div>
          <b style="display:block;font-size:16.5px;margin-bottom:7px;">Remember why decisions were made</b><span style="font-size:14px;color:#9aa6b8;line-height:1.55;">Capture the reasoning behind decisions as searchable institutional memory, with a person in the loop throughout.</span>
        </div>
        <div style="background:linear-gradient(165deg,#0c1422,#0a1018);border:1px solid #18223a;border-radius:18px;padding:24px;">
          <div style="width:44px;height:44px;border-radius:12px;background:linear-gradient(150deg,rgba(34,211,238,.24),rgba(79,143,247,.05));border:1px solid rgba(45,212,218,.22);position:relative;margin-bottom:16px;"><span style="position:absolute;width:16px;height:18px;border-radius:8px 8px 3px 3px;border:2.5px solid #22D3EE;left:9px;top:11px;"></span><span style="position:absolute;width:6px;height:6px;border-radius:50%;background:#A855F7;left:14px;top:17px;"></span></div>
          <b style="display:block;font-size:16.5px;margin-bottom:7px;">Run onboarding &amp; risk checks</b><span style="font-size:14px;color:#9aa6b8;line-height:1.55;">Apply your rules to onboarding and risk rating, and escalate only the cases that need a human.</span>
        </div>
        <div style="background:linear-gradient(165deg,#0c1422,#0a1018);border:1px solid #18223a;border-radius:18px;padding:24px;">
          <div style="width:44px;height:44px;border-radius:12px;background:linear-gradient(150deg,rgba(79,143,247,.24),rgba(110,115,242,.05));border:1px solid rgba(79,143,247,.26);position:relative;margin-bottom:16px;"><span style="position:absolute;width:13px;height:13px;border-radius:50%;border:2.5px solid #4F8FF7;left:8px;top:8px;"></span><span style="position:absolute;width:8px;height:2.5px;background:#A855F7;border-radius:2px;transform:rotate(45deg);left:20px;top:24px;"></span></div>
          <b style="display:block;font-size:16.5px;margin-bottom:7px;">Find your next customers</b><span style="font-size:14px;color:#9aa6b8;line-height:1.55;">Monitor public sources for prospects and displacement signals, and surface them to your sales team.</span>
        </div>
        <div style="background:linear-gradient(160deg,rgba(13,20,34,.5),rgba(10,16,24,.5));border:1px dashed #29344c;border-radius:18px;padding:24px;">
          <div style="width:44px;height:44px;border-radius:12px;background:rgba(120,140,170,.08);position:relative;margin-bottom:16px;"><span style="position:absolute;width:3px;height:16px;background:#5a6679;border-radius:2px;left:20px;top:14px;"></span><span style="position:absolute;width:16px;height:3px;background:#5a6679;border-radius:2px;left:14px;top:20px;"></span></div>
          <b style="display:block;font-size:16.5px;margin-bottom:7px;color:#9aa6b8;">Or something only you need</b><span style="font-size:14px;color:#6B7689;line-height:1.55;">If the work has inputs, rules, and an outcome, we can build a worker for it.</span>
        </div>
      </div>
    </section>

    
    <section id="lb-how" style="position:relative;padding:54px 24px;overflow:hidden;scroll-margin-top:96px;">
      <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:900px;height:400px;background:radial-gradient(ellipse,rgba(168,85,247,.1),transparent 70%);pointer-events:none;"></div>
      <div style="position:relative;max-width:1200px;margin:0 auto;">
        <div style="font-size:12.5px;font-weight:600;letter-spacing:.18em;text-transform:uppercase;color:#c79bff;margin-bottom:14px;text-align:center;">How a build works</div>
        <h2 style="font-size:clamp(30px,4vw,44px);font-weight:700;letter-spacing:-.025em;line-height:1.08;margin:0 0 16px;text-align:center;">Three layers. One outcome you control.</h2>
        <p style="font-size:17px;line-height:1.65;color:#AEB9C9;max-width:62ch;margin:0 auto 48px;text-align:center;">Every Labs build comes in three parts, so you get a working tool and the controls to keep it yours.</p>
        <div class="q-3col" style="display:grid;grid-template-columns:repeat(3,1fr);gap:18px;">
          <div style="background:linear-gradient(165deg,#0c1422,#0a1018);border:1px solid #18223a;border-radius:18px;padding:28px;">
            <div style="font-family:'Geist Mono',monospace;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:#c79bff;margin-bottom:14px;">Layer 1</div>
            <div style="width:56px;height:56px;border-radius:15px;background:linear-gradient(150deg,#241a3d,#130f24);border:1px solid #3a2a5c;display:grid;place-items:center;margin-bottom:18px;"><span style="width:0;height:0;border-left:11px solid transparent;border-right:11px solid transparent;border-bottom:18px solid #A855F7;"></span></div>
            <b style="display:block;font-size:18px;margin-bottom:8px;">The worker</b><span style="font-size:14.5px;color:#9aa6b8;line-height:1.55;">The agentic intelligence. It reads your inputs, applies your logic, and produces the output.</span>
          </div>
          <div style="background:linear-gradient(165deg,#0c1422,#0a1018);border:1px solid #18223a;border-radius:18px;padding:28px;">
            <div style="font-family:'Geist Mono',monospace;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:#7fb3ff;margin-bottom:14px;">Layer 2</div>
            <div style="width:56px;height:56px;border-radius:15px;background:linear-gradient(150deg,#16243f,#0c1626);border:1px solid #25345a;display:grid;place-items:center;margin-bottom:18px;"><span style="width:24px;height:18px;border-radius:4px;border:2.5px solid #4F8FF7;position:relative;"><span style="position:absolute;top:-1px;left:-1px;right:-1px;height:5px;background:#4F8FF7;border-radius:3px 3px 0 0;"></span></span></div>
            <b style="display:block;font-size:18px;margin-bottom:8px;">Your dashboard</b><span style="font-size:14.5px;color:#9aa6b8;line-height:1.55;">The interface your team actually uses. Built for the task, not a generic chat box.</span>
          </div>
          <div style="background:linear-gradient(165deg,#0c1422,#0a1018);border:1px solid #18223a;border-radius:18px;padding:28px;">
            <div style="font-family:'Geist Mono',monospace;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:#7fdce6;margin-bottom:14px;">Layer 3</div>
            <div style="width:56px;height:56px;border-radius:15px;background:linear-gradient(150deg,#0d2a38,#0c1a2c);border:1px solid #1c4254;display:grid;place-items:center;margin-bottom:18px;"><span style="width:22px;height:22px;border-radius:50%;border:3px solid #22D3EE;position:relative;"><span style="position:absolute;width:7px;height:7px;border-radius:50%;background:#22D3EE;left:4px;top:4px;"></span></span></div>
            <b style="display:block;font-size:18px;margin-bottom:8px;">Your controls</b><span style="font-size:14.5px;color:#9aa6b8;line-height:1.55;">Set the prompts, guardrails, rules, and knowledge yourself. Change how it behaves without coming back to us.</span>
          </div>
        </div>
        <p style="font-size:16px;font-weight:600;color:#E8EEF6;margin:30px auto 0;text-align:center;max-width:60ch;">Your logic lives in settings, not code &mdash; so it adapts as you do.</p>
      </div>
    </section>

    
    <section id="lb-why" style="max-width:1200px;margin:0 auto;padding:54px 24px;scroll-margin-top:96px;">
      <div style="font-size:12.5px;font-weight:600;letter-spacing:.18em;text-transform:uppercase;color:#c79bff;margin-bottom:14px;text-align:center;">Why Qiko Labs</div>
      <h2 style="font-size:clamp(30px,4vw,44px);font-weight:700;letter-spacing:-.025em;line-height:1.08;margin:0 0 18px;max-width:22ch;margin-left:auto;margin-right:auto;text-align:center;">A specialist built on your data, not a model rented from someone else.</h2>
      <p style="font-size:17px;line-height:1.65;color:#AEB9C9;max-width:64ch;margin:0 auto 40px;text-align:center;">The advantage was never the model. It is your data, your judgment, and a specialist built to do exactly your work.</p>
      <div class="q-3col" style="display:grid;grid-template-columns:repeat(3,1fr);gap:18px;">
        <div style="background:linear-gradient(165deg,#0c1422,#0a1018);border:1px solid #18223a;border-radius:18px;padding:26px;">
          <div style="width:44px;height:44px;border-radius:12px;background:linear-gradient(150deg,rgba(34,211,238,.24),rgba(79,143,247,.05));border:1px solid rgba(45,212,218,.22);position:relative;margin-bottom:16px;"><span style="position:absolute;width:11px;height:11px;border-radius:50%;background:#22D3EE;left:7px;top:17px;"></span><span style="position:absolute;width:11px;height:11px;border-radius:50%;border:2px solid #A855F7;left:17px;top:11px;"></span><span style="position:absolute;width:11px;height:11px;border-radius:50%;border:2px solid #4F8FF7;left:22px;top:21px;"></span></div>
          <b style="display:block;font-size:16.5px;margin-bottom:7px;">No stack to run</b><span style="font-size:14px;color:#9aa6b8;line-height:1.55;">Multiple frontier models, isolated and encrypted, hosted in your region. No GPUs to manage.</span>
        </div>
        <div style="background:linear-gradient(165deg,#0c1422,#0a1018);border:1px solid #18223a;border-radius:18px;padding:26px;">
          <div style="width:44px;height:44px;border-radius:12px;background:linear-gradient(150deg,rgba(79,143,247,.24),rgba(110,115,242,.05));border:1px solid rgba(79,143,247,.26);position:relative;margin-bottom:16px;"><span style="position:absolute;width:14px;height:14px;border-radius:50%;border:2.5px solid #4F8FF7;left:8px;top:15px;"></span><span style="position:absolute;width:6px;height:10px;border-radius:3px;background:#A855F7;left:25px;top:12px;"></span><span style="position:absolute;width:6px;height:6px;border-radius:50%;background:#22D3EE;left:25px;top:24px;"></span></div>
          <b style="display:block;font-size:16.5px;margin-bottom:7px;">Yours to control</b><span style="font-size:14px;color:#9aa6b8;line-height:1.55;">Config, not code. Your team tunes behaviour through settings, with no redevelopment cycle.</span>
        </div>
        <div style="background:linear-gradient(165deg,#0c1422,#0a1018);border:1px solid #18223a;border-radius:18px;padding:26px;">
          <div style="width:44px;height:44px;border-radius:12px;background:linear-gradient(150deg,rgba(168,85,247,.24),rgba(79,143,247,.05));border:1px solid rgba(168,85,247,.26);position:relative;margin-bottom:16px;"><span style="position:absolute;width:11px;height:11px;border-radius:50%;border:2.5px solid #A855F7;left:8px;top:11px;"></span><span style="position:absolute;width:18px;height:9px;border-radius:0 0 9px 9px;border:2.5px solid #A855F7;border-top:none;left:13px;top:24px;"></span><span style="position:absolute;width:5px;height:5px;border-radius:50%;background:#22D3EE;left:30px;top:11px;"></span></div>
          <b style="display:block;font-size:16.5px;margin-bottom:7px;">Human in the loop</b><span style="font-size:14px;color:#9aa6b8;line-height:1.55;">You decide where the worker acts on its own and where a person signs off.</span>
        </div>
        <div style="background:linear-gradient(165deg,#0c1422,#0a1018);border:1px solid #18223a;border-radius:18px;padding:26px;">
          <div style="width:44px;height:44px;border-radius:12px;background:linear-gradient(150deg,rgba(34,211,238,.24),rgba(79,143,247,.05));border:1px solid rgba(45,212,218,.22);position:relative;margin-bottom:16px;"><span style="position:absolute;width:7px;height:18px;border-radius:3px;background:#22D3EE;left:9px;top:13px;"></span><span style="position:absolute;width:7px;height:13px;border-radius:3px;background:#4F8FF7;left:18px;top:18px;"></span><span style="position:absolute;width:7px;height:9px;border-radius:3px;background:#A855F7;left:27px;top:22px;"></span></div>
          <b style="display:block;font-size:16.5px;margin-bottom:7px;">Delivered by a studio</b><span style="font-size:14px;color:#9aa6b8;line-height:1.55;">A dedicated build team that ships. A typical first build lands in weeks, not quarters.</span>
        </div>
        <div style="background:linear-gradient(165deg,#0c1422,#0a1018);border:1px solid #18223a;border-radius:18px;padding:26px;">
          <div style="width:44px;height:44px;border-radius:12px;background:linear-gradient(150deg,rgba(79,143,247,.24),rgba(110,115,242,.05));border:1px solid rgba(79,143,247,.26);position:relative;margin-bottom:16px;"><span style="position:absolute;width:0;height:0;border-top:7px solid transparent;border-bottom:7px solid transparent;border-left:11px solid #4F8FF7;left:10px;top:15px;"></span><span style="position:absolute;width:8px;height:8px;border-radius:50%;border:2px solid #A855F7;left:24px;top:18px;"></span></div>
          <b style="display:block;font-size:16.5px;margin-bottom:7px;">Primed for what's next</b><span style="font-size:14px;color:#9aa6b8;line-height:1.55;">Everything we build is structured for the agent-to-agent world, so you are ready as agents start to transact.</span>
        </div>
        <div style="background:linear-gradient(165deg,#0c1422,#0a1018);border:1px solid #18223a;border-radius:18px;padding:26px;">
          <div style="width:44px;height:44px;border-radius:12px;background:linear-gradient(150deg,rgba(168,85,247,.24),rgba(79,143,247,.05));border:1px solid rgba(168,85,247,.26);position:relative;margin-bottom:16px;"><svg width="20" height="20" viewBox="0 0 32 32" fill="none" style="position:absolute;left:12px;top:12px;"><circle cx="16" cy="16" r="11" stroke="#A855F7" stroke-width="3.2"></circle><line x1="13.5" y1="18.5" x2="20" y2="12" stroke="#22D3EE" stroke-width="3.2" stroke-linecap="round"></line></svg></div>
          <b style="display:block;font-size:16.5px;margin-bottom:7px;">Built on Qiko</b><span style="font-size:14px;color:#9aa6b8;line-height:1.55;">The same platform behind Signal, so visibility, presence, and custom workers all sit in one place.</span>
        </div>
      </div>
    </section>
</main>`;

export default function LabsPage() {
  const router = useRouter();

  const openExternal = (path: string) => window.open(`https://qiko.ai${path}`, "_blank", "noopener");

  const goHome = () => router.push("/");
  const goSignal = () => openExternal("/signal");
  const sigHow = () => openExternal("/signal#sg-report");
  const sigCheck = () => openExternal("/signal#sg-check");
  const sigPricing = () => openExternal("/signal#sg-pricing");

  const scrollTo = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
  const goLabs = () => window.scrollTo({ top: 0, behavior: "smooth" });
  const labBuild = () => scrollTo("lb-build");
  const labHow = () => scrollTo("lb-how");
  const labWhy = () => scrollTo("lb-why");
  const goAbout = () => router.push("/#under-the-hood");
  const goSignIn = () => router.push("/login");
  const goGetStarted = () => router.push("/onboarding");

  return (
    <div
      className="qiko-landing-1to1"
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
      <QikoNav onHome={goHome} onSignal={goSignal} onLabs={goLabs} onAbout={goAbout} onSignIn={goSignIn} onGetStarted={goGetStarted}
           sigHow={sigHow} sigCheck={sigCheck} sigPricing={sigPricing} labBuild={labBuild} labHow={labHow} labWhy={labWhy} />
      <div suppressHydrationWarning dangerouslySetInnerHTML={{ __html: LABS_HTML }} />
      {/* Rendered as real JSX (not dangerouslySetInnerHTML + a portal into it) so the
          interactive form is part of React's own tree from the start -- no
          hydration-timing race to find and mount into a raw-HTML placeholder node. */}
      <section id="lb-contact" style={{ position: "relative", maxWidth: 1200, margin: "0 auto", padding: "54px 24px 90px", scrollMarginTop: 96 }}>
        <div style={{ position: "absolute", top: 40, right: -60, width: 420, height: 420, borderRadius: "50%", background: "radial-gradient(circle,rgba(168,85,247,.14),transparent 65%)", pointerEvents: "none" }} />
        <div className="grid grid-cols-1 md:grid-cols-[.9fr_1.1fr]" style={{ position: "relative", gap: 48, alignItems: "start" }}>
          <div>
            <div style={{ fontSize: 12.5, fontWeight: 600, letterSpacing: ".18em", textTransform: "uppercase", color: "#c79bff", marginBottom: 14 }}>Get in touch</div>
            <h2 style={{ fontSize: "clamp(30px,4vw,44px)", fontWeight: 700, letterSpacing: "-.025em", lineHeight: 1.08, margin: "0 0 18px" }}>Tell us what you want to build.</h2>
            <p style={{ fontSize: 17, lineHeight: 1.65, color: "#AEB9C9", maxWidth: "44ch", margin: "0 0 26px" }}>Send us the shape of the problem and we will come back with how Qiko Labs would approach it.</p>
            <p style={{ fontSize: 15, fontWeight: 600, color: "#E8EEF6", maxWidth: "42ch" }}>Built on Qiko, so what you build today is ready for what comes next.</p>
          </div>
          <div style={{ background: "linear-gradient(165deg,#0d1526,#0a1120)", border: "1px solid #1d2942", borderRadius: 20, padding: 30 }}>
            <LabsContactForm />
          </div>
        </div>
      </section>
      <QikoFooter onSignal={goSignal} onLabs={goLabs} onAbout={goAbout} onSignIn={goSignIn} onGetStarted={goGetStarted} />
    </div>
  );
}
