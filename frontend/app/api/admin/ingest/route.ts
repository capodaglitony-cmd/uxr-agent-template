/**
 * /api/admin/ingest — server-side relay to Modal /admin/ingest.
 *
 * Two-layer auth:
 *   1. GitHub OAuth via auth() — confirms the caller is a signed-in
 *      user matching OWNER_GITHUB_USER (signIn callback already
 *      enforced this; we re-check belt-and-suspenders).
 *   2. X-Admin-Token added server-side from env var. The token never
 *      reaches the browser; the only way to call Modal is via this
 *      Vercel route, and the only way to reach this route is via a
 *      valid OAuth session.
 */

import { NextResponse } from "next/server";
import { auth } from "@/auth";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 90;

export async function POST() {
  const session = await auth();
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const allowed = process.env.OWNER_GITHUB_USER;
  const userLogin = (session.user as { login?: string }).login || "";
  if (!allowed || userLogin.toLowerCase() !== allowed.toLowerCase()) {
    return NextResponse.json(
      {
        error:
          "Forbidden. Signed-in account does not match OWNER_GITHUB_USER.",
      },
      { status: 403 }
    );
  }

  const modalEndpoint = process.env.MODAL_ENDPOINT;
  const adminToken = process.env.ADMIN_TOKEN;
  if (!modalEndpoint) {
    return NextResponse.json(
      { error: "MODAL_ENDPOINT not configured on Vercel." },
      { status: 503 }
    );
  }
  if (!adminToken) {
    return NextResponse.json(
      {
        error:
          "ADMIN_TOKEN not configured on Vercel. Set it to the same value used in the admin-token Modal secret so this route can authenticate to Modal /admin/ingest.",
      },
      { status: 503 }
    );
  }

  const target = `${modalEndpoint.replace(/\/$/, "")}/admin/ingest`;
  let res: Response;
  try {
    res = await fetch(target, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Admin-Token": adminToken,
      },
      body: JSON.stringify({ confirm: true }),
      signal: AbortSignal.timeout(85_000),
    });
  } catch (e) {
    return NextResponse.json(
      {
        error: `Network error reaching Modal: ${
          e instanceof Error ? e.message : String(e)
        }`,
        target,
      },
      { status: 502 }
    );
  }

  const data = await res.json().catch(() => ({}));
  return NextResponse.json(data, { status: res.status });
}
