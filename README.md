# ParcelPilot Support AI

An AI support agent for ParcelPilot, a B2B logistics platform. Built for the CalQuity AI
Engineer hiring assessment. Supports both a **customer-facing** chat context and an
**internal ParcelPilot staff** context (agent / manager roles), with a shared tool-calling
agent underneath and access control enforced server-side.

See `docs/ARCHITECTURE.md` and `docs/PRODUCT.md` for the design write-up, and
`docs/AI_TOOL_USAGE.md` for how AI coding tools were used to build this.

## What's here

- `backend/` -- FastAPI service: the agent loop (Gemini function calling), the four tools
  (document search, structured-data lookup, calculations, mocked actions), session/access
  control, and the proactive-issue-detection endpoint.
- `frontend/` -- React (Vite) chat UI with a mock login, a tool-trace panel, inline
  action-confirmation UI, and an internal-only Insights dashboard.
- `data_pack/` -- the supplied policy/SOP/agreement PDFs and the accounts/orders/tickets
  workbook. Loaded at startup; nothing here is hardcoded into the app logic.

## Running locally

Requires Python 3.10+ and Node 18+.

### 1. Backend

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # then edit .env and paste your GEMINI_API_KEY
python -m uvicorn app.main:app --reload --port 8000
```

The backend loads the workbook into an in-memory SQLite database and indexes the PDF pack
on startup, so there's no separate seed/migration step.

Run the test suite (no API key needed -- these exercise the data layer, calculations, and
access control, not the LLM):

```bash
cd backend
python -m pytest tests/ -v
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Visit `http://localhost:5173`. The Vite dev server proxies `/api` to the backend on
`:8000` (see `frontend/vite.config.js`).

### 3. Production-style single-service run

```bash
cd frontend && npm install && npm run build
cd ../backend && pip install -r requirements.txt
GEMINI_API_KEY=... python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

With `frontend/dist/` built, FastAPI serves it directly at `/`, so one process serves both
the API and the UI. This is what's deployed at the hosted URL (see below).

## Getting a Gemini API key

1. Go to Google AI Studio (aistudio.google.com), sign in, and create an API key.
2. The free tier is quota-limited per model/day -- this project defaults to
   `gemini-3.5-flash-lite`, which carries a much higher free daily quota than the newer
   flagship preview models. Override with `GEMINI_MODEL` if you have a paid key and want a
   stronger model.

## Hosted app

[URL to be added once deployed]

## Trying it out

Log in as **Internal Staff / agent** or pick a **Customer** account, then ask things like:

- "Can Northstar cancel ORD-1001 without a cancellation fee? Explain why."
- "A pickup is three hours late because of carrier fault -- should I get a service credit?"
- "There's possible API key exposure reported in TKT-505, what should I do?" (internal)
- As a LumenWorks customer, try asking about Northstar's account -- it will correctly find
  nothing.

Switch to a **manager** internal session to see the manager-approval gate on
higher-value/P1 actions.
