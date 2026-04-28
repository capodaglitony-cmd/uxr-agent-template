import { NextRequest } from "next/server";
import { proxyToModal } from "@/lib/proxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
// Final cascade step triggers the ensemble call (~25-30s); allow up to 90s.
export const maxDuration = 90;

export async function POST(req: NextRequest) {
  let body: unknown = {};
  try {
    body = await req.json();
  } catch {
    return new Response(
      JSON.stringify({ error: "Request body must be JSON." }),
      { status: 400, headers: { "Content-Type": "application/json" } }
    );
  }
  return proxyToModal("/wizard/answer", body, { timeoutMs: 90_000 });
}
