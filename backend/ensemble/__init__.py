"""
ensemble/ — Stage 4 scaffolding for the agent2agent corpus system.

Public API:
    from ensemble import (
        PMAnswerer, DesignerAnswerer, EngineerAnswerer,
        Aggregator, AggregatorInput,
        AnswererOutput, AggregatedOutput,
    )

Version 0.1.0 (scaffolding). Core logic wired end-to-end. Retrieval endpoints
on MM24 are not yet built; smoke test will fail on the retrieval call until
they ship.
"""

from .schemas import (
    Persona, EpistemicStatus, Claim, Coverage, RetrievalStats,
    AnswererOutput, ConfidenceBreakdown, Disagreement, EvidenceBase,
    EpistemicStatusCounts, DroppedEntity, SingleSourceFlag, AuditTrail,
    ScoringFields, AggregatedOutput,
)
from .answerer_base import AnswererBase, PersonaConfig
from .answerer_pm import PMAnswerer
from .answerer_designer import DesignerAnswerer
from .answerer_engineer import EngineerAnswerer
from .aggregator import Aggregator, AggregatorInput

__version__ = "0.1.0-scaffolding"

__all__ = [
    "Persona", "EpistemicStatus", "Claim", "Coverage", "RetrievalStats",
    "AnswererOutput", "ConfidenceBreakdown", "Disagreement", "EvidenceBase",
    "EpistemicStatusCounts", "DroppedEntity", "SingleSourceFlag", "AuditTrail",
    "ScoringFields", "AggregatedOutput",
    "AnswererBase", "PersonaConfig",
    "PMAnswerer", "DesignerAnswerer", "EngineerAnswerer",
    "Aggregator", "AggregatorInput",
]
