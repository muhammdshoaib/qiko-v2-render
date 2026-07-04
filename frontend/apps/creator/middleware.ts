import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Route guard: the httpOnly access cookie is readable server-side here (never in client JS).
export function middleware(req: NextRequest) {
  const authed = req.cookies.has("qiko_access");
  const isLogin = req.nextUrl.pathname.startsWith("/login");
  if (!authed && !isLogin) return NextResponse.redirect(new URL("/login", req.url));
  if (authed && isLogin) return NextResponse.redirect(new URL("/dashboard", req.url));
  return NextResponse.next();
}

// /embed/* and /widget.js are public (no auth) so the chat can be embedded anywhere.
export const config = { matcher: ["/((?!_next|favicon.ico|embed|widget.js).*)"] };
