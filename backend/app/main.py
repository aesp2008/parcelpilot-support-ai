from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.data_loader import load_workbook_to_sqlite
from app.documents import DocumentIndex
from app.session import create_customer_session, create_internal_session, get_session
from app.agent import run_turn
from app.tools import actions
from app.insights import build_insights

app = FastAPI(title="ParcelPilot Support AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_db_conn = load_workbook_to_sqlite()
_doc_index = DocumentIndex()

# server-held per-session chat history, keyed by session_id -- keeps the browser stateless
_chat_histories: dict[str, list[dict]] = {}


class LoginRequest(BaseModel):
    kind: str  # "customer" | "internal"
    account_id: str | None = None
    role: str | None = None  # "agent" | "manager"


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ConfirmRequest(BaseModel):
    session_id: str
    pending_id: str


@app.get("/api/accounts")
def list_accounts():
    """Public list of accounts for the mock login screen's customer picker."""
    conn = _db_conn
    conn.row_factory = None
    cur = conn.execute("SELECT account_id, account_name, plan FROM accounts")
    return [{"account_id": r[0], "account_name": r[1], "plan": r[2]} for r in cur.fetchall()]


@app.post("/api/login")
def login(req: LoginRequest):
    if req.kind == "customer":
        if not req.account_id:
            raise HTTPException(400, "account_id is required for a customer session")
        conn = _db_conn
        row = conn.execute("SELECT account_name FROM accounts WHERE account_id = ?",
                            (req.account_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Unknown account_id")
        session = create_customer_session(req.account_id, row[0])
    elif req.kind == "internal":
        if req.role not in ("agent", "manager"):
            raise HTTPException(400, "role must be 'agent' or 'manager'")
        session = create_internal_session(req.role, "Support Staff")
    else:
        raise HTTPException(400, "kind must be 'customer' or 'internal'")

    _chat_histories[session.session_id] = []
    return {"session_id": session.session_id, "label": session.label, "kind": session.kind}


@app.post("/api/chat")
def chat(req: ChatRequest):
    session = get_session(req.session_id)
    if session is None:
        raise HTTPException(401, "Invalid or expired session")

    history = _chat_histories.get(req.session_id, [])
    result = run_turn(_db_conn, _doc_index, session, history, req.message)
    _chat_histories[req.session_id] = result["history"]

    pending_actions = [
        entry["result"] for entry in result["trace"]
        if entry["tool"] == "propose_action" and entry["result"].get("status") == "awaiting_confirmation"
    ]
    return {"reply": result["reply"], "trace": result["trace"], "pending_actions": pending_actions}


@app.post("/api/actions/confirm")
def confirm_action(req: ConfirmRequest):
    session = get_session(req.session_id)
    if session is None:
        raise HTTPException(401, "Invalid or expired session")
    return actions.execute_action(session, req.pending_id)


@app.get("/api/insights")
def insights(session_id: str):
    session = get_session(session_id)
    if session is None or session.kind != "internal":
        raise HTTPException(403, "Insights are only available to internal ParcelPilot sessions")
    return build_insights(_db_conn)


# Serve the built React frontend if present (production deploy). In local dev the
# frontend runs on its own Vite dev server instead, so this is a no-op there.
_frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
