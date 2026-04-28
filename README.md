# uxr-agent-template

**A self-deployed UX research portfolio agent.** Drop your case stories into `corpus/`, set three API keys, click deploy. Hiring managers and collaborators visit your URL and get answers grounded in your actual work — three-persona divergence preserved, anti-hallucination gate active, and a Wizard mode that produces real research proposals on demand.

> Built on the architecture from [Tony Capodagli's uxr-agent research project](https://github.com/capodaglitony-cmd/uxr-agent) (2025-2026). This is the cloud-deployable template fork. The local research-grade version stays in the source repo.

---

## What you get

Three modes, all running against your corpus:

- **Fast** — ~3-second conversational answer with chunk citations.
- **Deep** — ~25-second three-persona ensemble (PM / Designer / Engineer) with divergence-band classification, anti-hallucination drops, and SME synthesis with a hard audit gate.
- **Wizard** — split-view conversational cascade through the Playing-to-Win strategy framework. Ends in a 2-page research proposal markdown brief, methodologically grounded in your case stories.

The runtime architecture, prompt templates, anti-hallucination logic, and SME audit gate carry from the lab repo unchanged. **You're not building an AI tool. You're filling in the corpus of an opinionated harness.**

---

## What stays locked, what you fill in

This template is tuned for **UX research practitioners** and adjacent roles (PMs, Designers, Devs, hiring managers). The architecture-level decisions stay locked because the audience already gets them right:

| Locked | Yours to fill in |
|---|---|
| 3-persona stack (PM / Designer / Engineer) | `corpus/` content |
| Playing-to-Win wizard cascade (5 questions + fork) | `config/profile.yaml` (your name, specialty, branding) |
| Method recommendation table (UX methods only) | `config/case_anchor_map.json` (optional; auto-generated from filenames if missing) |
| Embedding model (Voyage `voyage-3`) | Your three API keys (Anthropic + Voyage + Qdrant) |
| Vector store (Qdrant Cloud) | Optional: persona-prompt overrides for your domain emphasis |
| Anti-hallucination + SME audit gate | |

---

## Deploy

See [DEPLOY.md](./DEPLOY.md) for the step-by-step. Total time from fork to live agent: **12-18 minutes** (most of it corpus ingestion).

```
1. Fork this repo
2. Click "Deploy to Vercel" → set ANTHROPIC_API_KEY, VOYAGE_API_KEY,
   QDRANT_URL, QDRANT_API_KEY, OWNER_GITHUB_USER, MODAL_ENDPOINT
3. modal deploy backend/modal_app.py from your fork
4. Drop your case stories into corpus/, push, and trigger ingestion
   from /admin (auth-gated to your GitHub account)
5. Done — your agent is live at <your-project-name>.vercel.app
```

---

## Cost

Practitioner-scale (~100 queries/month from recruiters and collaborators):

| Item | Monthly |
|---|---|
| Anthropic API (mix of Fast + Deep + Wizard with prompt caching) | $4-8 |
| Voyage AI embeddings (one-time ingest, re-runs on corpus edits) | <$0.10 |
| Qdrant Cloud free tier (1GB, fits ~50-doc portfolios) | $0 |
| Vercel Hobby tier | $0 |
| Modal (1 always-on backend, light traffic) | $5-10 |
| **Total** | **$9-18/month** |

All bills go directly to your accounts at each vendor. The template author covers nothing.

---

## Status

**v0.1 — backend-ready, frontend in progress.**

What's deployable today: the Python backend (FastAPI on Modal) wraps the entire ensemble pipeline + wizard cascade. Routes are testable via `curl`.

What's coming in v0.2: the Next.js frontend port of the widget UI from the lab repo, including the three-mode toggle and the Wizard split-view layout.

What's coming in v0.3: drag-and-drop corpus upload via an auth-gated `/admin` panel.

See [docs/ROADMAP.md](./docs/ROADMAP.md) for the staged plan.

---

## License

Apache License 2.0. See [LICENSE](./LICENSE) and [NOTICE](./NOTICE).

The short version: do whatever you want with this code, keep the copyright notice, don't sue Tony or other contributors over patents related to the project.

## Security

Found a vulnerability? See [SECURITY.md](./SECURITY.md) for disclosure.

## Contributing

Issues and PRs welcome. The architecture is locked at the levels listed above; everything else (UI polish, additional embedding providers, alternative LLM backends, ingestion improvements) is fair game.
