"""
ensemble/sme_prompt.py

The UXR SME synthesis prompt. Lives separate from prompts.py because the
SME has a structurally different job: it reads the three persona outputs
and produces the accountable answer, not retrieval-grounded claims.

See SME_Synthesis_Design_v1.md for the full design.

The SME prompt enforces the owner's voice per MyVoice.md (Analytical +
Representational cell, strictest constraints) plus TONY_LINT_RULES v3.3.
Hard constraints are listed in the prompt as behavioral rules. Examples
are deliberately omitted because Qwen 14B imitates example subject matter;
the constraints are the guidance.

Changelog:
  2026-04-23: v1. Initial SME prompt per SME_Synthesis_Design_v1 Section 9.
"""

from typing import Dict, Any, List
from .schemas import AnswererOutput, DivergenceMetrics


# ── The SME system prompt ───────────────────────────────────────────────
#
# This prompt is the highest-leverage artifact in the SME layer. If the
# prompt drifts, the synthesis drifts. Keep it versioned, keep it explicit,
# and keep it grounded in MyVoice.md Section 10 forbidden patterns and
# TONY_LINT_RULES v3.3.

SME_SYSTEM_PROMPT = """You are a Senior UX Researcher with 12+ years of experience across \
healthcare, financial services, and consulting. You are reading three \
research perspectives on a question and producing the accountable answer \
that integrates them.

The three perspectives are from your own team, each with a distinct \
retrieval strategy:
- PM (strategy layer): BGE base plus 1-hop graph. Sources: case stories, \
strategy documents, outcome framings.
- Designer (service-design layer): MiniLM only. Sources: service \
blueprints, workflow artifacts, participant findings.
- Engineer (implementation layer): graph-primary plus BGE base. Sources: \
system architecture, implementation detail, technical constraints.

Your job: read the three perspectives, take a stance on the question, \
and produce a single synthesized answer in your voice.

VOICE CONSTRAINTS (hard rules, no exceptions):

Direct. Declarative. Practitioner inside the work.
Default short sentences, 12 to 18 words. Justify long.
No contrast framing. Never use "not X but Y", "rather than", "instead \
of", "not just", "as opposed to".
No hyphens, em dashes, or en dashes. Rewrite to avoid all three.
No modal stacking. Never write "strongly believe that probably" or "it is \
likely that it may".
No condescending qualifiers. Never write "actually", "simply", \
"obviously", "clearly".
No performative warmth. Never write "excited", "passionate", "journey \
taught me".
No observer stance. Do not write "the PM said" or "the Designer thinks" \
or "according to the Engineer". Instead reference what each retrieval \
layer surfaced.
No stacked adjectives. One precise descriptor per noun.
Claims bounded to what the three perspectives contributed. Do not \
introduce entities, numbers, frameworks, or named methods not present \
in their outputs.
Epistemic labels where uncertainty lives: fact, inference, assumption, \
hypothesis, unknown.
Use "So" as a transition when the reasoning moves forward.
Use "The question:" or "The lesson:" to land an insight when the \
synthesis earns it.

DIVERGENCE HANDLING:

When the three perspectives converge on the same finding, integrate the \
shared finding into one clean statement. Note that three retrieval \
methodologies surfaced the same answer if the convergence strengthens \
the grounding.

When the three perspectives agree on substance but contribute different \
facets, integrate the substance and name which facets came from which \
retrieval layer. Do not collapse the facets into false consensus.

When the three perspectives disagree on substance, name the disagreement \
directly. Take a position. Ground the position in which perspective's \
evidence you draw from, and explain the reasoning. Do not hedge. Do not \
split the difference. The answer is the position, with the dissent \
named.

When the three perspectives do not answer the question asked, say so \
directly. State what the perspectives do cover. Decline to invent an \
answer the evidence does not support. A direct refusal is a complete \
answer.

STRUCTURE:

1. Direct answer. One or two sentences. Answer the question as posed.
2. Integration. Three to four sentences. Name convergence, divergence, \
or refusal. Reference the retrieval layers that contributed.
3. Landing. Optional. Use "The lesson:" or "The question:" only if the \
synthesis earns it.
4. Bounded next step. Optional. Name a specific artifact or research \
pass if the question genuinely calls for one.

LENGTH: three to six sentences total. Concise. Grounded.

Output the synthesized answer only. No section headers. No meta-commentary \
about your process. No "Here is the synthesis:" preamble. Just the \
answer."""


# ── Input formatting ────────────────────────────────────────────────────
#
# The SME does not see raw chunks. It sees structured persona output:
# each persona's surviving claims with chunk counts and epistemic labels,
# plus the divergence metrics and band. See SME_Synthesis_Design_v1 §7.

def build_sme_input(
    question: str,
    pm_output: AnswererOutput,
    designer_output: AnswererOutput,
    engineer_output: AnswererOutput,
    pm_claims_surviving,
    designer_claims_surviving,
    engineer_claims_surviving,
    divergence_metrics: DivergenceMetrics,
    divergence_band: str,
    dropped_count: int,
) -> str:
    """
    Build the SME input payload as a structured string the LLM can read.

    Takes the surviving claims (post-anti-hallucination) rather than the
    raw Answerer output, so the SME never sees fabrications the persona
    layer already caught.

    Returns a formatted string ready to append to the SME system prompt.
    """

    def format_persona_block(
        persona_name: str,
        layer_label: str,
        output: AnswererOutput,
        surviving_claims,
    ) -> str:
        """Format one persona's contribution for the SME to read."""
        lines = [f"### {persona_name} ({layer_label})"]
        lines.append(
            f"Top source: {output.retrieval_stats.top_source or 'unknown'}"
        )
        lines.append(
            f"Claims surviving anti-hallucination: {len(surviving_claims)}"
        )
        lines.append("")

        if surviving_claims:
            lines.append("Claims:")
            for c in surviving_claims:
                chunk_strength = len(c.chunk_ids)
                lines.append(
                    f"- {c.claim_text} "
                    f"[epistemic: {c.epistemic_status.value}, "
                    f"grounding: {chunk_strength} chunks]"
                )
        else:
            lines.append(
                "Claims: none surviving (this layer did not contribute "
                "corpus-grounded claims on this question)."
            )

        if output.uncertainty:
            lines.append("")
            lines.append("Surfaced uncertainty:")
            for u in output.uncertainty:
                lines.append(f"- {u}")

        if output.coverage and output.coverage.not_addressed:
            lines.append("")
            lines.append("Question aspects this layer did not address:")
            for item in output.coverage.not_addressed:
                lines.append(f"- {item}")

        return "\n".join(lines)

    blocks = [
        f"QUESTION: {question}",
        "",
        f"DIVERGENCE SIGNAL: band={divergence_band}, "
        f"jaccard_distance={divergence_metrics.jaccard_distance}, "
        f"claim_overlap={divergence_metrics.claim_overlap}"
        + (f", watch_flag={divergence_metrics.watch_flag}"
           if divergence_metrics.watch_flag else ""),
        "",
        f"CLAIMS DROPPED BY ANTI-HALLUCINATION: {dropped_count}",
        "",
        "---",
        "",
        "THREE PERSPECTIVES TO SYNTHESIZE:",
        "",
        format_persona_block(
            "PM", "strategy layer", pm_output, pm_claims_surviving,
        ),
        "",
        format_persona_block(
            "Designer", "service-design layer",
            designer_output, designer_claims_surviving,
        ),
        "",
        format_persona_block(
            "Engineer", "implementation layer",
            engineer_output, engineer_claims_surviving,
        ),
        "",
        "---",
        "",
        "Produce the synthesized answer now. Follow all voice constraints. "
        "Output only the answer, no preamble.",
    ]

    return "\n".join(blocks)


def build_sme_full_prompt(
    question: str,
    pm_output: AnswererOutput,
    designer_output: AnswererOutput,
    engineer_output: AnswererOutput,
    pm_claims_surviving,
    designer_claims_surviving,
    engineer_claims_surviving,
    divergence_metrics: DivergenceMetrics,
    divergence_band: str,
    dropped_count: int,
) -> str:
    """
    Build the complete prompt string (system + input) for the LLM call.
    """
    input_block = build_sme_input(
        question=question,
        pm_output=pm_output,
        designer_output=designer_output,
        engineer_output=engineer_output,
        pm_claims_surviving=pm_claims_surviving,
        designer_claims_surviving=designer_claims_surviving,
        engineer_claims_surviving=engineer_claims_surviving,
        divergence_metrics=divergence_metrics,
        divergence_band=divergence_band,
        dropped_count=dropped_count,
    )
    return f"{SME_SYSTEM_PROMPT}\n\n{input_block}"
