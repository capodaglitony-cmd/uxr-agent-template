/**
 * lib/proxy.ts
 *
 * Server-side helper for thin-proxying /api/* routes to the Modal
 * backend. Reads MODAL_ENDPOINT from env (set in Vercel project
 * settings or .env.local for dev). Never imported from client code.
 */

import { NextResponse } from "next/server";

export function modalEndpoint(): string {
  const url = process.env.MODAL_ENDPOINT;
  if (!url) {
    throw new Error(
      "MODAL_ENDPOINT environment variable is not set. " +
        "Deploy the Python backend with `modal deploy backend/modal_app.py` " +
        "and set MODAL_ENDPOINT in your Vercel project (or .env.local for dev) " +
        "to the URL Modal printed."
    );
  }
  return url.replace(/\/$/, ""); // strip trailing slash
}

export async function proxyToModal(
  path: string,
  body: unknown,
  options: { timeoutMs?: number } = {}
): Promise<NextResponse> {
  let endpoint: string;
  try {
    endpoint = modalEndpoint();
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : String(e) },
      { status: 503 }
    );
  }

  const url = `${endpoint}${path}`;
  const controller = new AbortController();
  const timeoutMs = options.timeoutMs ?? 60_000;
  const t = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body ?? {}),
      signal: controller.signal,
    });
    clearTimeout(t);
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (e) {
    clearTimeout(t);
    const msg = e instanceof Error ? e.message : String(e);
    return NextResponse.json(
      { error: `Proxy to Modal failed: ${msg}`, target: url },
      { status: 502 }
    );
  }
}
