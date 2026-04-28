"""
ensemble/wizard/schemas.py — wizard data contracts.

The WizardProposal envelope wraps the existing AggregatedOutput (no
schema break upstream) and carries the cascade-derived structure plus
the rendered 2-page brief. The widget/CLI/proxy each consume the same
envelope.

See specs/Research_Proposal_Wizard_Implementation_Plan_v0.1.md §4.
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Literal, Optional

from ..schemas import AggregatedOutput
from .classifier import Intent, Routing, MethodRecommendation


# ── Proposal sections (Spec v0.4 §"Proposal Output") ─────────────────────

@dataclass
class ProposalSections:
    """Structured form of the 2-page brief, per Spec v0.4 §"Proposal Output".

    The renderer in proposal.py turns this dict into Markdown. The widget
    can also consume the structured form directly to display section
    headers as expandable cards.
    """
    decision_context: str = ""
    primary_research_question: str = ""
    secondary_research_questions: List[str] = field(default_factory=list)
    out_of_scope_questions: List[str] = field(default_factory=list)
    recommended_methodology: str = ""
    methodology_rationale: str = ""
    alternative_methods_considered: List[str] = field(default_factory=list)
    phasing_note: str = ""
    target_population: str = ""
    inclusion_exclusion: List[str] = field(default_factory=list)
    sample_size: str = ""
    recruitment_approach: str = ""
    study_design: str = ""
    timeline: str = ""
    deliverable_format: str = ""
    risks: List[str] = field(default_factory=list)

    def to_payload(self) -> Dict[str, Any]:
        return asdict(self)


# ── Wizard proposal envelope ─────────────────────────────────────────────

ProposalStatus = Literal["proposal", "deny", "guardrail"]


@dataclass
class WizardProposal:
    """The wizard's terminal output.

    Three statuses share the envelope:
      - "proposal": the standard 2-page brief was generated from a
        completed cascade. proposal_markdown is populated.
      - "deny":     the routing classifier returned "deny". Instead of a
        brief, deny_copy is populated and the ensemble call was skipped.
      - "guardrail": the root question parser fired the 3+ guardrail.
        Cascade never advanced past ROOT. guardrail_copy is populated.

    aggregated_output is populated only for status="proposal". The two
    short-circuit paths skip the ensemble call by design (Plan §4).
    """
    status: ProposalStatus
    cascade_state: Dict[str, Any]
    intent: Optional[Intent] = None
    routing: Optional[Routing] = None
    method_recommendation: Optional[MethodRecommendation] = None
    aggregated_output: Optional[AggregatedOutput] = None
    proposal_markdown: str = ""
    proposal_sections: ProposalSections = field(default_factory=ProposalSections)
    out_of_scope_questions: List[str] = field(default_factory=list)
    deny_copy: str = ""
    guardrail_copy: str = ""
    elapsed_seconds: float = 0.0

    def to_payload(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "status": self.status,
            "cascade_state": self.cascade_state,
            "intent": self.intent,
            "routing": self.routing,
            "method_recommendation": (
                self.method_recommendation.to_payload()
                if self.method_recommendation else None
            ),
            "aggregated_output": (
                self.aggregated_output.to_dict()
                if self.aggregated_output else None
            ),
            "proposal_markdown": self.proposal_markdown,
            "proposal_sections": self.proposal_sections.to_payload(),
            "out_of_scope_questions": list(self.out_of_scope_questions),
            "deny_copy": self.deny_copy,
            "guardrail_copy": self.guardrail_copy,
            "elapsed_seconds": self.elapsed_seconds,
        }
        return d
