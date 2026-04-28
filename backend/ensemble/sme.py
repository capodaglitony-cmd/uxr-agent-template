"""
ensemble/sme.py

The UXR SME synthesizer. Fifth LLM call above the three-persona layer.
Reads the three persona outputs after anti-hallucination and produces
the accountable answer that the widget main bubble renders.

See SME_Synthesis_Design_v1.md for the full design.

Architectural role:
- Personas: three corpus-grounded research perspectives with per-persona
  anti-hallucination. Preserve divergence.
- SME: synthesis layer above preservation. Reads the three persona
  outputs, takes a stance, produces the accountable answer in the owner's
  voice.

Not a return to v1 consensus-seeking. The personas still preserve
divergence in claims_by_persona. The SME adds a synthesis layer on top.

Changelog:
  2026-04-23: v1. Initial SME synthesizer per SME_Synthesis_Design_v1
    Section 18 implementation plan step 2.
"""

from dataclasses import dataclass
from typing import List, Optional
import requests

from .schemas import AnswererOutput, Claim, DivergenceMetrics
from .sme_prompt import build_sme_full_prompt


# ── SME LLM configuration ──────────────────────────────────────────────
#
# Same model as the Answerers for cost parity and consistent voice.
# Timeout is higher than the Answerers' 120s because the SME reads a
# larger input payload (three structured persona outputs) and must
# produce a considered answer, not a bulleted list. 150s gives headroom
# for Qwen to generate the 3-6 sentence answer with occasional longer
# divergence-handling cases.

import os
_SME_PROXY_BASE = os.environ.get(
    "MODAL_ENDPOINT",
    os.environ.get("UXR_PROXY_BASE", "http://localhost:8080"),
)
SME_OLLAMA_ENDPOINT = f"{_SME_PROXY_BASE}/generate"
SME_OLLAMA_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
SME_TIMEOUT_SEC = 150


# ── Fallback reason codes ──────────────────────────────────────────────

FALLBACK_CALL_FAILED = "call_failed"
FALLBACK_EMPTY_OUTPUT = "empty_output"
FALLBACK_MALFORMED = "malformed"


@dataclass
class SMEResult:
    """Result of the SME synthesis pass.

    answer: the SME's synthesized answer (empty string if fallback fired).
    fallback_reason: None if the call succeeded, one of FALLBACK_*
      constants if the caller should fall back to deterministic_answer.
    elapsed_seconds: wall time for the SME call, useful for latency
      tracking and the widget footer.
    """
    answer: str
    fallback_reason: Optional[str] = None
    elapsed_seconds: float = 0.0


class SMESynthesizer:
    """The UXR SME synthesis layer.

    Usage:
        sme = SMESynthesizer()
        result = sme.synthesize(
            question=...,
            pm_output=...,
            designer_output=...,
            engineer_output=...,
            pm_claims_surviving=...,
            designer_claims_surviving=...,
            engineer_claims_surviving=...,
            divergence_metrics=...,
            divergence_band=...,
            dropped_count=...,
        )
        # result.answer contains the synthesis (or empty string on fallback)
        # result.fallback_reason is None if the call succeeded

    The synthesizer is stateless. Safe to instantiate once at module
    load time (matches how the proxy_server instantiates the Answerers
    and Aggregator).
    """

    def __init__(
        self,
        endpoint: str = SME_OLLAMA_ENDPOINT,
        model: str = SME_OLLAMA_MODEL,
        timeout: int = SME_TIMEOUT_SEC,
    ):
        self.endpoint = endpoint
        self.model = model
        self.timeout = timeout

    def synthesize(
        self,
        question: str,
        pm_output: AnswererOutput,
        designer_output: AnswererOutput,
        engineer_output: AnswererOutput,
        pm_claims_surviving: List[Claim],
        designer_claims_surviving: List[Claim],
        engineer_claims_surviving: List[Claim],
        divergence_metrics: DivergenceMetrics,
        divergence_band: str,
        dropped_count: int,
    ) -> SMEResult:
        """Run the SME synthesis pass.

        Builds the full prompt from the three persona outputs, calls
        Qwen, parses the response, and returns an SMEResult. On any
        failure mode, returns a result with a fallback_reason set so
        the caller can route to deterministic_answer.

        Does not raise. All failure modes are captured in the result.
        """
        import time
        t_start = time.time()

        prompt = build_sme_full_prompt(
            question=question,
            pm_output=pm_output,
            designer_output=designer_output,
            engineer_output=engineer_output,
            pm_claims_surviving=pm_claims_surviving,
            designer_claims_surviving=designer_claims_surviving,
            engineer_claims_surviving=engineer_claims_surviving,
            divergence_metrics=divergence_metrics,
            divergence_band=divergence_band,
            dropped_count=dropped_count,
        )

        raw_response = self._call_llm(prompt)

        elapsed = time.time() - t_start

        if raw_response is None:
            return SMEResult(
                answer="",
                fallback_reason=FALLBACK_CALL_FAILED,
                elapsed_seconds=elapsed,
            )

        cleaned = self._clean_response(raw_response)

        if not cleaned or not cleaned.strip():
            return SMEResult(
                answer="",
                fallback_reason=FALLBACK_EMPTY_OUTPUT,
                elapsed_seconds=elapsed,
            )

        if self._is_malformed(cleaned):
            return SMEResult(
                answer="",
                fallback_reason=FALLBACK_MALFORMED,
                elapsed_seconds=elapsed,
            )

        return SMEResult(
            answer=cleaned,
            fallback_reason=None,
            elapsed_seconds=elapsed,
        )

    # ── LLM call (mirrors AnswererBase._call_llm pattern) ──────────────

    def _call_llm(self, prompt: str) -> Optional[str]:
        """Call Qwen via Ollama. Returns raw text or None on failure.

        Mirrors the AnswererBase._call_llm pattern so the proxy_server's
        wiring and the ThreadingHTTPServer re-entrancy handling applies
        identically.
        """
        try:
            resp = requests.post(
                self.endpoint,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "")
        except Exception as e:
            print(f"[SME] LLM call failed: {e}")
            return None

    # ── Response cleanup ───────────────────────────────────────────────

    def _clean_response(self, raw: str) -> str:
        """Strip common LLM preamble and trailing noise.

        Qwen occasionally ignores the "no preamble" instruction and emits
        "Here is the synthesized answer:" or similar. Strip these
        specifically rather than via aggressive heuristics so we don't
        accidentally trim real content.
        """
        cleaned = raw.strip()

        # Strip known preamble patterns. Conservative — only match at the
        # very start and only on patterns the prompt explicitly forbids.
        preamble_patterns = [
            "Here is the synthesized answer:",
            "Here is the synthesis:",
            "Here is my synthesized answer:",
            "Here is the answer:",
            "Synthesized answer:",
            "Synthesis:",
            "Answer:",
        ]
        for pattern in preamble_patterns:
            if cleaned.lower().startswith(pattern.lower()):
                cleaned = cleaned[len(pattern):].strip()
                break

        # Strip leading/trailing quote marks if Qwen wrapped the whole
        # answer in quotes (happens occasionally).
        if (cleaned.startswith('"') and cleaned.endswith('"')) or \
           (cleaned.startswith("'") and cleaned.endswith("'")):
            cleaned = cleaned[1:-1].strip()

        # Strip any residual trailing whitespace or newlines.
        return cleaned.strip()

    def _is_malformed(self, text: str) -> bool:
        """Heuristic check for obviously broken SME output.

        Returns True for:
          - Responses that are just an echo of the prompt or system
            instructions.
          - Responses with no sentence-ending punctuation at all (Qwen
            occasionally produces a single comma-separated fragment).
          - Responses over 1200 characters (SME should produce 3-6
            sentences; anything this long suggests the model drifted
            into rambling or restated the input).

        Conservative heuristics. If a response passes these, it goes
        through unchanged. The audit pass in aggregator.py catches
        content-level issues.
        """
        lowered = text.lower()

        # Echo check: responses that start by repeating prompt language.
        echo_markers = (
            "you are a senior ux researcher",
            "voice constraints",
            "divergence handling",
            "the three perspectives are",
        )
        for marker in echo_markers:
            if marker in lowered[:200]:
                return True

        # No sentence terminator at all.
        if not any(p in text for p in (".", "!", "?")):
            return True

        # Too long — SME should be 3-6 sentences, roughly 300-700 chars.
        # 1200 is a generous ceiling before we treat it as drift.
        if len(text) > 1200:
            return True

        return False
