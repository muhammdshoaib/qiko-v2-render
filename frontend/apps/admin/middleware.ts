import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(req: NextRequest) {
  const authed = req.cookies.has("qiko_access");
  const isLogin = req.nextUrl.pathname.startsWith("/login");
  if (!authed && !isLogin) return NextResponse.redirect(new URL("/login", req.url));
  if (authed && isLogin) return NextResponse.redirect(new URL("/overview", req.url));
  return NextResponse.next();
}

export const config = { matcher: ["/((?!_next|favicon.ico).*)"] };
