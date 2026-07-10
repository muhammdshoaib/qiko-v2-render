"use client";

import { useState } from "react";

const dropdownItem: React.CSSProperties = {
  display: "block", padding: "9px 12px", borderRadius: 9, fontSize: 14, color: "#cdd7e3",
  textDecoration: "none", cursor: "pointer",
};

export type SiteChromeActions = {
  onHome: () => void; onSignal: () => void; onLabs: () => void; onAbout: () => void;
  onSignIn: () => void; onGetStarted: () => void;
  sigHow: () => void; sigCheck: () => void; sigPricing: () => void;
  labBuild: () => void; labHow: () => void; labWhy: () => void;
};

/** Nav -- ported 1:1 from the live site's client/src/new-site/components/Nav.tsx, shared
 * between the landing page and /labs (real site: Nav/Footer are shared across every page
 * via NewSiteLayout/SiteShell). Signal/Labs/Sign in/Get started targets are adapted to this
 * app's actual routes (the real site links to separate /signal, /labs marketing pages;
 * Signal is a different product this app doesn't own -- see page.tsx for how each action
 * is wired). */
export function QikoNav({
  onHome, onSignal, onLabs, onAbout, onSignIn, onGetStarted,
  sigHow, sigCheck, sigPricing, labBuild, labHow, labWhy,
}: SiteChromeActions) {
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
        <a onClick={onHome} style={{ display: "flex", alignItems: "center", textDecoration: "none", cursor: "pointer", flex: "0 0 auto" }}>
          <img src="/qiko-logo.webp" alt="Qiko" style={{ height: 30, width: "auto", display: "block" }} />
        </a>

        <div style={{ alignItems: "center", gap: 6, margin: "0 auto" }} className="hidden md:flex">
          <a onClick={onHome} style={{ fontSize: 14.5, fontWeight: 500, color: "#E6ECF5", textDecoration: "none", padding: "8px 14px", borderRadius: 999, cursor: "pointer" }}>Home</a>

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
          <a onClick={closeMobileAnd(onHome)} style={{ display: "block", padding: "12px 14px", borderRadius: 10, fontSize: 15, fontWeight: 500, color: "#E6ECF5", textDecoration: "none", cursor: "pointer" }}>Home</a>
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
export function QikoFooter({ onSignal, onLabs, onAbout, onSignIn, onGetStarted }: {
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
