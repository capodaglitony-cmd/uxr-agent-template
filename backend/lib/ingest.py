"""
backend/lib/ingest.py — corpus ingestion pipeline.

Walks the corpus directory, chunks each document, embeds via Voyage,
upserts to Qdrant with metadata derived from filenames + an optional
case_anchor_map.json. Auto-generates a basic anchor map from filenames
if one isn't present.

Usage:
    from lib.ingest import ingest_corpus
    stats = ingest_corpus(corpus_dir="corpus")
"""

import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .voyage_embeddings import embed_documents
from .qdrant_retriever import (
    QDRANT_COLLECTION,
    ensure_collection_exists,
    get_client,
)

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
MIN_CHUNK_CHARS = 100

# File extensions we ingest. Skips binary formats we can't extract.
_TEXT_EXT = {".md", ".txt", ".rst"}
_RICH_EXT = {".pdf", ".docx"}
_SUPPORTED_EXT = _TEXT_EXT | _RICH_EXT


def _load_case_anchor_map(corpus_dir: Path) -> Dict[str, Any]:
    """Load case_anchor_map.json from config/ or auto-generate one."""
    candidates = [
        Path("config/case_anchor_map.json"),
        Path("/root/config/case_anchor_map.json"),
        corpus_dir.parent / "config" / "case_anchor_map.json",
    ]
    for path in candidates:
        if path.exists():
            return json.loads(path.read_text())
    # Auto-generate: every file becomes its own pseudo-case at default weight.
    return {
        "version": "auto-generated",
        "defaults": {"content_weight": {"case_story": 1.0, "unmatched": 0.75}},
        "cases": {},
    }


def _content_weight_for(source_file: str, anchor_map: Dict[str, Any]) -> float:
    """Match a filename against the anchor map's patterns; return weight.
    Falls back to the unmatched default."""
    import fnmatch
    fn_lower = source_file.lower()
    for case_id, case_entry in anchor_map.get("cases", {}).items():
        for pattern in case_entry.get("source_file_patterns", []):
            if fnmatch.fnmatch(fn_lower, pattern.lower()):
                return float(case_entry.get(
                    "content_weight",
                    anchor_map.get("defaults", {}).get("content_weight", {}).get("case_story", 1.0),
                ))
    return float(anchor_map.get("defaults", {}).get("content_weight", {}).get("unmatched", 0.75))


def _extract_text(path: Path) -> str:
    """Extract plain text from a doc file."""
    ext = path.suffix.lower()
    if ext in _TEXT_EXT:
        return path.read_text(encoding="utf-8", errors="replace")
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    if ext == ".docx":
        from docx import Document
        doc = Document(str(path))
        return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
    return ""


def _chunk_text(text: str) -> List[str]:
    """Sliding-window chunker matching lab v2 ingestion (1000/200)."""
    text = text.strip()
    if len(text) < MIN_CHUNK_CHARS:
        return []
    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        chunk = text[start:end].strip()
        if len(chunk) >= MIN_CHUNK_CHARS:
            chunks.append(chunk)
        if end == len(text):
            break
        start = end - CHUNK_OVERLAP
    return chunks


def ingest_corpus(corpus_dir: str = "corpus") -> Dict[str, Any]:
    """Walk corpus_dir, chunk + embed + upsert to Qdrant. Returns stats."""
    root = Path(corpus_dir)
    if not root.exists():
        return {"error": f"corpus directory {corpus_dir} not found", "files": 0, "chunks": 0}

    anchor_map = _load_case_anchor_map(root)
    ensure_collection_exists()
    client = get_client()

    files_processed = 0
    chunks_total = 0
    chunks_to_upsert: List[Dict[str, Any]] = []

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in _SUPPORTED_EXT:
            continue
        if path.name.startswith("."):
            continue

        text = _extract_text(path)
        if not text.strip():
            continue
        chunks = _chunk_text(text)
        if not chunks:
            continue

        weight = _content_weight_for(path.name, anchor_map)
        files_processed += 1
        chunks_total += len(chunks)

        for idx, chunk_text in enumerate(chunks):
            chunk_id = hashlib.md5(
                f"{path.name}_{idx}_{chunk_text[:80]}".encode()
            ).hexdigest()
            chunks_to_upsert.append({
                "id": chunk_id,
                "text": chunk_text,
                "payload": {
                    "text": chunk_text,
                    "source": path.stem,
                    "source_file": path.name,
                    "source_path": str(path.relative_to(root)),
                    "chunk_index": idx,
                    "content_weight": weight,
                    "ingested_at": datetime.utcnow().isoformat(),
                    "corpus_batch": "v0.1-cloud",
                },
            })

    if not chunks_to_upsert:
        return {"files": files_processed, "chunks": 0, "note": "no chunks produced"}

    # Batch embed + upsert.
    BATCH = 64
    upserted = 0
    for i in range(0, len(chunks_to_upsert), BATCH):
        batch = chunks_to_upsert[i:i + BATCH]
        embeddings = embed_documents([c["text"] for c in batch])
        points = [
            {"id": c["id"], "vector": vec, "payload": c["payload"]}
            for c, vec in zip(batch, embeddings)
        ]
        client.upsert(collection_name=QDRANT_COLLECTION, points=points)
        upserted += len(points)

    return {
        "files": files_processed,
        "chunks": chunks_total,
        "upserted": upserted,
        "collection": QDRANT_COLLECTION,
    }
