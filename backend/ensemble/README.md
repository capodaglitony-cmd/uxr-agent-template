# /ensemble — The Ensemble Python Package

The three-persona aggregator system. This is a Python package that lives both here (canonical source) and deployed on Mini PC.

Core modules:
- aggregator.py — Rubric-scored divergence classification, four-band system
- answerer_base.py, answerer_pm.py, answerer_designer.py, answerer_engineer.py — Three persona answerers
- retrieval.py — Chunk retrieval with v2 rag_server field support
- schemas.py — Data models (Chunk, PersonaAnswer, AggregatedOutput)
- sme.py, sme_prompt.py — SME synthesis layer with audit gate
- prompts.py — Persona system prompts
- run_ensemble_eval.py — 30-question eval runner

Note: The existing ~/Desktop/ensemble/ directory is the current canonical copy. It will be migrated here.
