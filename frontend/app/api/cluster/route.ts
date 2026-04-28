import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
  const endpoint = process.env.MODAL_ENDPOINT;
  if (!endpoint) {
    return NextResponse.json({
      modal_endpoint: null,
      modal_reachable: false,
      reason: "MODAL_ENDPOINT not set in env",
    });
  }
  try {
    const res = await fetch(endpoint.replace(/\/$/, "") + "/", {
      method: "GET",
      signal: AbortSignal.timeout(5000),
    });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json({
      modal_endpoint: endpoint,
      modal_reachable: res.ok,
      backend: data,
    });
  } catch (e) {
    return NextResponse.json({
      modal_endpoint: endpoint,
      modal_reachable: false,
      reason: e instanceof Error ? e.message : String(e),
    });
  }
}
