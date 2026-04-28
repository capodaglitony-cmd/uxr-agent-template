"""
ensemble/wizard/state.py — cascade state machine.

Implements the Playing-to-Win cascade described in
specs/Research_Proposal_Wizard_Spec_v0.4.md and the Phase 1 §1 design in
specs/Research_Proposal_Wizard_Implementation_Plan_v0.1.md.

Pure-Python, no LLM calls. The state object drives one cascade through
the steps:

    root_question  ->  q1_winning_aspiration
                   ->  q2_where_to_play
                   ->  q3_how_to_win
                   ->  q4_capabilities          (multi-select)
                   ->  q5_management_systems
                   ->  fork_direction_or_certainty
                   ->  complete

The pre-cascade root question is parsed for decision count. If the
parser detects three or more decisions, current_step transitions to
guardrail_tripped and next_question() returns None. The orchestrator
then renders the space-cowboy guardrail copy from the spec instead of
generating a proposal.

The state is fully serializable via to_payload() / from_payload() so the
proxy layer can round-trip it through HTTP without a server-side store.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any, Literal
from enum import Enum
import re


# ── Cascade steps ─────────────────────────────────────────────────────────

class CascadeStep(str, Enum):
    ROOT = "root_question"
    Q1_ASPIRATION = "q1_winning_aspiration"
    Q2_WHERE_TO_PLAY = "q2_where_to_play"
    Q3_HOW_TO_WIN = "q3_how_to_win"
    Q4_CAPABILITIES = "q4_capabilities"
    Q5_MANAGEMENT = "q5_management_systems"
    FORK = "fork_direction_or_certainty"
    COMPLETE = "complete"
    GUARDRAIL_TRIPPED = "guardrail_tripped"


# ── Pill copy (verbatim from spec v0.4 §"The Cascade") ────────────────────

Q1_ASPIRATION_PILLS: List[str] = [
    "Grow adoption / engagement",
    "Reduce friction / errors",
    "Enter a new market / segment",
    "Improve satisfaction / retention",
]

Q2_WHERE_TO_PLAY_PILLS: List[str] = [
    "A specific feature or flow",
    "A full product or platform",
    "A new concept or market",
    "Internal tools or processes",
]

Q3_HOW_TO_WIN_PILLS: List[str] = [
    "I don't have one yet — I need to explore",
    "I have a hunch but need to validate",
    "I have a design and need to test it",
    "I need data to quantify what I already know",
]

Q4_CAPABILITY_PILLS: List[str] = [
    "A live product / feature",
    "A prototype or mockup",
    "Prior research or data",
    "Nothing yet — just the idea",
]

Q5_MANAGEMENT_PILLS: List[str] = [
    "Stakeholder alignment on direction",
    "Go/no-go decision on a design",
    "Metrics moving (conversion, satisfaction, etc.)",
    "I'm not sure yet",
]

FORK_PILLS: List[str] = [
    "Direction — help me figure out what to do",
    "Certainty — tell me if this works",
    "Both — I need to explore first, then validate",
]


# Spec design decision #9. Three or more decisions in the root response
# triggers the human-in-the-loop guardrail.
GUARDRAIL_THRESHOLD: int = 3

GUARDRAIL_COPY: str = (
    "Slow down there, space cowboy... it looks like you have the toughest "
    "job we've seen yet with all these decisions you need to make! We "
    "recommend speaking with your researcher in person before using this "
    "wizard."
)


# ── Question / Answer dataclasses ────────────────────────────────────────

@dataclass
class WizardQuestion:
    """A prompt to surface to the user.

    The orchestrator (CLI, widget, or proxy route) reads `prompt`, renders
    the pills if any, and accepts a free-text response when allowed. The
    `step` field is echoed back on the corresponding WizardAnswer so the
    state machine can confirm the response targets the expected step.
    """
    step: CascadeStep
    prompt: str
    pills: List[str] = field(default_factory=list)
    multi_select: bool = False
    free_text_allowed: bool = True
    note: str = ""


@dataclass
class WizardAnswer:
    """A user response. Pills, free text, or both."""
    step: CascadeStep
    pills_selected: List[str] = field(default_factory=list)
    free_text: str = ""

    def has_response(self) -> bool:
        return bool(self.pills_selected or self.free_text.strip())

    def value(self) -> str:
        """Flat single-string view for steps that don't care about the split."""
        text = self.free_text.strip()
        if self.pills_selected and text:
            return ", ".join(self.pills_selected) + "; " + text
        if self.pills_selected:
            return ", ".join(self.pills_selected)
        return text


# ── Static question templates ────────────────────────────────────────────

_QUESTION_TEMPLATES: Dict[CascadeStep, WizardQuestion] = {
    CascadeStep.ROOT: WizardQuestion(
        step=CascadeStep.ROOT,
        prompt="What decision are you needing to make?",
        pills=[],
        multi_select=False,
        free_text_allowed=True,
        note="Free text only. The wizard parses this for decision count.",
    ),
    CascadeStep.Q1_ASPIRATION: WizardQuestion(
        step=CascadeStep.Q1_ASPIRATION,
        prompt="What is your winning aspiration?",
        pills=list(Q1_ASPIRATION_PILLS),
        multi_select=False,
        free_text_allowed=True,
    ),
    CascadeStep.Q2_WHERE_TO_PLAY: WizardQuestion(
        step=CascadeStep.Q2_WHERE_TO_PLAY,
        prompt="Where will you play?",
        pills=list(Q2_WHERE_TO_PLAY_PILLS),
        multi_select=False,
        free_text_allowed=True,
    ),
    CascadeStep.Q3_HOW_TO_WIN: WizardQuestion(
        step=CascadeStep.Q3_HOW_TO_WIN,
        prompt="How will you win?",
        pills=list(Q3_HOW_TO_WIN_PILLS),
        multi_select=False,
        free_text_allowed=True,
        note="Drives research intent classification (Explore/Define/Validate/Measure).",
    ),
    CascadeStep.Q4_CAPABILITIES: WizardQuestion(
        step=CascadeStep.Q4_CAPABILITIES,
        prompt="What capabilities must be in place?",
        pills=list(Q4_CAPABILITY_PILLS),
        multi_select=True,
        free_text_allowed=True,
    ),
    CascadeStep.Q5_MANAGEMENT: WizardQuestion(
        step=CascadeStep.Q5_MANAGEMENT,
        prompt="What management systems are required?",
        pills=list(Q5_MANAGEMENT_PILLS),
        multi_select=False,
        free_text_allowed=True,
    ),
    CascadeStep.FORK: WizardQuestion(
        step=CascadeStep.FORK,
        prompt="One more — do you need direction, or certainty?",
        pills=list(FORK_PILLS),
        multi_select=False,
        free_text_allowed=True,
        note="Sharpens within-intent method selection. 'Both' triggers phased recommendation.",
    ),
}


# Cascade order for advancement after a successful answer.
_NEXT_STEP: Dict[CascadeStep, CascadeStep] = {
    CascadeStep.ROOT: CascadeStep.Q1_ASPIRATION,
    CascadeStep.Q1_ASPIRATION: CascadeStep.Q2_WHERE_TO_PLAY,
    CascadeStep.Q2_WHERE_TO_PLAY: CascadeStep.Q3_HOW_TO_WIN,
    CascadeStep.Q3_HOW_TO_WIN: CascadeStep.Q4_CAPABILITIES,
    CascadeStep.Q4_CAPABILITIES: CascadeStep.Q5_MANAGEMENT,
    CascadeStep.Q5_MANAGEMENT: CascadeStep.FORK,
    CascadeStep.FORK: CascadeStep.COMPLETE,
}


# ── Decision count parser ────────────────────────────────────────────────

# Tokens that typically separate items in a decision list. These patterns
# are intentionally broad: the plan calls for false positives over false
# negatives because the guardrail diverts to a human researcher, which is
# the cheaper failure mode. Tuned in Phase 6 against real test runs.
_SEPARATOR_PATTERN = re.compile(
    r"\b(?:and|or|versus|vs\.?|plus)\b|/|,|;",
    flags=re.IGNORECASE,
)

_DECISION_VERB_PATTERN = re.compile(
    r"\b(?:decide|deciding|choose|choosing|chose|pick|picking|"
    r"figure\s+out|figuring\s+out|determine|determining|select|selecting)\b",
    flags=re.IGNORECASE,
)

_ENUMERATION_PATTERN = re.compile(r"(?:^|\s)(?:\d+\)|\d+\.)\s")


def count_decisions(text: str) -> int:
    """
    Heuristic count of distinct decisions in a root-question response.

    Returns 0 for empty input, 1 for a single clean decision, and the
    list-item count for enumerated or conjunctive constructs. The spec
    fires the human-in-the-loop guardrail at GUARDRAIL_THRESHOLD (3).

    Examples (informal, refined in Phase 6):
        "Should I redesign the booking flow?"        -> 1
        "Decide whether to ship A or B"              -> 2
        "Decide pricing and positioning and launch"  -> 3 (fires guardrail)
        "1) pricing 2) launch 3) GTM 4) staffing"    -> 4 (fires guardrail)
    """
    if not text or not text.strip():
        return 0

    s = text.strip()

    # Numbered enumerations are an unambiguous signal.
    enumerations = _ENUMERATION_PATTERN.findall(s)
    if len(enumerations) >= 2:
        return len(enumerations)

    seps = _SEPARATOR_PATTERN.findall(s)
    verbs = _DECISION_VERB_PATTERN.findall(s)

    # Items implied by separators.
    sep_items = len(seps) + 1 if seps else 1

    # If there's no explicit decision verb, the user might just be giving
    # context. Cap at 2 so a comma-heavy single-decision sentence does not
    # trip the guardrail by accident.
    if not verbs:
        return min(sep_items, 2)

    # Decision verbs present: lean toward sep_items, but at least one per
    # verb so "I need to decide X. I also need to choose Y. Then I have to
    # pick Z." surfaces as 3.
    return max(len(verbs), sep_items)


# ── Direction / certainty fork resolver ──────────────────────────────────

DirectionOrCertainty = Literal["direction", "certainty", "both"]


def _resolve_fork(answer: WizardAnswer) -> Optional[DirectionOrCertainty]:
    """Map the fork pill or free text to a normalized direction/certainty/both value."""
    if answer.pills_selected:
        # Pills are the canonical FORK_PILLS list; match on the leading word.
        for pill in answer.pills_selected:
            head = pill.strip().lower().split(" ", 1)[0]
            head = head.rstrip(",.:;—-")
            if head == "direction":
                return "direction"
            if head == "certainty":
                return "certainty"
            if head == "both":
                return "both"

    text = (answer.free_text or "").strip().lower()
    if not text:
        return None

    has_direction = "direction" in text or "explore" in text or "figure out" in text
    has_certainty = "certainty" in text or "validate" in text or "test if" in text or "tell me if" in text

    if has_direction and has_certainty:
        return "both"
    if has_direction:
        return "direction"
    if has_certainty:
        return "certainty"
    # Could not parse. Leave None; classifier defaults to "direction".
    return None


# ── Wizard state ──────────────────────────────────────────────────────────

@dataclass
class WizardState:
    """Cascade state. One instance per user session.

    All answer fields are optional until the user reaches that step. The
    derived `direction_or_certainty` is populated once the FORK step is
    answered. `decision_count` is populated once the ROOT step is answered.
    """
    # Raw responses (per step).
    decision_text: str = ""
    decision_count: int = 0
    q1_answer: Optional[WizardAnswer] = None
    q2_answer: Optional[WizardAnswer] = None
    q3_answer: Optional[WizardAnswer] = None
    q4_answer: Optional[WizardAnswer] = None
    q5_answer: Optional[WizardAnswer] = None
    fork_answer: Optional[WizardAnswer] = None

    # Derived.
    direction_or_certainty: Optional[DirectionOrCertainty] = None

    # Status.
    current_step: CascadeStep = CascadeStep.ROOT
    guardrail_tripped: bool = False

    # ── Cascade control ──────────────────────────────────────────────

    def next_question(self) -> Optional[WizardQuestion]:
        """Return the prompt for the next step, or None when terminal."""
        if self.current_step in (CascadeStep.COMPLETE, CascadeStep.GUARDRAIL_TRIPPED):
            return None
        return _QUESTION_TEMPLATES[self.current_step]

    def record_answer(self, answer: WizardAnswer) -> None:
        """Apply a user response and advance the cascade.

        Raises ValueError if the answer's step does not match current_step,
        if the cascade has already terminated, or if a required response is
        missing for a step that needs one.
        """
        if self.current_step in (CascadeStep.COMPLETE, CascadeStep.GUARDRAIL_TRIPPED):
            raise ValueError(
                f"Cascade already terminal (step={self.current_step.value}). "
                "Construct a new WizardState to start over."
            )
        if answer.step != self.current_step:
            raise ValueError(
                f"Answer step {answer.step.value} does not match current "
                f"step {self.current_step.value}."
            )

        if answer.step == CascadeStep.ROOT:
            self._apply_root(answer)
            return

        if not answer.has_response():
            raise ValueError(
                f"Step {answer.step.value} requires a pill choice or free text."
            )

        if answer.step == CascadeStep.Q1_ASPIRATION:
            self.q1_answer = answer
        elif answer.step == CascadeStep.Q2_WHERE_TO_PLAY:
            self.q2_answer = answer
        elif answer.step == CascadeStep.Q3_HOW_TO_WIN:
            self.q3_answer = answer
        elif answer.step == CascadeStep.Q4_CAPABILITIES:
            self.q4_answer = answer
        elif answer.step == CascadeStep.Q5_MANAGEMENT:
            self.q5_answer = answer
        elif answer.step == CascadeStep.FORK:
            self.fork_answer = answer
            self.direction_or_certainty = _resolve_fork(answer)

        self.current_step = _NEXT_STEP[answer.step]

    def _apply_root(self, answer: WizardAnswer) -> None:
        text = (answer.free_text or "").strip()
        if not text and answer.pills_selected:
            # Pills are not used at ROOT, but be permissive: fall back to value().
            text = answer.value()
        if not text:
            raise ValueError("Root question requires free-text input.")
        self.decision_text = text
        self.decision_count = count_decisions(text)
        if self.decision_count >= GUARDRAIL_THRESHOLD:
            self.guardrail_tripped = True
            self.current_step = CascadeStep.GUARDRAIL_TRIPPED
        else:
            self.current_step = CascadeStep.Q1_ASPIRATION

    def is_complete(self) -> bool:
        return self.current_step == CascadeStep.COMPLETE

    def is_terminal(self) -> bool:
        return self.current_step in (CascadeStep.COMPLETE, CascadeStep.GUARDRAIL_TRIPPED)

    # ── Serialization ────────────────────────────────────────────────

    def to_payload(self) -> Dict[str, Any]:
        """Flat dict for prompt assembly, persistence, and HTTP round-tripping."""
        d = asdict(self)
        # Enums serialize as raw strings.
        d["current_step"] = self.current_step.value
        for key in ("q1_answer", "q2_answer", "q3_answer", "q4_answer", "q5_answer", "fork_answer"):
            ans = d.get(key)
            if ans and isinstance(ans.get("step"), CascadeStep):
                ans["step"] = ans["step"].value
        return d

    @classmethod
    def from_payload(cls, data: Dict[str, Any]) -> "WizardState":
        """Reconstruct a state object from to_payload() output."""
        def _answer(key: str) -> Optional[WizardAnswer]:
            raw = data.get(key)
            if not raw:
                return None
            return WizardAnswer(
                step=CascadeStep(raw["step"]),
                pills_selected=list(raw.get("pills_selected") or []),
                free_text=raw.get("free_text") or "",
            )

        return cls(
            decision_text=data.get("decision_text") or "",
            decision_count=int(data.get("decision_count") or 0),
            q1_answer=_answer("q1_answer"),
            q2_answer=_answer("q2_answer"),
            q3_answer=_answer("q3_answer"),
            q4_answer=_answer("q4_answer"),
            q5_answer=_answer("q5_answer"),
            fork_answer=_answer("fork_answer"),
            direction_or_certainty=data.get("direction_or_certainty"),
            current_step=CascadeStep(data.get("current_step") or CascadeStep.ROOT.value),
            guardrail_tripped=bool(data.get("guardrail_tripped") or False),
        )
