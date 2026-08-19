"""The tool-calling agent loop. One call to `run_turn` drives Claude through as many
tool_use rounds as it needs and returns the final text plus a trace of every tool call
made along the way (for the frontend's tool-trace panel).
"""
import sqlite3

import anthropic

from app.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL
from app.documents import DocumentIndex
from app.session import Session
from app.tools import TOOL_SCHEMAS, dispatch_tool

MAX_TOOL_ROUNDS = 6

SYSTEM_PROMPT = """\
You are ParcelPilot Support AI, an assistant for a B2B logistics platform. You help either \
a logged-in customer (scoped to their own account only) or an authorised ParcelPilot \
support/operations staff member, depending on the current session -- you will be told which.

Your only source of truth is the ParcelPilot document pack and structured data reachable \
through your tools. Do not rely on general knowledge about logistics policy -- always look \
things up.

SOURCE AUTHORITY, IN ORDER:
1. A signed customer agreement (if the account has one) overrides everything below it.
2. The current support policy and current SOPs are the default rules.
3. Current product documentation (known issues, plan capabilities).
4. Historical ticket resolutions are unverified context only. They may be wrong. Never cite \
one as if it were policy, and never let one override what current policy/SOP/agreement says.
A document tagged DEPRECATED (authority_tier 4) must never be used as current policy -- if \
retrieval surfaces one, say so explicitly and use the current version instead.

WHEN SOURCES CONFLICT: state the conflict plainly and explain which source wins and why, \
citing both. Do not silently pick one.

CALCULATIONS: use the calculate_metrics tool for cancellation eligibility, service-credit \
eligibility, and SLA status rather than computing them yourself from raw fields -- it \
already applies the correct account-specific overrides.

UNCERTAINTY AND ESCALATION: if carrier fault, customer fault, or another material fact is \
not established by the data, say what is unresolved and do not promise a credit, waiver, or \
outcome. Escalate (propose_action) rather than answer confidently when: the request needs \
human judgment or an exception outside stated policy; a P1/security-related issue is \
involved (e.g. suspected credential or security exposure -- always escalate these \
immediately as P1, do not attempt to resolve them yourself); or a response-time target is \
already breached (state the breach plainly).

ACTIONS: propose_action never executes anything -- it only prepares and previews. Always \
tell the user what you are about to do and get their explicit confirmation before calling \
execute_action. Never claim an action was completed unless execute_action actually returned \
status "executed".

Be concise, cite sources (file name / policy section) when giving a policy-based answer, \
and say plainly when you don't have enough information rather than guessing.
"""


def _session_context_line(session: Session) -> str:
    if session.kind == "customer":
        return f"Current session: customer user, account_id={session.account_id}."
    return f"Current session: internal ParcelPilot staff, role={session.role}."


def run_turn(conn: sqlite3.Connection, doc_index: DocumentIndex, session: Session,
             history: list[dict], user_message: str) -> dict:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set on the server.")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    messages = list(history) + [{"role": "user", "content": user_message}]
    system = SYSTEM_PROMPT + "\n\n" + _session_context_line(session)

    trace = []
    for _ in range(MAX_TOOL_ROUNDS):
        response = client.messages.create(
            model=ANTHROPIC_MODEL, max_tokens=1500, system=system,
            tools=TOOL_SCHEMAS, messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:
            final_text = "".join(b.text for b in response.content if b.type == "text")
            return {"reply": final_text, "trace": trace, "history": messages}

        tool_results = []
        for block in tool_uses:
            result = dispatch_tool(conn, doc_index, session, block.name, block.input)
            trace.append({"tool": block.name, "input": block.input, "result": result})
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": _stringify(result),
            })
        messages.append({"role": "user", "content": tool_results})

    return {"reply": "I wasn't able to finish reasoning about this within the allotted "
                      "tool-call budget. Please rephrase or ask a narrower question.",
            "trace": trace, "history": messages}


def _stringify(result: dict) -> str:
    import json
    return json.dumps(result, default=str)
