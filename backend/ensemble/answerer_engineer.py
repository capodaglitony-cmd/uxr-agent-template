"""
ensemble/answerer_engineer.py

Engineer persona. Per Persona Retrieval Spec v1 Stage 1.

Retrieval strategy:
- Primary: Graph index (dual-collection 0.5 vector + 0.5 graph scoring)
- Secondary: BGE base, top-6 chunks (for specific technical vocabulary)
- Graph hops: 2 (broader than PM's 1, because system boundaries are farther apart)
- Ceiling: ~15 chunks total

Role and stance:
- Asks how the work was built, what constraints shaped it, where the system breaks.
- Lives in the implementation layer.
- Mechanism-oriented. Dependency-aware. Failure-mode-aware.
"""

from .answerer_base import AnswererBase, PersonaConfig
from .schemas import Persona
from .prompts import ENGINEER_SYSTEM_PROMPT, ENGINEER_EXPANSION_VOCAB


# Empty by default in the cloud template; see PM_SOURCE_PREFERENCES note.
ENGINEER_SOURCE_PREFERENCES: list = []


class EngineerAnswerer(AnswererBase):
    def __init__(self):
        self.config = PersonaConfig(
            persona=Persona.ENGINEER,
            strategy="graph_primary",
            top_k=6,              # BGE base secondary
            graph_hops=2,         # 2-hop radius, broader than PM
            expansion_cap=15,
            expansion_vocab=ENGINEER_EXPANSION_VOCAB,
            system_prompt=ENGINEER_SYSTEM_PROMPT,
            source_preferences=ENGINEER_SOURCE_PREFERENCES,
        )
