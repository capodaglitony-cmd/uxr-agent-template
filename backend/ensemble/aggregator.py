"""
ensemble/aggregator.py

v2 UXR-as-Aggregator. The Aggregator reads three Answerer outputs and produces
a synthesis that preserves divergence across PM, Designer, and Engineer
perspectives rather than collapsing them to consensus.

Pipeline (v2.2):
  1. Per-persona anti-hallucination pass. Five drop conditions from Spec v2
     §Anti-Hallucination Pass. Aggressive drop stance.
  2. Refusal check. If every persona has zero chunk-grounded fact/inference
     claims, route to _handle_refusal_path.
  3. Divergence metrics. Pairwise Jaccard on entity sets + claim-overlap
     signature ratio. Watch flag for low-divergence-red-flag and
     high-divergence-incoherence cases.
  4. Band categorization. expected / productive / red_flag / refusal.
  5. Synthesis prose in UXR voice. Per-persona attribution. No "the team said."
  6. Deterministic answer. v2.1 per-band top-claim selection. Now the fallback.
  7. SME synthesis (v2.2). Fifth LLM call, reads persona outputs, produces
     accountable answer in the owner's voice.
  8. SME audit pass (v2.2.1). Anti-hallucination flags on the SME output
     against the chunk union. High-severity flags trigger hard fallback
     to deterministic_answer.

Supersedes v1. See Aggregator_Rubric_Spec_v2.md §"What changed from v1".

Changelog:
  2026-04-23 (v2.2.2 scope-inflation detector):
    - Widget browser smoke test on today's Q29 revealed that entity-count
      alone is insufficient: SME produced "<owner> prioritizes research load
      and capacity within a large team" with only 1 entity flagged low.
      The answer is still a confabulation (asserts management scope the
      corpus does not support) but slips under the count threshold.
    - Added _SCOPE_INFLATION_PATTERNS: narrow list of phrases that claim
      management scope (large team, leads a team, manages N researchers,
      pipeline from intake to repository, etc).
    - Added _SCOPE_QUESTION_KEYWORDS: narrow list (manage, team, lead,
      director, oversee, direct report) that flags the question as a
      scope question.
    - Added _scope_inflation_check(): when both are present in the same
      SME call, add a high-severity flag regardless of entity count.
      The existing hard gate then falls back to deterministic_answer.
    - Narrow on purpose. Only catches the known Q29-shape failure. False
      positives on legitimate management-case answers are accepted as
      the trade for catching scope-inflation confabulation.

  2026-04-23 (v2.2.1 hard audit gate):
    - _sme_audit_pass now sets sme_fallback_reason to
      FALLBACK_AUDIT_REJECTED when a high-severity flag fires.
    - The top_level_answer computed property on AggregatedOutput does
      the actual gating (schema v2.2.1).
    - sme_answer preserved on the object when the gate fires.

  2026-04-23 (v2.2 SME synthesis layer):
    - New fifth LLM call above the persona layer.
    - _run_sme_synthesis() wires the SME call into the pipeline.
    - _sme_audit_pass() runs anti-hallucination on SME output.
    - Internal `top_level_answer` renamed to `deterministic_answer`.

  2026-04-23 (v2.1 UX: expected-band framing tightened):
    - Changed expected-band framing sentence to "Corpus support for
      this answer is partial. Expand to see per-persona detail and any
      adjacent findings."

  2026-04-23 (v2.1 UX: deterministic answer field):
    - AggregatedOutput carries a deterministic answer string.

  2026-04-23 (v2.1 path-b-removal):
    - _should_refuse simplified to path (a) only.

  2026-04-23 (v2.1 fabrication confidence scoring):
    - _anti_hallucination_pass rewritten with four-signal weighted score.

  2026-04-23 (v2 synthesis voice refinement):
    - Added BAND_CONVERGED. _build_synthesis_prose split into four voices.

  2026-04-23 (v2): UXR-as-Aggregator redesign. Divergence preserved.
"""

from collections import Counter
from dataclasses import dataclass
from typing import List, Dict, Set, Tuple, Optional
import re

from .schemas import (
    AnswererOutput, AggregatedOutput, Claim, Persona, EpistemicStatus,
    EvidenceBase, EpistemicStatusCounts, AuditTrail, ScoringFields,
    DroppedClaim, DivergenceMetrics, SMEAuditFlag,
    FALLBACK_AUDIT_REJECTED,
    SME_AUDIT_BLOCKING_SEVERITIES,
    DroppedEntity,
    ConfidenceBreakdown,
    Disagreement, SingleSourceFlag,
)
from .retrieval import Chunk, extract_entities_from_chunks
from .sme import SMESynthesizer


# ── Thin-retrieval thresholds ─────────────────────────────────────────────

THIN_RETRIEVAL_THRESHOLDS = {
    Persona.PM: 4,
    Persona.DESIGNER: 4,
    Persona.ENGINEER: 5,
}


# ── Divergence bands ──────────────────────────────────────────────────────

BAND_EXPECTED = "expected"
BAND_PRODUCTIVE = "productive"
BAND_RED_FLAG = "red_flag"
BAND_REFUSAL = "refusal"
BAND_CONVERGED = "converged"


# ── Divergence metric thresholds ──────────────────────────────────────────

JACCARD_LOW = 0.3
JACCARD_HIGH = 0.7
OVERLAP_HIGH = 0.5
OVERLAP_LOW = 0.1


# ── Anti-hallucination drop reason codes ───────────────────────────────────

DROP_FABRICATION_CONFIDENCE_EXCEEDED = "fabrication_confidence_exceeded"
DROP_ENTITY_NOT_IN_CHUNKS = "entity_not_in_chunks"
DROP_CROSS_CASE_CONTAMINATION = "cross_case_contamination"
DROP_INVENTED_PROPER_NOUN = "invented_proper_noun"
DROP_CONTRADICTS_CHUNK_FACT = "contradicts_chunk_fact"
DROP_UNSUPPORTED_CAUSATION = "unsupported_causation"


# ── Fabrication confidence scoring (v2.1) ─────────────────────────────────

FABRICATION_DROP_THRESHOLD = 0.80

WEIGHT_ENTITY_MISSING = 0.40
WEIGHT_NAMED_INVENTION = 0.30
WEIGHT_CONTENT_ANCHORING = 0.20
WEIGHT_EPISTEMIC_OVERREACH = 0.10

_NAMED_INVENTION_PATTERNS = (
    re.compile(r"\b[A-Z]{2,4}\s+(?:Framework|Model|Method|System|Approach)\b"),
    re.compile(
        r"\b(?:Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|[0-9]+)[- ]"
        r"(?:Layer|Step|Part|Phase|Stage|Pillar|Point|Element|Tier)\s+"
        r"(?:Framework|Model|Method|System|Approach)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b[A-Z][a-z]+-[A-Z][a-z]+(?:-[A-Z][a-z]+)+\b"),
)


# ── SME audit thresholds (v2.2.1) ──────────────────────────────────────────
#
# severity "high" is now a HARD GATE. The top_level_answer computed property
# on AggregatedOutput falls back to deterministic_answer when any SMEAuditFlag
# has severity "high" (see schemas.py v2.2.1).
#
#   low:    1-2 missing entities. Legitimate paraphrasing.
#   medium: 3-4 missing entities. Visible-but-shipped.
#   high:   5+ missing entities. HARD GATE.

SME_AUDIT_LOW_THRESHOLD = 2
SME_AUDIT_MEDIUM_THRESHOLD = 4


# ── Scope-inflation detector (v2.2.2) ──────────────────────────────────────
#
# Today's Q29 smoke test showed the SME can confabulate management scope
# using only corpus-grounded entities. Entity-count alone misses this.
# This detector fires a high-severity flag when:
#   (a) the question contains scope keywords (management, team, lead)
#   (b) AND the SME answer contains a scope-inflation phrase
#
# Both conditions must be met to avoid false positives on legitimate
# questions that happen to mention teams (e.g. "What case studies
# involved your team?" — not a scope question about the owner's management).
#
# Narrow scope on purpose. Only catches management/team-scope inflation,
# which is the documented Q29 failure. Other forms of semantic drift
# (e.g. implying <owner> worked somewhere they didn't) would need their own
# detectors if they surface in practice.

_SCOPE_QUESTION_KEYWORDS = (
    "manage", "managing", "management", "manages", "manager",
    "team of", "leads a", "lead a", "leading", "leads the", "leadership",
    "director", "directing", "oversee", "overseeing", "oversees",
    "direct report", "direct reports",
    "how many researchers", "how many people",
)

_SCOPE_INFLATION_PATTERNS = (
    # Team-size claims
    re.compile(r"\b(?:a\s+)?large\s+(?:researcher\s+)?team\b", re.IGNORECASE),
    re.compile(r"\b(?:a\s+)?big\s+(?:researcher\s+)?team\b", re.IGNORECASE),
    re.compile(r"\bteam\s+of\s+(?:\d+|ten|eleven|twelve|many|multiple)\b", re.IGNORECASE),
    re.compile(r"\b(?:his|her|their|the)\s+researcher\s+team\b", re.IGNORECASE),

    # Direct management claims
    re.compile(r"\bmanages?\s+(?:a\s+)?(?:large|big|team|researcher)", re.IGNORECASE),
    re.compile(r"\bleads?\s+(?:a\s+)?(?:large|big|team|researcher)", re.IGNORECASE),
    re.compile(r"\bdirects?\s+(?:a\s+)?(?:large|big|team|researcher)", re.IGNORECASE),
    re.compile(r"\boversees?\s+(?:a\s+)?(?:team|group|researcher)", re.IGNORECASE),

    # Structural claims the corpus doesn't support
    re.compile(r"\bpipeline\s+from\s+intake\s+to\s+repository\b", re.IGNORECASE),
    re.compile(r"\bdirect\s+reports?\b", re.IGNORECASE),
    re.compile(r"\bhis\s+team\s+of\b", re.IGNORECASE),
    re.compile(r"\bher\s+team\s+of\b", re.IGNORECASE),
    re.compile(r"\btheir\s+team\s+of\b", re.IGNORECASE),
)


# ── Stopwords ──────────────────────────────────────────────────────────────

_GROUPING_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has",
    "have", "in", "into", "is", "it", "its", "of", "on", "or", "over", "per",
    "so", "that", "the", "their", "them", "there", "these", "this", "those",
    "to", "was", "were", "will", "with", "within", "across", "between",
    "analyzed", "analysis", "completed", "built", "used", "via", "using",
}


# ── Causation heuristics ───────────────────────────────────────────────────

_CAUSAL_MARKERS = (
    "caused", "led to", "resulted in", "because",
    "due to", "drove", "produced", "triggered",
)


# ── Persona order for deterministic tie-breaking ───────────────────────────

_PERSONA_ORDER = ("PM", "Designer", "Engineer")


@dataclass
class AggregatorInput:
    pm_output: AnswererOutput
    designer_output: AnswererOutput
    engineer_output: AnswererOutput
    pm_chunks: List[Chunk]
    designer_chunks: List[Chunk]
    engineer_chunks: List[Chunk]


class Aggregator:
    def __init__(
        self,
        thresholds: Optional[Dict[Persona, int]] = None,
        enable_sme: bool = True,
    ):
        self.thresholds = thresholds or THIN_RETRIEVAL_THRESHOLDS
        self.enable_sme = enable_sme
        self.sme = SMESynthesizer() if enable_sme else None

    def aggregate(self, inputs: AggregatorInput) -> AggregatedOutput:
        out = AggregatedOutput(question=inputs.pm_output.question)
        out.evidence_base = self._build_evidence_base(inputs)

        pm_claims, pm_dropped = self._anti_hallucination_pass(
            inputs.pm_output.primary_claims, Persona.PM, inputs.pm_chunks
        )
        designer_claims, designer_dropped = self._anti_hallucination_pass(
            inputs.designer_output.primary_claims, Persona.DESIGNER,
            inputs.designer_chunks
        )
        engineer_claims, engineer_dropped = self._anti_hallucination_pass(
            inputs.engineer_output.primary_claims, Persona.ENGINEER,
            inputs.engineer_chunks
        )
        out.dropped_claims = pm_dropped + designer_dropped + engineer_dropped

        out.claims_by_persona = {
            "PM": pm_claims,
            "Designer": designer_claims,
            "Engineer": engineer_claims,
        }
        out.epistemic_summary = {
            "PM": self._count_epistemic(
                pm_claims, inputs.pm_output.uncertainty,
            ),
            "Designer": self._count_epistemic(
                designer_claims, inputs.designer_output.uncertainty,
            ),
            "Engineer": self._count_epistemic(
                engineer_claims, inputs.engineer_output.uncertainty,
            ),
        }

        out.audit_trail.dropped_entities = [
            DroppedEntity(
                entity=dc.claim_text,
                reason=dc.drop_reason,
                asserting_persona=dc.persona,
            )
            for dc in out.dropped_claims
        ]

        out.divergence_metrics = self._compute_divergence_metrics(
            pm_claims, designer_claims, engineer_claims
        )

        if self._should_refuse(
            pm_claims, designer_claims, engineer_claims,
            out.divergence_metrics, out.dropped_claims,
        ):
            return self._handle_refusal_path(out, inputs)

        out.divergence_band = self._categorize_divergence_band(
            out.divergence_metrics, out.dropped_claims
        )

        out.synthesis_prose = self._build_synthesis_prose(
            out.claims_by_persona, out.divergence_band,
            out.divergence_metrics, out.dropped_claims,
            inputs,
        )

        out.deterministic_answer = self._build_deterministic_answer(
            out.claims_by_persona, out.divergence_band,
        )

        if self.enable_sme and self.sme is not None:
            self._run_sme_synthesis(out, inputs)

            # v2.2.1: audit pass may set sme_fallback_reason on high
            # severity. top_level_answer property then returns
            # deterministic_answer.
            if out.sme_fallback_reason is None and out.sme_answer.strip():
                self._sme_audit_pass(out, inputs)

        out.scoring_fields = ScoringFields()
        return out

    def _anti_hallucination_pass(
        self,
        claims: List[Claim],
        persona: Persona,
        persona_chunks: List[Chunk],
    ) -> Tuple[List[Claim], List[DroppedClaim]]:
        chunk_entities = extract_entities_from_chunks(persona_chunks)
        chunk_text_blob = " ".join(c.text for c in persona_chunks).lower()

        retained: List[Claim] = []
        dropped: List[DroppedClaim] = []

        for claim in claims:
            claim_entities = self._extract_claim_entities(claim.claim_text)
            claim.entities = claim_entities

            if self._is_causation_claim(claim.claim_text):
                if not self._causation_supported_in_chunks(chunk_text_blob):
                    dropped.append(DroppedClaim(
                        claim_text=claim.claim_text,
                        persona=persona,
                        drop_reason=DROP_UNSUPPORTED_CAUSATION,
                        chunks_checked=[c.chunk_id for c in persona_chunks],
                    ))
                    continue

            entity_ratio = self._signal_entity_missing_ratio(
                claim_entities, chunk_entities,
            )
            invention = self._signal_named_invention(claim.claim_text)
            anchoring = self._signal_content_anchoring(
                claim.claim_text, chunk_text_blob,
            )
            overreach = self._signal_epistemic_overreach(
                claim.epistemic_status, entity_ratio, anchoring,
            )

            fab_confidence = (
                WEIGHT_ENTITY_MISSING * entity_ratio
                + WEIGHT_NAMED_INVENTION * invention
                + WEIGHT_CONTENT_ANCHORING * (1.0 - anchoring)
                + WEIGHT_EPISTEMIC_OVERREACH * overreach
            )

            if invention >= 1.0:
                fab_confidence = max(fab_confidence, 0.85)

            if fab_confidence >= FABRICATION_DROP_THRESHOLD:
                dropped.append(DroppedClaim(
                    claim_text=claim.claim_text,
                    persona=persona,
                    drop_reason=DROP_FABRICATION_CONFIDENCE_EXCEEDED,
                    chunks_checked=[c.chunk_id for c in persona_chunks],
                    fabrication_confidence=round(fab_confidence, 3),
                    entity_missing_ratio=round(entity_ratio, 3),
                    named_invention_penalty=round(invention, 3),
                    content_anchoring=round(anchoring, 3),
                    epistemic_overreach=round(overreach, 3),
                ))
                continue

            retained.append(claim)

        return retained, dropped

    def _signal_entity_missing_ratio(
        self, claim_entities: Set[str], chunk_entities: Set[str],
    ) -> float:
        if not claim_entities:
            return 0.0
        missing = sum(1 for e in claim_entities if e not in chunk_entities)
        return missing / len(claim_entities)

    def _signal_named_invention(self, claim_text: str) -> float:
        for pattern in _NAMED_INVENTION_PATTERNS:
            if pattern.search(claim_text):
                return 1.0
        return 0.0

    def _signal_content_anchoring(
        self, claim_text: str, chunk_text_blob: str,
    ) -> float:
        lowered = claim_text.lower()
        words = re.findall(r"[a-z]+", lowered)
        content = [
            w for w in words
            if len(w) >= 4 and w not in _GROUPING_STOPWORDS
        ]
        if not content:
            return 0.5
        matching = sum(1 for w in content if w in chunk_text_blob)
        return matching / len(content)

    def _signal_epistemic_overreach(
        self,
        epistemic_status: EpistemicStatus,
        entity_ratio: float,
        anchoring: float,
    ) -> float:
        weak_grounding = entity_ratio > 0.5 or anchoring < 0.3
        if not weak_grounding:
            return 0.0
        if epistemic_status == EpistemicStatus.FACT:
            return 1.0
        if epistemic_status == EpistemicStatus.INFERENCE:
            return 0.5
        return 0.0

    def _is_causation_claim(self, text: str) -> bool:
        lowered = " " + text.lower() + " "
        return any(" " + m + " " in lowered for m in _CAUSAL_MARKERS)

    def _causation_supported_in_chunks(self, chunk_blob: str) -> bool:
        return any(m in chunk_blob for m in _CAUSAL_MARKERS)

    def _extract_claim_entities(self, text: str) -> Set[str]:
        pattern = re.compile(
            r'\b(?:[A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+)*|[A-Z]{2,})\b'
        )
        return set(pattern.findall(text))

    def _should_refuse(
        self,
        pm_claims: List[Claim],
        designer_claims: List[Claim],
        engineer_claims: List[Claim],
        metrics: DivergenceMetrics,
        dropped: List[DroppedClaim],
    ) -> bool:
        _ = metrics, dropped

        def persona_supported(claims: List[Claim]) -> bool:
            for c in claims:
                if not c.chunk_ids:
                    continue
                if c.epistemic_status in (
                    EpistemicStatus.FACT, EpistemicStatus.INFERENCE,
                ):
                    return True
            return False

        return not (
            persona_supported(pm_claims)
            or persona_supported(designer_claims)
            or persona_supported(engineer_claims)
        )

    def _handle_refusal_path(
        self, out: AggregatedOutput, inputs: AggregatorInput,
    ) -> AggregatedOutput:
        out.refusal_triggered = True
        out.divergence_band = BAND_REFUSAL
        out.refusal_reason = (
            "No persona produced chunk-grounded fact or inference "
            "claims after anti-hallucination pass."
        )

        pm_stats = inputs.pm_output.retrieval_stats
        ds_stats = inputs.designer_output.retrieval_stats
        eng_stats = inputs.engineer_output.retrieval_stats

        out.deterministic_answer = (
            "The corpus does not contain evidence to answer this question "
            "at the scope asked."
        )

        out.synthesis_prose = (
            "The corpus does not contain evidence to answer this question.\n\n"
            "What was retrieved:\n"
            f"- PM: {pm_stats.chunk_count} chunks, "
            f"top source {pm_stats.top_source or 'none'}\n"
            f"- Designer: {ds_stats.chunk_count} chunks, "
            f"top source {ds_stats.top_source or 'none'}\n"
            f"- Engineer: {eng_stats.chunk_count} chunks, "
            f"top source {eng_stats.top_source or 'none'}\n\n"
            f"Claims dropped during anti-hallucination pass: "
            f"{len(out.dropped_claims)}."
        )

        if self.enable_sme and self.sme is not None:
            self._run_sme_synthesis(out, inputs)
            if out.sme_fallback_reason is None and out.sme_answer.strip():
                self._sme_audit_pass(out, inputs)

        return out

    def _run_sme_synthesis(
        self, out: AggregatedOutput, inputs: AggregatorInput,
    ) -> None:
        pm_claims = out.claims_by_persona.get("PM", [])
        designer_claims = out.claims_by_persona.get("Designer", [])
        engineer_claims = out.claims_by_persona.get("Engineer", [])

        try:
            result = self.sme.synthesize(
                question=out.question,
                pm_output=inputs.pm_output,
                designer_output=inputs.designer_output,
                engineer_output=inputs.engineer_output,
                pm_claims_surviving=pm_claims,
                designer_claims_surviving=designer_claims,
                engineer_claims_surviving=engineer_claims,
                divergence_metrics=out.divergence_metrics,
                divergence_band=out.divergence_band,
                dropped_count=len(out.dropped_claims),
            )
            out.sme_answer = result.answer
            out.sme_fallback_reason = result.fallback_reason
            out.sme_elapsed_seconds = round(result.elapsed_seconds, 2)
        except Exception as e:
            print(f"[Aggregator] SME synthesis raised unexpected exception: {e}")
            out.sme_answer = ""
            out.sme_fallback_reason = "call_failed"
            out.sme_elapsed_seconds = 0.0

    def _sme_audit_pass(
        self, out: AggregatedOutput, inputs: AggregatorInput,
    ) -> None:
        """v2.2.1: anti-hallucination on the SME output with hard gate
        on high severity.

        Low and medium flags: visible in widget, SME answer still ships.
        High flags: set sme_fallback_reason = FALLBACK_AUDIT_REJECTED.
        The top_level_answer computed property on AggregatedOutput then
        returns deterministic_answer instead of sme_answer.

        sme_answer is preserved on the object for diagnostic visibility.

        v2.2.2 adds scope-inflation check as a second high-severity
        trigger. Catches Q29-shape confabulation (management scope
        claimed from corpus-grounded entities).
        """
        if not out.sme_answer.strip():
            return

        union_chunks = (
            inputs.pm_chunks + inputs.designer_chunks + inputs.engineer_chunks
        )
        chunk_entities = extract_entities_from_chunks(union_chunks)

        persona_claim_entities: Set[str] = set()
        for claims in out.claims_by_persona.values():
            for c in claims:
                persona_claim_entities |= c.entities or self._extract_claim_entities(c.claim_text)

        grounded_entities = chunk_entities | persona_claim_entities

        sme_entities = self._extract_claim_entities(out.sme_answer)
        flagged = [e for e in sme_entities if e not in grounded_entities]

        prompt_terms = {
            "PM", "Designer", "Engineer", "BGE", "MiniLM", "Qwen",
            "UX", "UXR", "Senior", "Research", "Researcher",
        }
        flagged = [e for e in flagged if e not in prompt_terms and len(e) > 2]

        # Entity-count based severity (v2.2.1 behavior, unchanged).
        if flagged:
            n = len(flagged)
            if n <= SME_AUDIT_LOW_THRESHOLD:
                severity = "low"
                reason = (
                    f"{n} entit{'y' if n == 1 else 'ies'} in SME answer "
                    "not directly present in persona outputs. "
                    "Typical of legitimate paraphrasing."
                )
            elif n <= SME_AUDIT_MEDIUM_THRESHOLD:
                severity = "medium"
                reason = (
                    f"{n} entities in SME answer not directly present in "
                    "persona outputs. Worth reader attention."
                )
            else:
                severity = "high"
                reason = (
                    f"{n} entities in SME answer not present in persona "
                    "outputs. Possible over-synthesis or invention. "
                    "SME answer rejected, falling back to deterministic answer."
                )

            out.sme_audit_flags.append(SMEAuditFlag(
                claim_span=out.sme_answer[:240] + ("..." if len(out.sme_answer) > 240 else ""),
                flagged_entities=flagged,
                reason=reason,
                severity=severity,
            ))

            if severity in SME_AUDIT_BLOCKING_SEVERITIES:
                out.sme_fallback_reason = FALLBACK_AUDIT_REJECTED
                print(
                    f"[Aggregator] SME audit gate fired (entity-count): "
                    f"severity={severity}, flagged_entities={flagged}. "
                    f"Falling back to deterministic_answer."
                )

        # v2.2.2: scope-inflation check. Independent of entity count.
        # Fires only when question is a scope question AND the SME
        # answer contains a scope-inflation phrase.
        self._scope_inflation_check(out)

    def _scope_inflation_check(self, out: AggregatedOutput) -> None:
        """v2.2.2: detect scope-inflation confabulation.

        Trigger conditions (both must be true):
          1. Question contains a scope keyword (manage, team, lead,
             director, oversee, direct report, or similar).
          2. SME answer contains a scope-inflation phrase (large team,
             leads a team, pipeline from intake to repository, etc).

        When both are true, add a high-severity audit flag with the
        matched phrase surfaced as the flagged entity. The existing
        hard gate in sme_fallback_reason then routes top_level_answer
        to deterministic_answer.

        This is a narrow detector. It catches the Q29-shape failure
        (management scope confabulated from corpus-grounded entities).
        It does NOT attempt general semantic-distance measurement —
        that's a separate research problem parked for later.
        """
        question_lower = out.question.lower()
        is_scope_question = any(
            kw in question_lower for kw in _SCOPE_QUESTION_KEYWORDS
        )
        if not is_scope_question:
            return

        matched_phrases: List[str] = []
        for pattern in _SCOPE_INFLATION_PATTERNS:
            m = pattern.search(out.sme_answer)
            if m:
                matched_phrases.append(m.group(0))

        if not matched_phrases:
            return

        # Deduplicate in case multiple patterns match the same span.
        unique_phrases = list(dict.fromkeys(matched_phrases))

        reason = (
            f"Scope-inflation phrase detected in SME answer: "
            f"{', '.join(repr(p) for p in unique_phrases)}. "
            "The question asks about management or team scope. The SME "
            "answer asserts scope that the persona outputs do not "
            "support. SME answer rejected, falling back to deterministic "
            "answer."
        )

        out.sme_audit_flags.append(SMEAuditFlag(
            claim_span=out.sme_answer[:240] + ("..." if len(out.sme_answer) > 240 else ""),
            flagged_entities=unique_phrases,
            reason=reason,
            severity="high",
        ))

        out.sme_fallback_reason = FALLBACK_AUDIT_REJECTED
        print(
            f"[Aggregator] SME audit gate fired (scope-inflation): "
            f"phrases={unique_phrases}. Falling back to deterministic_answer."
        )

    def _compute_divergence_metrics(
        self,
        pm_claims: List[Claim],
        designer_claims: List[Claim],
        engineer_claims: List[Claim],
    ) -> DivergenceMetrics:
        def entity_set(claims: List[Claim]) -> Set[str]:
            s: Set[str] = set()
            for c in claims:
                s |= (
                    c.entities
                    if c.entities
                    else self._extract_claim_entities(c.claim_text)
                )
            return s

        def claim_signatures(claims: List[Claim]) -> Set[str]:
            return {
                self._claim_overlap_signature(c.claim_text) for c in claims
            }

        pm_e = entity_set(pm_claims)
        des_e = entity_set(designer_claims)
        eng_e = entity_set(engineer_claims)

        pm_s = claim_signatures(pm_claims)
        des_s = claim_signatures(designer_claims)
        eng_s = claim_signatures(engineer_claims)

        jaccard = (
            self._jaccard_distance(pm_e, des_e)
            + self._jaccard_distance(pm_e, eng_e)
            + self._jaccard_distance(des_e, eng_e)
        ) / 3.0

        overlap = (
            self._overlap_ratio(pm_s, des_s)
            + self._overlap_ratio(pm_s, eng_s)
            + self._overlap_ratio(des_s, eng_s)
        ) / 3.0

        watch: Optional[str] = None
        if jaccard < JACCARD_LOW and overlap > OVERLAP_HIGH:
            watch = "low_divergence_red_flag"
        elif jaccard > JACCARD_HIGH and overlap < OVERLAP_LOW:
            watch = "high_divergence_incoherence"

        return DivergenceMetrics(
            jaccard_distance=round(jaccard, 3),
            claim_overlap=round(overlap, 3),
            watch_flag=watch,
        )

    @staticmethod
    def _jaccard_distance(a: Set[str], b: Set[str]) -> float:
        if not a and not b:
            return 0.0
        union = len(a | b)
        if union == 0:
            return 0.0
        return 1.0 - (len(a & b) / union)

    @staticmethod
    def _overlap_ratio(a: Set[str], b: Set[str]) -> float:
        if not a or not b:
            return 0.0
        return len(a & b) / max(len(a), len(b))

    def _claim_overlap_signature(self, text: str) -> str:
        lowered = text.lower()
        numbers = sorted({
            n.replace(",", "")
            for n in re.findall(r"\b\d[\d,]*\b", lowered)
        })
        words = re.findall(r"[a-z]+", lowered)
        content = [
            w for w in words
            if len(w) >= 3 and w not in _GROUPING_STOPWORDS
        ]
        top_keywords = sorted(
            [w for w, _ in Counter(content).most_common(4)]
        )
        if numbers:
            return (
                "N:" + "|".join(numbers)
                + ":K:" + "|".join(top_keywords[:2])
            )
        return "K:" + "|".join(top_keywords)

    def _categorize_divergence_band(
        self,
        metrics: DivergenceMetrics,
        dropped: List[DroppedClaim],
    ) -> str:
        if dropped and metrics.watch_flag == "low_divergence_red_flag":
            return BAND_RED_FLAG

        if not dropped and metrics.watch_flag == "low_divergence_red_flag":
            return BAND_CONVERGED

        if (
            JACCARD_LOW <= metrics.jaccard_distance < 0.6
            and metrics.claim_overlap >= 0.2
        ):
            return BAND_PRODUCTIVE

        return BAND_EXPECTED

    def _build_deterministic_answer(
        self,
        claims_by_persona: Dict[str, List[Claim]],
        band: str,
    ) -> str:
        if band == BAND_CONVERGED:
            return self._build_deterministic_answer_converged(claims_by_persona)
        if band == BAND_PRODUCTIVE:
            return self._build_deterministic_answer_productive(claims_by_persona)
        if band == BAND_RED_FLAG:
            return self._build_deterministic_answer_red_flag(claims_by_persona)
        return self._build_deterministic_answer_expected(claims_by_persona)

    def _build_deterministic_answer_converged(
        self, claims_by_persona: Dict[str, List[Claim]],
    ) -> str:
        pm_claims = claims_by_persona.get("PM", [])
        if pm_claims:
            return self._normalize_claim_text(pm_claims[0].claim_text)
        for persona_name in ("Designer", "Engineer"):
            claims = claims_by_persona.get(persona_name, [])
            if claims:
                return self._normalize_claim_text(claims[0].claim_text)
        return (
            "The corpus does not contain evidence to answer this question "
            "at the scope asked."
        )

    def _build_deterministic_answer_productive(
        self, claims_by_persona: Dict[str, List[Claim]],
    ) -> str:
        top = self._pick_top_claim(claims_by_persona)
        if top is None:
            return (
                "The corpus does not contain evidence to answer this "
                "question at the scope asked."
            )
        return self._normalize_claim_text(top.claim_text)

    def _build_deterministic_answer_expected(
        self, claims_by_persona: Dict[str, List[Claim]],
    ) -> str:
        top = self._pick_top_claim(claims_by_persona)
        if top is None:
            return (
                "The corpus does not contain evidence to answer this "
                "question at the scope asked."
            )
        primary = self._normalize_claim_text(top.claim_text)
        frame = (
            "Corpus support for this answer is partial. Expand to see "
            "per-persona detail and any adjacent findings."
        )
        return f"{primary} {frame}"

    def _build_deterministic_answer_red_flag(
        self, claims_by_persona: Dict[str, List[Claim]],
    ) -> str:
        top = self._pick_top_claim(claims_by_persona)
        if top is None:
            return (
                "The corpus does not contain evidence to answer this "
                "question at the scope asked."
            )
        primary = self._normalize_claim_text(top.claim_text)
        frame = (
            "The three retrieval personas produced meaningfully different "
            "framings on this question. Treat the answer as partial and "
            "expand to see the surviving claims in full."
        )
        return f"{primary} {frame}"

    def _pick_top_claim(
        self, claims_by_persona: Dict[str, List[Claim]],
    ) -> Optional[Claim]:
        best: Optional[Tuple[int, int, int, Claim]] = None
        for persona_idx, persona_name in enumerate(_PERSONA_ORDER):
            claims = claims_by_persona.get(persona_name, [])
            for claim_idx, claim in enumerate(claims):
                chunk_count = len(claim.chunk_ids)
                key = (-chunk_count, persona_idx, claim_idx, claim)
                if best is None or key < best:
                    best = key
        return best[3] if best is not None else None

    @staticmethod
    def _normalize_claim_text(text: str) -> str:
        cleaned = text.strip()
        cleaned = re.sub(
            r"\s*\[(fact|inference|hypothesis|assumption|unknown)\]\s*$",
            "", cleaned, flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\s*\[chunks?:[^\]]*\]\s*$", "", cleaned)
        cleaned = re.sub(r"\s*\[chunk_id:[^\]]*\]", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned and cleaned[-1] not in ".!?":
            cleaned += "."
        return cleaned

    def _build_synthesis_prose(
        self,
        claims_by_persona: Dict[str, List[Claim]],
        band: str,
        metrics: DivergenceMetrics,
        dropped: List[DroppedClaim],
        inputs: AggregatorInput,
    ) -> str:
        if band == BAND_CONVERGED:
            return self._build_converged_voice(
                claims_by_persona, metrics, inputs,
            )
        if band == BAND_PRODUCTIVE:
            return self._build_productive_voice(
                claims_by_persona, metrics, dropped, inputs,
            )
        if band == BAND_RED_FLAG:
            return self._build_red_flag_voice(
                claims_by_persona, metrics, dropped,
            )
        return self._build_expected_voice(
            claims_by_persona, metrics, dropped,
        )

    def _build_converged_voice(
        self,
        claims_by_persona: Dict[str, List[Claim]],
        metrics: DivergenceMetrics,
        inputs: AggregatorInput,
    ) -> str:
        lines: List[str] = [
            "Three retrieval paths converged on this finding. "
            "PM (BGE base + 1-hop graph), Designer (MiniLM only), "
            "and Engineer (graph primary + BGE base) each surfaced "
            "the same claim from their own retrieval strategy and "
            "source preferences. Convergence across methodologies "
            "strengthens the grounding.",
            "",
        ]

        all_claims = []
        for persona_name in ("PM", "Designer", "Engineer"):
            for c in claims_by_persona.get(persona_name, []):
                all_claims.append((persona_name, c))

        if not all_claims:
            return self._build_expected_voice(claims_by_persona, metrics, [])

        shared_claim = None
        pm_claims = claims_by_persona.get("PM", [])
        if pm_claims:
            shared_claim = pm_claims[0]
        else:
            shared_claim = all_claims[0][1]

        all_chunks: List[str] = []
        for persona_name, c in all_claims:
            for cid in c.chunk_ids:
                if cid not in all_chunks:
                    all_chunks.append(cid)

        lines.append("Shared finding:")
        lines.append(
            f"  - {shared_claim.claim_text} "
            f"[{shared_claim.epistemic_status.value}] "
            f"[corroborated by all three personas] "
            f"[chunks: {', '.join(all_chunks) if all_chunks else 'none'}]"
        )

        extras_by_persona: Dict[str, List[Claim]] = {}
        for persona_name in ("PM", "Designer", "Engineer"):
            persona_claims = claims_by_persona.get(persona_name, [])
            if len(persona_claims) > 1:
                extras_by_persona[persona_name] = persona_claims[1:]

        if extras_by_persona:
            lines.append("")
            lines.append("Persona-specific detail beyond the shared claim:")
            for persona_name, extras in extras_by_persona.items():
                lines.append(f"{persona_name}:")
                for c in extras:
                    chunks_str = (
                        ", ".join(c.chunk_ids) if c.chunk_ids else "no chunks"
                    )
                    lines.append(
                        f"  - {c.claim_text} "
                        f"[{persona_name}: {c.epistemic_status.value}] "
                        f"[chunks: {chunks_str}]"
                    )

        return "\n".join(lines)

    def _build_productive_voice(
        self,
        claims_by_persona: Dict[str, List[Claim]],
        metrics: DivergenceMetrics,
        dropped: List[DroppedClaim],
        inputs: AggregatorInput,
    ) -> str:
        lines: List[str] = [
            "PM, Designer, and Engineer surfaced overlapping but "
            "distinct framings of this question. The divergence "
            "reflects three retrieval lenses on the same corpus. "
            "All framings are corpus-supported.",
            "",
        ]

        top_sources = {
            "PM": inputs.pm_output.retrieval_stats.top_source,
            "Designer": inputs.designer_output.retrieval_stats.top_source,
            "Engineer": inputs.engineer_output.retrieval_stats.top_source,
        }

        for persona_name in ("PM", "Designer", "Engineer"):
            claims = claims_by_persona.get(persona_name, [])
            if not claims:
                lines.append(
                    f"{persona_name} produced no chunk-grounded claims "
                    f"after anti-hallucination."
                )
                lines.append("")
                continue

            top_source = top_sources.get(persona_name) or "unknown source"
            lines.append(
                f"{persona_name}, drawing primarily from {top_source}, "
                f"frames this as:"
            )
            for c in claims:
                chunks_str = (
                    ", ".join(c.chunk_ids) if c.chunk_ids else "no chunks"
                )
                lines.append(
                    f"  - {c.claim_text} "
                    f"[{persona_name}: {c.epistemic_status.value}] "
                    f"[chunks: {chunks_str}]"
                )
            lines.append("")

        if dropped:
            lines.append(
                f"Dropped during anti-hallucination pass: {len(dropped)} "
                f"claim(s). See dropped_claims in audit trail for details."
            )
            lines.append("")

        if metrics.watch_flag:
            lines.append(
                f"Divergence watch: {metrics.watch_flag} "
                f"(jaccard={metrics.jaccard_distance}, "
                f"overlap={metrics.claim_overlap})."
            )

        return "\n".join(lines).rstrip()

    def _build_expected_voice(
        self,
        claims_by_persona: Dict[str, List[Claim]],
        metrics: DivergenceMetrics,
        dropped: List[DroppedClaim],
    ) -> str:
        lines: List[str] = []

        for persona_name in ("PM", "Designer", "Engineer"):
            claims = claims_by_persona.get(persona_name, [])
            if not claims:
                lines.append(
                    f"{persona_name}: no chunk-grounded claims after "
                    f"anti-hallucination pass."
                )
                continue
            lines.append(f"{persona_name}:")
            for c in claims:
                chunks_str = (
                    ", ".join(c.chunk_ids) if c.chunk_ids else "no chunks"
                )
                lines.append(
                    f"  - {c.claim_text} "
                    f"[{persona_name}: {c.epistemic_status.value}] "
                    f"[chunks: {chunks_str}]"
                )

        if dropped:
            lines.append("")
            lines.append(
                f"Dropped during anti-hallucination pass: {len(dropped)} "
                f"claim(s). See dropped_claims in audit trail for details."
            )

        if metrics.watch_flag:
            lines.append("")
            lines.append(
                f"Divergence watch: {metrics.watch_flag} "
                f"(jaccard={metrics.jaccard_distance}, "
                f"overlap={metrics.claim_overlap})."
            )

        return "\n".join(lines)

    def _build_red_flag_voice(
        self,
        claims_by_persona: Dict[str, List[Claim]],
        metrics: DivergenceMetrics,
        dropped: List[DroppedClaim],
    ) -> str:
        lines: List[str] = [
            f"Anti-hallucination dropped {len(dropped)} claim(s) as "
            "unsupported by the retrieved chunks. The surviving "
            "synthesis preserves only chunk-grounded claims with "
            "per-persona attribution.",
            "",
        ]

        for persona_name in ("PM", "Designer", "Engineer"):
            claims = claims_by_persona.get(persona_name, [])
            if not claims:
                lines.append(
                    f"{persona_name}: no claims survived "
                    f"anti-hallucination."
                )
                continue
            lines.append(f"{persona_name}:")
            for c in claims:
                chunks_str = (
                    ", ".join(c.chunk_ids) if c.chunk_ids else "no chunks"
                )
                lines.append(
                    f"  - {c.claim_text} "
                    f"[{persona_name}: {c.epistemic_status.value}] "
                    f"[chunks: {chunks_str}]"
                )

        lines.append("")
        lines.append(
            "See dropped_claims in audit trail for which claims were "
            "dropped and why."
        )

        if metrics.watch_flag:
            lines.append("")
            lines.append(
                f"Divergence watch: {metrics.watch_flag} "
                f"(jaccard={metrics.jaccard_distance}, "
                f"overlap={metrics.claim_overlap})."
            )

        return "\n".join(lines)

    def _build_evidence_base(self, inputs: AggregatorInput) -> EvidenceBase:
        union_ids: Set[str] = set()
        for c in (
            inputs.pm_chunks + inputs.designer_chunks + inputs.engineer_chunks
        ):
            union_ids.add(c.chunk_id)
        return EvidenceBase(
            pm_chunk_count=len(inputs.pm_chunks),
            pm_top_case=inputs.pm_output.retrieval_stats.top_source,
            designer_chunk_count=len(inputs.designer_chunks),
            designer_top_case=inputs.designer_output.retrieval_stats.top_source,
            engineer_chunk_count=len(inputs.engineer_chunks),
            engineer_top_case=inputs.engineer_output.retrieval_stats.top_source,
            union_chunk_count=len(union_ids),
        )

    def _count_epistemic(
        self,
        claims: List[Claim],
        uncertainty: Optional[List[str]] = None,
    ) -> EpistemicStatusCounts:
        counts = EpistemicStatusCounts()
        for claim in claims:
            s = claim.epistemic_status
            if s == EpistemicStatus.FACT:
                counts.facts += 1
            elif s == EpistemicStatus.INFERENCE:
                counts.inferences += 1
            elif s == EpistemicStatus.HYPOTHESIS:
                counts.hypotheses += 1
            elif s == EpistemicStatus.UNKNOWN:
                counts.unknowns += 1
        if uncertainty:
            counts.unknowns += len(uncertainty)
        return counts
