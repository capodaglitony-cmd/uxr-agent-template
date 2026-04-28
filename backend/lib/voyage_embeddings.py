"""
backend/lib/voyage_embeddings.py — Voyage AI embedding adapter.

Locked default per cloud spec v0.1.2: voyage-3 (1024-dim). Practitioners
shouldn't pick embedding models in v0.1; if a future version exposes
this as a profile.yaml knob, this module gets a small dispatch table.
"""

import os
from typing import List

VOYAGE_MODEL = os.environ.get("VOYAGE_MODEL", "voyage-3")
VOYAGE_DIM = 1024  # voyage-3 produces 1024-dim vectors


def embed_documents(texts: List[str]) -> List[List[float]]:
    """Embed a batch of document chunks for storage in Qdrant.

    voyage-3 supports input_type="document" for retrieval-side encoding;
    queries should use input_type="query" via embed_query() below.
    """
    if not texts:
        return []
    import voyageai
    client = voyageai.Client()  # reads VOYAGE_API_KEY from env
    result = client.embed(texts, model=VOYAGE_MODEL, input_type="document")
    return result.embeddings


def embed_query(text: str) -> List[float]:
    """Embed a single query string for retrieval."""
    import voyageai
    client = voyageai.Client()
    result = client.embed([text], model=VOYAGE_MODEL, input_type="query")
    return result.embeddings[0]
