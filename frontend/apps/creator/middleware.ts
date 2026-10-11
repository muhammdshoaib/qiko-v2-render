import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Route guard: httpOnly auth cookies are readable server-side here (never in client JS).
// Let refresh-only visitors reach protected pages so the client can renew an expired 15-minute
// access token. Cookie presence does not prove validity, so only a real access cookie redirects the
// login page; a failed client refresh returns the visitor to login without a redirect loop.
export function middleware(req: NextRequest) {
  const hasAccess = req.cookies.has("qiko_access");
  const hasSession = hasAccess || req.cookies.has("qiko_refresh");
  const { pathname } = req.nextUrl;
  // Creator has no marketing homepage; / would 404. Send testers to login or the app.
  if (pathname === "/") {
    return NextResponse.redirect(new URL(hasSession ? "/studio" : "/login", req.url));
  }
  const isPublic = pathname === "/.well-known/security.txt" || pathname.startsWith("/labs") || pathname.startsWith("/login") || pathname.startsWith("/signup") || pathname.startsWith("/onboarding") || pathname.startsWith("/forgot-password") || pathname.startsWith("/reset-password") || pathname.startsWith("/verify-email") || pathname.startsWith("/terms") || pathname.startsWith("/privacy") || pathname.startsWith("/cookies") || pathname.startsWith("/chat/");
  if (!hasSession && !isPublic) return NextResponse.redirect(new URL("/login", req.url));
  // Always allow the login page. Cookie presence does not prove validity, and redirecting based on
  // a stale cookie can trap the browser in a login/dashboard loop when refresh is revoked.
  return NextResponse.next();
}

// Landing (/), /login, /signup, /embed/*, /widget.js and /fonts/* are public.
export const config = { matcher: ["/((?!_next|api|health|favicon.ico|qiko-logo|qiko-icon|embed|widget.js|fonts/).*)"] };
