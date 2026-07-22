import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(req: NextRequest) {
  const hasAccess = req.cookies.has("qiko_access");
  const hasSession = hasAccess || req.cookies.has("qiko_refresh");
  const isLogin = req.nextUrl.pathname.startsWith("/login");
  const isPublic = isLogin || req.nextUrl.pathname.startsWith("/forgot-password");
  if (!hasSession && !isPublic) return NextResponse.redirect(new URL("/login", req.url));
  // Always allow login. A present but expired cookie must not create a redirect loop.
  return NextResponse.next();
}

export const config = { matcher: ["/((?!_next|favicon.ico).*)"] };
