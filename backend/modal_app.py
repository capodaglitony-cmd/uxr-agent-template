"""
backend/modal_app.py — Modal-hosted FastAPI deployment.

Wraps the ensemble pipeline + wizard cascade as a public HTTP API on
Modal. Vercel's frontend functions thin-proxy to this endpoint via the
MODAL_ENDPOINT env var.

Deploy with:
    modal deploy backend/modal_app.py

Modal will print a public URL like
    https://<handle>--uxr-agent-template-fastapi-app.modal.run
which you set as MODAL_ENDPOINT in your Vercel project's env vars.

Routes match the source lab's proxy v4 plus admin/ingest:
    GET  /                  - health check
    POST /generate          - LLM passthrough to Anthropic Claude
    POST /retrieve/bge      - Qdrant retrieval (graph/minilm aliases too)
    POST /retrieve/minilm   - alias of /retrieve/bge in v0.1
    POST /retrieve/graph    - alias of /retrieve/bge in v0.1
    POST /ensemble          - 3-persona + aggregator + SME
    POST /wizard/start      - empty cascade state + first question
    POST /wizard/answer     - apply one answer, branch on outcome
    POST /wizard/proposal   - regenerate proposal from terminal state
    POST /admin/ingest      - chunk + embed + store corpus to Qdrant

The /admin/ingest route reads files from the corpus/ directory baked
into the Modal image at deploy time. To re-ingest after corpus changes,
redeploy: `modal deploy backend/modal_app.py`.
"""

import os
from pathlib import Path

import modal


# ── Modal app + image ────────────────────────────────────────────────────

app = modal.App("uxr-agent-template")

# Build the runtime image: install Python deps, copy ensemble code + corpus.
# `add_local_python_source` ships the package; `add_local_dir` ships the
# corpus alongside so /admin/ingest can read it.
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_requirements("requirements.txt")
    .add_local_python_source("ensemble")
    .add_local_dir("../corpus", remote_path="/root/corpus")
    .add_local_dir("../config", remote_path="/root/config")
)


# ── Secrets ──────────────────────────────────────────────────────────────

# Set these as Modal secrets before first deploy:
#   modal secret create anthropic-api-key ANTHROPIC_API_KEY=sk-ant-...
#   modal secret create voyage-api-key VOYAGE_API_KEY=pa-...
#   modal secret create qdrant-config QDRANT_URL=https://... QDRANT_API_KEY=...

secrets = [
    modal.Secret.from_name("anthropic-api-key"),
    modal.Secret.from_name("voyage-api-key"),
    modal.Secret.from_name("qdrant-config"),
]


# ── FastAPI app ──────────────────────────────────────────────────────────

@app.function(image=image, secrets=secrets, timeout=300)
@modal.asgi_app()
def fastapi_app():
    """The entire FastAPI surface lives inside this function so Modal
    can introspect the asgi_app decorator. Imports happen here too so
    Modal's image build doesn't try to import LLM clients at deploy
    time."""
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    from typing import Any, Dict, List, Optional

    from ensemble import (
        PMAnswerer, DesignerAnswerer, EngineerAnswerer,
        Aggregator, AggregatorInput,
    )
    from ensemble.wizard import (
        CascadeStep, ProposalGenerator, WizardAnswer, WizardState,
    )

    api = FastAPI(title="uxr-agent-template")

    api.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],   # tighten in prod via env-var allowlist
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Module-level instances reused across requests.
    pm = PMAnswerer()
    designer = DesignerAnswerer()
    engineer = EngineerAnswerer()
    aggregator = Aggregator()
    wizard_generator = ProposalGenerator()

    # ── Schemas ──────────────────────────────────────────────────────

    class QueryBody(BaseModel):
        query: str
        top_k: int = 8

    class GenerateBody(BaseModel):
        prompt: str
        model: Optional[str] = None
        options: Optional[Dict[str, Any]] = None

    class EnsembleBody(BaseModel):
        question: str

    class WizardAnswerBody(BaseModel):
        state: Dict[str, Any]
        answer: Dict[str, Any]

    class WizardProposalBody(BaseModel):
        state: Dict[str, Any]

    # ── Health ───────────────────────────────────────────────────────

    @api.get("/")
    def root():
        return {
            "status": "ok",
            "service": "uxr-agent-template",
            "routes": [
                "/generate", "/retrieve/{bge,minilm,graph}",
                "/ensemble", "/wizard/start", "/wizard/answer",
                "/wizard/proposal", "/admin/ingest",
            ],
        }

    # ── /generate (Anthropic passthrough for persona + SME calls) ────

    @api.post("/generate")
    def generate(body: GenerateBody):
        from anthropic import Anthropic
        client = Anthropic()  # reads ANTHROPIC_API_KEY from env
        model = body.model or os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        try:
            msg = client.messages.create(
                model=model,
                max_tokens=2048,
                messages=[{"role": "user", "content": body.prompt}],
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Anthropic call failed: {e}")
        # Match the {"response": str} shape the lifted ensemble code expects.
        text = "".join(b.text for b in msg.content if hasattr(b, "text"))
        return {"response": text, "model": model}

    # ── /retrieve/* (Qdrant query) ───────────────────────────────────

    @api.post("/retrieve/bge")
    @api.post("/retrieve/minilm")
    @api.post("/retrieve/graph")
    def retrieve(body: QueryBody):
        from lib.qdrant_retriever import query_qdrant
        try:
            chunks = query_qdrant(body.query, top_k=body.top_k)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Qdrant query failed: {e}")
        return {"chunks": chunks, "strategy": "bge_base_only", "count": len(chunks)}

    # ── /ensemble (Deep mode) ────────────────────────────────────────

    @api.post("/ensemble")
    def ensemble(body: EnsembleBody):
        question = body.question.strip()
        if not question:
            raise HTTPException(400, "Missing question")
        try:
            pm_out = pm.answer(question)
            des_out = designer.answer(question)
            eng_out = engineer.answer(question)
            from ensemble.retrieval import retrieve as ens_retrieve
            pm_chunks = ens_retrieve(question, pm.config.strategy, pm.config.top_k,
                                      pm.config.graph_hops, pm.config.expansion_cap).chunks
            des_chunks = ens_retrieve(question, designer.config.strategy, designer.config.top_k,
                                       designer.config.graph_hops, designer.config.expansion_cap).chunks
            eng_chunks = ens_retrieve(question, engineer.config.strategy, engineer.config.top_k,
                                       engineer.config.graph_hops, engineer.config.expansion_cap).chunks
            agg = aggregator.aggregate(AggregatorInput(
                pm_output=pm_out, designer_output=des_out, engineer_output=eng_out,
                pm_chunks=pm_chunks, designer_chunks=des_chunks, engineer_chunks=eng_chunks,
            ))
        except Exception as e:
            raise HTTPException(502, f"Ensemble failed: {e}")
        return {
            "status": "ok",
            "question": question,
            "aggregated": agg.to_dict(),
        }

    # ── /wizard/* ────────────────────────────────────────────────────

    def _question_to_dict(q):
        if q is None:
            return None
        return {
            "step": q.step.value, "prompt": q.prompt,
            "pills": list(q.pills), "multi_select": bool(q.multi_select),
            "free_text_allowed": bool(q.free_text_allowed), "note": q.note or "",
        }

    @api.post("/wizard/start")
    def wizard_start():
        state = WizardState()
        return {
            "status": "ok",
            "state": state.to_payload(),
            "next_question": _question_to_dict(state.next_question()),
        }

    @api.post("/wizard/answer")
    def wizard_answer(body: WizardAnswerBody):
        try:
            state = WizardState.from_payload(body.state)
            answer = WizardAnswer(
                step=CascadeStep(body.answer["step"]),
                pills_selected=list(body.answer.get("pills_selected") or []),
                free_text=body.answer.get("free_text") or "",
            )
            state.record_answer(answer)
        except (ValueError, KeyError) as e:
            raise HTTPException(400, str(e))

        if state.guardrail_tripped:
            proposal = ProposalGenerator(dry_run=True).generate(state)
            return {"status": "guardrail", "state": state.to_payload(),
                    "next_question": None, "proposal": proposal.to_payload()}

        if state.is_complete():
            try:
                proposal = wizard_generator.generate(state)
            except Exception as e:
                raise HTTPException(502, f"Proposal generation failed: {e}")
            outer = "complete" if proposal.status == "proposal" else proposal.status
            return {"status": outer, "state": state.to_payload(),
                    "next_question": None, "proposal": proposal.to_payload()}

        return {"status": "in_progress", "state": state.to_payload(),
                "next_question": _question_to_dict(state.next_question())}

    @api.post("/wizard/proposal")
    def wizard_proposal(body: WizardProposalBody):
        try:
            state = WizardState.from_payload(body.state)
        except Exception as e:
            raise HTTPException(400, f"Invalid state: {e}")
        if not state.is_terminal():
            raise HTTPException(400, "Cascade not terminal yet")
        try:
            proposal = wizard_generator.generate(state)
        except Exception as e:
            raise HTTPException(502, f"Proposal generation failed: {e}")
        return {"status": "ok", "proposal": proposal.to_payload()}

    # ── /admin/ingest (auth-gated by Vercel) ─────────────────────────

    class IngestBody(BaseModel):
        confirm: bool = False

    @api.post("/admin/ingest")
    def admin_ingest(body: IngestBody, request: Request):
        # Vercel handles GitHub OAuth; this endpoint trusts the caller.
        # If you expose this Modal URL directly to the internet, add an
        # X-Admin-Token header check here.
        if not body.confirm:
            raise HTTPException(400, "Ingestion requires confirm=true")
        from lib.ingest import ingest_corpus
        try:
            stats = ingest_corpus(corpus_dir="/root/corpus")
        except Exception as e:
            raise HTTPException(502, f"Ingest failed: {e}")
        return {"status": "ok", "stats": stats}

    return api
