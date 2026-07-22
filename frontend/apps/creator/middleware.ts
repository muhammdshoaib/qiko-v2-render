import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Route guard: the httpOnly access cookie is readable server-side here (never in client JS).
// Treat a valid refresh cookie as authed too: the access token is short-lived (15 min), so a user
// who has been idle drops qiko_access but still holds the 14-day qiko_refresh. Redirecting them to
// login on the next navigation is the kick-out we must avoid; the client silently refreshes the
// access token on its first API call, so let the navigation through when a refresh cookie exists.
export function middleware(req: NextRequest) {
  const authed = req.cookies.has("qiko_access") || req.cookies.has("qiko_refresh");
  const { pathname } = req.nextUrl;
  const isPublic = pathname === "/" || pathname.startsWith("/labs") || pathname.startsWith("/login") || pathname.startsWith("/signup") || pathname.startsWith("/onboarding") || pathname.startsWith("/forgot-password") || pathname.startsWith("/reset-password") || pathname.startsWith("/terms") || pathname.startsWith("/privacy") || pathname.startsWith("/cookies");
  const isLogin = pathname.startsWith("/login");
  if (!authed && !isPublic) return NextResponse.redirect(new URL("/login", req.url));
  if (authed && isLogin) return NextResponse.redirect(new URL("/dashboard", req.url));
  return NextResponse.next();
}

// Landing (/), /login, /signup, /embed/*, /widget.js and /fonts/* are public.
export const config = { matcher: ["/((?!_next|favicon.ico|qiko-logo|qiko-icon|embed|widget.js|fonts/).*)"] };
