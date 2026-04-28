"use client";

import { useState } from "react";
import {
  WizardProposal as WizardProposalType,
  WizardStatePayload,
} from "@/lib/wizard-types";
import { MarkdownRender } from "./MarkdownRender";

interface DoneAnswer {
  step: string;
  pills_selected: string[];
  free_text: string;
}

export interface WizardProposalProps {
  cascadeStatus: "idle" | "in_progress" | "generating" | "complete" | "deny" | "guardrail";
  history: DoneAnswer[];
  state: WizardStatePayload | null;
  proposal: WizardProposalType | null;
  onStartOver: () => void;
  onAskInDeepMode: (decisionText: string) => void;
}

export function WizardProposalPane({
  cascadeStatus,
  history,
  state,
  proposal,
  onStartOver,
  onAskInDeepMode,
}: WizardProposalProps) {
  return (
    <div className="bg-bg overflow-y-auto p-6 sm:p-7 flex flex-col gap-3.5 h-full">
      <StatusBadge status={cascadeStatus} elapsed={proposal?.elapsed_seconds} />

      {(cascadeStatus === "idle" ||
        (cascadeStatus === "in_progress" && history.length === 0)) && (
        <div className="text-textdim italic text-[13px] text-center mt-20">
          Answer the first question to begin building your proposal.
        </div>
      )}

      {cascadeStatus === "in_progress" && history.length > 0 && (
        <InProgressPreview history={history} />
      )}

      {cascadeStatus === "generating" && (
        <>
          <div className="proposal-md">
            <p className="!text-textmuted italic !mt-4">
              The three personas are answering against the corpus, the aggregator
              is merging their perspectives, and the SME is synthesizing the
              rationale. This typically takes 25-30 seconds.
            </p>
          </div>
          <InProgressPreview history={history} />
        </>
      )}

      {cascadeStatus === "guardrail" && proposal && (
        <>
          <div className="p-5 bg-surface2 border border-border1 border-l-[3px] border-l-warn-text rounded text-textmuted text-[13px] leading-relaxed">
            {proposal.guardrail_copy}
          </div>
          <ActionRow>
            <ActionButton onClick={onStartOver}>Start over</ActionButton>
          </ActionRow>
        </>
      )}

      {cascadeStatus === "deny" && proposal && (
        <>
          <div className="p-5 bg-surface2 border border-border1 border-l-[3px] border-l-accent-bright rounded text-textmuted text-[13px] leading-relaxed">
            {proposal.deny_copy}
          </div>
          <ActionRow>
            <ActionButton onClick={onStartOver}>Start over</ActionButton>
            <ActionButton
              onClick={() =>
                onAskInDeepMode(state?.decision_text ?? "")
              }
            >
              Ask in Deep mode instead
            </ActionButton>
          </ActionRow>
        </>
      )}

      {cascadeStatus === "complete" && proposal && (
        <CompleteProposal
          proposal={proposal}
          onStartOver={onStartOver}
        />
      )}
    </div>
  );
}

function StatusBadge({
  status,
  elapsed,
}: {
  status: WizardProposalProps["cascadeStatus"];
  elapsed?: number | null;
}) {
  let label = "Awaiting first answer";
  let cls = "bg-surface2 text-textdim border-border1";
  let pulsing = false;

  if (status === "in_progress") {
    label = "Building as you answer";
    cls = "bg-warn text-warn-text border-warn";
    pulsing = true;
  } else if (status === "generating") {
    label = "Generating proposal...";
    cls = "bg-accent-glow text-accent-bright border-accent";
    pulsing = true;
  } else if (status === "complete") {
    label = elapsed ? `Complete · ${elapsed.toFixed(1)}s` : "Complete";
    cls = "bg-ok text-ok-text border-ok";
  } else if (status === "deny") {
    label = "Routing: deny";
    cls = "bg-ok text-ok-text border-ok";
  } else if (status === "guardrail") {
    label = "Guardrail";
    cls = "bg-ok text-ok-text border-ok";
  }

  return (
    <div
      className={[
        "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-xl text-[10px] font-mono uppercase tracking-wider self-end border",
        cls,
      ].join(" ")}
    >
      <span
        className={[
          "w-1.5 h-1.5 rounded-full bg-current",
          pulsing ? "animate-pulse-dot" : "",
        ].join(" ")}
      />
      {label}
    </div>
  );
}

function InProgressPreview({ history }: { history: DoneAnswer[] }) {
  function get(step: string) {
    return history.find((h) => h.step === step);
  }
  function answerText(h: DoneAnswer | undefined): string {
    if (!h) return "";
    return h.pills_selected.length > 0
      ? h.pills_selected.join(", ")
      : h.free_text;
  }

  const decision = get("root_question");
  const q1 = get("q1_winning_aspiration");
  const q2 = get("q2_where_to_play");
  const q3 = get("q3_how_to_win");
  const q4 = get("q4_capabilities");
  const q5 = get("q5_management_systems");

  return (
    <div className="proposal-md">
      {decision && (
        <div className="mb-3">
          <h2>1. Decision Context</h2>
          <p>{decision.free_text}</p>
        </div>
      )}
      {(q1 || q2) && (
        <div className="mb-3">
          <h2>2. Research Questions</h2>
          <p>
            <em>Refining as you answer.</em>
          </p>
          {q1 && (
            <p>
              <strong>Aspiration:</strong> {answerText(q1)}
            </p>
          )}
          {q2 && (
            <p>
              <strong>Playing field:</strong> {answerText(q2)}
            </p>
          )}
        </div>
      )}
      {q3 && (
        <div className="mb-3">
          <h2>3. Recommended Methodology</h2>
          <p>
            <em>Method will be derived from cascade once complete.</em>
          </p>
          <p>
            <strong>Approach signal:</strong> {answerText(q3)}
          </p>
        </div>
      )}
      {q4 && (
        <div className="mb-3">
          <h2>5. Study Design</h2>
          <p>
            <strong>Capabilities on hand:</strong> {answerText(q4)}
          </p>
        </div>
      )}
      {q5 && (
        <div className="mb-3">
          <h2>6. Timeline, Outputs, and Risks</h2>
          <p>
            <strong>Decision-maker needs:</strong> {answerText(q5)}
          </p>
        </div>
      )}
      <p className="!text-textdim italic !mt-3.5">
        Continuing the cascade. Methodology, participants, and timeline will
        populate when the proposal is generated.
      </p>
    </div>
  );
}

function CompleteProposal({
  proposal,
  onStartOver,
}: {
  proposal: WizardProposalType;
  onStartOver: () => void;
}) {
  const [copyLabel, setCopyLabel] = useState("Copy as markdown");

  return (
    <>
      <MarkdownRender md={proposal.proposal_markdown} />
      <ActionRow>
        <ActionButton
          onClick={() => {
            navigator.clipboard.writeText(proposal.proposal_markdown).then(() => {
              setCopyLabel("Copied");
              setTimeout(() => setCopyLabel("Copy as markdown"), 1500);
            });
          }}
        >
          {copyLabel}
        </ActionButton>
        <ActionButton onClick={onStartOver}>Start over</ActionButton>
      </ActionRow>
    </>
  );
}

function ActionRow({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex gap-2 mt-4 pt-3 border-t border-border1">
      {children}
    </div>
  );
}

function ActionButton({
  onClick,
  children,
}: {
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="px-3.5 py-1.5 bg-transparent border border-border2 rounded text-textmuted font-mono text-[11px] cursor-pointer hover:bg-surface2 hover:text-textmain hover:border-accent transition"
    >
      {children}
    </button>
  );
}
