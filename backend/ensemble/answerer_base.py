"""
ensemble/answerer_base.py

Abstract base class for the three persona Answerers. Handles the common
pattern: expand query -> retrieve -> build prompt -> call LLM -> parse
structured output into AnswererOutput.

Subclasses override the persona config block (strategy, top_k, graph_hops,
expansion vocab, system prompt, source preferences). Everything else is
shared.

Changelog:
  2026-04-23 (v2 post-Q2-smoke-test parser hardening):
    - _parse_claim_line now tolerates singular [chunk_id: X] fragments
      repeated within one claim line, and unclosed [chunk_id: ...
      fragments. Q2 smoke test revealed Designer's LLM emitting singular
      form with missing close brackets. Parser now extracts chunk IDs
      from all such patterns and strips them from claim_text.
    - _parse_structured_output UNCERTAINTY filter extended to catch
      template-echo patterns (lines containing "if any", "one per line",
      "e.g.", "i.e.", or starting with "specific unknown"). Q2 Designer
      echoed the placeholder line from the old prompts.py contract;
      prompt is now rewritten but the parser defense stays as belt-and-
      suspenders.

  2026-04-23 (v1 post-smoke-test fixes):
    - Broadened _parse_claim_line regex to handle both bracketed label
      shorthand ([fact]) and the full [status: fact] form, plus tolerate
      compound/garbled LLM output like "[fact [unknown]".
    - _parse_structured_output filters out "none"/"no unknowns" noise from
      the UNCERTAINTY section so Designer's empty-list response no longer
      inflates the unknown count.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional
import os
import re
import requests

from .schemas import (
    AnswererOutput, Claim, Coverage, RetrievalStats,
    EpistemicStatus, Persona,
)
from .retrieval import retrieve, RetrievalResult, RetrievalStrategy
from .prompts import expand_query, build_answerer_prompt


# In the cloud template, persona LLM calls go through the Modal backend's
# /generate route, which proxies to Anthropic Claude. Variable names retain
# the "OLLAMA_*" prefix for parser symmetry with the source lab; the actual
# backend is provider-agnostic.
_LLM_PROXY_BASE = os.environ.get(
    "MODAL_ENDPOINT",
    os.environ.get("UXR_PROXY_BASE", "http://localhost:8080"),
)
OLLAMA_ENDPOINT = f"{_LLM_PROXY_BASE}/generate"
OLLAMA_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
ANSWERER_TIMEOUT_SEC = 120


# Known epistemic status strings, for the broadened parser regex
_EPISTEMIC_WORDS = "|".join(s.value for s in EpistemicStatus)

# Match any of these shapes where an epistemic word appears inside brackets:
#   [status: fact], [epistemic_status: fact], [fact], [Designer: fact],
#   [PM: inference]
# We allow any prefix word before the epistemic word (e.g. persona name)
# because Q2 Designer output produced [Designer: fact] instead of [fact].
# Tolerates garbage after the status word so "[fact [unknown]" still parses
# the first one cleanly as "fact".
_STATUS_PATTERN = re.compile(
    rf"\[[^\]]*?\b({_EPISTEMIC_WORDS})\b[^\]]*\]",
    re.IGNORECASE,
)

# Plural chunk IDs: [chunk_ids: a, b, c]. Stably formatted.
_CHUNK_IDS_PLURAL = re.compile(
    r"\[chunk_ids\s*:\s*([^\]]+)\]", re.IGNORECASE,
)

# Singular-form chunk IDs. Two shapes seen in Q2 Designer output:
#
#   Shape A: [chunk_id: a, chunk_id: b, chunk_id: c]
#   Shape B: [chunk_id: a, chunk_id: b, chunk_id: c      (unclosed)
#
# Both are one opening bracket with N "chunk_id: X" tokens separated by
# commas. _CHUNK_ID_BLOCK matches the entire span starting at the opening
# bracket and running until either the closing bracket or the next
# opening bracket (whichever comes first; handles unclosed case where
# another [tag] follows).
_CHUNK_ID_BLOCK = re.compile(
    r"\[\s*chunk_id\s*:\s*[^\[\]]+?(?=\s*\]|\s*\[)\]?",
    re.IGNORECASE,
)

# Extracts individual "chunk_id: X" tokens from inside a block.
_CHUNK_ID_TOKEN = re.compile(
    r"chunk_id\s*:\s*([A-Za-z0-9_\-]+)", re.IGNORECASE,
)

# Lines in the UNCERTAINTY section we should treat as empty signals.
# Expanded 2026-04-23 to catch template-echo patterns from the old
# prompts.py placeholder text.
_UNCERTAINTY_EMPTY_MARKERS = {
    "none", "no specific unknowns", "no unknowns", "n/a", "na",
    "specific unknowns: none", "specific unknown: none",
    "specific unknown", "specific unknowns",
}

# Substring patterns that indicate a line is a template-instruction echo
# rather than a genuine uncertainty item. Conservative: only matches
# known instructional phrasings that a real UXR wouldn't use as an unknown.
_UNCERTAINTY_TEMPLATE_ECHO_PATTERNS = (
    "if any",
    "one per line",
    "e.g.",
    "i.e.",
    "specific unknown",
    "do not copy",
    "list genuine",
)


@dataclass
class PersonaConfig:
    """Per-persona configuration. Subclasses define this."""
    persona: Persona
    strategy: RetrievalStrategy
    top_k: int
    graph_hops: int
    expansion_cap: Optional[int]
    expansion_vocab: List[str]
    system_prompt: str
    source_preferences: List[str]  # case ids or regions to weight higher


class AnswererBase(ABC):
    """Base class. Subclasses set self.config in __init__."""

    config: PersonaConfig

    @abstractmethod
    def __init__(self):
        """Subclasses populate self.config."""
        pass

    def answer(self, question: str) -> AnswererOutput:
        """
        Run the full pipeline: expand query, retrieve, prompt, parse.
        Returns a populated AnswererOutput. On failure, returns an output
        with empty claims and the error in uncertainty.
        """
        expanded = expand_query(question, self.config.expansion_vocab)

        retrieval = retrieve(
            query=expanded,
            strategy=self.config.strategy,
            top_k=self.config.top_k,
            graph_hops=self.config.graph_hops,
            expansion_cap=self.config.expansion_cap,
        )

        if retrieval.error or not retrieval.chunks:
            return AnswererOutput(
                persona=self.config.persona,
                question=question,
                primary_claims=[],
                coverage=Coverage(addressed=[], not_addressed=[question]),
                uncertainty=[
                    f"Retrieval failed or returned no chunks: {retrieval.error or 'empty result'}"
                ],
                retrieval_stats=RetrievalStats(
                    chunk_count=0,
                    top_source="",
                ),
            )

        chunks_text = self._format_chunks_for_prompt(retrieval)
        prompt = build_answerer_prompt(
            self.config.system_prompt, question, chunks_text
        )

        raw_response = self._call_llm(prompt)
        if raw_response is None:
            return AnswererOutput(
                persona=self.config.persona,
                question=question,
                primary_claims=[],
                coverage=Coverage(addressed=[], not_addressed=[question]),
                uncertainty=["LLM call failed or timed out."],
                retrieval_stats=RetrievalStats(
                    chunk_count=retrieval.chunk_count,
                    top_source=retrieval.top_source,
                ),
            )

        parsed = self._parse_structured_output(raw_response, question)
        parsed.retrieval_stats = RetrievalStats(
            chunk_count=retrieval.chunk_count,
            top_source=retrieval.top_source,
        )
        return parsed

    # ── Hooks subclasses can override ───────────────────────────────────

    def _format_chunks_for_prompt(self, retrieval: RetrievalResult) -> str:
        """
        Format retrieved chunks into a readable block for the LLM. Includes
        chunk_id and source so the LLM can cite them by ID in primary_claims.
        """
        lines = []
        for c in retrieval.chunks:
            lines.append(
                f"[chunk_id: {c.chunk_id} | source: {c.source} | score: {c.score:.3f}]\n"
                f"{c.text}\n"
            )
        return "\n---\n".join(lines)

    # ── LLM call and parser ────────────────────────────────────────────

    def _call_llm(self, prompt: str) -> Optional[str]:
        """
        Call Qwen2.5 14B via Ollama. Scaffolding uses MM24 proxy; real
        endpoint may differ. Returns raw text or None on failure.
        """
        try:
            resp = requests.post(
                OLLAMA_ENDPOINT,
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                },
                timeout=ANSWERER_TIMEOUT_SEC,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "")
        except Exception as e:
            print(f"[{self.config.persona}] LLM call failed: {e}")
            return None

    def _parse_structured_output(self, raw: str, question: str) -> AnswererOutput:
        """
        Parse the Answerer's structured output block back into an
        AnswererOutput. Tolerates minor formatting drift.

        Expected format (per prompts.py SHARED_OUTPUT_CONTRACT):

        PRIMARY CLAIMS:
        - claim text [fact] [chunk_ids: id1, id2]

        COVERAGE:
        - Question parts addressed: x, y
        - Question parts not addressed: z

        UNCERTAINTY:
        - specific unknown
        """
        claims = []
        addressed = []
        not_addressed = []
        uncertainty = []

        current_section = None
        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped:
                continue

            # Detect section headers
            upper = stripped.upper()
            if upper.startswith("PRIMARY CLAIMS"):
                current_section = "claims"
                continue
            if upper.startswith("COVERAGE"):
                current_section = "coverage"
                continue
            if upper.startswith("UNCERTAINTY"):
                current_section = "uncertainty"
                continue

            # Body lines
            if current_section == "claims" and stripped.startswith("-"):
                claim = self._parse_claim_line(stripped)
                if claim:
                    claims.append(claim)

            elif current_section == "coverage" and stripped.startswith("-"):
                body = stripped.lstrip("- ").strip()
                if body.lower().startswith("question parts addressed:"):
                    addressed = self._parse_csv_after_colon(body)
                elif body.lower().startswith("question parts not addressed:"):
                    not_addressed = self._parse_csv_after_colon(body)

            elif current_section == "uncertainty" and stripped.startswith("-"):
                item = stripped.lstrip("- ").strip()
                if self._is_uncertainty_noise(item):
                    continue
                uncertainty.append(item)

        return AnswererOutput(
            persona=self.config.persona,
            question=question,
            primary_claims=claims,
            coverage=Coverage(addressed=addressed, not_addressed=not_addressed),
            uncertainty=uncertainty,
            retrieval_stats=RetrievalStats(),  # filled in by caller
        )

    def _is_uncertainty_noise(self, item: str) -> bool:
        """
        Return True if the UNCERTAINTY line is empty-signal or a
        template-instruction echo rather than a genuine unknown.

        Two filters:
          1. Exact-match empty markers ("None", "N/A", etc).
          2. Substring match against template-echo patterns ("if any",
             "one per line", "specific unknown") that a real UXR would
             not write as an unknown item.
        """
        lowered = item.lower().strip().rstrip(".")

        # Exact-match empty markers
        if lowered in _UNCERTAINTY_EMPTY_MARKERS:
            return True

        # Handle "Specific unknowns: none" as a prefix match
        if ":" in item:
            after_colon = item.split(":", 1)[1].strip().lower().rstrip(".")
            if after_colon in _UNCERTAINTY_EMPTY_MARKERS or after_colon == "":
                return True

        # Template-echo substring match
        for pattern in _UNCERTAINTY_TEMPLATE_ECHO_PATTERNS:
            if pattern in lowered:
                return True

        return False

    def _parse_claim_line(self, line: str) -> Optional[Claim]:
        """Parse a single claim line.

        Handles all these LLM output variations seen in smoke tests:
          - "- [claim text] [status: fact] [chunk_ids: a, b]"
          - "- claim text [fact] [chunk_ids: a, b]"
          - "- claim text [fact [unknown] [chunk_ids: a]"  (garbled compound)
          - "- [fact] claim text [chunk_ids: a]"
          - "- claim text [chunk_id: a, chunk_id: b, chunk_id: c [fact]"
            (Q2 Designer pattern: singular form repeated, unclosed brackets)
        """
        body = line.lstrip("- ").strip()

        # Step 1: extract chunk IDs. Try plural form first (canonical),
        # then fall back to singular-form block scan.
        chunk_ids: List[str] = []

        plural_match = _CHUNK_IDS_PLURAL.search(body)
        if plural_match:
            chunk_ids = [
                c.strip() for c in plural_match.group(1).split(",")
                if c.strip()
            ]
            body = body[:plural_match.start()] + body[plural_match.end():]
        else:
            # Singular form: one bracket containing N "chunk_id: X" tokens,
            # possibly with missing close bracket. Find all such blocks,
            # pull every chunk_id: X token from each.
            block_matches = list(_CHUNK_ID_BLOCK.finditer(body))
            for m in block_matches:
                for tok in _CHUNK_ID_TOKEN.findall(m.group(0)):
                    chunk_ids.append(tok.strip())
            # Strip block spans from body, in reverse so indices stay valid.
            for m in reversed(block_matches):
                body = body[:m.start()] + body[m.end():]
            # Belt and suspenders: clean up any residual "chunk_id:" text
            # that escaped the block matcher (e.g. bare tokens without
            # an opening bracket, or orphan trailing fragments).
            body = re.sub(
                r",?\s*chunk_id\s*:\s*[A-Za-z0-9_\-]+\s*",
                " ", body, flags=re.IGNORECASE,
            )

        # Step 2: extract the FIRST epistemic status tag. Broadened regex
        # catches [status: X], [epistemic_status: X], [X], and tolerates
        # trailing garbage inside the brackets.
        status = EpistemicStatus.UNKNOWN
        status_match = _STATUS_PATTERN.search(body)
        if status_match:
            word = status_match.group(1).lower()
            try:
                status = EpistemicStatus(word)
            except ValueError:
                status = EpistemicStatus.UNKNOWN
            body = body[:status_match.start()] + body[status_match.end():]

        # Step 3: clean up remaining stray brackets and whitespace.
        # Strip any remaining bracketed tags that didn't match status or
        # chunk_id patterns (e.g. Q2 Designer's [chunks: no chunks]).
        # Also strip unclosed trailing brackets like "[chunks: no chunks".
        body = re.sub(r"\[[^\[\]]*\]", " ", body)
        body = re.sub(r"\[[^\[\]]*$", " ", body)
        claim_text = re.sub(r"\s+", " ", body).strip().strip("[]").strip()
        # Collapse doubled punctuation left behind by bracket removal.
        claim_text = re.sub(r"\s+([,.;:])", r"\1", claim_text)
        # Trim any trailing commas left from the chunk_id stripper.
        claim_text = claim_text.rstrip(",").strip()

        if not claim_text:
            return None

        return Claim(
            claim_text=claim_text,
            epistemic_status=status,
            chunk_ids=chunk_ids,
            named_entities=[],  # populated later by entity extraction pass
        )

    def _parse_csv_after_colon(self, text: str) -> List[str]:
        parts = text.split(":", 1)
        if len(parts) < 2:
            return []
        return [item.strip() for item in parts[1].split(",") if item.strip()]
