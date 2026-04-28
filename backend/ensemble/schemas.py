"""
ensemble/schemas.py

Data contracts for the agent2agent system. Answerers emit AnswererOutput.
The Aggregator consumes three of those and emits AggregatedOutput.

v2 (April 23, 2026): Aggregator output redesigned per Aggregator_Rubric_Spec_v2.
  - UXR as Aggregator, not fourth Answerer
  - Divergence preserved, not collapsed
  - synthesis_prose replaces aggregated_answer
  - claims_by_persona replaces flat retained list
  - DivergenceMetrics captures jaccard + claim-overlap + watch flag
  - DroppedClaim replaces DroppedEntity for anti-hallucination drops
  - refusal_triggered / refusal_reason for negative-case path
  - Legacy types (ConfidenceBreakdown, DroppedEntity, SingleSourceFlag,
    Disagreement) kept for AuditTrail compatibility and any v1 consumers
    that still import them.

v2.1 UX (April 23, 2026): widget UX fix.
  - top_level_answer added to AggregatedOutput. One to three sentences,
    declarative, the single answer the widget main bubble renders.
    synthesis_prose stays as the per-persona expandable detail. See
    aggregator.py for the per-band population rule.

v2.2 SME (April 23, 2026): UXR SME synthesis layer.
  - SME layer added above the three-persona array. Fifth LLM call that
    reads persona outputs and produces the accountable answer in the owner's
    voice.
  - New fields: deterministic_answer (renamed from v2.1's top_level_answer
    stored value), sme_answer, sme_audit_flags, sme_fallback_reason,
    sme_elapsed_seconds.
  - top_level_answer becomes a computed property: returns sme_answer
    when the SME call succeeded, falls back to deterministic_answer
    otherwise. Widget contract unchanged.

v2.2.1 SME audit gate (April 23, 2026): hard gate on high-severity flags.
  - First SME smoke test (Q29) revealed that audit flags alone are not
    enough. The SME confabulated "<owner> manages a large researcher team"
    with 5 missing entities, audit fired high-severity, but the computed
    top_level_answer still returned the bad SME output.
  - Fix: top_level_answer falls back to deterministic_answer whenever
    sme_audit_flags contains any entry with severity == "high".
  - Medium severity stays visible-but-shipped for v2.2.1. Low severity
    unchanged.
  - FALLBACK_AUDIT_REJECTED added as a new sme_fallback_reason code so
    the widget can indicate why the fallback fired.
  - sme_answer is preserved on the object for diagnostic visibility even
    when rejected. Widget can render it in an expandable diagnostic
    section instead of the main bubble.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Literal, Dict, Any, Set
from enum import Enum
import json


class Persona(str, Enum):
    PM = "PM"
    DESIGNER = "Designer"
    ENGINEER = "Engineer"


class EpistemicStatus(str, Enum):
    FACT = "fact"
    INFERENCE = "inference"
    ASSUMPTION = "assumption"
    HYPOTHESIS = "hypothesis"
    UNKNOWN = "unknown"


@dataclass
class Claim:
    """A single claim from an Answerer. One line, one epistemic label, one chunk set.

    v2: adds `entities` field populated by the Aggregator's anti-hallucination
    pass so the divergence metric can read entity sets without re-extracting.
    """
    claim_text: str
    epistemic_status: EpistemicStatus
    chunk_ids: List[str] = field(default_factory=list)
    named_entities: List[str] = field(default_factory=list)
    entities: Set[str] = field(default_factory=set)  # v2


@dataclass
class Coverage:
    addressed: List[str] = field(default_factory=list)
    not_addressed: List[str] = field(default_factory=list)


@dataclass
class RetrievalStats:
    chunk_count: int = 0
    top_source: str = ""


@dataclass
class AnswererOutput:
    """What a single Answerer returns. Matches Stage 1 spec output block."""
    persona: Persona
    question: str
    primary_claims: List[Claim] = field(default_factory=list)
    coverage: Coverage = field(default_factory=Coverage)
    uncertainty: List[str] = field(default_factory=list)
    retrieval_stats: RetrievalStats = field(default_factory=RetrievalStats)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)


# ── v2 types ──────────────────────────────────────────────────────────────

@dataclass
class DroppedClaim:
    """v2: replaces v1 DroppedEntity semantics. Logs the full claim that was
    dropped plus which of the five spec drop reasons fired.

    v2.1 (post-Q12-false-positive smoke test): adds fabrication confidence
    score and the four component subscores.
    """
    claim_text: str
    persona: Persona
    drop_reason: str
    chunks_checked: List[str] = field(default_factory=list)

    fabrication_confidence: Optional[float] = None
    entity_missing_ratio: Optional[float] = None
    named_invention_penalty: Optional[float] = None
    content_anchoring: Optional[float] = None
    epistemic_overreach: Optional[float] = None


@dataclass
class DivergenceMetrics:
    """v2: per-question divergence signal."""
    jaccard_distance: float = 0.0
    claim_overlap: float = 0.0
    watch_flag: Optional[str] = None


# ── v2.2 SME types ────────────────────────────────────────────────────────

@dataclass
class SMEAuditFlag:
    """v2.2: anti-hallucination flag on SME output.

    v2.2.1: severity "high" now triggers hard fallback via the
    top_level_answer computed property on AggregatedOutput. Medium and
    low remain visible-but-shipped.

    severity:
      - "low": 1-2 low-grounding entities. Typical paraphrasing.
      - "medium": 3-4 entities missing, or one plausibly adjacent
        entity. Visible in widget but does not drop.
      - "high": 5+ entities missing, or clear invention pattern.
        HARD GATE: triggers fallback to deterministic_answer. Would
        have been dropped at persona layer under normal circumstances.
    """
    claim_span: str
    flagged_entities: List[str]
    reason: str
    severity: str


# ── v2.2 SME fallback reason codes ────────────────────────────────────────
#
# Stored as strings on AggregatedOutput.sme_fallback_reason. None means
# the SME output shipped cleanly. Any non-None value means top_level_answer
# returns deterministic_answer instead.

FALLBACK_CALL_FAILED = "call_failed"
FALLBACK_EMPTY_OUTPUT = "empty_output"
FALLBACK_MALFORMED = "malformed"
FALLBACK_AUDIT_REJECTED = "audit_rejected"   # v2.2.1: high-severity gate fired


# Severity levels that trigger hard fallback (v2.2.1).
SME_AUDIT_BLOCKING_SEVERITIES = {"high"}


# ── v1 legacy types (kept for AuditTrail and any v1 import paths) ─────────

@dataclass
class ConfidenceBreakdown:
    """v1 legacy: no longer populated by the v2 Aggregator."""
    high_confidence_count: int = 0
    medium_confidence_count: int = 0
    single_source_count: int = 0
    dropped_count: int = 0


@dataclass
class Disagreement:
    """v1 legacy: replaced in v2 by claims_by_persona + divergence_band."""
    topic: str
    pm_view: Optional[str] = None
    designer_view: Optional[str] = None
    engineer_view: Optional[str] = None
    pm_chunks: List[str] = field(default_factory=list)
    designer_chunks: List[str] = field(default_factory=list)
    engineer_chunks: List[str] = field(default_factory=list)
    resolution: Literal["surfaced", "silently_resolved", "dropped"] = "surfaced"


@dataclass
class EvidenceBase:
    pm_chunk_count: int = 0
    pm_top_case: str = ""
    designer_chunk_count: int = 0
    designer_top_case: str = ""
    engineer_chunk_count: int = 0
    engineer_top_case: str = ""
    union_chunk_count: int = 0


@dataclass
class EpistemicStatusCounts:
    facts: int = 0
    inferences: int = 0
    hypotheses: int = 0
    unknowns: int = 0


@dataclass
class DroppedEntity:
    """v1 legacy: AuditTrail still uses this."""
    entity: str
    reason: str
    asserting_persona: Persona


@dataclass
class SingleSourceFlag:
    """v1 legacy."""
    claim: str
    persona: Persona
    chunk_id: str


@dataclass
class AuditTrail:
    dropped_entities: List[DroppedEntity] = field(default_factory=list)
    single_source_flags: List[SingleSourceFlag] = field(default_factory=list)
    thin_retrieval_triggered: bool = False


@dataclass
class ScoringFields:
    """Populated by reviewer, not the Aggregator itself."""
    factual_accuracy: Optional[int] = None
    epistemic_hygiene: Optional[int] = None
    coverage: Optional[int] = None
    grounded_attribution: Optional[int] = None
    anti_hallucination: Optional[int] = None
    contradiction_surfacing: Optional[int] = None
    total: Optional[int] = None

    def compute_total(self) -> Optional[int]:
        dims = [
            self.factual_accuracy,
            self.epistemic_hygiene,
            self.coverage,
            self.grounded_attribution,
            self.anti_hallucination,
            self.contradiction_surfacing,
        ]
        if any(d is None for d in dims):
            return None
        self.total = sum(dims)
        return self.total


# ── v2 AggregatedOutput ───────────────────────────────────────────────────

@dataclass
class AggregatedOutput:
    """v2: divergence-preserving synthesis output.

    v2.2 SME (April 23, 2026):
      - deterministic_answer: v2.1-style selection, used as fallback.
      - sme_answer: SME synthesis output, populated by the fifth LLM
        call when it succeeds.
      - sme_audit_flags: anti-hallucination flags on the SME output.
      - sme_fallback_reason: None if SME output shipped, otherwise one
        of the FALLBACK_* constants.
      - sme_elapsed_seconds: wall time for the SME call.
      - top_level_answer: computed property, returns sme_answer if
        shipped, else deterministic_answer.

    v2.2.1 (April 23, 2026, same day): hard audit gate.
      - top_level_answer now also falls back when sme_audit_flags
        contains a "high" severity entry.
      - sme_fallback_reason is set to "audit_rejected" in that case by
        aggregate() after the audit pass runs.
      - sme_answer is preserved on the object even when rejected, so
        the widget can show it in a diagnostic expandable section.
    """
    question: str
    deterministic_answer: str = ""
    sme_answer: str = ""
    sme_audit_flags: List["SMEAuditFlag"] = field(default_factory=list)
    sme_fallback_reason: Optional[str] = None
    sme_elapsed_seconds: float = 0.0
    synthesis_prose: str = ""
    claims_by_persona: Dict[str, List[Claim]] = field(default_factory=dict)
    divergence_band: str = "expected"
    divergence_metrics: DivergenceMetrics = field(default_factory=DivergenceMetrics)
    epistemic_summary: Dict[str, EpistemicStatusCounts] = field(default_factory=dict)
    dropped_claims: List[DroppedClaim] = field(default_factory=list)
    refusal_triggered: bool = False
    refusal_reason: Optional[str] = None
    evidence_base: EvidenceBase = field(default_factory=EvidenceBase)
    audit_trail: AuditTrail = field(default_factory=AuditTrail)
    scoring_fields: ScoringFields = field(default_factory=ScoringFields)
    divergence_preservation_score: Optional[int] = None

    def has_blocking_audit_flag(self) -> bool:
        """v2.2.1: return True if any audit flag has a blocking severity.

        Used by the top_level_answer computed property to gate the SME
        answer. Also available to aggregator.py and widget code that
        want to know before calling the property.
        """
        for flag in self.sme_audit_flags:
            if flag.severity in SME_AUDIT_BLOCKING_SEVERITIES:
                return True
        return False

    @property
    def top_level_answer(self) -> str:
        """v2.2.1: computed property with three gates.

        Returns deterministic_answer when any of these are true:
          1. sme_fallback_reason is set (call failed, empty, malformed,
             or audit-rejected).
          2. sme_answer is empty or whitespace-only.
          3. A blocking audit flag (severity "high") is present. This
             is the v2.2.1 gate that catches confabulation the SME's
             own fallback logic missed.

        Otherwise returns sme_answer.

        Widget code reads this property and gets the right value
        without needing to know the gate logic. Widget can separately
        check sme_fallback_reason and sme_answer if it wants to show
        the rejected SME output as diagnostic detail.
        """
        if self.sme_fallback_reason is not None:
            return self.deterministic_answer
        if not self.sme_answer.strip():
            return self.deterministic_answer
        if self.has_blocking_audit_flag():
            return self.deterministic_answer
        return self.sme_answer

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["top_level_answer"] = self.top_level_answer
        d["has_blocking_audit_flag"] = self.has_blocking_audit_flag()
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)
