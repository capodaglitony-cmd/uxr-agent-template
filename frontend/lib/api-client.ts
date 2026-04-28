/**
 * lib/api-client.ts
 *
 * Typed fetch wrapper for the /api/* routes. Used by client components
 * to talk to the Modal-hosted backend through the Vercel proxy.
 */

import type {
  WizardAnswer,
  WizardAnswerResponse,
  WizardProposalResponse,
  WizardStartResponse,
  WizardStatePayload,
} from "./wizard-types";

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const data = await res.json();
      if (data && typeof data.error === "string") detail = data.error;
    } catch {
      // ignore body-parse failures
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

// ── Wizard ────────────────────────────────────────────────────────────

export function wizardStart(): Promise<WizardStartResponse> {
  return postJson("/api/wizard/start", {});
}

export function wizardAnswer(
  state: WizardStatePayload,
  answer: WizardAnswer,
): Promise<WizardAnswerResponse> {
  return postJson("/api/wizard/answer", { state, answer });
}

export function wizardProposal(
  state: WizardStatePayload,
): Promise<WizardProposalResponse> {
  return postJson("/api/wizard/proposal", { state });
}

// ── Fast (single LLM call) ────────────────────────────────────────────

export interface FastResponse {
  response: string;
  model: string;
}

export function fastQuery(prompt: string): Promise<FastResponse> {
  return postJson("/api/query", { prompt });
}

// ── Deep (3-persona ensemble) ─────────────────────────────────────────

export interface DeepClaim {
  claim_text: string;
  epistemic_status: string;
  chunk_ids: string[];
  named_entities?: string[];
  entities?: string[]; // serialized from Python Set
}

export interface DivergenceMetrics {
  jaccard_distance: number;
  claim_overlap: number;
  watch_flag: string | null;
}

export interface DroppedClaim {
  claim_text: string;
  persona: string;
  drop_reason: string;
  chunks_checked?: string[];
  fabrication_confidence?: number | null;
}

export interface SMEAuditFlag {
  claim_span: string;
  flagged_entities: string[];
  reason: string;
  severity: string;
}

export interface AggregatedOutput {
  question: string;
  deterministic_answer: string;
  sme_answer: string;
  sme_audit_flags: SMEAuditFlag[];
  sme_fallback_reason: string | null;
  sme_elapsed_seconds: number;
  synthesis_prose: string;
  claims_by_persona: Record<string, DeepClaim[]>;
  divergence_band: string;
  divergence_metrics: DivergenceMetrics;
  epistemic_summary: Record<string, Record<string, number>>;
  dropped_claims: DroppedClaim[];
  refusal_triggered: boolean;
  refusal_reason: string | null;
  top_level_answer?: string; // computed property; backend includes it in to_dict()
  has_blocking_audit_flag?: boolean;
  [key: string]: unknown;
}

export interface DeepResponse {
  status: "ok";
  question: string;
  aggregated: AggregatedOutput;
}

export function deepQuery(question: string): Promise<DeepResponse> {
  return postJson("/api/ensemble", { question });
}
