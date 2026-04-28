/**
 * lib/wizard-types.ts
 *
 * TypeScript mirrors of the Python wizard schemas (backend/ensemble/wizard/
 * state.py, schemas.py, classifier.py). Kept manually in sync with the
 * Python side; the Python remains source of truth.
 *
 * Wire format: every WizardState round-trips as plain JSON via the proxy
 * routes, so these types describe what comes back from /api/wizard/*.
 */

// ── Cascade steps (mirrors CascadeStep enum) ──────────────────────────

export type CascadeStep =
  | "root_question"
  | "q1_winning_aspiration"
  | "q2_where_to_play"
  | "q3_how_to_win"
  | "q4_capabilities"
  | "q5_management_systems"
  | "fork_direction_or_certainty"
  | "complete"
  | "guardrail_tripped";

export const WIZARD_STEPS: CascadeStep[] = [
  "root_question",
  "q1_winning_aspiration",
  "q2_where_to_play",
  "q3_how_to_win",
  "q4_capabilities",
  "q5_management_systems",
  "fork_direction_or_certainty",
];

export const WIZARD_STEP_LABELS: Record<CascadeStep, string> = {
  root_question: "1 / Decision",
  q1_winning_aspiration: "2 / Winning aspiration",
  q2_where_to_play: "3 / Where to play",
  q3_how_to_win: "4 / How to win",
  q4_capabilities: "5 / Capabilities",
  q5_management_systems: "6 / Management systems",
  fork_direction_or_certainty: "7 / Direction or certainty",
  complete: "Complete",
  guardrail_tripped: "Guardrail",
};

// ── Question / Answer dataclasses ─────────────────────────────────────

export interface WizardQuestion {
  step: CascadeStep;
  prompt: string;
  pills: string[];
  multi_select: boolean;
  free_text_allowed: boolean;
  note: string;
}

export interface WizardAnswer {
  step: CascadeStep;
  pills_selected: string[];
  free_text: string;
}

// ── Wizard state (mirrors WizardState.to_payload()) ───────────────────

export interface WizardStatePayload {
  decision_text: string;
  decision_count: number;
  q1_answer: WizardAnswer | null;
  q2_answer: WizardAnswer | null;
  q3_answer: WizardAnswer | null;
  q4_answer: WizardAnswer | null;
  q5_answer: WizardAnswer | null;
  fork_answer: WizardAnswer | null;
  direction_or_certainty: "direction" | "certainty" | "both" | null;
  current_step: CascadeStep;
  guardrail_tripped: boolean;
}

// ── Classifier outputs ────────────────────────────────────────────────

export type Intent = "explore" | "define" | "validate" | "measure" | "mixed";

export type Routing =
  | "kickoff"
  | "backlog"
  | "next_sprint"
  | "spike"
  | "take_and_run"
  | "deny";

export interface MethodRecommendation {
  primary_methods: string[];
  alternative_methods: string[];
  rationale_anchors: string[];
  phasing_note: string;
}

// ── Proposal envelope (mirrors WizardProposal.to_payload()) ───────────

export type ProposalStatus = "proposal" | "deny" | "guardrail";

export interface ProposalSections {
  decision_context: string;
  primary_research_question: string;
  secondary_research_questions: string[];
  out_of_scope_questions: string[];
  recommended_methodology: string;
  methodology_rationale: string;
  alternative_methods_considered: string[];
  phasing_note: string;
  target_population: string;
  inclusion_exclusion: string[];
  sample_size: string;
  recruitment_approach: string;
  study_design: string;
  timeline: string;
  deliverable_format: string;
  risks: string[];
}

export interface WizardProposal {
  status: ProposalStatus;
  cascade_state: WizardStatePayload;
  intent: Intent | null;
  routing: Routing | null;
  method_recommendation: MethodRecommendation | null;
  aggregated_output: Record<string, unknown> | null;
  proposal_markdown: string;
  proposal_sections: ProposalSections;
  out_of_scope_questions: string[];
  deny_copy: string;
  guardrail_copy: string;
  elapsed_seconds: number;
}

// ── /api/wizard/* response shapes ─────────────────────────────────────

export type WizardResponseStatus =
  | "ok"
  | "in_progress"
  | "complete"
  | "deny"
  | "guardrail";

export interface WizardStartResponse {
  status: "ok";
  state: WizardStatePayload;
  next_question: WizardQuestion | null;
}

export interface WizardAnswerResponse {
  status: WizardResponseStatus;
  state: WizardStatePayload;
  next_question: WizardQuestion | null;
  proposal?: WizardProposal;
}

export interface WizardProposalResponse {
  status: "ok";
  proposal: WizardProposal;
}

export interface WizardErrorResponse {
  error: string;
  state?: WizardStatePayload;
}
