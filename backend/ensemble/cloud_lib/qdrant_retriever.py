"""
backend/lib/qdrant_retriever.py — Qdrant Cloud retrieval adapter.

One collection per deployment. Collection name defaults to
`uxr-agent` and can be overridden via the QDRANT_COLLECTION env var.

Returns chunks shaped to match the v0.1 lab response so the lifted
ensemble parser works without modification.
"""

import os
from typing import Any, Dict, List

from .voyage_embeddings import embed_query, VOYAGE_DIM

QDRANT_COLLECTION = os.environ.get("QDRANT_COLLECTION", "uxr-agent")


def get_client():
    """Return a Qdrant client for the deployment's cloud cluster."""
    from qdrant_client import QdrantClient
    return QdrantClient(
        url=os.environ["QDRANT_URL"],
        api_key=os.environ["QDRANT_API_KEY"],
    )


def query_qdrant(query: str, top_k: int = 8) -> List[Dict[str, Any]]:
    """Retrieve top_k chunks for a query. Returns a list of dicts shaped
    to match the lab pipeline's chunk JSON so ensemble/retrieval.py
    parses them without modification."""
    client = get_client()
    qvec = embed_query(query)
    hits = client.query_points(
        collection_name=QDRANT_COLLECTION,
        query=qvec,
        limit=top_k,
        with_payload=True,
    ).points

    chunks: List[Dict[str, Any]] = []
    for hit in hits:
        payload = hit.payload or {}
        score = float(hit.score)
        content_weight = float(payload.get("content_weight", 1.0))
        chunks.append({
            "chunk_id": str(hit.id),
            "text": payload.get("text", ""),
            "source": payload.get("source", payload.get("source_file", "")),
            "score": score,
            "score_pre_weight": score / max(content_weight, 1e-6),
            "vector_score": score,
            "graph_score": 0.0,
            "content_weight_applied": content_weight,
            "collection": "qdrant",
            "metadata": {k: v for k, v in payload.items() if k != "text"},
        })
    return chunks


def ensure_collection_exists():
    """Create the collection if it doesn't already exist. Called once
    by the ingest pipeline before the first upsert."""
    from qdrant_client import QdrantClient
    from qdrant_client.http.models import Distance, VectorParams
    client = get_client()
    existing = {c.name for c in client.get_collections().collections}
    if QDRANT_COLLECTION not in existing:
        client.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=VectorParams(size=VOYAGE_DIM, distance=Distance.COSINE),
        )
