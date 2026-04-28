import { NextRequest } from "next/server";
import { proxyToModal } from "@/lib/proxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 60;

// Fast mode: thin proxy to Modal /generate. Single Anthropic call,
// no retrieval, no persona scaffolding. ~3-5s typical latency.
export async function POST(req: NextRequest) {
  let body: { prompt?: string } = {};
  try {
    body = await req.json();
  } catch {
    return new Response(
      JSON.stringify({ error: "Request body must be JSON." }),
      { status: 400, headers: { "Content-Type": "application/json" } }
    );
  }
  const prompt = (body.prompt || "").trim();
  if (!prompt) {
    return new Response(
      JSON.stringify({ error: "Missing 'prompt' field." }),
      { status: 400, headers: { "Content-Type": "application/json" } }
    );
  }
  return proxyToModal("/generate", { prompt }, { timeoutMs: 60_000 });
}
