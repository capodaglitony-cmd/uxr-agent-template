"use client";

import { useState } from "react";
import { ModeToggle, type Mode } from "./components/ModeToggle";
import { WizardView } from "./components/WizardView";
import { FastView } from "./components/FastView";
import { DeepView } from "./components/DeepView";

const MODE_HINTS: Record<Mode, string> = {
  fast: "Fast: ~3-5s single Anthropic call · Enter to send",
  deep: "Deep: ~25-35s three-persona ensemble + SME synthesis · Enter to send",
  wizard: "Wizard: research proposal cascade · click pills or type to advance",
};

export default function Home() {
  const [mode, setMode] = useState<Mode>("wizard");
  const [crossModePrefill, setCrossModePrefill] = useState<{
    target: Mode;
    text: string;
  } | null>(null);

  function switchToDeep(decision: string) {
    setCrossModePrefill({ target: "deep", text: decision });
    setMode("deep");
  }

  // Pull prefill only when matching this render's mode, then clear it so
  // user-typed text isn't overwritten on next render.
  const prefillForCurrent =
    crossModePrefill && crossModePrefill.target === mode
      ? crossModePrefill.text
      : undefined;

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
        {mode === "wizard" && <WizardView onSwitchToDeep={switchToDeep} />}
        {mode === "fast" && <FastView initialPrompt={prefillForCurrent} />}
        {mode === "deep" && <DeepView initialPrompt={prefillForCurrent} />}
      </main>

      {/* Footer with mode toggle */}
      <footer className="bg-surface border-t border-border1 px-6 py-3 flex items-center justify-between gap-4 flex-shrink-0">
        <ModeToggle active={mode} onChange={setMode} />
        <div className="text-[11px] font-mono text-textdim">{MODE_HINTS[mode]}</div>
      </footer>
    </div>
  );
}
