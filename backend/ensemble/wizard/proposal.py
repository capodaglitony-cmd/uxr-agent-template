"""
ensemble/wizard/proposal.py — proposal orchestrator + brief renderer.

Implements Phase 2 §2 of the Implementation Plan. Three jobs:

  1. Orchestrate the proposal pipeline:

         WizardState
           -> classify_intent + classify_routing + recommend_methods
           -> build wizard preamble per persona
           -> call PMAnswerer / DesignerAnswerer / EngineerAnswerer
              (with the wizard preamble injected into each persona's
               existing system prompt)
           -> Aggregator -> SMEAnswerer -> AggregatedOutput
           -> assemble into WizardProposal envelope
           -> render Markdown 2-page brief

  2. Short-circuit the deny path before the ensemble call. The deny
     classifier output produces a 1-paragraph reframe instead of a
     2-page brief, so we save the four-LLM-call cost.

  3. Short-circuit the guardrail path entirely. If the cascade tripped
     the 3+ decisions guardrail, the cascade never reaches FORK and the
     proposal generator returns the space-cowboy copy directly.

The renderer is deterministic: section headers come from Spec v0.4
§"Proposal Output", and the bullets are derived from cascade state,
classification, and (when present) the SME synthesis. The LLM does the
narrative work upstream; the renderer just composes.
"""

from copy import copy
from dataclasses import replace
from time import time
from typing import Dict, List, Optional, Tuple

from ..schemas import (
    AggregatedOutput,
    AnswererOutput,
    Persona,
)
from ..answerer_pm import PMAnswerer
from ..answerer_designer import DesignerAnswerer
from ..answerer_engineer import EngineerAnswerer
from ..aggregator import Aggregator, AggregatorInput
from ..retrieval import retrieve

from .state import (
    GUARDRAIL_COPY,
    WizardState,
)
from .classifier import (
    ClassificationResult,
    Intent,
    MethodRecommendation,
    Routing,
    classify,
)
from .prompts import (
    build_wizard_preamble,
    build_wizard_question,
)
from .schemas import (
    ProposalSections,
    WizardProposal,
)


# ── Deny copy variants ───────────────────────────────────────────────────

# Three deny variants discriminate by which deny condition fired.
# Spec v0.4 supplies one. The classifier currently emits a single deny
# routing; we discriminate by cascade signal.

_DENY_DECISION_ALREADY_CLEAR = (
    "Based on your answers, research may not be what you need here. The "
    "decision sounds like it may already be clear — you have a strong "
    "direction in mind and limited stimulus material to test against. "
    "Talk it through with a researcher in person before kicking off a "
    "study. The wizard is built for decisions where research can move "
    "the needle, and the value isn't there yet."
)

_DENY_NEEDS_REFRAMING = (
    "Based on your answers, research may not be what you need here. The "
    "question may need reframing before research can help. There isn't "
    "enough cascade signal yet — the wizard couldn't classify the "
    "research intent from your responses. Spend a kick-off conversation "
    "shaping the question, then come back."
)


# ── Generator ────────────────────────────────────────────────────────────

class ProposalGenerator:
    """Orchestrates the proposal pipeline.

    Construction is cheap. Each ``generate(...)`` call is one cascade ->
    one proposal, including the four LLM calls (three personas + SME).

    For local rendering tests without infrastructure, pass dry_run=True
    to skip the ensemble call. The generator returns a WizardProposal
    that has classification, method recommendation, and a markdown brief
    rendered from cascade state alone — useful for unit tests of the
    renderer.
    """

    def __init__(self, *, dry_run: bool = False):
        self.dry_run = dry_run
        self._aggregator: Optional[Aggregator] = None

    # ── Public ───────────────────────────────────────────────────────

    def generate(self, state: WizardState) -> WizardProposal:
        start = time()

        if state.guardrail_tripped:
            return WizardProposal(
                status="guardrail",
                cascade_state=state.to_payload(),
                guardrail_copy=GUARDRAIL_COPY,
                elapsed_seconds=round(time() - start, 3),
            )

        if not state.is_complete():
            raise ValueError(
                "Cannot generate a proposal from an incomplete cascade. "
                f"Current step: {state.current_step.value}. Walk the cascade "
                "to completion (or trip the guardrail) before calling generate()."
            )

        classification = classify(state)

        if classification.routing == "deny":
            deny_copy = self._select_deny_copy(state, classification)
            return WizardProposal(
                status="deny",
                cascade_state=state.to_payload(),
                intent=classification.intent,
                routing=classification.routing,
                method_recommendation=classification.method_recommendation,
                deny_copy=deny_copy,
                elapsed_seconds=round(time() - start, 3),
            )

        aggregated = None
        if not self.dry_run:
            aggregated = self._run_ensemble(state, classification)

        sections = self._build_sections(state, classification, aggregated)
        markdown = render_markdown(sections, state, classification)

        return WizardProposal(
            status="proposal",
            cascade_state=state.to_payload(),
            intent=classification.intent,
            routing=classification.routing,
            method_recommendation=classification.method_recommendation,
            aggregated_output=aggregated,
            proposal_markdown=markdown,
            proposal_sections=sections,
            out_of_scope_questions=list(sections.out_of_scope_questions),
            elapsed_seconds=round(time() - start, 3),
        )

    # ── Ensemble orchestration ───────────────────────────────────────

    def _run_ensemble(
        self,
        state: WizardState,
        classification: ClassificationResult,
    ) -> AggregatedOutput:
        """Instantiate persona answerers, inject wizard preamble into each
        system prompt, run all three, then aggregate.

        We mutate each answerer's config.system_prompt in place after
        construction. This keeps the existing PMAnswerer / DesignerAnswerer
        / EngineerAnswerer files untouched (Plan risk #1: do not bleed
        wizard tone into Q&A modes).
        """
        question = build_wizard_question(state, classification)

        pm = PMAnswerer()
        designer = DesignerAnswerer()
        engineer = EngineerAnswerer()

        for persona_name, answerer in (
            ("PM", pm),
            ("Designer", designer),
            ("Engineer", engineer),
        ):
            preamble = build_wizard_preamble(state, classification, persona_name)
            answerer.config = replace(
                answerer.config,
                system_prompt=preamble + "\n\n" + answerer.config.system_prompt,
            )

        # Each answerer runs its own retrieval inside answer().
        pm_out = _safe_answer(pm, question, "PM")
        designer_out = _safe_answer(designer, question, "Designer")
        engineer_out = _safe_answer(engineer, question, "Engineer")

        # Aggregator needs the chunk lists too. Re-run retrieval with each
        # persona's strategy so we can pass the same chunk set to the
        # anti-hallucination pass.
        pm_chunks = _safe_retrieve(pm, question)
        designer_chunks = _safe_retrieve(designer, question)
        engineer_chunks = _safe_retrieve(engineer, question)

        if self._aggregator is None:
            self._aggregator = Aggregator()

        return self._aggregator.aggregate(AggregatorInput(
            pm_output=pm_out,
            designer_output=designer_out,
            engineer_output=engineer_out,
            pm_chunks=pm_chunks,
            designer_chunks=designer_chunks,
            engineer_chunks=engineer_chunks,
        ))

    # ── Section assembly ─────────────────────────────────────────────

    def _build_sections(
        self,
        state: WizardState,
        classification: ClassificationResult,
        aggregated: Optional[AggregatedOutput],
    ) -> ProposalSections:
        s = ProposalSections()

        s.decision_context = self._render_decision_context(state, classification)
        s.primary_research_question = self._render_primary_question(state, classification)
        s.secondary_research_questions = self._render_secondary_questions(state, classification)
        s.out_of_scope_questions = self._render_out_of_scope(state, classification)

        rec = classification.method_recommendation
        s.recommended_methodology = ", ".join(rec.primary_methods) if rec.primary_methods else ""
        s.alternative_methods_considered = list(rec.alternative_methods)
        s.phasing_note = rec.phasing_note
        s.methodology_rationale = self._render_rationale(state, classification, aggregated)

        s.target_population = self._render_target_population(state)
        s.inclusion_exclusion = self._render_inclusion_exclusion(state)
        s.sample_size = self._render_sample_size(classification.intent)
        s.recruitment_approach = self._render_recruitment(state, classification.intent)
        s.study_design = self._render_study_design(state, classification, aggregated)
        s.timeline = self._render_timeline(classification)
        s.deliverable_format = self._render_deliverable(state)
        s.risks = self._render_risks(state, classification, aggregated)

        return s

    # ── Section renderers (each returns a small string) ──────────────

    @staticmethod
    def _render_decision_context(
        state: WizardState,
        classification: ClassificationResult,
    ) -> str:
        decision = state.decision_text.strip().rstrip(".")
        intent_label = classification.intent
        aspiration = state.q1_answer.value() if state.q1_answer else ""
        whereto = state.q2_answer.value() if state.q2_answer else ""

        sentence_one = f"This research informs the decision: {decision}."
        sentence_two = (
            f"The user is operating with a {intent_label} research intent "
            f"in service of \"{aspiration.lower() or 'the stated aspiration'}\" "
            f"on {whereto.lower() or 'the chosen playing field'}."
        )
        sentence_three = (
            "Findings should change the recommended action for the decision "
            "above; if findings cannot move the decision, the study is not "
            "worth the calendar."
        )
        return " ".join([sentence_one, sentence_two, sentence_three])

    @staticmethod
    def _render_primary_question(
        state: WizardState,
        classification: ClassificationResult,
    ) -> str:
        decision = state.decision_text.strip().rstrip("?.")
        intent_to_phrase = {
            "explore": "What does the problem space look like for",
            "define": "What hypothesis best explains the friction in",
            "validate": "Does the proposed design solve the problem in",
            "measure": "What is the magnitude of the effect for",
            "mixed": "What does the problem space look like, and which solution holds up under test, for",
        }
        stem = intent_to_phrase.get(classification.intent, "What does the user need to know about")
        return f"{stem} {decision.lower()}?"

    @staticmethod
    def _render_secondary_questions(
        state: WizardState,
        classification: ClassificationResult,
    ) -> List[str]:
        intent = classification.intent
        whereto = (state.q2_answer.value() if state.q2_answer else "the chosen playing field").lower()

        if intent == "explore":
            return [
                f"Who experiences this problem in {whereto}, and how do they describe it?",
                f"What workarounds or adaptations have users built around this?",
                f"What adjacent problems are downstream if this stays unaddressed?",
            ]
        if intent == "define":
            return [
                f"Which of the candidate framings best matches user mental models in {whereto}?",
                f"What language do users use for this concept that we should mirror in design?",
                f"Which user segments diverge most on this framing?",
            ]
        if intent == "validate":
            return [
                f"Where in the recommended design do users encounter friction?",
                f"Which task steps produce errors or abandonment, and at what rate?",
                f"What edge cases or accessibility gaps surface in moderated sessions?",
            ]
        if intent == "measure":
            return [
                f"What is the baseline metric on {whereto} prior to the change?",
                f"How does the metric shift across user segments?",
                f"What confidence interval is acceptable for the decision?",
            ]
        # mixed
        return [
            f"What does the problem space look like in {whereto}?",
            f"Which candidate solutions hold up under early validation?",
            f"What metric movement is required to ship?",
        ]

    @staticmethod
    def _render_out_of_scope(
        state: WizardState,
        classification: ClassificationResult,
    ) -> List[str]:
        # The STOP gate principle from Spec v0.4 §"Corpus Integration".
        # These are the questions an analyst will be tempted to slide into
        # scope mid-study; naming them up front makes sliding visible.
        intent = classification.intent
        items: List[str] = []
        if intent in ("explore", "define"):
            items.append("Final design decisions or A/B test winners (separate validation study)")
        if intent in ("validate", "measure"):
            items.append("Strategic problem reframing (separate discovery study)")
        items.append("Compensation, pricing, or commercial-model questions unless explicitly scoped")
        items.append("Questions about populations or markets outside the chosen playing field")
        if state.q4_answer and any(
            "nothing yet" in p.lower() for p in state.q4_answer.pills_selected
        ):
            items.append("Production-readiness or engineering-feasibility validation (no stimulus exists)")
        return items

    @staticmethod
    def _render_rationale(
        state: WizardState,
        classification: ClassificationResult,
        aggregated: Optional[AggregatedOutput],
    ) -> str:
        rec = classification.method_recommendation
        primary = rec.primary_methods[0] if rec.primary_methods else "the recommended method"
        intent = classification.intent
        fork = state.direction_or_certainty or "direction"

        anchor_phrase = ""
        if rec.rationale_anchors:
            anchors = ", ".join(rec.rationale_anchors)
            from ..profile import owner_possessive
            anchor_phrase = (
                f" {owner_possessive()} portfolio shows analogous applications anchored by {anchors}."
            )

        sme_phrase = ""
        if aggregated is not None:
            top = aggregated.top_level_answer.strip()
            if top:
                sme_phrase = f" Synthesized rationale from the ensemble: {top}"

        return (
            f"{primary} fits a {intent}/{fork} cascade because the user has "
            f"signalled the matching capability profile and decision posture in "
            f"the cascade." + anchor_phrase + sme_phrase
        )

    @staticmethod
    def _render_target_population(state: WizardState) -> str:
        whereto = state.q2_answer.value() if state.q2_answer else ""
        if not whereto:
            return "Users in the chosen playing field"
        return f"Users engaged with {whereto.lower()}"

    @staticmethod
    def _render_inclusion_exclusion(state: WizardState) -> List[str]:
        items = []
        if state.q2_answer:
            items.append(f"Inclusion: active users of {state.q2_answer.value().lower()}")
        items.append("Inclusion: ability to complete a 45-60 minute remote session")
        items.append("Exclusion: employees of the user's organization (avoid feedback contamination)")
        items.append("Exclusion: participants in any study run on this surface in the last 90 days")
        return items

    @staticmethod
    def _render_sample_size(intent: Intent) -> str:
        # Conservative defaults aligned to common UXR practice. Tunable in
        # Phase 6 against actual fielded studies.
        if intent == "explore":
            return "8-12 participants per segment for theme saturation."
        if intent == "define":
            return "10-15 participants total; segment if the cascade names two distinct user groups."
        if intent == "validate":
            return "8-12 moderated sessions, or N>=80 unmoderated if statistical rigor is required."
        if intent == "measure":
            return "N>=200 for stable proportion estimates; larger if segment cuts are needed."
        # mixed
        return "Phase 1: 8-10. Phase 2: 6-8 concept-test sessions. Phase 3: 8-12 validation sessions."

    @staticmethod
    def _render_recruitment(state: WizardState, intent: Intent) -> str:
        if intent == "measure":
            return "Panel-based or analytics-derived sampling for population coverage."
        return "Researcher-led recruit through the user's existing participant pool or a recruit panel."

    @staticmethod
    def _render_study_design(
        state: WizardState,
        classification: ClassificationResult,
        aggregated: Optional[AggregatedOutput],
    ) -> str:
        rec = classification.method_recommendation
        primary = rec.primary_methods[0] if rec.primary_methods else "the recommended method"
        capability_summary = (
            ", ".join(state.q4_answer.pills_selected) if state.q4_answer else "no stimulus listed"
        )
        return (
            f"Run {primary.lower()} sessions structured around the "
            f"primary research question. Stimulus: {capability_summary or 'none yet'}. "
            f"Capture verbatim quotes plus task-level metrics where the method "
            f"produces them. Synthesize against the {classification.intent} intent "
            f"and the cascade context."
        )

    @staticmethod
    def _render_timeline(classification: ClassificationResult) -> str:
        rec = classification.method_recommendation
        if rec.phasing_note:
            return (
                "Three phases. Phase 1 (Discovery) ~2-3 weeks. Phase 2 (Concept) "
                "~2 weeks. Phase 3 (Validation) ~2-3 weeks. Final review ~1 week. "
                "Total wall time: ~7-9 weeks contingent on recruit speed."
            )
        if classification.intent == "validate":
            return "~3-4 weeks: 1 week recruit, 1.5 weeks fielding, 1 week analysis."
        if classification.intent == "measure":
            return "~3-5 weeks: instrument design and pilot ~1 week, fielding ~2 weeks, analysis ~1-2 weeks."
        return "~4-6 weeks: kickoff and recruit ~1.5 weeks, fielding ~2 weeks, synthesis ~1.5 weeks, readout ~1 week."

    @staticmethod
    def _render_deliverable(state: WizardState) -> str:
        if not state.q5_answer:
            return "Synthesis readout with primary findings and recommendations."
        q5_value = state.q5_answer.value().lower()
        if "go/no-go" in q5_value:
            return "Go/no-go memo with primary findings, decision recommendation, and risk register."
        if "metrics moving" in q5_value:
            return "Quantitative report with baseline and post-change metrics, segment cuts, and confidence intervals."
        if "alignment on direction" in q5_value:
            return "Stakeholder alignment readout with direction recommendation and supporting evidence."
        return "Synthesis readout matching the management system the cascade named."

    @staticmethod
    def _render_risks(
        state: WizardState,
        classification: ClassificationResult,
        aggregated: Optional[AggregatedOutput],
    ) -> List[str]:
        risks: List[str] = []
        intent = classification.intent
        if intent == "explore":
            risks.append("Theme saturation may require additional sessions if the playing field is broad.")
        if intent == "validate":
            risks.append("Stimulus maturity matters: if the design changes mid-study, re-baseline.")
        if intent == "measure":
            risks.append("Sample bias from panel sourcing; weight results or add a backfill recruit if skewed.")
        if state.q4_answer and any(
            "prior research" in p.lower() for p in state.q4_answer.pills_selected
        ):
            risks.append("Re-using prior research artifacts can prime participants; pilot the protocol.")
        if aggregated is not None:
            band = aggregated.divergence_band
            if band == "red_flag":
                risks.append(
                    "Persona divergence flagged a red_flag band on this proposal; "
                    "review the cascade with a researcher before fielding."
                )
            elif band == "productive":
                risks.append(
                    "Persona divergence is productive on this proposal: the brief "
                    "preserves multiple perspectives that should be reconciled in "
                    "kickoff."
                )
        if not risks:
            risks.append("Calendar slip from recruit; pre-screen panel before kickoff.")
        return risks

    # ── Deny copy selection ──────────────────────────────────────────

    @staticmethod
    def _select_deny_copy(
        state: WizardState,
        classification: ClassificationResult,
    ) -> str:
        # Discriminate by which deny condition fired in classify_routing.
        # The classifier returns "deny" in two cases; pick the matching copy.
        if state.q3_answer is None or not (
            state.q3_answer.pills_selected or (state.q3_answer.free_text or "").strip()
        ):
            return _DENY_NEEDS_REFRAMING
        return _DENY_DECISION_ALREADY_CLEAR


# ── Helpers ──────────────────────────────────────────────────────────────

def _safe_answer(answerer, question: str, label: str) -> AnswererOutput:
    try:
        return answerer.answer(question)
    except Exception as e:
        # Return an empty AnswererOutput so the aggregator can still run.
        from ..schemas import Coverage, RetrievalStats
        return AnswererOutput(
            persona=answerer.config.persona,
            question=question,
            primary_claims=[],
            coverage=Coverage(addressed=[], not_addressed=[question]),
            uncertainty=[f"{label} answerer raised: {e}"],
            retrieval_stats=RetrievalStats(),
        )


def _safe_retrieve(answerer, question: str):
    """Re-run retrieval for the aggregator's anti-hallucination pass.

    The answerer already retrieved in answer(); this is a second call
    against the same endpoint so we can hand the chunk list to the
    Aggregator. Cheap because the proxy caches.
    """
    try:
        from ..prompts import expand_query
        expanded = expand_query(question, answerer.config.expansion_vocab)
        result = retrieve(
            query=expanded,
            strategy=answerer.config.strategy,
            top_k=answerer.config.top_k,
            graph_hops=answerer.config.graph_hops,
            expansion_cap=answerer.config.expansion_cap,
        )
        return result.chunks
    except Exception:
        return []


# ── Markdown renderer ────────────────────────────────────────────────────

def render_markdown(
    sections: ProposalSections,
    state: WizardState,
    classification: ClassificationResult,
) -> str:
    """Compose the ProposalSections into a 2-page Markdown brief.

    Section headings come from Spec v0.4 §"Proposal Output". Order is
    fixed; the renderer is deterministic.
    """
    lines: List[str] = []
    lines.append("# Research Proposal")
    lines.append("")
    lines.append(
        f"_Intent: **{classification.intent}** · "
        f"Routing: **{classification.routing}** · "
        f"Direction-or-certainty: **{state.direction_or_certainty or 'unspecified'}**_"
    )
    lines.append("")

    lines.append("## 1. Decision Context")
    lines.append("")
    lines.append(sections.decision_context)
    lines.append("")

    lines.append("## 2. Research Questions")
    lines.append("")
    lines.append(f"**Primary:** {sections.primary_research_question}")
    lines.append("")
    if sections.secondary_research_questions:
        lines.append("**Secondary:**")
        for q in sections.secondary_research_questions:
            lines.append(f"- {q}")
        lines.append("")
    if sections.out_of_scope_questions:
        lines.append("**Out of scope (STOP gate):**")
        for q in sections.out_of_scope_questions:
            lines.append(f"- {q}")
        lines.append("")

    lines.append("## 3. Recommended Methodology")
    lines.append("")
    lines.append(f"**Recommended:** {sections.recommended_methodology}")
    lines.append("")
    lines.append(sections.methodology_rationale)
    lines.append("")
    if sections.alternative_methods_considered:
        lines.append("**Alternatives considered:**")
        for m in sections.alternative_methods_considered:
            lines.append(f"- {m}")
        lines.append("")
    if sections.phasing_note:
        lines.append(f"**Phasing:** {sections.phasing_note}")
        lines.append("")

    lines.append("## 4. Participants")
    lines.append("")
    lines.append(f"**Population:** {sections.target_population}")
    lines.append("")
    lines.append("**Inclusion / exclusion criteria:**")
    for c in sections.inclusion_exclusion:
        lines.append(f"- {c}")
    lines.append("")
    lines.append(f"**Sample size:** {sections.sample_size}")
    lines.append("")
    lines.append(f"**Recruitment:** {sections.recruitment_approach}")
    lines.append("")

    lines.append("## 5. Study Design")
    lines.append("")
    lines.append(sections.study_design)
    lines.append("")

    lines.append("## 6. Timeline, Outputs, and Risks")
    lines.append("")
    lines.append(f"**Timeline:** {sections.timeline}")
    lines.append("")
    lines.append(f"**Deliverable:** {sections.deliverable_format}")
    lines.append("")
    if sections.risks:
        lines.append("**Risks:**")
        for r in sections.risks:
            lines.append(f"- {r}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
