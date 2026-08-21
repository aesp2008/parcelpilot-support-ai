"""The tool-calling agent loop, built on Gemini function calling. One call to `run_turn`
drives the model through as many function-call rounds as it needs and returns the final
text plus a trace of every tool call made along the way (for the frontend's tool-trace
panel).
"""
import sqlite3

from google import genai
from google.genai import types

from app.config import GEMINI_API_KEY, GEMINI_MODEL
from app.documents import DocumentIndex
from app.session import Session
from app.tools import TOOL_SCHEMAS, dispatch_tool

MAX_TOOL_ROUNDS = 5
MAX_OUTPUT_TOKENS = 1024  # keep responses tight -- this project runs on a metered key

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

TOOL-CALL BUDGET: you have a small number of tool calls available per turn, so use them \
deliberately. Never issue two search_documents calls with similar wording -- if a search \
already returned relevant passages, use what you have instead of rephrasing and searching \
again. The document pack is small (six files); if a specific procedure isn't in the first \
relevant result, it likely doesn't exist as a separate document, and you should reason from \
the general policy/severity rules you already found rather than continuing to search for it. \
For anything you can already decide from a P1/P2/P3 definition plus "escalate immediately" \
language (e.g. any security/credential-exposure report), go straight to propose_action \
instead of searching further.

GROUNDING: never state a specific number, fee, threshold, or time window unless it \
appears verbatim in a tool result you received in this conversation. This pack has several \
similar-looking thresholds in the same document (e.g. the cancellation SOP's 30-minute fee \
grace period is a different rule from its service-credit delay threshold) -- do not blend \
them, and do not add "for context, the general rule is..." asides unless you actually \
called a tool this turn that confirms the specific number you are about to state. If you \
are not certain a detail is grounded in an actual tool result, leave it out rather than \
guessing at it.
"""


def _to_gemini_tools() -> list[types.Tool]:
    declarations = [
        types.FunctionDeclaration(
            name=schema["name"],
            description=schema["description"],
            parameters=schema["input_schema"],
        )
        for schema in TOOL_SCHEMAS
    ]
    return [types.Tool(function_declarations=declarations)]


def _session_context_line(session: Session) -> str:
    if session.kind == "customer":
        return f"Current session: customer user, account_id={session.account_id}."
    return f"Current session: internal ParcelPilot staff, role={session.role}."


def run_turn(conn: sqlite3.Connection, doc_index: DocumentIndex, session: Session,
             history: list[types.Content], user_message: str) -> dict:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set on the server.")

    client = genai.Client(api_key=GEMINI_API_KEY)
    contents = list(history) + [types.Content(role="user", parts=[types.Part(text=user_message)])]
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT + "\n\n" + _session_context_line(session),
        tools=_to_gemini_tools(),
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )

    trace = []
    for _ in range(MAX_TOOL_ROUNDS):
        response = client.models.generate_content(
            model=GEMINI_MODEL, contents=contents, config=config,
        )
        candidate = response.candidates[0]
        contents.append(candidate.content)

        function_calls = [p.function_call for p in candidate.content.parts if p.function_call]
        if not function_calls:
            final_text = "".join(p.text for p in candidate.content.parts if p.text)
            return {"reply": final_text, "trace": trace, "history": contents}

        response_parts = []
        for fc in function_calls:
            result = dispatch_tool(conn, doc_index, session, fc.name, dict(fc.args))
            trace.append({"tool": fc.name, "input": dict(fc.args), "result": result})
            response_parts.append(types.Part(function_response=types.FunctionResponse(
                name=fc.name, response={"result": result},
            )))
        contents.append(types.Content(role="user", parts=response_parts))

    return {"reply": "I wasn't able to finish reasoning about this within the allotted "
                      "tool-call budget. Please rephrase or ask a narrower question.",
            "trace": trace, "history": contents}
