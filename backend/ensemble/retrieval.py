"""
ensemble/retrieval.py

Retrieval wrapper. Each persona calls retrieve() with its configured
strategy and gets back a list of chunks plus metadata.

In the cloud template, retrieval queries the Qdrant collection through
the Modal-hosted FastAPI backend's /retrieve endpoint. The retrieve()
contract preserves the strategy slot (`bge_base_only`, `minilm_only`,
`graph_primary`) for compatibility with the source lab pipeline; in
the cloud variant only `bge_base_only` is wired to the live collection
and the other two fall back to the same source. Graph expansion is
deferred to a future version.

Chunk dataclass fields (vector_score, graph_score, score_pre_weight,
content_weight_applied) are kept for parser symmetry with the lab.
Cloud responses populate vector_score and content_weight_applied;
graph_score defaults to 0.0.
"""

import json
import os
import time
import requests
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Literal
from enum import Enum


# ── Configuration ──────────────────────────────────────────────────────────

# In the cloud template, retrieval routes through the Modal backend's
# /retrieve endpoint. Set MODAL_ENDPOINT to your Modal app URL when
# deploying. For local development with a self-hosted proxy, set
# UXR_PROXY_BASE.
MM24_PROXY_BASE = os.environ.get(
    "MODAL_ENDPOINT",
    os.environ.get("UXR_PROXY_BASE", "http://localhost:8080"),
)

# Per-persona retrieval endpoints. These DO NOT exist yet on the server side.
# Stage 4 execution phase includes building them. Scaffolding points at them
# with the understanding that the smoke test will fail until they ship.
ENDPOINTS = {
    "bge_base_only": f"{MM24_PROXY_BASE}/retrieve/bge",
    "minilm_only": f"{MM24_PROXY_BASE}/retrieve/minilm",
    "graph_primary": f"{MM24_PROXY_BASE}/retrieve/graph",
}

RETRIEVAL_TIMEOUT_SEC = 60


# ── Retrieval contracts ───────────────────────────────────────────────────

RetrievalStrategy = Literal["bge_base_only", "minilm_only", "graph_primary"]


@dataclass
class Chunk:
    """A single retrieved chunk with enough metadata for the Aggregator to
    trace claims back to source and run entity-presence checks.

    v3 fields (from v2 rag_server):
      vector_score: raw cosine similarity from the embedding collection
      graph_score: 1.0 if chunk is a true graph neighbor (not a seed), else 0.0
      score_pre_weight: score after vector + graph_bonus blend, before content_weight
      content_weight_applied: multiplicative tier weight (1.0 case story, 0.85 aiLab,
                              0.75 support, 0.75 default for pre-TOC chunks)

    All four default to values that make v1 responses parse cleanly:
    vector_score=0.0 and score_pre_weight=0.0 mean "unknown" (parser will
    fall back to the blended `score` field), graph_score=0.0 means "not a
    neighbor," content_weight_applied=1.0 means "no reweighting applied."
    """
    chunk_id: str
    text: str
    source: str               # case story id, aiLab doc, etc.
    score: float              # retrieval similarity score (post-weight in v2)
    collection: str           # 'bge_base', 'minilm', 'graph', or 'expansion'
    metadata: dict
    # v3 fields (default-safe for v1 responses)
    vector_score: float = 0.0
    graph_score: float = 0.0
    score_pre_weight: float = 0.0
    content_weight_applied: float = 1.0

    def to_dict(self) -> dict:
        """Serialize for inclusion in eval results JSON."""
        return {
            "chunk_id": self.chunk_id,
            "source": self.source,
            "collection": self.collection,
            "score": self.score,
            "score_pre_weight": self.score_pre_weight,
            "vector_score": self.vector_score,
            "graph_score": self.graph_score,
            "content_weight_applied": self.content_weight_applied,
            # text and metadata intentionally omitted from per-chunk summary
            # to keep results file compact. They live in the Answerer output
            # already via claim attribution.
        }


@dataclass
class RetrievalResult:
    chunks: List[Chunk]
    strategy_used: RetrievalStrategy
    expansion_applied: bool
    elapsed_seconds: float
    error: Optional[str] = None

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)

    @property
    def top_source(self) -> str:
        if not self.chunks:
            return ""
        # Count chunks per source; return the most common.
        counts = {}
        for c in self.chunks:
            counts[c.source] = counts.get(c.source, 0) + 1
        return max(counts.items(), key=lambda kv: kv[1])[0]

    def all_text(self) -> str:
        return "\n\n".join(c.text for c in self.chunks)

    # v3 summary helpers for the eval runner
    def graph_neighbor_count(self) -> int:
        """How many chunks have graph_score > 0 (i.e. surfaced via graph walk,
        not just as retrieval seeds). Sharp signal that the v2 graph fixes
        are firing."""
        return sum(1 for c in self.chunks if c.graph_score > 0.0)

    def content_weight_firing_count(self) -> int:
        """How many chunks had content_weight != 1.0 applied. Counts chunks
        that were either tier-boosted above or tier-reduced below default."""
        return sum(
            1 for c in self.chunks
            if abs(c.content_weight_applied - 1.0) > 1e-6
        )


# ── Retrieval function ────────────────────────────────────────────────────

def retrieve(
    query: str,
    strategy: RetrievalStrategy,
    top_k: int,
    graph_hops: int = 0,
    expansion_cap: Optional[int] = None,
) -> RetrievalResult:
    """
    Call the retrieval endpoint matching the requested strategy and return
    a normalized RetrievalResult. Failures return empty chunks with the error
    set; callers decide whether to propagate or continue.

    Args:
        query: the expanded query string (persona has already prepended its vocab)
        strategy: which retrieval flavor to run
        top_k: max chunks to return
        graph_hops: 0 for no graph expansion, 1 for PM, 2 for Engineer
        expansion_cap: optional ceiling on total chunks after graph expansion
    """
    start = time.time()

    # Cloud path: query Qdrant directly via cloud_lib if QDRANT_URL is set.
    # Local lab path: fall back to HTTP proxy (preserves source pattern).
    if os.environ.get("QDRANT_URL"):
        try:
            from .cloud_lib.qdrant_retriever import query_qdrant
            chunks_data = query_qdrant(query, top_k=top_k)
        except Exception as e:
            return RetrievalResult(
                chunks=[], strategy_used=strategy,
                expansion_applied=(graph_hops > 0),
                elapsed_seconds=round(time.time() - start, 2),
                error=f"Qdrant query failed: {e}",
            )
        chunks = []
        for c in chunks_data:
            chunks.append(Chunk(
                chunk_id=c.get("chunk_id", ""),
                text=c.get("text", ""),
                source=c.get("source", ""),
                score=float(c.get("score", 0.0)),
                collection=c.get("collection", "qdrant"),
                metadata=c.get("metadata", {}),
                vector_score=float(c.get("vector_score", 0.0)),
                graph_score=float(c.get("graph_score", 0.0)),
                score_pre_weight=float(c.get("score_pre_weight", 0.0)),
                content_weight_applied=float(c.get("content_weight_applied", 1.0)),
            ))
        return RetrievalResult(
            chunks=chunks, strategy_used=strategy,
            expansion_applied=False,
            elapsed_seconds=round(time.time() - start, 2),
            error=None,
        )

    endpoint = ENDPOINTS.get(strategy)
    if not endpoint:
        return RetrievalResult(
            chunks=[],
            strategy_used=strategy,
            expansion_applied=False,
            elapsed_seconds=0.0,
            error=f"Unknown strategy: {strategy}",
        )

    payload = {
        "query": query,
        "top_k": top_k,
        "graph_hops": graph_hops,
        "expansion_cap": expansion_cap,
    }

    try:
        resp = requests.post(endpoint, json=payload, timeout=RETRIEVAL_TIMEOUT_SEC)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.Timeout:
        return RetrievalResult(
            chunks=[],
            strategy_used=strategy,
            expansion_applied=(graph_hops > 0),
            elapsed_seconds=round(time.time() - start, 2),
            error=f"Retrieval timed out after {RETRIEVAL_TIMEOUT_SEC}s",
        )
    except Exception as e:
        return RetrievalResult(
            chunks=[],
            strategy_used=strategy,
            expansion_applied=(graph_hops > 0),
            elapsed_seconds=round(time.time() - start, 2),
            error=str(e),
        )

    chunks = []
    for c in data.get("chunks", []):
        # v3: pull v2 rag_server fields off the top-level chunk JSON.
        # Defaults keep v1 responses parsing cleanly. The `score` field
        # remains the single-number blended output the Aggregator uses for
        # ranking — v2 rag_server defines it as post-weight final score.
        chunks.append(Chunk(
            chunk_id=c.get("chunk_id", ""),
            text=c.get("text", ""),
            source=c.get("source", ""),
            score=float(c.get("score", 0.0)),
            collection=c.get("collection", strategy),
            metadata=c.get("metadata", {}),
            vector_score=float(c.get("vector_score", 0.0)),
            graph_score=float(c.get("graph_score", 0.0)),
            score_pre_weight=float(c.get("score_pre_weight", 0.0)),
            content_weight_applied=float(c.get("content_weight_applied", 1.0)),
        ))

    return RetrievalResult(
        chunks=chunks,
        strategy_used=strategy,
        expansion_applied=(graph_hops > 0),
        elapsed_seconds=round(time.time() - start, 2),
        error=None,
    )


# ── Named-entity extraction (scaffolding stub) ────────────────────────────

def extract_entities_from_chunks(chunks: List[Chunk]) -> set:
    """
    Build the set of named entities present in the retrieved chunks.
    Used by the Aggregator's anti-hallucination pass.

    Stage 4 TODO: replace this stub with a real extraction pass.
    Options per Stage 3 Open Question 1:
    - Regex + capitalized-phrase heuristic (fast, lossy)
    - Lightweight NER model call (slower, more accurate)
    - Part of the Aggregator prompt itself (simplest, least reliable)

    For scaffolding, returns a naive set of capitalized multi-word phrases
    and standalone tokens that look like acronyms or proper nouns.
    """
    import re
    entities = set()
    pattern = re.compile(r'\b(?:[A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+)*|[A-Z]{2,})\b')
    for chunk in chunks:
        for match in pattern.findall(chunk.text):
            entities.add(match)
    return entities
