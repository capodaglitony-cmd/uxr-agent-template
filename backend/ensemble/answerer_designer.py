"""
ensemble/answerer_designer.py

Designer persona. Per Persona Retrieval Spec v1 Stage 1.

Retrieval strategy:
- Primary: MiniLM, top-10 chunks (broader semantic net for experiential language)
- Secondary: none. Designer stays close to retrieved chunks. Graph expansion
  risks wandering into system or outcome language and diluting experiential focus.
- Ceiling: 10 chunks total

Role and stance:
- Asks what users experienced, where the experience broke, what we learned.
- Lives closest to the user and the prototype.
- Craft-oriented. Journey-aware. Participant-voice-preserving.
"""

from .answerer_base import AnswererBase, PersonaConfig
from .schemas import Persona
from .prompts import DESIGNER_SYSTEM_PROMPT, DESIGNER_EXPANSION_VOCAB


# Empty by default in the cloud template; see PM_SOURCE_PREFERENCES note.
DESIGNER_SOURCE_PREFERENCES: list = []


class DesignerAnswerer(AnswererBase):
    def __init__(self):
        self.config = PersonaConfig(
            persona=Persona.DESIGNER,
            strategy="minilm_only",
            top_k=10,
            graph_hops=0,         # no graph expansion by design
            expansion_cap=10,
            expansion_vocab=DESIGNER_EXPANSION_VOCAB,
            system_prompt=DESIGNER_SYSTEM_PROMPT,
            source_preferences=DESIGNER_SOURCE_PREFERENCES,
        )
