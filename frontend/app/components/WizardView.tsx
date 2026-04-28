"use client";

import { useCallback, useEffect, useState } from "react";
import {
  CascadeStep,
  WizardAnswer,
  WizardProposal,
  WizardQuestion,
  WizardStatePayload,
} from "@/lib/wizard-types";
import { wizardAnswer, wizardStart } from "@/lib/api-client";
import { WizardCascade } from "./WizardCascade";
import { WizardProposalPane } from "./WizardProposal";

interface DoneAnswer {
  step: CascadeStep;
  prompt: string;
  pills_selected: string[];
  free_text: string;
}

type CascadeStatus =
  | "idle"
  | "in_progress"
  | "generating"
  | "complete"
  | "deny"
  | "guardrail";

export function WizardView({
  onSwitchToDeep,
}: {
  onSwitchToDeep: (decisionText: string) => void;
}) {
  const [state, setState] = useState<WizardStatePayload | null>(null);
  const [currentQuestion, setCurrentQuestion] = useState<WizardQuestion | null>(
    null
  );
  const [history, setHistory] = useState<DoneAnswer[]>([]);
  const [proposal, setProposal] = useState<WizardProposal | null>(null);
  const [multiStaged, setMultiStaged] = useState<string[]>([]);
  const [cascadeStatus, setCascadeStatus] = useState<CascadeStatus>("idle");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const start = useCallback(async () => {
    setError(null);
    setHistory([]);
    setProposal(null);
    setMultiStaged([]);
    setCascadeStatus("idle");
    try {
      const res = await wizardStart();
      setState(res.state);
      setCurrentQuestion(res.next_question);
      setCascadeStatus("in_progress");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  // Auto-start on mount.
  useEffect(() => {
    start();
  }, [start]);

  const submitAnswer = useCallback(
    async (answer: WizardAnswer) => {
      if (busy || !state) return;
      setBusy(true);
      setError(null);

      const optimisticHistory: DoneAnswer[] = [
        ...history,
        {
          step: answer.step,
          prompt: currentQuestion?.prompt ?? "",
          pills_selected: [...answer.pills_selected],
          free_text: answer.free_text,
        },
      ];
      setHistory(optimisticHistory);
      setMultiStaged([]);

      const wasFinalStep =
        currentQuestion?.step === "fork_direction_or_certainty";
      if (wasFinalStep) {
        setCascadeStatus("generating");
        setCurrentQuestion(null);
      } else {
        setCurrentQuestion(null);
      }

      try {
        const res = await wizardAnswer(state, answer);
        setState(res.state);
        if (res.status === "in_progress") {
          setCurrentQuestion(res.next_question);
          setCascadeStatus("in_progress");
        } else if (res.status === "guardrail") {
          setProposal(res.proposal ?? null);
          setCascadeStatus("guardrail");
          setCurrentQuestion(null);
        } else if (res.status === "deny") {
          setProposal(res.proposal ?? null);
          setCascadeStatus("deny");
          setCurrentQuestion(null);
        } else if (res.status === "complete") {
          setProposal(res.proposal ?? null);
          setCascadeStatus("complete");
          setCurrentQuestion(null);
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        // Roll back optimistic update.
        setHistory(history);
        setCascadeStatus("in_progress");
        setCurrentQuestion(currentQuestion);
      } finally {
        setBusy(false);
      }
    },
    [busy, state, history, currentQuestion]
  );

  const handlePillClick = useCallback(
    (pill: string, q: WizardQuestion) => {
      if (busy) return;
      if (q.multi_select) {
        setMultiStaged((prev) =>
          prev.includes(pill)
            ? prev.filter((p) => p !== pill)
            : [...prev, pill]
        );
      } else {
        // Single-select: paint then auto-advance.
        setMultiStaged([pill]);
        setTimeout(() => {
          submitAnswer({
            step: q.step,
            pills_selected: [pill],
            free_text: "",
          });
        }, 250);
      }
    },
    [busy, submitAnswer]
  );

  const handleCommit = useCallback(
    (q: WizardQuestion, freeText: string) => {
      if (busy) return;
      const trimmed = freeText.trim();
      const pills = q.multi_select ? [...multiStaged] : [];
      if (q.step === "root_question" && !trimmed) return;
      if (pills.length === 0 && !trimmed) return;
      submitAnswer({
        step: q.step,
        pills_selected: pills,
        free_text: trimmed,
      });
    },
    [busy, multiStaged, submitAnswer]
  );

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-px bg-border1 flex-1 min-h-0">
      <WizardCascade
        history={history}
        currentQuestion={currentQuestion}
        cascadeStatus={cascadeStatus}
        multiStaged={multiStaged}
        guardrailCopy={proposal?.guardrail_copy ?? null}
        busy={busy}
        onPillClick={handlePillClick}
        onCommit={handleCommit}
        onStartOver={start}
      />
      <WizardProposalPane
        cascadeStatus={cascadeStatus}
        history={history}
        state={state}
        proposal={proposal}
        onStartOver={start}
        onAskInDeepMode={(decision) => onSwitchToDeep(decision)}
      />
      {error && (
        <div className="absolute bottom-4 right-4 max-w-md p-3 bg-err border border-err-text rounded text-err-text text-[12px] font-mono z-50">
          {error}
        </div>
      )}
    </div>
  );
}
