"""
ensemble/answerer_pm.py

Product Manager persona. Full implementation, canonical template for the
other two personas. Per Persona Retrieval Spec v1 Stage 1.

Retrieval strategy:
- Primary: BGE base, top-8 chunks (tight semantic match for business vocabulary)
- Secondary: Graph index, 1-hop expansion, up to 4 additional chunks
- Ceiling: 12 chunks total

Role and stance:
- Asks what problem the work solved, for whom, what changed as a result.
- Lives between user insight and business decision.
- Outcome-oriented. Stakeholder-aware. Roadmap-aware.
"""

from .answerer_base import AnswererBase, PersonaConfig
from .schemas import Persona
from .prompts import PM_SYSTEM_PROMPT, PM_EXPANSION_VOCAB


# Case regions the PM weights more heavily when ranking retrieved chunks.
# Empty by default in the cloud template — the live retrieval pipeline
# already applies content_weight from the corpus's case_anchor_map.json.
# Practitioners can populate this with case IDs from their own corpus
# if they want extra rerank pressure on PM-relevant chunks. IDs must
# match anchors defined in config/case_anchor_map.json.
PM_SOURCE_PREFERENCES: list = []


class PMAnswerer(AnswererBase):
    def __init__(self):
        self.config = PersonaConfig(
            persona=Persona.PM,
            strategy="bge_base_only",
            top_k=8,
            graph_hops=1,          # 1-hop expansion, narrow radius
            expansion_cap=12,      # total chunk ceiling
            expansion_vocab=PM_EXPANSION_VOCAB,
            system_prompt=PM_SYSTEM_PROMPT,
            source_preferences=PM_SOURCE_PREFERENCES,
        )
