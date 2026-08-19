"""Mocked auth. A real deployment would swap this for actual customer/staff SSO -- what
matters for this assessment is that every tool call is scoped from a server-held session
object, never from anything the model puts in a tool_use argument.
"""
import uuid
from dataclasses import dataclass


@dataclass
class Session:
    session_id: str
    kind: str  # "customer" | "internal"
    account_id: str | None = None  # set only for kind == "customer"
    role: str | None = None  # "agent" | "manager", set only for kind == "internal"
    label: str = ""


_sessions: dict[str, Session] = {}


def create_customer_session(account_id: str, account_name: str) -> Session:
    sid = str(uuid.uuid4())
    session = Session(session_id=sid, kind="customer", account_id=account_id,
                       label=f"Customer @ {account_name}")
    _sessions[sid] = session
    return session


def create_internal_session(role: str, agent_name: str) -> Session:
    sid = str(uuid.uuid4())
    session = Session(session_id=sid, kind="internal", role=role,
                       label=f"{agent_name} ({role})")
    _sessions[sid] = session
    return session


def get_session(session_id: str) -> Session | None:
    return _sessions.get(session_id)
