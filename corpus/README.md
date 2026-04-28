# corpus/

This is where your case stories, STAR narratives, portfolio docs, and any other content you want the agent to be able to answer questions about goes.

## What to drop in

- **Case stories.** Your most polished narrative descriptions of past projects. Markdown, PDF, or DOCX. ~3-10 per portfolio is typical.
- **STAR narratives.** Situation / Task / Action / Result write-ups for individual studies or events. These give the corpus depth on specific moments.
- **Portfolio docs.** Public-facing portfolio site exports, LinkedIn featured items, conference talks transcripts.
- **Method artifacts.** Discussion guides, recruitment screeners, synthesis frameworks — anything that shows how you actually work.

## What NOT to drop in

- **Client-confidential content.** Even if it's "redacted," don't put PHI, PII, internal program names, or unreleased product details into a cloud-deployed agent. Embeddings live in Qdrant Cloud; chunks may be returned verbatim in answers.
- **Anything under NDA.** Sample sizes, internal metrics, pre-launch features. If you're not sure, leave it out.
- **The `_sample/` folder.** Replace it with your own content; don't add to it. The fictional cases there exist purely as a "freshly forked" demo so the agent has something to answer questions about before you've ingested your real content.

## How ingestion works

When you push to your fork (or trigger re-ingest from `/admin`), the Modal backend:

1. Walks this directory recursively
2. Extracts text from `.md`, `.txt`, `.pdf`, `.docx`
3. Chunks each document into ~1000-character segments with 200-character overlap
4. Embeds each chunk via Voyage AI `voyage-3`
5. Upserts to your Qdrant collection with metadata (`source_file`, `chunk_index`, `content_weight`, etc.)

A 50-document portfolio takes ~30-90 seconds to ingest end-to-end and costs ~$0.05 in Voyage embedding fees. Re-ingest only runs when you explicitly trigger it; the daily Vercel deployments don't re-embed anything.

## Optional: case_anchor_map.json

If you want explicit control over which files contribute to which "cases" and what content_weight each gets (1.0 for case stories, 0.75-0.85 for supporting material), drop a `config/case_anchor_map.json` next to `config/profile.yaml`. The format is documented at `docs/case-anchor-map.md`. Without it, the ingester auto-assigns 1.0 weight to every supported file.

## Layout suggestion

```
corpus/
├── README.md                          # this file
├── _sample/                           # delete after first ingest of real content
│   ├── healthcare-scheduling-redesign.md
│   ├── fintech-onboarding-flow.md
│   ├── b2b-saas-dashboard-usability.md
│   ├── internal-tools-workflow.md
│   └── mobile-app-retention-measurement.md
├── case-1-portfolio-narrative.md      # your real content goes here
├── star-narratives.md
└── ...
```
