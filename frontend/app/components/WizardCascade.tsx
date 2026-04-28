"use client";

import { useEffect, useRef, useState } from "react";
import {
  CascadeStep,
  WIZARD_STEP_LABELS,
  WIZARD_STEPS,
  WizardAnswer,
  WizardQuestion,
} from "@/lib/wizard-types";
import { WizardStepDots } from "./WizardStepDots";

interface DoneAnswer {
  step: CascadeStep;
  prompt: string;
  pills_selected: string[];
  free_text: string;
}

export interface WizardCascadeProps {
  history: DoneAnswer[];
  currentQuestion: WizardQuestion | null;
  cascadeStatus: "idle" | "in_progress" | "generating" | "complete" | "deny" | "guardrail";
  multiStaged: string[];
  guardrailCopy: string | null;
  busy: boolean;
  onPillClick: (pill: string, q: WizardQuestion) => void;
  onCommit: (q: WizardQuestion, freeText: string) => void;
  onStartOver: () => void;
}

export function WizardCascade({
  history,
  currentQuestion,
  cascadeStatus,
  multiStaged,
  guardrailCopy,
  busy,
  onPillClick,
  onCommit,
  onStartOver,
}: WizardCascadeProps) {
  const completedSteps = history.map((h) => h.step);
  const currentStep = currentQuestion ? currentQuestion.step : null;

  const inputRef = useRef<HTMLInputElement | null>(null);
  const [freeText, setFreeText] = useState("");

  // Reset free-text input when the active question changes.
  useEffect(() => {
    setFreeText("");
    // Auto-focus on root question (no pills) so users can just type.
    if (currentQuestion && (!currentQuestion.pills || currentQuestion.pills.length === 0)) {
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [currentQuestion?.step]);

  return (
    <div className="bg-bg overflow-y-auto p-6 sm:p-7 flex flex-col gap-4 h-full">
      <WizardStepDots completedSteps={completedSteps} currentStep={currentStep} />

      {history.map((h, idx) => (
        <DoneQuestion key={`${h.step}-${idx}`} entry={h} />
      ))}

      {cascadeStatus === "in_progress" && currentQuestion && (
        <ActiveQuestion
          question={currentQuestion}
          multiStaged={multiStaged}
          freeText={freeText}
          setFreeText={setFreeText}
          inputRef={inputRef}
          busy={busy}
          onPillClick={onPillClick}
          onCommit={onCommit}
        />
      )}

      {cascadeStatus === "guardrail" && (
        <div className="space-y-3">
          <div className="p-5 bg-surface2 border border-border1 border-l-[3px] border-l-warn-text rounded text-textmuted text-[13px] leading-relaxed">
            {guardrailCopy ?? "Guardrail tripped."}
          </div>
          <button
            type="button"
            onClick={onStartOver}
            className="self-start px-3.5 py-1.5 bg-transparent border border-border2 rounded text-textmuted font-mono text-[11px] cursor-pointer hover:bg-surface2 hover:text-textmain hover:border-accent transition"
          >
            Start over
          </button>
        </div>
      )}

      {cascadeStatus === "in_progress" && currentQuestion && (
        <UpcomingQuestions reachedStep={currentQuestion.step} />
      )}
    </div>
  );
}

function DoneQuestion({ entry }: { entry: DoneAnswer }) {
  const value =
    entry.pills_selected.length > 0 && entry.free_text
      ? `${entry.pills_selected.join(", ")} — ${entry.free_text}`
      : entry.pills_selected.length > 0
      ? entry.pills_selected.join(", ")
      : entry.free_text || "(no answer)";
  return (
    <div className="opacity-55 transition-opacity flex flex-col gap-1.5 py-2.5 border-t border-border1 first:border-t-0">
      <div className="text-[10px] font-mono uppercase tracking-[1.5px] text-textdim">
        {WIZARD_STEP_LABELS[entry.step]}
      </div>
      <div className="text-[14px] text-textmain leading-snug">{entry.prompt}</div>
      <div className="text-[13px] text-accent-bright pl-2 border-l-2 border-accent leading-relaxed mt-0.5">
        {value}
      </div>
    </div>
  );
}

function ActiveQuestion({
  question,
  multiStaged,
  freeText,
  setFreeText,
  inputRef,
  busy,
  onPillClick,
  onCommit,
}: {
  question: WizardQuestion;
  multiStaged: string[];
  freeText: string;
  setFreeText: (v: string) => void;
  inputRef: React.RefObject<HTMLInputElement | null>;
  busy: boolean;
  onPillClick: (pill: string, q: WizardQuestion) => void;
  onCommit: (q: WizardQuestion, freeText: string) => void;
}) {
  return (
    <div className="opacity-100 transition-opacity flex flex-col gap-1.5 py-2.5 border-t border-border1 first:border-t-0">
      <div className="text-[10px] font-mono uppercase tracking-[1.5px] text-textdim">
        {WIZARD_STEP_LABELS[question.step]}
      </div>
      <div className="text-[14px] text-textmain leading-snug">{question.prompt}</div>
      {question.note && (
        <div className="text-[11px] text-textdim italic">{question.note}</div>
      )}

      {question.pills.length > 0 && (
        <div className="flex flex-wrap gap-2 mt-1">
          {question.pills.map((pill) => {
            const selected = multiStaged.includes(pill);
            return (
              <button
                key={pill}
                type="button"
                disabled={busy}
                onClick={() => onPillClick(pill, question)}
                className={[
                  "inline-flex items-center px-3.5 py-1.5 rounded-full text-[13px] font-sans cursor-pointer transition-colors duration-150 border",
                  selected
                    ? "bg-accent-glow border-accent-bright text-accent-bright"
                    : "bg-transparent border-border2 text-textmuted hover:text-textmain hover:border-accent",
                  busy ? "opacity-50 cursor-not-allowed" : "",
                ].join(" ")}
              >
                {pill}
              </button>
            );
          })}
        </div>
      )}

      {question.free_text_allowed && (
        <input
          ref={inputRef}
          type="text"
          value={freeText}
          onChange={(e) => setFreeText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              onCommit(question, freeText);
            }
          }}
          placeholder={
            question.pills.length > 0
              ? "Or type your own..."
              : "Type your answer..."
          }
          disabled={busy}
          className="w-full bg-bg border border-border2 rounded px-3 py-2 text-[13px] text-textmain font-sans outline-none focus:border-accent transition-colors mt-1.5 placeholder:text-textdim disabled:opacity-50"
        />
      )}

      {question.multi_select && (
        <button
          type="button"
          disabled={busy || (multiStaged.length === 0 && !freeText.trim())}
          onClick={() => onCommit(question, freeText)}
          className="self-start px-4 py-1.5 bg-accent border border-accent-bright rounded text-textmain font-mono text-[11px] cursor-pointer hover:bg-accent-bright transition mt-2 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Continue →
        </button>
      )}
    </div>
  );
}

function UpcomingQuestions({ reachedStep }: { reachedStep: CascadeStep }) {
  const reachedIdx = WIZARD_STEPS.indexOf(reachedStep);
  const upcoming = WIZARD_STEPS.slice(reachedIdx + 1);
  return (
    <>
      {upcoming.map((step) => (
        <div
          key={step}
          className="opacity-30 pointer-events-none flex flex-col gap-1.5 py-2.5 border-t border-border1"
        >
          <div className="text-[10px] font-mono uppercase tracking-[1.5px] text-textdim">
            {WIZARD_STEP_LABELS[step]}
          </div>
        </div>
      ))}
    </>
  );
}
