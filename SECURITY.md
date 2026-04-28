# Security Policy

## Reporting a vulnerability

If you find a security issue in `uxr-agent-template`, please **do not file a public GitHub issue**. Instead, email the maintainer directly:

  **capodagli.tony@gmail.com**

Include:
- A description of the vulnerability
- Steps to reproduce (or a proof-of-concept)
- Your assessment of impact (e.g., "exposes practitioner's `ANTHROPIC_API_KEY` to unauthenticated visitors")
- Whether you've shared this with anyone else

Expect an acknowledgment within 72 hours and a fix or mitigation plan within 14 days for confirmed issues.

## Scope

This policy covers vulnerabilities in code shipped under this repository, including:

- The Python ensemble + wizard backend (`backend/`)
- The Vercel frontend (`frontend/`)
- The Modal deployment configuration (`backend/modal_app.py`)
- The ingestion pipeline (`backend/lib/ingest.py`)
- Documentation that could mislead deployers into insecure configurations

This policy does NOT cover:

- Vulnerabilities in upstream dependencies — please report those to the dependency maintainer (Anthropic SDK, Voyage SDK, Qdrant client, Modal SDK, FastAPI, Next.js)
- Misconfiguration of forks (e.g., a deployer who exposed their `ANTHROPIC_API_KEY` in a committed `.env` file is responsible for rotating their own key)
- DoS via heavy use of the ensemble (each query is a real LLM call; rate-limiting is the deployer's responsibility)

## What an attacker could do (threat model snapshot)

| Asset | Risk | Mitigation in template |
|---|---|---|
| `ANTHROPIC_API_KEY` | Theft → mass billing | Stored as Vercel env var, never returned in API responses |
| `VOYAGE_API_KEY`, `QDRANT_API_KEY` | Theft → corpus access | Same as above |
| Corpus content | Exfiltration via prompt injection | Anti-hallucination drop logic + SME audit gate; chunks never echoed to user verbatim |
| `/admin` routes | Unauthorized corpus modification | GitHub OAuth gated by `OWNER_GITHUB_USER` |
| Cost spikes from abusive traffic | Bill explosion | Rate-limiting middleware (deployer config) |

## Hall of fame

Security researchers who responsibly disclose issues will be acknowledged here (with permission).

_None yet._
