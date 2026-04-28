"""
ensemble/wizard/classifier.py — pure-function classifier.

Maps a completed (or partially-completed) WizardState onto:

  - research intent: Explore / Define / Validate / Measure / Mixed
  - routing: kickoff / backlog / next_sprint / spike / take_and_run / deny
  - method recommendation: primary methods + alternatives + rationale anchors

No LLM calls. Implements Phase 1 §2 of the Implementation Plan against
the table in Spec v0.4 §"Method Recommendation Logic / Direction vs.
Certainty Within Each Intent".

The recommendation table is encoded as a dict, not an LLM call, so the
LLM gets to elaborate the *rationale* downstream while the *method*
itself is deterministic. When the recommendation table goes stale,
update it here and bump Spec §"Method Recommendation Logic".
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Literal, Optional, Tuple, Any

from .state import (
    CascadeStep,
    WizardAnswer,
    WizardState,
    Q3_HOW_TO_WIN_PILLS,
    Q4_CAPABILITY_PILLS,
    Q5_MANAGEMENT_PILLS,
)


Intent = Literal["explore", "define", "validate", "measure", "mixed"]
Routing = Literal["kickoff", "backlog", "next_sprint", "spike", "take_and_run", "deny"]
DirectionOrCertainty = Literal["direction", "certainty", "both"]


# ── Intent classification ────────────────────────────────────────────────

# Q3 pill copy → intent. Pulled from spec v0.4 §"Cascade Question 3".
# Keys are the exact pill strings; lookup is case-insensitive at call time.
Q3_PILL_TO_INTENT: Dict[str, Intent] = {
    Q3_HOW_TO_WIN_PILLS[0]: "explore",   # "I don't have one yet — I need to explore"
    Q3_HOW_TO_WIN_PILLS[1]: "define",    # "I have a hunch but need to validate"
    Q3_HOW_TO_WIN_PILLS[2]: "validate",  # "I have a design and need to test it"
    Q3_HOW_TO_WIN_PILLS[3]: "measure",   # "I need data to quantify what I already know"
}

# Free-text keyword fallback. Each list keeps its strongest signals first.
# Tuned conservatively: a single hit pushes the intent to a winner; ties
# escalate to "mixed".
_INTENT_KEYWORDS: Dict[Intent, List[str]] = {
    "explore": [
        "explore", "discover", "scan", "open question", "no hypothesis",
        "don't know", "do not know", "what's out there", "problem space",
        "early days", "haven't decided",
    ],
    "define": [
        "hunch", "narrow down", "co-create", "co-design", "clarify",
        "shape the problem", "still defining", "framing", "refine the idea",
    ],
    "validate": [
        "validate", "usability", "test it", "test the design", "evaluate",
        "prototype", "mockup", "does this work", "see if it works",
    ],
    "measure": [
        "measure", "quantify", "quantitative", "metric", "kpi", "benchmark",
        "survey", "analytics", "dashboard", "trend", "longitudinal",
    ],
}


def classify_intent(state: WizardState) -> Intent:
    """
    Resolve the user's research intent from cascade state.

    Resolution order:
      1. Q3 pill match (canonical, case-insensitive). If the user picked
         exactly one pill, intent = that pill's mapped intent.
      2. Q3 free-text keyword scan. Highest-hit intent wins; ties produce
         "mixed".
      3. Default: "explore" (the most permissive intent — better than
         arbitrarily forcing measure or validate when signal is missing).

    Special cases:
      - direction_or_certainty == "both" upgrades any single-pill match to
        "mixed" because the user has signalled phased intent.
      - Multiple distinct Q3 pills also produce "mixed".
    """
    q3 = state.q3_answer
    if not q3:
        return "explore"

    # 1. Pill match (canonical labels, case-insensitive).
    pill_intents: List[Intent] = []
    for pill in q3.pills_selected:
        match = _match_pill_to_intent(pill)
        if match is not None:
            pill_intents.append(match)

    if pill_intents:
        unique = list(dict.fromkeys(pill_intents))
        if len(unique) > 1:
            return "mixed"
        single: Intent = unique[0]
        if state.direction_or_certainty == "both":
            return "mixed"
        return single

    # 2. Free-text keyword scan.
    text = (q3.free_text or "").lower()
    if text:
        keyword_hits: Dict[Intent, int] = {k: 0 for k in _INTENT_KEYWORDS}
        for intent, kws in _INTENT_KEYWORDS.items():
            for kw in kws:
                if kw in text:
                    keyword_hits[intent] += 1
        max_hits = max(keyword_hits.values())
        if max_hits > 0:
            # If two or more distinct intents register, free text is
            # spanning — return mixed (this is the spec's Q3-free-text
            # mixed-intent trigger).
            distinct_intents_with_hits = [k for k, v in keyword_hits.items() if v > 0]
            if len(distinct_intents_with_hits) >= 2:
                return "mixed"
            winners = [k for k, v in keyword_hits.items() if v == max_hits]
            single_kw: Intent = winners[0]
            if state.direction_or_certainty == "both":
                return "mixed"
            return single_kw

    # 3. Default.
    return "explore"


def _match_pill_to_intent(pill: str) -> Optional[Intent]:
    pill_norm = pill.strip().lower()
    for canonical, intent in Q3_PILL_TO_INTENT.items():
        if pill_norm == canonical.lower():
            return intent
    return None


# ── Routing classification ───────────────────────────────────────────────

# Pre-extracted lowercase tokens for capability detection.
_CAP_LIVE_PRODUCT = "a live product / feature"
_CAP_PROTOTYPE = "a prototype or mockup"
_CAP_PRIOR_RESEARCH = "prior research or data"
_CAP_NOTHING_YET = "nothing yet — just the idea"

# Q5 pill canonical strings.
_Q5_ALIGNMENT = "stakeholder alignment on direction"
_Q5_GO_NO_GO = "go/no-go decision on a design"
_Q5_METRICS = "metrics moving (conversion, satisfaction, etc.)"
_Q5_NOT_SURE = "i'm not sure yet"


def classify_routing(state: WizardState, intent: Intent) -> Routing:
    """
    Map cascade state + intent onto one of the six routing actions.

    The mapping mirrors a six-action research-ops triage (see source
    Spec v0.4 §"Routing"):

      - deny:          decision-already-made or no-research-question signal
      - take_and_run:  measure intent + analytics-y q5 + research/data on hand
      - spike:         explore intent + nothing-yet capabilities (still has q5 signal)
      - backlog:       alignment-on-direction q5 with explore/define intent
      - next_sprint:   validate intent + design or live product available
      - kickoff:       default — full proposal + RO meeting

    Order matters: deny first (short-circuit); then specific positive
    routes; kickoff last as the catch-all.
    """
    caps_lower = _capability_tokens(state)
    q5_lower = _q5_token(state)
    has_q3_signal = _has_response(state.q3_answer)
    has_q4_signal = _has_response(state.q4_answer)

    only_idea = (
        len(caps_lower) == 1
        and _CAP_NOTHING_YET in caps_lower
        and not (state.q4_answer.free_text or "").strip()
    ) if state.q4_answer else False

    no_signal_q3 = not has_q3_signal
    not_sure_q5 = (q5_lower == _Q5_NOT_SURE) or not q5_lower

    # 1. Deny — research can't help here, or the user hasn't surfaced enough.
    if no_signal_q3:
        return "deny"
    if only_idea and not_sure_q5:
        return "deny"

    # 2. Take and run — measure + metrics + data already on hand.
    if intent == "measure":
        metrics_signal = (q5_lower == _Q5_METRICS)
        data_on_hand = (
            _CAP_PRIOR_RESEARCH in caps_lower
            or _CAP_LIVE_PRODUCT in caps_lower
        )
        if metrics_signal and data_on_hand:
            return "take_and_run"

    # 3. Spike — explore intent, very little built yet, but Q5 has direction.
    if intent == "explore":
        if _CAP_NOTHING_YET in caps_lower and not not_sure_q5:
            return "spike"

    # 4. Backlog — alignment-on-direction with explore/define intent.
    if q5_lower == _Q5_ALIGNMENT and intent in ("explore", "define"):
        return "backlog"

    # 5. Next sprint — validate intent + something testable available.
    if intent == "validate":
        if (
            _CAP_PROTOTYPE in caps_lower
            or _CAP_LIVE_PRODUCT in caps_lower
        ):
            return "next_sprint"

    # 6. Default — full proposal + kickoff meeting.
    if not has_q4_signal:
        # No capability data at all and we're not on a deny-signal path:
        # send it to backlog rather than kickoff so a human RO disambiguates.
        return "backlog"

    return "kickoff"


def _capability_tokens(state: WizardState) -> List[str]:
    if not state.q4_answer:
        return []
    return [p.strip().lower() for p in state.q4_answer.pills_selected if p]


def _q5_token(state: WizardState) -> str:
    if not state.q5_answer:
        return ""
    if state.q5_answer.pills_selected:
        return state.q5_answer.pills_selected[0].strip().lower()
    return (state.q5_answer.free_text or "").strip().lower()


def _has_response(answer: Optional[WizardAnswer]) -> bool:
    if answer is None:
        return False
    return bool(answer.pills_selected or (answer.free_text or "").strip())


# ── Method recommendation ────────────────────────────────────────────────

@dataclass
class MethodRecommendation:
    """Structured method recommendation for one cascade.

    `rationale_anchors` are case_anchor_map case IDs (e.g. "case_2",
    "case_14"). The proposal generator uses these to retrieve grounded
    supporting evidence from the corpus.
    """
    primary_methods: List[str]
    alternative_methods: List[str] = field(default_factory=list)
    rationale_anchors: List[str] = field(default_factory=list)
    phasing_note: str = ""

    def to_payload(self) -> Dict[str, Any]:
        return asdict(self)


# Static lookup table for non-mixed intents. Spec v0.4 §"Method
# Recommendation Logic / Direction vs. Certainty Within Each Intent".
# Comments cite the spec line each entry implements so a future tuner can
# diff against the source of truth.
_METHOD_TABLE: Dict[Tuple[Intent, DirectionOrCertainty], MethodRecommendation] = {
    # Spec: "Explore + Direction → ethnographic observation, open-ended interviews"
    ("explore", "direction"): MethodRecommendation(
        primary_methods=[
            "Ethnographic observation",
            "Open-ended stakeholder interviews",
        ],
        alternative_methods=[
            "Diary studies",
            "Field observation",
            "Targeted literature review",
        ],
        rationale_anchors=["case_1", "case_2", "case_4"],
    ),
    # Spec: "Explore + Certainty → structured contextual inquiry with predefined observation framework"
    ("explore", "certainty"): MethodRecommendation(
        primary_methods=[
            "Structured contextual inquiry with predefined observation framework",
        ],
        alternative_methods=[
            "Heuristic analysis",
            "Comparative literature review",
        ],
        rationale_anchors=["case_2", "case_8"],
    ),
    # Spec: "Define + Direction → co-creation workshops, concept testing (early stage)"
    ("define", "direction"): MethodRecommendation(
        primary_methods=[
            "Co-creation workshops",
            "Early-stage concept testing",
        ],
        alternative_methods=[
            "In-depth interviews",
            "Persona refinement workshop",
        ],
        rationale_anchors=["case_3", "case_5"],
    ),
    # Spec: "Define + Certainty → card sorting, heuristic analysis"
    ("define", "certainty"): MethodRecommendation(
        primary_methods=[
            "Card sorting",
            "Heuristic analysis",
        ],
        alternative_methods=[
            "Tree testing",
            "Concept evaluation interviews",
        ],
        rationale_anchors=["case_3"],
    ),
    # Spec: "Validate + Direction → moderated usability with think-aloud (richer but slower)"
    ("validate", "direction"): MethodRecommendation(
        primary_methods=[
            "Moderated usability testing with think-aloud",
        ],
        alternative_methods=[
            "Diary studies post-prototype",
            "Co-design sessions",
        ],
        rationale_anchors=["case_14", "case_22"],
    ),
    # Spec: "Validate + Certainty → unmoderated task-based testing with statistical rigor (faster, quantifiable)"
    ("validate", "certainty"): MethodRecommendation(
        primary_methods=[
            "Unmoderated task-based testing with statistical rigor",
        ],
        alternative_methods=[
            "A/B testing",
            "Tree testing",
        ],
        rationale_anchors=["case_14", "case_22"],
    ),
    # Spec: "Measure + Direction → survey + open-ended follow-up interviews"
    ("measure", "direction"): MethodRecommendation(
        primary_methods=[
            "Survey with open-ended follow-up interviews",
        ],
        alternative_methods=[
            "SUS plus qualitative debrief",
        ],
        rationale_anchors=["case_11", "case_12"],
    ),
    # Spec: "Measure + Certainty → analytics funnel analysis, benchmarking, longitudinal SUS/NPS"
    ("measure", "certainty"): MethodRecommendation(
        primary_methods=[
            "Analytics funnel analysis",
            "Competitive benchmarking",
            "Longitudinal SUS/NPS",
        ],
        alternative_methods=[
            "Statistical surveys",
            "Cohort analysis",
        ],
        rationale_anchors=["case_8", "case_11"],
    ),
}

# Mixed intent maps to the Discovery → Concept → Validation → Strategy
# Review framework from the Setting Up Shop blueprint (Spec v0.4
# §"Mixed Intent → Phased Research"). Phasing note explains the linkage
# explicitly so the proposal renderer can cite it.
_MIXED_RECOMMENDATION = MethodRecommendation(
    primary_methods=[
        "Phase 1 (Discovery): Ethnographic observation or contextual inquiry",
        "Phase 2 (Concept): Co-creation workshops + concept testing",
        "Phase 3 (Validation): Low-fidelity prototype usability testing",
        "Phase 4 (Strategy Review): Convergence on a shippable solution",
    ],
    alternative_methods=[
        "Time-boxed spike before full phased plan if calendar pressure is high",
    ],
    rationale_anchors=["case_2", "case_4", "case_14"],
    phasing_note=(
        "Aligned to the Discovery → Concept → Validation → Final Strategy "
        "Review convergence framework from the Setting Up Shop blueprint "
        "(Spec v0.4 §'Mixed Intent → Phased Research')."
    ),
)


def recommend_methods(state: WizardState, intent: Intent) -> MethodRecommendation:
    """
    Return the canonical method recommendation for (intent, fork).

    Falls back to the direction variant when the user has not answered the
    fork. Mixed intent always returns the phased recommendation regardless
    of fork value.
    """
    if intent == "mixed":
        return _MIXED_RECOMMENDATION

    fork: DirectionOrCertainty = state.direction_or_certainty or "direction"  # type: ignore[assignment]
    key: Tuple[Intent, DirectionOrCertainty] = (intent, fork)
    if key in _METHOD_TABLE:
        return _METHOD_TABLE[key]

    # Defensive fallback: direction variant. Should not be reachable given
    # the Literal types, but the table is the source of truth and a stale
    # spec edit could leave a hole.
    direction_key: Tuple[Intent, DirectionOrCertainty] = (intent, "direction")
    return _METHOD_TABLE[direction_key]


# ── Convenience: classify everything in one call ────────────────────────

@dataclass
class ClassificationResult:
    intent: Intent
    routing: Routing
    method_recommendation: MethodRecommendation

    def to_payload(self) -> Dict[str, Any]:
        return {
            "intent": self.intent,
            "routing": self.routing,
            "method_recommendation": self.method_recommendation.to_payload(),
        }


def classify(state: WizardState) -> ClassificationResult:
    """One-call wrapper used by the proposal orchestrator."""
    intent = classify_intent(state)
    routing = classify_routing(state, intent)
    methods = recommend_methods(state, intent)
    return ClassificationResult(
        intent=intent,
        routing=routing,
        method_recommendation=methods,
    )
