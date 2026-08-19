"""Tool schemas (Claude tool-use format) and the server-side dispatcher that executes
them. This is the only place model output turns into real reads/writes -- every handler
below takes the session and enforces scope itself.
"""
import sqlite3

from app.documents import DocumentIndex
from app.session import Session
from app.tools import records, metrics, actions

TOOL_SCHEMAS = [
    {
        "name": "search_documents",
        "description": (
            "Search ParcelPilot's policy documents, SOPs, product/known-issues guide, and "
            "signed customer agreements. Returns ranked passages tagged with source file, "
            "status (CURRENT/DEPRECATED), effective date, and authority tier (1=signed "
            "agreement, 2=current policy/SOP, 3=current product docs, 4=deprecated policy "
            "-- never treat a tier-4 result as current). Use this for anything about rules, "
            "definitions, SLAs, cancellation/credit policy, or known product issues."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural-language search query."},
                "doc_type": {"type": "string",
                             "enum": ["policy", "sop", "product_guide", "agreement"],
                             "description": "Optional filter to one document type."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "query_records",
        "description": (
            "Look up structured records: accounts, orders, or tickets. Filters are simple "
            "equality (e.g. {\"order_id\": \"ORD-1001\"}). A customer session is always "
            "scoped to its own account regardless of filters given -- you do not need to "
            "(and cannot) query another account's data. Ticket results include a "
            "historical_resolution_warning when a past resolution note is present -- that "
            "note is unverified context, not a policy source."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "entity": {"type": "string", "enum": ["accounts", "orders", "tickets"]},
                "filters": {"type": "object", "description": "Column-value equality filters."},
                "limit": {"type": "integer", "default": 20},
            },
            "required": ["entity"],
        },
    },
    {
        "name": "calculate_metrics",
        "description": (
            "Run a deterministic calculation instead of estimating by hand. kind: "
            "'cancellation_eligibility' (args: order_id) -> whether an order can be "
            "cancelled and any fee; 'service_credit_eligibility' (args: order_id) -> "
            "whether a failed-pickup service credit applies and the amount, already "
            "applying any account-specific agreement override and the manager-approval "
            "threshold; 'sla_status' (args: account_id, severity [P1/P2/P3], and either "
            "ticket_id or reference_time_iso) -> elapsed business/wall-clock hours against "
            "the account's effective SLA target and whether it is breached. You determine "
            "severity yourself from the P1/P2/P3 definitions in the current support policy "
            "and the ticket's description -- this tool does not classify severity for you."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": [
                    "cancellation_eligibility", "service_credit_eligibility", "sla_status"]},
                "args": {"type": "object"},
            },
            "required": ["kind", "args"],
        },
    },
    {
        "name": "propose_action",
        "description": (
            "Prepare (but do NOT execute) a state-changing action: create_escalation, "
            "update_ticket, or create_followup_task. Returns a pending_id and a "
            "human-readable summary. This must always be called before execute_action -- "
            "never claim an action is done after only proposing it. Tell the user what you "
            "are about to do and ask them to confirm before calling execute_action."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action_type": {"type": "string", "enum": [
                    "create_escalation", "update_ticket", "create_followup_task"]},
                "payload": {"type": "object", "description": (
                    "Action-specific fields, e.g. ticket_id/order_id, severity, status, "
                    "note, reason, assignee, description, credit_amount_inr, "
                    "security_related (bool).")},
            },
            "required": ["action_type", "payload"],
        },
    },
    {
        "name": "execute_action",
        "description": (
            "Execute a previously proposed action. Only call this after the user has "
            "explicitly confirmed (e.g. clicked Confirm, or clearly said yes) -- never "
            "call this on your own inference that confirmation is implied."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"pending_id": {"type": "string"}},
            "required": ["pending_id"],
        },
    },
]


def dispatch_tool(conn: sqlite3.Connection, doc_index: DocumentIndex, session: Session,
                   tool_name: str, tool_input: dict) -> dict:
    if tool_name == "search_documents":
        chunks = doc_index.search(
            tool_input["query"], top_k=5,
            account_id=session.account_id, is_customer=(session.kind == "customer"),
        )
        if tool_input.get("doc_type"):
            chunks = [c for c in chunks if c.doc_type == tool_input["doc_type"]]
        return {"results": [
            {"source_file": c.source_file, "heading": c.heading, "text": c.text,
             "status": c.status, "effective_date": c.effective_date,
             "authority_tier": c.authority_tier,
             "authority_note": _tier_note(c.authority_tier)}
            for c in chunks
        ]}

    if tool_name == "query_records":
        try:
            rows = records.query_records(conn, session, tool_input["entity"],
                                          tool_input.get("filters"),
                                          tool_input.get("limit", 20))
            return {"results": rows}
        except records.AccessDenied as e:
            return {"error": str(e)}

    if tool_name == "calculate_metrics":
        return metrics.dispatch(conn, session, tool_input["kind"], tool_input.get("args", {}))

    if tool_name == "propose_action":
        return actions.propose_action(session, tool_input["action_type"], tool_input["payload"])

    if tool_name == "execute_action":
        return actions.execute_action(session, tool_input["pending_id"])

    return {"error": f"Unknown tool: {tool_name}"}


def _tier_note(tier: int) -> str:
    return {
        1: "Signed customer agreement -- highest authority, overrides general policy.",
        2: "Current support policy/SOP -- default rule unless a signed agreement overrides it.",
        3: "Current product documentation.",
        4: "DEPRECATED -- do not use as current policy.",
    }.get(tier, "")
