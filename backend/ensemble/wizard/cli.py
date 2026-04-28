"""
ensemble/wizard/cli.py — terminal cascade runner + fixture batch tester.

Single-fixture / interactive:
  python3 -m ensemble.wizard.cli                    # interactive cascade
  python3 -m ensemble.wizard.cli --dry-run          # skip ensemble call
  python3 -m ensemble.wizard.cli --fixture PATH     # replay a saved fixture
  python3 -m ensemble.wizard.cli --fixture PATH --dry-run

Fixture batch (regression test):
  python3 -m ensemble.wizard.cli --fixture-batch eval/wizard_fixtures/
  python3 -m ensemble.wizard.cli --fixture-batch DIR --live   # run with LLM
  python3 -m ensemble.wizard.cli --fixture-batch DIR --verbose

Fixtures are JSON files of the shape:

    {
      "label": "validate-prototype-go-no-go-certainty",
      "expected_status": "proposal",                  // optional, default
      "expected_intent": "validate",                  // optional
      "expected_routing": "next_sprint",              // optional
      "expected_method_family": "unmoderated task",   // case-insensitive
      "must_contain_phrases": ["statistical rigor"],  // case-insensitive
      "answers": {
        "root_question": {"free_text": "..."},
        "q1_winning_aspiration": {"pills_selected": ["..."]},
        ...
      }
    }

Batch mode is dry-run by default (deterministic, fast). Pass --live to
exercise the live ensemble pipeline; expect ~25-30s per fixture.

The CLI exercises the state machine, classifier, prompt builder, and
proposal generator end-to-end without any UI dependency. Plan §1.4
calls this the "first thing that should work".
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional

from .state import (
    CascadeStep,
    GUARDRAIL_COPY,
    WizardAnswer,
    WizardQuestion,
    WizardState,
)
from .proposal import ProposalGenerator
from .schemas import ProposalStatus, WizardProposal


# ── Fixture replay ──────────────────────────────────────────────────────

def _answer_from_dict(step: CascadeStep, raw: dict) -> WizardAnswer:
    return WizardAnswer(
        step=step,
        pills_selected=list(raw.get("pills_selected") or []),
        free_text=raw.get("free_text") or "",
    )


def replay_fixture(path: Path) -> WizardState:
    """Build a fully-walked WizardState from a fixture JSON."""
    data = json.loads(path.read_text())
    answers = data.get("answers") or {}
    state = WizardState()

    while not state.is_terminal():
        question = state.next_question()
        if question is None:
            break
        raw = answers.get(question.step.value)
        if raw is None:
            raise ValueError(
                f"Fixture {path} missing answer for step "
                f"{question.step.value!r}."
            )
        state.record_answer(_answer_from_dict(question.step, raw))

    return state


# ── Interactive prompt ──────────────────────────────────────────────────

def _render_prompt(question: WizardQuestion) -> str:
    out = [f"\n{question.prompt}"]
    if question.note:
        out.append(f"  ({question.note})")
    if question.pills:
        for i, pill in enumerate(question.pills, 1):
            out.append(f"  {i}. {pill}")
        if question.multi_select:
            out.append(
                "  Type one or more pill numbers separated by commas, or type "
                "free text. Blank to skip free text."
            )
        else:
            out.append("  Type a pill number, or type free text.")
    elif question.free_text_allowed:
        out.append("  (free text)")
    return "\n".join(out) + "\n> "


def _parse_response(question: WizardQuestion, response: str) -> WizardAnswer:
    response = response.strip()
    if not response:
        return WizardAnswer(step=question.step)

    pills_selected = []
    free_text = ""

    if question.pills:
        # Allow comma-separated pill numbers (multi-select).
        tokens = [t.strip() for t in response.split(",")]
        all_numeric = all(t.isdigit() for t in tokens) and tokens
        if all_numeric:
            for tok in tokens:
                idx = int(tok) - 1
                if 0 <= idx < len(question.pills):
                    pills_selected.append(question.pills[idx])
                else:
                    raise ValueError(f"Pill number {tok!r} out of range.")
        else:
            free_text = response
    else:
        free_text = response

    if not question.multi_select and len(pills_selected) > 1:
        # Single-select: take the first.
        pills_selected = pills_selected[:1]

    return WizardAnswer(
        step=question.step,
        pills_selected=pills_selected,
        free_text=free_text,
    )


def run_interactive() -> WizardState:
    state = WizardState()
    print(
        "Research Proposal Wizard — interactive cascade\n"
        "Press Ctrl-C to exit at any time.\n"
    )
    while not state.is_terminal():
        question = state.next_question()
        if question is None:
            break
        try:
            response = input(_render_prompt(question))
        except EOFError:
            print("\n[EOF, aborting cascade]")
            return state
        try:
            answer = _parse_response(question, response)
        except ValueError as e:
            print(f"  ! {e}  Try again.")
            continue
        try:
            state.record_answer(answer)
        except ValueError as e:
            print(f"  ! {e}  Try again.")
            continue

    return state


# ── Output ──────────────────────────────────────────────────────────────

def _print_proposal(proposal: WizardProposal) -> None:
    print()
    print("=" * 70)
    print(f"STATUS: {proposal.status}")
    print("=" * 70)

    if proposal.status == "guardrail":
        print()
        print(proposal.guardrail_copy)
        return

    if proposal.status == "deny":
        print()
        print(proposal.deny_copy)
        return

    if proposal.intent or proposal.routing:
        print(f"intent={proposal.intent}  routing={proposal.routing}  "
              f"elapsed={proposal.elapsed_seconds}s")
        print()

    print(proposal.proposal_markdown)


# ── Fixture batch runner ────────────────────────────────────────────────

@dataclass
class FixtureResult:
    """One fixture's outcome from the batch runner."""
    label: str
    path: Path
    status: ProposalStatus
    intent: Optional[str]
    routing: Optional[str]
    elapsed: float
    failures: List[str] = field(default_factory=list)
    proposal: Optional[WizardProposal] = None

    @property
    def passed(self) -> bool:
        return not self.failures


def _check_expectations(
    proposal: WizardProposal,
    expected: dict,
) -> List[str]:
    """Compare a proposal against the fixture's expected_* fields.

    Returns a list of human-readable failure messages. Empty list = pass.
    """
    failures: List[str] = []

    expected_status = expected.get("expected_status") or "proposal"
    if proposal.status != expected_status:
        failures.append(
            f"status: expected {expected_status!r}, got {proposal.status!r}"
        )

    # Intent/routing are populated for "proposal" and "deny" statuses only.
    # Skip those checks for guardrail unless the fixture explicitly asks.
    if proposal.status in ("proposal", "deny"):
        exp_intent = expected.get("expected_intent")
        if exp_intent and proposal.intent != exp_intent:
            failures.append(
                f"intent: expected {exp_intent!r}, got {proposal.intent!r}"
            )

        exp_routing = expected.get("expected_routing")
        if exp_routing and proposal.routing != exp_routing:
            failures.append(
                f"routing: expected {exp_routing!r}, got {proposal.routing!r}"
            )

    # Method family check only meaningful when a recommendation exists.
    if proposal.status == "proposal":
        exp_method = expected.get("expected_method_family")
        if exp_method and proposal.method_recommendation:
            haystack = " | ".join(
                proposal.method_recommendation.primary_methods
            ).lower()
            if exp_method.lower() not in haystack:
                preview = haystack[:120] + ("..." if len(haystack) > 120 else "")
                failures.append(
                    f"method_family: {exp_method!r} not found in primary "
                    f"methods (got: {preview!r})"
                )

    # must_contain_phrases scans the user-visible output text. For
    # proposal status, that's the markdown brief; for deny, the deny copy;
    # for guardrail, the guardrail copy.
    must_contain = expected.get("must_contain_phrases") or []
    if must_contain:
        if proposal.status == "proposal":
            text = proposal.proposal_markdown
        elif proposal.status == "deny":
            text = proposal.deny_copy
        else:
            text = proposal.guardrail_copy
        text_lower = (text or "").lower()
        for phrase in must_contain:
            if phrase.lower() not in text_lower:
                failures.append(f"must_contain phrase missing: {phrase!r}")

    return failures


def run_single_fixture(
    path: Path,
    *,
    dry_run: bool,
    generator: Optional[ProposalGenerator] = None,
) -> FixtureResult:
    """Replay one fixture and check it against its expected_* fields."""
    data = json.loads(path.read_text())
    state = replay_fixture(path)
    if generator is None:
        generator = ProposalGenerator(dry_run=dry_run)
    proposal = generator.generate(state)

    failures = _check_expectations(proposal, data)

    return FixtureResult(
        label=data.get("label") or path.stem,
        path=path,
        status=proposal.status,
        intent=proposal.intent,
        routing=proposal.routing,
        elapsed=proposal.elapsed_seconds,
        failures=failures,
        proposal=proposal,
    )


def run_fixture_batch(
    target: Path,
    *,
    dry_run: bool,
    verbose: bool = False,
) -> int:
    """Run every fixture under `target` (file or directory) and emit a
    pass/fail summary. Returns 0 if all pass, 1 if any fail, 2 on bad
    inputs.
    """
    if target.is_dir():
        fixture_paths = sorted(target.glob("*.json"))
    elif target.is_file():
        fixture_paths = [target]
    else:
        print(f"ERROR: --fixture-batch target {target} is neither a file nor a directory.")
        return 2

    if not fixture_paths:
        print(f"ERROR: no *.json fixtures found in {target}.")
        return 2

    mode = "dry-run" if dry_run else "live"
    print("Wizard Fixture Batch Runner")
    print("=" * 78)
    print(f"Mode:    {mode}")
    print(f"Target:  {target}")
    print(f"Found:   {len(fixture_paths)} fixture(s)")
    print("=" * 78)
    print()

    # One generator across the whole batch so the SME instance is reused.
    generator = ProposalGenerator(dry_run=dry_run)

    results: List[FixtureResult] = []
    for path in fixture_paths:
        try:
            r = run_single_fixture(path, dry_run=dry_run, generator=generator)
        except Exception as e:
            r = FixtureResult(
                label=path.stem,
                path=path,
                status="proposal",
                intent=None,
                routing=None,
                elapsed=0.0,
                failures=[f"raised exception: {type(e).__name__}: {e}"],
                proposal=None,
            )
        results.append(r)
        marker = "PASS" if r.passed else "FAIL"
        intent_s = r.intent or "-"
        routing_s = r.routing or "-"
        print(
            f"  {marker:4}  {path.stem:38}  "
            f"status={r.status:9}  intent={intent_s:9}  "
            f"routing={routing_s:13}  {r.elapsed:5.1f}s"
        )
        for failure in r.failures:
            print(f"        ↳ {failure}")
        if verbose and r.passed and r.proposal is not None:
            print()
            output = (
                r.proposal.proposal_markdown
                or r.proposal.deny_copy
                or r.proposal.guardrail_copy
            )
            for line in output.splitlines():
                print(f"        {line}")
            print()

    print()
    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed
    print("=" * 78)
    print(f"  {passed}/{len(results)} PASS · {failed}/{len(results)} FAIL")
    print("=" * 78)

    return 0 if failed == 0 else 1


# ── Main ────────────────────────────────────────────────────────────────

def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ensemble.wizard.cli",
        description="Walk the Research Proposal Wizard cascade in the terminal.",
    )
    parser.add_argument(
        "--fixture", type=Path, default=None,
        help="Replay a saved cascade fixture (JSON) instead of asking interactively.",
    )
    parser.add_argument(
        "--fixture-batch", dest="fixture_batch", type=Path, default=None,
        metavar="PATH",
        help="Run every *.json fixture in a directory (or one file) and "
             "emit a pass/fail summary. Defaults to dry-run for fast "
             "deterministic regression. Pass --live to override.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Skip the live ensemble call. Cascade runs, classification "
             "runs, proposal renders from cascade state alone. Useful when "
             "the Mini PC is offline or for unit tests. Default mode for "
             "--fixture-batch.",
    )
    parser.add_argument(
        "--live", action="store_true",
        help="Force live ensemble calls. Default for single-fixture and "
             "interactive modes; opt-in for --fixture-batch.",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="In batch mode, dump the full output for each passing fixture.",
    )
    parser.add_argument(
        "--json", dest="emit_json", action="store_true",
        help="Emit the WizardProposal as JSON (full payload) instead of "
             "the human-readable markdown brief. Single-fixture and "
             "interactive modes only.",
    )
    args = parser.parse_args(argv)

    if args.dry_run and args.live:
        parser.error("--dry-run and --live are mutually exclusive.")

    # Batch path: dry-run unless --live is explicitly requested.
    if args.fixture_batch is not None:
        if args.fixture is not None:
            parser.error("--fixture and --fixture-batch are mutually exclusive.")
        dry_run = not args.live  # batch default: dry-run
        if args.dry_run:
            dry_run = True       # explicit override (no-op here, but supported)
        return run_fixture_batch(
            args.fixture_batch,
            dry_run=dry_run,
            verbose=args.verbose,
        )

    # Single-fixture / interactive path: live by default.
    dry_run = args.dry_run

    if args.fixture is not None:
        state = replay_fixture(args.fixture)
        print(f"[fixture] {args.fixture}: cascade walked, "
              f"current_step={state.current_step.value}")
    else:
        state = run_interactive()

    generator = ProposalGenerator(dry_run=dry_run)
    proposal = generator.generate(state)

    if args.emit_json:
        print(json.dumps(proposal.to_payload(), indent=2, default=str))
    else:
        _print_proposal(proposal)

    return 0


if __name__ == "__main__":
    sys.exit(main())
