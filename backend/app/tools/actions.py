"""State-changing action tool: create_escalation, update_ticket, create_followup_task.

Two-phase so confirmation is a server-side gate, not a prompt instruction the model could
skip: `propose_action` records a pending action and returns a human-readable preview;
`execute_action` only runs it if given a pending_id that was actually proposed for this
session and the frontend user clicked "Confirm" (the frontend never calls execute without
that click). Actions above the manager-approval threshold, or flagged as security-related,
additionally require an internal `manager` session to execute -- an `agent` session can
propose but not confirm those.
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from app.session import Session
from app import policy_rules

_ACTION_TYPES = {"create_escalation", "update_ticket", "create_followup_task"}


@dataclass
class PendingAction:
    pending_id: str
    session_id: str
    action_type: str
    payload: dict
    requires_manager: bool
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


_pending: dict[str, PendingAction] = {}
_executed_log: list[dict] = []  # mocked persistence of completed actions


def _requires_manager(action_type: str, payload: dict) -> bool:
    if payload.get("severity") == "P1" or payload.get("security_related"):
        return True
    amount = payload.get("credit_amount_inr")
    if amount is not None and amount > policy_rules.MANAGER_APPROVAL_THRESHOLD_INR:
        return True
    return False


def propose_action(session: Session, action_type: str, payload: dict) -> dict:
    if action_type not in _ACTION_TYPES:
        return {"error": f"Unknown action_type: {action_type}"}

    needs_manager = _requires_manager(action_type, payload)
    pending_id = str(uuid.uuid4())[:8]
    _pending[pending_id] = PendingAction(
        pending_id=pending_id, session_id=session.session_id,
        action_type=action_type, payload=payload, requires_manager=needs_manager,
    )
    summary = _describe(action_type, payload)
    return {
        "pending_id": pending_id,
        "action_type": action_type,
        "summary": summary,
        "requires_manager_approval": needs_manager,
        "status": "awaiting_confirmation",
        "note": "This action has NOT been executed yet. It requires explicit user "
                "confirmation (and manager sign-off if flagged) before it runs.",
    }


def execute_action(session: Session, pending_id: str) -> dict:
    pending = _pending.get(pending_id)
    if pending is None:
        return {"error": "No such pending action (it may have already been executed or "
                          "never proposed)."}
    if pending.session_id != session.session_id:
        return {"error": "This pending action belongs to a different session."}
    if pending.requires_manager and not (session.kind == "internal" and session.role == "manager"):
        return {"error": "This action requires manager approval to execute. Current "
                          "session does not have manager role.",
                "requires_manager_approval": True}

    record = {
        "action_id": f"ACT-{len(_executed_log) + 1:04d}",
        "action_type": pending.action_type,
        "payload": pending.payload,
        "executed_by": session.label,
        "executed_at": datetime.utcnow().isoformat(),
    }
    _executed_log.append(record)
    del _pending[pending_id]
    return {"status": "executed", **record}


def _describe(action_type: str, payload: dict) -> str:
    if action_type == "create_escalation":
        return (f"Create a {payload.get('severity', '?')} escalation for "
                f"{payload.get('ticket_id') or payload.get('order_id') or 'this issue'}: "
                f"{payload.get('reason', '')}")
    if action_type == "update_ticket":
        return (f"Update ticket {payload.get('ticket_id')}: set status to "
                f"{payload.get('status', '?')}" +
                (f", add note: {payload['note']}" if payload.get("note") else ""))
    if action_type == "create_followup_task":
        return (f"Create follow-up task for {payload.get('assignee', 'ops team')}: "
                f"{payload.get('description', '')}")
    return str(payload)


def list_executed_actions() -> list[dict]:
    return list(_executed_log)
