import { NextRequest } from "next/server";
import { proxyToModal } from "@/lib/proxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
// Deep mode runs 3 personas + aggregator + SME = ~25-35s; allow 90s headroom.
export const maxDuration = 90;

export async function POST(req: NextRequest) {
  let body: { question?: string } = {};
  try {
    body = await req.json();
  } catch {
    return new Response(
      JSON.stringify({ error: "Request body must be JSON." }),
      { status: 400, headers: { "Content-Type": "application/json" } }
    );
  }
  const question = (body.question || "").trim();
  if (!question) {
    return new Response(
      JSON.stringify({ error: "Missing 'question' field." }),
      { status: 400, headers: { "Content-Type": "application/json" } }
    );
  }
  return proxyToModal("/ensemble", { question }, { timeoutMs: 90_000 });
}
