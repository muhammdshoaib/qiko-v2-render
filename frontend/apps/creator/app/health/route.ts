import { NextResponse } from "next/server";

export async function GET() {
  const upstream = process.env.API_UPSTREAM?.replace(/\/$/, "");
  if (!upstream) {
    return NextResponse.json({ status: "ok", service: "creator" });
  }
  try {
    const res = await fetch(`${upstream}/health`, { cache: "no-store" });
    const body = await res.json().catch(() => ({ status: "unknown" }));
    return NextResponse.json(body, { status: res.status });
  } catch {
    return NextResponse.json({ status: "degraded", service: "creator" }, { status: 503 });
  }
}
