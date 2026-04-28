"use client";

import { useEffect, useRef, useState } from "react";
import { deepQuery, type AggregatedOutput, type DeepClaim } from "@/lib/api-client";

interface Exchange {
  question: string;
  result?: AggregatedOutput;
  error?: string;
  elapsed?: number;
}

export function DeepView({ initialPrompt }: { initialPrompt?: string }) {
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [input, setInput] = useState(initialPrompt ?? "");
  const [busy, setBusy] = useState(false);
  const taRef = useRef<HTMLTextAreaElement | null>(null);
  const convRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!taRef.current) return;
    taRef.current.style.height = "auto";
    taRef.current.style.height = Math.min(taRef.current.scrollHeight, 160) + "px";
  }, [input]);

  useEffect(() => {
    convRef.current?.scrollTo({ top: convRef.current.scrollHeight });
  }, [exchanges]);

  useEffect(() => {
    if (initialPrompt) {
      setInput(initialPrompt);
      taRef.current?.focus();
    }
  }, [initialPrompt]);

  async function send() {
    const question = input.trim();
    if (!question || busy) return;
    setExchanges((x) => [...x, { question }]);
    setInput("");
    setBusy(true);
    const start = Date.now();
    try {
      const res = await deepQuery(question);
      const elapsed = (Date.now() - start) / 1000;
      setExchanges((x) =>
        x.map((ex, i) =>
          i === x.length - 1 ? { ...ex, result: res.aggregated, elapsed } : ex
        )
      );
    } catch (e) {
      setExchanges((x) =>
        x.map((ex, i) =>
          i === x.length - 1
            ? { ...ex, error: e instanceof Error ? e.message : String(e) }
            : ex
        )
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div ref={convRef} className="flex-1 overflow-y-auto px-6 sm:px-8 py-6 flex flex-col gap-7">
        {exchanges.length === 0 && (
          <div className="m-auto text-center text-textdim max-w-md">
            <h2 className="text-base font-normal text-textmuted mb-2">Deep mode</h2>
            <p className="text-[13px] leading-relaxed">
              Three-persona ensemble (PM / Designer / Engineer) plus aggregator and SME synthesis. ~25-35s per question. Divergence preserved.
            </p>
          </div>
        )}
        {exchanges.map((ex, i) => (
          <ExchangeCard key={i} exchange={ex} pending={i === exchanges.length - 1 && busy} />
        ))}
      </div>
      <div className="border-t border-border1 bg-surface px-6 py-4">
        <div className="flex gap-2.5 items-end">
          <textarea
            ref={taRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            placeholder="Ask a question. The three personas answer separately, then the SME synthesizes."
            rows={1}
            disabled={busy}
            className="flex-1 bg-bg border border-border2 rounded-md px-3.5 py-2.5 text-textmain font-sans text-[14px] leading-snug outline-none focus:border-accent transition resize-none min-h-[44px] max-h-40 placeholder:text-textdim disabled:opacity-50"
          />
          <button
            type="button"
            onClick={send}
            disabled={busy || !input.trim()}
            className="px-5 py-2.5 bg-accent border border-accent-bright rounded-md text-textmain font-mono text-[12px] cursor-pointer hover:bg-accent-bright transition h-[44px] disabled:opacity-40 disabled:cursor-not-allowed whitespace-nowrap"
          >
            send ↩
          </button>
        </div>
      </div>
    </div>
  );
}

function ExchangeCard({ exchange, pending }: { exchange: Exchange; pending: boolean }) {
  return (
    <div className="flex flex-col gap-3 max-w-4xl w-full">
      {/* User question */}
      <div className="self-end max-w-2xl flex flex-col gap-1.5 items-end">
        <div className="text-[10px] font-mono uppercase tracking-[1.5px] text-textdim">YOU</div>
        <div className="px-4 py-3 leading-relaxed text-[14px] rounded-md rounded-br-sm bg-accent-glow border border-accent">
          {exchange.question}
        </div>
      </div>

      {/* Result or pending or error */}
      {pending && !exchange.result && !exchange.error && (
        <div className="self-start text-[11px] font-mono text-warn-text flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-warn-text animate-pulse-dot" />
          Three personas working ⋅ aggregator ⋅ SME ⋅ ~25-35s
        </div>
      )}
      {exchange.error && (
        <div className="self-start max-w-2xl px-3 py-2 bg-err border border-err-text rounded text-err-text font-mono text-[12px]">
          {exchange.error}
        </div>
      )}
      {exchange.result && <ResultCard result={exchange.result} elapsed={exchange.elapsed} />}
    </div>
  );
}

function ResultCard({ result, elapsed }: { result: AggregatedOutput; elapsed?: number }) {
  const [showDetails, setShowDetails] = useState(false);
  const top = result.top_level_answer || result.deterministic_answer || "(no answer)";
  const band = result.divergence_band;
  const droppedCount = result.dropped_claims?.length || 0;
  const auditFlags = result.sme_audit_flags || [];
  const fallbackReason = result.sme_fallback_reason;

  return (
    <div className="self-start w-full flex flex-col gap-2.5">
      <div className="flex items-center gap-2.5 text-[10px] font-mono uppercase tracking-[1.5px] text-textdim">
        <span>CORPUS · ENSEMBLE</span>
        <BandPill band={band} />
        {fallbackReason && (
          <span className="text-warn-text">SME fallback: {fallbackReason}</span>
        )}
        {elapsed != null && <span className="ml-auto normal-case tracking-normal">{elapsed.toFixed(1)}s</span>}
      </div>

      <div className="px-4 py-3.5 bg-surface border border-border1 rounded-md text-[14px] leading-relaxed whitespace-pre-wrap">
        {top}
      </div>

      <button
        type="button"
        onClick={() => setShowDetails((v) => !v)}
        className="self-start text-[11px] font-mono text-textdim hover:text-textmuted cursor-pointer bg-transparent border-none px-0 text-left"
      >
        {showDetails ? "▾ hide" : "▸ show"} per-persona breakdown ({result.divergence_metrics?.jaccard_distance?.toFixed(2) || "—"} jaccard, {droppedCount} dropped, {auditFlags.length} audit flags)
      </button>

      {showDetails && <DetailsPanel result={result} />}
    </div>
  );
}

function BandPill({ band }: { band: string }) {
  const cls: Record<string, string> = {
    converged: "bg-ok text-ok-text border-ok",
    productive: "bg-accent-glow text-accent-bright border-accent",
    expected: "bg-surface2 text-textmuted border-border2",
    red_flag: "bg-warn text-warn-text border-warn",
    refusal: "bg-err text-err-text border-err",
  };
  return (
    <span
      className={[
        "inline-block px-2.5 py-0.5 rounded-xl text-[9px] font-mono uppercase tracking-wider border",
        cls[band] || "bg-surface2 text-textmuted border-border2",
      ].join(" ")}
    >
      {band}
    </span>
  );
}

function DetailsPanel({ result }: { result: AggregatedOutput }) {
  return (
    <div className="bg-surface2 border border-border1 rounded-md p-3.5 max-h-[460px] overflow-y-auto font-mono text-[11px] text-textmuted space-y-3.5">
      {result.synthesis_prose && (
        <div>
          <div className="text-textdim mb-1.5">synthesis prose</div>
          <pre className="whitespace-pre-wrap leading-relaxed font-sans text-textmain text-[12px]">
            {result.synthesis_prose}
          </pre>
        </div>
      )}

      {Object.entries(result.claims_by_persona || {}).map(([persona, claims]) => (
        <PersonaBlock key={persona} persona={persona} claims={claims} />
      ))}

      {result.dropped_claims && result.dropped_claims.length > 0 && (
        <div>
          <div className="text-textdim mb-1.5">dropped claims (anti-hallucination)</div>
          {result.dropped_claims.map((d, i) => (
            <div key={i} className="my-1.5 px-2 py-1.5 bg-err/30 border-l-2 border-err-text rounded-r text-err-text">
              <div>{d.claim_text}</div>
              <div className="text-[10px] text-warn-text mt-0.5">
                {d.persona} · {d.drop_reason}
                {d.fabrication_confidence != null
                  ? ` · ${d.fabrication_confidence.toFixed(2)} fab confidence`
                  : ""}
              </div>
            </div>
          ))}
        </div>
      )}

      {result.sme_audit_flags && result.sme_audit_flags.length > 0 && (
        <div>
          <div className="text-textdim mb-1.5">SME audit flags</div>
          {result.sme_audit_flags.map((f, i) => (
            <div key={i} className="my-1.5">
              <span className="text-warn-text">{f.severity}</span>: {f.reason}
              <div className="text-textdim text-[10px]">{f.claim_span}</div>
            </div>
          ))}
        </div>
      )}

      {result.divergence_metrics && (
        <div>
          <div className="text-textdim mb-1.5">divergence metrics</div>
          <MetricRow k="jaccard distance" v={result.divergence_metrics.jaccard_distance?.toFixed(3)} />
          <MetricRow k="claim overlap" v={result.divergence_metrics.claim_overlap?.toFixed(3)} />
          {result.divergence_metrics.watch_flag && (
            <MetricRow k="watch flag" v={result.divergence_metrics.watch_flag} />
          )}
        </div>
      )}
    </div>
  );
}

function PersonaBlock({ persona, claims }: { persona: string; claims: DeepClaim[] }) {
  if (!claims || claims.length === 0) return null;
  return (
    <div>
      <div className="text-accent-bright font-semibold mb-1">{persona}</div>
      {claims.map((c, i) => (
        <div key={i} className="my-1 ml-3 pl-2 border-l-2 border-border2 leading-relaxed">
          {c.claim_text}
          <div className="text-textdim text-[10px]">
            [{c.epistemic_status}]{c.chunk_ids?.length ? ` chunks: ${c.chunk_ids.join(", ")}` : ""}
          </div>
        </div>
      ))}
    </div>
  );
}

function MetricRow({ k, v }: { k: string; v: string | undefined | null }) {
  return (
    <div className="flex justify-between py-0.5">
      <span className="text-textdim">{k}</span>
      <span className="text-textmain">{v ?? "—"}</span>
    </div>
  );
}
