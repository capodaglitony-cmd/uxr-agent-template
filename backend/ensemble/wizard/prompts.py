"""
ensemble/wizard/prompts.py — wizard prompt builders.

The wizard does not invent a new prompt format. It reuses the existing
PM/Designer/Engineer system prompts (ensemble.prompts) and prepends a
"wizard preamble" that injects:

  - the cascade context (decision text, Q1..Q5 answers, fork)
  - the classified intent and routing
  - the canonical method recommendation
  - a section-specific directive telling each persona which proposal
    section they are contributing to

The personas keep their existing chunk grounding, anti-hallucination
contract, and TONY_LINT_RULES tone. The preamble narrows their scope
to the proposal-section task.

See Implementation Plan v0.1 §3.
"""

from dataclasses import asdict
from typing import Dict, Optional

from .state import WizardState
from .classifier import (
    ClassificationResult,
    Intent,
    MethodRecommendation,
    Routing,
)
from ..profile import OWNER_NAME, owner_possessive

_OWNER_POSS = owner_possessive()


# ── Per-persona section assignments (Spec v0.4 §"Persona Integration") ───

PM_SECTION_DIRECTIVE = """
You are contributing the DECISION CONTEXT and STAKEHOLDER READINESS
sections of a research proposal. Your scope:
- Is the framing of the decision clear and actionable?
- Who acts on the findings, and is the organization positioned to act?
- What changes if research confirms vs. disconfirms the hypothesis?
- Are there outcome metrics or roadmap signals already in motion?

Stay out of study design, stimulus readiness, and feasibility — those
are the Designer and Engineer sections.
""".strip()

DESIGNER_SECTION_DIRECTIVE = """
You are contributing the STUDY DESIGN and STIMULUS READINESS sections of
a research proposal. Your scope:
- Is the design or concept mature enough for the recommended method?
- What participant experience does the recommended method produce?
- What stimulus materials need to exist for the study to run?
- Where is the experience risk that the method must surface?

Stay out of decision context (PM) and feasibility/data constraints
(Engineer).
""".strip()

ENGINEER_SECTION_DIRECTIVE = """
You are contributing the FEASIBILITY and DATA CONSTRAINT sections of a
research proposal. Your scope:
- Can we access the data, systems, or participant pool the method needs?
- What infrastructure or tooling constraints affect timeline?
- What integration or instrumentation is required for the method?
- What are the top failure modes or risks during execution?

Stay out of decision context (PM) and study design / participant
experience (Designer).
""".strip()


_SECTION_DIRECTIVES = {
    "PM": PM_SECTION_DIRECTIVE,
    "Designer": DESIGNER_SECTION_DIRECTIVE,
    "Engineer": ENGINEER_SECTION_DIRECTIVE,
}


# ── Cascade context block ───────────────────────────────────────────────

def _format_method_recommendation(rec: MethodRecommendation) -> str:
    lines = ["RECOMMENDED METHODS (canonical, derived from cascade):"]
    for m in rec.primary_methods:
        lines.append(f"  - {m}")
    if rec.alternative_methods:
        lines.append("ALTERNATIVE METHODS CONSIDERED:")
        for m in rec.alternative_methods:
            lines.append(f"  - {m}")
    if rec.phasing_note:
        lines.append(f"PHASING NOTE: {rec.phasing_note}")
    if rec.rationale_anchors:
        lines.append(
            "RATIONALE ANCHORS (case story IDs the rationale should cite): "
            + ", ".join(rec.rationale_anchors)
        )
    return "\n".join(lines)


def _format_cascade_context(state: WizardState, classification: ClassificationResult) -> str:
    """One readable block summarizing the cascade for the LLM."""
    q1 = state.q1_answer.value() if state.q1_answer else "(unspecified)"
    q2 = state.q2_answer.value() if state.q2_answer else "(unspecified)"
    q3 = state.q3_answer.value() if state.q3_answer else "(unspecified)"
    q4_pills = state.q4_answer.pills_selected if state.q4_answer else []
    q4_free = state.q4_answer.free_text.strip() if state.q4_answer else ""
    q4 = ", ".join(q4_pills) + ((f"; {q4_free}" if q4_pills and q4_free else q4_free) if q4_free else "")
    q4 = q4 or "(unspecified)"
    q5 = state.q5_answer.value() if state.q5_answer else "(unspecified)"
    fork_value = state.direction_or_certainty or "(not specified — defaulting to direction)"

    decision = state.decision_text or "(decision not captured)"

    lines = [
        "CASCADE CONTEXT (Playing to Win):",
        f"  Decision the user is making: {decision}",
        f"  Q1 winning aspiration:       {q1}",
        f"  Q2 where to play:            {q2}",
        f"  Q3 how to win:               {q3}",
        f"  Q4 capabilities in place:    {q4}",
        f"  Q5 management systems:       {q5}",
        f"  Direction-or-certainty fork: {fork_value}",
        "",
        f"CLASSIFIED RESEARCH INTENT: {classification.intent}",
        f"ROUTING DECISION:           {classification.routing}",
        "",
        _format_method_recommendation(classification.method_recommendation),
    ]
    return "\n".join(lines)


# ── Wizard preamble builder ─────────────────────────────────────────────

WIZARD_PREAMBLE_HEADER = (
    "WIZARD MODE — RESEARCH PROPOSAL GENERATION\n"
    "You are answering as part of a wizard cascade. The user has walked "
    "through the Playing-to-Win cascade, and the answers below are your "
    "ground truth for this conversation. Treat the cascade context as "
    "given facts about the user's situation; do not re-derive them or "
    "second-guess them. Your job is to contribute one section of the "
    "proposal, grounded in the corpus chunks the retriever returns."
)

WIZARD_PREAMBLE_FOOTER = (
    "Output discipline:\n"
    "- Cite chunks for every factual claim, just as in normal Q&A mode.\n"
    "- If the chunks do not support a section requirement, mark it as an\n"
    "  uncertainty rather than inventing.\n"
    "- Stay strictly within the section scope assigned to your persona.\n"
    f"- Speak in the wizard voice: consultant in {_OWNER_POSS} voice, direct,\n"
    "  warm, occasionally opinionated. Voice constraints still apply."
)


def build_wizard_preamble(
    state: WizardState,
    classification: ClassificationResult,
    persona: str,
) -> str:
    """Compose the wizard preamble for a single persona.

    The preamble is prepended to the persona's existing system prompt;
    it does not replace any of the existing scaffolding (output contract,
    lint rules, deliberate gaps).
    """
    if persona not in _SECTION_DIRECTIVES:
        raise ValueError(
            f"Unknown persona {persona!r}. Expected one of "
            f"{sorted(_SECTION_DIRECTIVES)}."
        )

    directive = _SECTION_DIRECTIVES[persona]
    cascade_block = _format_cascade_context(state, classification)

    return "\n\n".join([
        WIZARD_PREAMBLE_HEADER,
        cascade_block,
        f"YOUR ASSIGNED SECTION ({persona}):\n{directive}",
        WIZARD_PREAMBLE_FOOTER,
    ])


def build_wizard_question(state: WizardState, classification: ClassificationResult) -> str:
    """Compose the question string the personas answer.

    The personas already retrieve corpus chunks based on this string, so
    the question shapes which case stories surface. Frame it around the
    method recommendation so chunks about analogous methods get pulled in.
    """
    primary_method = (
        classification.method_recommendation.primary_methods[0]
        if classification.method_recommendation.primary_methods
        else "the recommended method"
    )
    intent_phrase = {
        "explore": "exploring an open problem space",
        "define": "defining a hypothesis or problem",
        "validate": "validating a design or hypothesis",
        "measure": "measuring a known phenomenon quantitatively",
        "mixed": "phased exploration through validation",
    }.get(classification.intent, classification.intent)

    decision = state.decision_text.strip().rstrip(".") or "this research decision"
    return (
        f"What does {_OWNER_POSS} portfolio show about applying {primary_method.lower()} "
        f"when {intent_phrase}, and how should this proposal for "
        f"\"{decision}\" handle the section your persona is responsible for?"
    )
