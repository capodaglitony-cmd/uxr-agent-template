import { NextRequest } from "next/server";
import { proxyToModal } from "@/lib/proxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(_req: NextRequest) {
  return proxyToModal("/wizard/start", {}, { timeoutMs: 10_000 });
}
