import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Route guard: the httpOnly access cookie is readable server-side here (never in client JS).
export function middleware(req: NextRequest) {
  const authed = req.cookies.has("qiko_access");
  const { pathname } = req.nextUrl;
  const isPublic = pathname === "/" || pathname.startsWith("/labs") || pathname.startsWith("/login") || pathname.startsWith("/signup") || pathname.startsWith("/onboarding") || pathname.startsWith("/forgot-password") || pathname.startsWith("/reset-password");
  const isLogin = pathname.startsWith("/login");
  if (!authed && !isPublic) return NextResponse.redirect(new URL("/login", req.url));
  if (authed && isLogin) return NextResponse.redirect(new URL("/dashboard", req.url));
  return NextResponse.next();
}

// Landing (/), /login, /signup, /embed/*, /widget.js and /fonts/* are public.
export const config = { matcher: ["/((?!_next|favicon.ico|qiko-logo|qiko-icon|embed|widget.js|fonts/).*)"] };
