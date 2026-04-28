# Deploy

Step-by-step from fork to live agent. Total time ~12-18 minutes.

## 1. Fork the repo

Click the **Fork** button at the top of this page. You'll get a copy under your GitHub account at `github.com/<your-handle>/uxr-agent-template`.

## 2. Sign up for the four services

You'll need accounts at four vendors. All have generous free tiers; total monthly cost in steady state is ~$9-18.

| Service | What it does | Free tier | Sign up |
|---|---|---|---|
| **Anthropic** | Claude API for the persona ensemble + SME synthesis | $5 free credit | https://console.anthropic.com |
| **Voyage AI** | `voyage-3` embeddings for your corpus | 50M tokens free | https://dash.voyageai.com |
| **Qdrant Cloud** | Vector store for retrieval | 1GB free, fits ~50 docs | https://cloud.qdrant.io |
| **Modal** | Serverless Python backend hosting | $30/month free credits | https://modal.com |

After signup, grab one secret from each:

```
ANTHROPIC_API_KEY=sk-ant-...
VOYAGE_API_KEY=pa-...
QDRANT_URL=https://....qdrant.cloud
QDRANT_API_KEY=...
```

## 3. Configure your profile

Copy the example profile:

```bash
cp config/profile.yaml.example config/profile.yaml
```

Edit `config/profile.yaml`:

```yaml
owner:
  name: "Your Name"
  github: your-github-handle           # used for /admin auth gate
  specialty: "UX research"             # what kind of work
  bio_short: "Senior UXR with 8 years in fintech and B2B SaaS."
  bio_url: "https://your-portfolio.com"

branding:
  agent_handle: "yn-uxragent"          # appears in widget header + .vercel.app URL
  accent_color: "#3a7ab8"              # any CSS color
```

## 4. Deploy the Python backend to Modal

The backend wraps the ensemble pipeline (3 personas + aggregator + SME) and the wizard cascade as a FastAPI service.

```bash
pip install modal
modal token new                        # one-time auth
modal deploy backend/modal_app.py
```

Modal will print a public URL like `https://your-handle--uxr-agent-template-fastapi-app.modal.run`. **Copy that URL** — you'll set it as an env var in Vercel next.

## 5. Deploy the frontend to Vercel

```bash
# from the repo root
npx vercel deploy
```

Or click the Vercel "Import Git Repository" button and pick your fork.

When Vercel prompts for environment variables, set:

```
ANTHROPIC_API_KEY=sk-ant-...
VOYAGE_API_KEY=pa-...
QDRANT_URL=https://....qdrant.cloud
QDRANT_API_KEY=...
MODAL_ENDPOINT=https://...modal.run    # from step 4
OWNER_GITHUB_USER=your-github-handle    # gates /admin to your account only
```

After the first deploy succeeds, **rename the Vercel project** if you want a portfolio-friendly URL. Project Settings → General → Project Name. Setting it to `yn-uxragent` gives you `yn-uxragent.vercel.app`. (Defaults to your repo name if you don't change it.)

## 6. Custom domain (optional)

The default `<project-name>.vercel.app` URL works fine for most practitioners — it's an honest signal: "I deployed an open-source template." If you want a vanity domain like `agent.yourname.com`, two paths:

- **Vercel Pro** ($20/month) — official path. Settings → Domains → add your domain → follow DNS instructions.
- **Cloudflare proxy in front of Hobby** (free + ~$15/year for the domain). Buy domain at any registrar, point it at Cloudflare DNS, set a CNAME rewrite to `<project>.vercel.app`. Documentation: see [docs/cloudflare-custom-domain.md](./docs/cloudflare-custom-domain.md).

Neither is required.

## 7. Drop your corpus in and ingest

```bash
# Place your case stories, STAR narratives, and portfolio docs:
cp ~/path/to/your/case_stories/*.md ./corpus/
cp ~/path/to/your/portfolio/*.pdf ./corpus/

# Optional: author config/case_anchor_map.json to give your cases
# explicit IDs and content weights. If you skip this, the ingester
# auto-generates one from filenames.

git add corpus/ config/
git commit -m "Add my corpus"
git push
```

Vercel will redeploy automatically. To trigger ingestion against your new files:

```bash
curl -X POST https://<your-project>.vercel.app/api/admin/ingest \
  -H "Cookie: $(your-session-cookie)" \
  -H "Content-Type: application/json"
```

Or visit `https://<your-project>.vercel.app/admin` in a browser, sign in with your GitHub account (matched against `OWNER_GITHUB_USER`), and click **Re-ingest corpus**.

Ingest runs on Modal: chunks every doc, calls Voyage to embed, writes to your Qdrant collection. Takes ~30-90 seconds for a 50-doc portfolio.

## 8. You're live

Open `https://<your-project>.vercel.app/`. The widget loads with three modes (Fast / Deep / Wizard). Try a question about something in your corpus — Fast mode is the quickest sanity check.

For a more thorough test, switch to Wizard mode and walk through the cascade. The proposal that drops out should be grounded in your actual case stories.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| All three personas return empty claims | Modal endpoint not reachable from Vercel — check `MODAL_ENDPOINT` env var |
| `/api/wizard/start` returns 503 | Wizard package import failed on Modal — check `modal app logs` |
| Empty retrieval, "no chunks found" | Corpus not ingested yet — visit `/admin` and click Re-ingest |
| Hiring manager sees 401 on `/admin` | Expected. Only the GitHub user matching `OWNER_GITHUB_USER` can access it. |
| SME outputs flagged as `audit_rejected` | The audit gate is doing its job — read the divergence band and dropped claims for context |

If something's broken, file an issue on the source repo at https://github.com/capodaglitony-cmd/uxr-agent-template/issues with logs from `modal app logs` and the relevant Vercel function logs.
