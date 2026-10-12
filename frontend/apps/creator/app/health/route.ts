import { NextResponse } from "next/server";
import { resolveApiOrigin } from "@/lib/api-origin";

export async function GET() {
  try {
    const res = await fetch(`${resolveApiOrigin()}/health`, {
      cache: "no-store",
      signal: AbortSignal.timeout(25_000),
    });
    const body = await res.json().catch(() => ({ status: "unknown" }));
    return NextResponse.json(body, { status: res.status });
  } catch {
    return NextResponse.json({ status: "starting", service: "creator" }, { status: 503 });
  }
}
