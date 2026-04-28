/**
 * lib/api-client.ts
 *
 * Typed fetch wrapper for the /api/wizard/* routes. Used by client
 * components to walk the cascade. Same-origin so no CORS config needed.
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
      // ignore body-parse failures; surface the status code
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

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
