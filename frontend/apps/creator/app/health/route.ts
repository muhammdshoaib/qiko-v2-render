import { NextResponse } from "next/server";

export async function GET() {
  const upstream = process.env.API_UPSTREAM?.replace(/\/$/, "");
  if (!upstream) {
    return NextResponse.json({ status: "ok", service: "creator" });
  }
  try {
    const res = await fetch(`${upstream}/health`, {
      cache: "no-store",
      signal: AbortSignal.timeout(25_000),
    });
    const body = await res.json().catch(() => ({ status: "unknown" }));
    return NextResponse.json(body, { status: res.status });
  } catch {
    return NextResponse.json({ status: "starting", service: "creator" }, { status: 503 });
  }
}
