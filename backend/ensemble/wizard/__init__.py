"""
ensemble.wizard — Research Proposal Wizard implementation.

Phase 1 + Phase 2 surface: state machine, classifier, prompts, proposal
orchestrator, CLI runner. Phase 3 (eval fixtures) and beyond add proxy
endpoints and the widget mode. See
specs/Research_Proposal_Wizard_Implementation_Plan_v0.1.md for the
staged build plan and specs/Research_Proposal_Wizard_Spec_v0.4.md for
behavioral ground truth.
"""

from .state import (
    CascadeStep,
    WizardAnswer,
    WizardQuestion,
    WizardState,
    GUARDRAIL_THRESHOLD,
    GUARDRAIL_COPY,
    Q1_ASPIRATION_PILLS,
    Q2_WHERE_TO_PLAY_PILLS,
    Q3_HOW_TO_WIN_PILLS,
    Q4_CAPABILITY_PILLS,
    Q5_MANAGEMENT_PILLS,
    FORK_PILLS,
    count_decisions,
)
from .classifier import (
    ClassificationResult,
    Intent,
    MethodRecommendation,
    Routing,
    classify,
    classify_intent,
    classify_routing,
    recommend_methods,
)
from .schemas import (
    ProposalSections,
    ProposalStatus,
    WizardProposal,
)
from .proposal import ProposalGenerator, render_markdown
from .prompts import build_wizard_preamble, build_wizard_question

__all__ = [
    # state
    "CascadeStep",
    "WizardAnswer",
    "WizardQuestion",
    "WizardState",
    "GUARDRAIL_THRESHOLD",
    "GUARDRAIL_COPY",
    "Q1_ASPIRATION_PILLS",
    "Q2_WHERE_TO_PLAY_PILLS",
    "Q3_HOW_TO_WIN_PILLS",
    "Q4_CAPABILITY_PILLS",
    "Q5_MANAGEMENT_PILLS",
    "FORK_PILLS",
    "count_decisions",
    # classifier
    "ClassificationResult",
    "Intent",
    "MethodRecommendation",
    "Routing",
    "classify",
    "classify_intent",
    "classify_routing",
    "recommend_methods",
    # schemas
    "ProposalSections",
    "ProposalStatus",
    "WizardProposal",
    # proposal
    "ProposalGenerator",
    "render_markdown",
    # prompts
    "build_wizard_preamble",
    "build_wizard_question",
]
