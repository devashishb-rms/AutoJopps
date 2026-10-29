# AutoJopps — Prototype v1

**AutoJopps** (auto-J-opps) = **Automated New Job Opportunities and Smooth Job-Search Operations and Job Hops**: receive frequent new job opportunities through automated, fast job applies. Also called AutoJobOpps.

Automated Job Opportunities: a human-in-the-loop job-application agent as a self-service SaaS.
This is the working prototype of the AutoJopps architecture (see the design documents): React UI,
FastAPI control plane, Playwright browser runner, live view, caps and billing, tracking, and the
learning loop (answer memory, portal skills, recorded demonstrations, self-heal).

It ships with **JobHub**, a realistic mock job portal (login, OTP, form, screening questions,
human check, recruiter-status simulation) so the whole flow can be demonstrated end to end without
touching real portals. Real portals are added as adapters (see "Next steps").

## Quick start (macOS / Linux)

```bash
# 1. Python backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium

# 2. Keys (all optional; demo modes kick in when a key is missing)
cd ..
cp .env.example .env        # edit .env — never commit it

# 3. Run (serves the built UI at http://localhost:8000)
./run.sh
```

Open http://localhost:8000, sign in (Google if configured, otherwise "Demo sign-in"), and follow the
8-step setup. Then "Start applying". The first application asks you to sign in to JobHub once in the
live view (password `demo`), then an OTP arrives on the simulated phone shown in the card.

To work on the UI with hot reload: `cd frontend && npm install && npm run dev` (http://localhost:5173,
proxied to the backend). `npm run build` refreshes `frontend/dist`, which the backend serves.

## What is in the box

| Area | Where | Notes |
|---|---|---|
| Google sign-in (OIDC) + demo sign-in | `backend/app/auth.py` | Gmail read scope optional (`GOOGLE_GMAIL_SCOPE=1`, Testing mode); forwarding-alias fallback |
| Resume upload + parsing | `backend/app/profile.py`, `ai.py` | Claude when `ANTHROPIC_API_KEY` is set, heuristic parser otherwise; per-field confidence |
| Naukri-style onboarding, preferences, 2–3 target JDs, alerts + consent | `profile.py`, `frontend/src/pages/Onboarding.jsx` | Consent time recorded (DPDP) |
| Plans ₹501 / ₹1,001 / ₹2,001, Razorpay test checkout, demo activation, daily + monthly caps | `billing.py`, `PlanPicker.jsx` | Signature verification + webhook |
| Orchestrator: discover → score → queue → run, one run per user, status polling | `orchestrator.py` | Scores from skills, target-JD similarity, designation, hard filters |
| Browser runner (Playwright) with HITL states: login, OTP, question, human check, approval | `runner.py` | Vault keeps the portal session only; Google/portal password never stored |
| Live view: screenshot stream + click/type relay over WebSocket | `api.py` (`/api/live/{id}`), `Dashboard.jsx` | Also records demonstrations when asked |
| Notifications: in-app always; SMTP email + WhatsApp Cloud API when configured and consented | `notify.py` | WhatsApp uses a utility template (24-hour rule) |
| Tracking: funnel, states, timeline, run log, proof screenshot | `Applications.jsx` | viewed / in process / shortlisted come from the portal status API |
| Learning loop: answer memory, versioned portal skills, recorded demonstrations → draft skill, self-heal → trial skill, promote | `runner.py`, `api.py`, `Learning.jsx` | "Demo: break the portal" renames JobHub's fields to show self-heal |
| Admin (founder view): MRR, cost per application, HITL rate, skills | `Admin.jsx` | |
| DPDP: delete-my-data, consent record, data minimisation | `profile.py` | Prototype stores the vault as plain JSON; production: KMS-encrypted |

## Demo script (10 minutes)

1. Sign in (demo), upload `samples/sample_resume.txt`, show the pre-filled form and confidence flags.
2. Targets, 2 JDs, alerts with WhatsApp consent, pick Premium, connect Gmail (alias), Start applying.
3. Overview: live agent shows the bot's browser. Sign in once (or "Demo: type portal credentials"), OTP from the simulated phone.
4. Questions: standard ones answered from the profile; an unusual one pauses for you. Human check via the live view.
5. Submitted → proof screenshot → tracker. After ~1 minute JobHub marks it "viewed", later "in process", then a decision.
6. Learning: answer memory now has your answers; recording of your sign-in; "Demo: break the portal" then "Apply now" on a match → self-heal log and a trial skill v2.
7. Admin: MRR, cost per application, human-help events.

## Tests

```bash
python3 samples/api_smoke.py   # drives the full flow through the HTTP API
python3 samples/ui_e2e.py      # drives the full flow through the real UI with Playwright; screenshots in samples/shots/
```

Both expect the server on http://localhost:8000 with a fresh database (`rm autojopps.db data/vault/*`).

## Next steps towards production

- Real portal adapters (Naukri, LinkedIn Easy Apply where terms allow, company career sites) behind the same skill format; Grok Bot as the teacher adapter for new portals.
- Postgres + pgvector, Redis queues, per-tenant KMS keys for the vault, S3 for resumes and proofs.
- Razorpay Subscriptions (recurring) instead of one-time orders; GST invoices.
- Google OAuth verification (restricted Gmail scope) or keep the forwarding-alias route.
- Cell-based deployment, canary bot per cell, cost meter with kill switch (see the architecture document).
- Security review and DPDP notice, retention and breach runbook.

## Licence and credentials

Keys live only in `.env` (git-ignored). Do not paste keys in chat or commit them.
