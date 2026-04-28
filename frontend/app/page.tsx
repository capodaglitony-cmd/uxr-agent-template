"use client";

import { useState } from "react";
import { ModeToggle, type Mode } from "./components/ModeToggle";
import { WizardView } from "./components/WizardView";

const MODE_HINTS: Record<Mode, string> = {
  fast: "Fast: ~3s conversational answer · v0.3",
  deep: "Deep: ~25s three-persona ensemble synthesis · v0.3",
  wizard: "Wizard: research proposal cascade · click pills or type to advance",
};

export default function Home() {
  const [mode, setMode] = useState<Mode>("wizard");
  const [deepPrefill, setDeepPrefill] = useState("");

  return (
    <div className="flex flex-col h-screen bg-bg text-textmain">
      {/* Header */}
      <header className="bg-surface border-b border-border1 flex items-center px-5 h-12 gap-4 flex-shrink-0">
        <div className="font-mono text-[13px] tracking-wider">
          uxr<span className="text-accent-bright">agent</span>
        </div>
        <div className="text-[11px] font-mono text-textdim hidden sm:block">
          self-deployed research portfolio agent
        </div>
        <a
          href="https://github.com/capodaglitony-cmd/uxr-agent-template"
          target="_blank"
          rel="noreferrer"
          className="ml-auto text-[11px] font-mono text-textmuted hover:text-textmain transition px-3 py-1 border border-border2 rounded"
        >
          template ↗
        </a>
      </header>

      {/* Main content area */}
      <main className="flex-1 flex flex-col min-h-0 overflow-hidden relative">
        {mode === "wizard" ? (
          <WizardView
            onSwitchToDeep={(decision) => {
              setDeepPrefill(decision);
              setMode("deep");
            }}
          />
        ) : (
          <ModePlaceholder mode={mode} prefill={mode === "deep" ? deepPrefill : ""} />
        )}
      </main>

      {/* Footer with mode toggle */}
      <footer className="bg-surface border-t border-border1 px-6 py-3 flex items-center justify-between gap-4 flex-shrink-0">
        <ModeToggle active={mode} onChange={setMode} />
        <div className="text-[11px] font-mono text-textdim">{MODE_HINTS[mode]}</div>
      </footer>
    </div>
  );
}

function ModePlaceholder({ mode, prefill }: { mode: Mode; prefill: string }) {
  const lines: Record<Exclude<Mode, "wizard">, { title: string; body: string }> = {
    fast: {
      title: "Fast mode",
      body:
        "Single-call streaming Q&A against the corpus. Coming in v0.3 — for now, deploy the Modal backend and hit /generate via curl.",
    },
    deep: {
      title: "Deep mode",
      body:
        "Three-persona ensemble (PM / Designer / Engineer) with divergence-band classification, anti-hallucination drops, and SME synthesis. Coming in v0.3 — for now, deploy the Modal backend and POST to /ensemble.",
    },
  } as const;

  const m = lines[mode as Exclude<Mode, "wizard">];

  return (
    <div className="flex flex-col items-center justify-center h-full px-6 text-center max-w-xl mx-auto">
      <div className="text-textmuted font-mono text-[11px] uppercase tracking-wider mb-3">
        {m.title}
      </div>
      <p className="text-textmain text-[14px] leading-relaxed mb-4">{m.body}</p>
      {prefill && (
        <div className="bg-surface2 border border-border1 rounded p-3 text-[12px] text-textmuted font-mono w-full">
          <div className="text-textdim text-[10px] mb-1">prefilled question:</div>
          {prefill}
        </div>
      )}
      <div className="mt-6 text-[11px] text-textdim">
        Wizard mode is fully wired in v0.2 · switch to it via the toggle below.
      </div>
    </div>
  );
}
