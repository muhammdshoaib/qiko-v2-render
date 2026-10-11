import { NextRequest, NextResponse } from "next/server";

const HOP = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailers",
  "transfer-encoding",
  "upgrade",
  "host",
  "content-length",
]);

const RETRIES = 2;
const RETRY_STATUSES = new Set([502, 503, 504]);

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function forward(res: Response) {
  const outHeaders = new Headers();
  res.headers.forEach((value, key) => {
    if (key.toLowerCase() === "set-cookie") return;
    if (!HOP.has(key.toLowerCase())) outHeaders.set(key, value);
  });

  const out = new NextResponse(res.body, { status: res.status, headers: outHeaders });
  const cookies = typeof res.headers.getSetCookie === "function" ? res.headers.getSetCookie() : [];
  for (const cookie of cookies) {
    out.headers.append("set-cookie", cookie.replace(/;\s*domain=[^;]*/i, ""));
  }
  return out;
}

async function proxy(req: NextRequest, path: string[]) {
  const upstream = process.env.API_UPSTREAM?.replace(/\/$/, "");
  if (!upstream) {
    return NextResponse.json({ detail: "API_UPSTREAM is not configured" }, { status: 502 });
  }

  const url = `${upstream}/api/${path.join("/")}${req.nextUrl.search}`;
  const headers = new Headers();
  req.headers.forEach((value, key) => {
    if (!HOP.has(key.toLowerCase())) headers.set(key, value);
  });

  const body = req.method === "GET" || req.method === "HEAD" ? undefined : await req.arrayBuffer();

  for (let attempt = 0; attempt < RETRIES; attempt++) {
    try {
      const res = await fetch(url, { method: req.method, headers, body, redirect: "manual" });
      if (RETRY_STATUSES.has(res.status) && attempt < RETRIES - 1) {
        await sleep(2000 * (attempt + 1));
        continue;
      }
      return forward(res);
    } catch {
      if (attempt === RETRIES - 1) {
        return NextResponse.json(
          { detail: "API is starting up after idle. Wait 20 seconds and sign in again." },
          { status: 503 },
        );
      }
      await sleep(2000 * (attempt + 1));
    }
  }

  return NextResponse.json(
    { detail: "API is starting up after idle. Wait 20 seconds and sign in again." },
    { status: 503 },
  );
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function POST(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function PUT(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function PATCH(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function DELETE(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function OPTIONS(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
