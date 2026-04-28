"use client";

import { useState } from "react";

interface IngestStats {
  files?: number;
  chunks?: number;
  upserted?: number;
  collection?: string;
}

export function AdminPanel({
  user,
  signOutAction,
}: {
  user: { name?: string | null; login?: string; image?: string | null };
  signOutAction: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string; stats?: IngestStats } | null>(
    null
  );

  async function reingest() {
    if (busy) return;
    setBusy(true);
    setResult(null);
    try {
      const res = await fetch("/api/admin/ingest", { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        setResult({
          ok: true,
          text: "Ingest complete.",
          stats: data.stats,
        });
      } else {
        setResult({
          ok: false,
          text: data.error || `HTTP ${res.status}`,
        });
      }
    } catch (e) {
      setResult({
        ok: false,
        text: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-bg text-textmain">
      <header className="bg-surface border-b border-border1 flex items-center px-6 h-12 gap-4">
        <div className="font-mono text-[13px] tracking-wider">
          uxr<span className="text-accent-bright">agent</span>
          <span className="text-textdim ml-2">/ admin</span>
        </div>
        <div className="ml-auto flex items-center gap-3">
          <span className="text-[11px] font-mono text-textmuted">
            {user.login ? `@${user.login}` : user.name || "signed in"}
          </span>
          <form action={signOutAction}>
            <button
              type="submit"
              className="px-3 py-1 bg-transparent border border-border2 rounded text-textmuted font-mono text-[11px] cursor-pointer hover:bg-surface2 hover:text-textmain hover:border-accent transition"
            >
              Sign out
            </button>
          </form>
        </div>
      </header>

      <main className="max-w-3xl mx-auto p-8 flex flex-col gap-8">
        <Section
          title="Corpus"
          subtitle="Re-ingest the corpus baked into your Modal image. Runs the chunk → embed → Qdrant pipeline."
        >
          <div className="flex flex-col gap-3">
            <button
              type="button"
              disabled={busy}
              onClick={reingest}
              className="self-start px-4 py-2 bg-accent border border-accent-bright rounded-md text-textmain font-mono text-[12px] cursor-pointer hover:bg-accent-bright transition disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {busy ? "Re-ingesting…" : "Re-ingest corpus"}
            </button>
            {busy && (
              <div className="text-[11px] font-mono text-warn-text flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-warn-text animate-pulse-dot" />
                Modal: chunk → Voyage embed → Qdrant upsert · ~30-90s
              </div>
            )}
            {result && (
              <div
                className={[
                  "p-3 rounded text-[12px] font-mono leading-relaxed",
                  result.ok
                    ? "bg-ok border border-ok-text text-ok-text"
                    : "bg-err border border-err-text text-err-text",
                ].join(" ")}
              >
                <div>{result.text}</div>
                {result.stats && (
                  <div className="text-[11px] mt-1 opacity-90">
                    files: {result.stats.files ?? "—"} · chunks:{" "}
                    {result.stats.chunks ?? "—"} · upserted:{" "}
                    {result.stats.upserted ?? "—"} · collection:{" "}
                    {result.stats.collection ?? "—"}
                  </div>
                )}
              </div>
            )}
          </div>
        </Section>

        <Section
          title="Pipeline"
          subtitle="Backend health check and quick links."
        >
          <div className="flex flex-col gap-2 text-[12px] font-mono text-textmuted">
            <a
              href="/api/cluster"
              target="_blank"
              rel="noreferrer"
              className="hover:text-textmain underline-offset-2 hover:underline"
            >
              /api/cluster — Modal reachability check
            </a>
            <a
              href="/"
              className="hover:text-textmain underline-offset-2 hover:underline"
            >
              / — Public widget (Fast / Deep / Wizard)
            </a>
          </div>
        </Section>

        <Section
          title="Token rotation"
          subtitle="If the X-Admin-Token gets compromised, rotate it — instructions live in DEPLOY.md."
        >
          <div className="text-[12px] font-mono text-textmuted leading-relaxed">
            The browser side of admin uses GitHub OAuth (this page). The
            server-side <code className="text-accent-bright">/api/admin/ingest</code> attaches{" "}
            <code className="text-accent-bright">X-Admin-Token</code> from the Vercel env var when
            calling Modal — the token never leaves the server. Rotate by:
            <ol className="list-decimal ml-5 mt-1.5 space-y-0.5">
              <li>Generate a new token locally</li>
              <li>
                Run{" "}
                <code className="text-accent-bright">
                  modal secret create admin-token --force
                </code>
              </li>
              <li>
                Update <code className="text-accent-bright">ADMIN_TOKEN</code> in Vercel project
                env vars
              </li>
              <li>Redeploy backend + frontend</li>
            </ol>
          </div>
        </Section>
      </main>
    </div>
  );
}

function Section({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="bg-surface border border-border1 rounded-lg p-6">
      <h2 className="text-textmain text-base font-medium mb-1">{title}</h2>
      {subtitle && (
        <p className="text-textmuted text-[12px] mb-4 leading-relaxed">{subtitle}</p>
      )}
      {children}
    </section>
  );
}
