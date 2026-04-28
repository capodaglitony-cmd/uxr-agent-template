# Frontend

Next.js 14 (App Router) + Tailwind. Hosts the practitioner-facing widget UI and thin-proxies API calls to the Modal-hosted Python backend.

## Local dev

```bash
cd frontend
npm install
cp .env.example .env.local
# edit .env.local: set MODAL_ENDPOINT to your deployed Modal app URL
npm run dev
# open http://localhost:3000
```

## Production deploy

Push to GitHub → Vercel auto-deploys. Set environment variables in Vercel project settings:

- `MODAL_ENDPOINT` — your Modal app URL (from `modal deploy backend/modal_app.py`)

## Architecture

- `app/page.tsx` — main shell with three-mode toggle (Fast / Deep / Wizard)
- `app/components/` — React components for the Wizard split-view UI
- `app/api/wizard/{start,answer,proposal}/route.ts` — thin proxies to Modal
- `lib/wizard-types.ts` — TypeScript mirrors of the Python wizard schemas
- `lib/api-client.ts` — typed fetch wrapper

The state machine, classifier, and proposal generator stay on the Python side; the frontend is presentation + orchestration only.
