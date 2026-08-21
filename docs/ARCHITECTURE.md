# Architecture Note

## Agent design

One tool-calling loop (`backend/app/agent.py`) serves both the customer and internal
contexts. Rather than building two separate agents, the session object (`app/session.py`)
carries `kind` (`customer`/`internal`), `account_id`, and `role`, and every tool call is
scoped from that session server-side. The system prompt tells the model which context it's
in, but the model's own instructions are never the enforcement mechanism -- see "Source
reliability" and "Tool design" below.

The loop is a plain round-trip: send the conversation + tool schemas, execute any
`function_call` the model returns, feed results back as `function_response`, repeat up to
a fixed round budget (5), then return. Capping rounds mattered in practice: an early version
of the system prompt let the model re-issue near-duplicate `search_documents` calls
hunting for a procedure document that doesn't exist in the pack, burning the whole round
budget without ever answering. Fixed by telling the model explicitly that the document
pack is small, repeated near-duplicate searches are wasted, and that "P1 + escalate
immediately" language is sufficient basis to go straight to `propose_action`.

## Tool design

Four tools, each a thin wrapper that takes the session and enforces its own scope:

1. **`search_documents`** -- BM25 lexical search (`rank_bm25`) over the PDF pack, chunked
   by section at startup. Each chunk carries `authority_tier` (1 = signed agreement,
   2 = current policy/SOP, 3 = current product docs, 4 = deprecated), `status`, and
   `effective_date`. A customer session's search results exclude any agreement chunk that
   isn't their own account's -- enforced in `DocumentIndex.search`, not left to the prompt.
2. **`query_records`** -- structured lookup over `accounts`/`orders`/`tickets` (loaded from
   the workbook into SQLite at startup). A customer session's filters are always ANDed with
   their own `account_id` regardless of what the model asks for (`app/tools/records.py`).
   Ticket rows carry a `historical_resolution_warning` whenever a past resolution note is
   present, so the model can't treat it as authoritative without being told otherwise.
3. **`calculate_metrics`** -- cancellation eligibility, service-credit eligibility, and SLA
   business-hours math, kept separate from `query_records` so the model is nudged toward
   calling a calculation rather than doing arithmetic on raw fields itself. Internally it
   re-applies the same precedence rule as the docs: an account's signed-agreement override
   (`app/policy_rules.py`) is checked before falling back to the SOP/policy default.
4. **`propose_action` / `execute_action`** -- the state-changing tool, split into two calls
   so confirmation is a server-side gate rather than a prompt instruction the model could
   skip. `propose_action` only ever writes to an in-memory pending-action table and returns
   a preview; `execute_action` checks that the caller is allowed to confirm it (see below)
   before it "executes" (also mocked -- appended to an in-memory action log).

Access control on `execute_action`: a customer's own pending action can only be confirmed
by that same customer session. Internal staff share one pending-action queue (an agent
proposes, a manager can confirm the same pending id), but anything flagged
`requires_manager_approval` -- P1/security-related actions, or a service credit above the
INR 1,000 threshold -- can only actually execute from a `manager`-role session; an `agent`
session gets an explicit error if it tries.

## Document and structured-data handling

- **Documents**: `pypdf` extracts text at startup, normalized (the PDF's font metrics
  produce doubled inter-word spaces) and split into sections on numbered/short heading
  lines. No embeddings/vector DB -- the corpus is six short documents, so BM25 lexical
  search is sufficient, avoids an external embeddings API/cost, and is trivially fast to
  reindex. This is a real trade-off: it wouldn't scale as-is to a large, growing document
  set, where a vector index would earn its keep.
- **Structured data**: the workbook is loaded into an in-memory SQLite database
  (`app/data_loader.py`) rather than queried as a dataframe or stuffed into the prompt.
  This gives real parameterized SQL (with a column allowlist per entity to avoid
  injection), keeps lookups exact instead of LLM-estimated, and made writing deterministic
  tests straightforward.
- **Policy numbers**: SLA targets, cancellation fees, and credit rules are transcribed once
  into `app/policy_rules.py`, each entry tagged with its source PDF, rather than re-parsing
  tables out of extracted PDF text at call time (fragile) or having the model read them off
  a table itself (error-prone at exactly the numbers that matter). `search_documents`
  remains the source of truth for anything narrative and for surfacing the deprecated v2
  policy. The trade-off: if a document changes, this file and the PDF can drift apart --
  acceptable for a fixed assessment pack, not for a live product (see Product Note).
- **Business hours**: not defined anywhere in the pack, so `app/business_hours.py` assumes
  Mon-Fri 09:00-18:00 IST (documented assumption, consistent with the workbook's
  Asia/Kolkata timezone and LumenWorks' "no weekend/after-hours" clause). All "now" is the
  workbook's stated snapshot time (2026-08-16 11:00 IST), not wall-clock time, since the
  dataset itself is frozen there.

## Source reliability and conflict handling

This is the backbone of the system prompt, not a bolt-on: **signed agreement > current
policy/SOP > current product docs > historical tickets (context only)**. Concretely:

- Deprecated documents (Support Policy v2) are still indexed and searchable, but every
  result carries `status: DEPRECATED` and an explicit "do not use as current policy" note;
  the prompt instructs the model to say so out loud if one surfaces.
- Historical ticket resolutions are always labeled unverified context, never treated as a
  policy source. Two of the seeded historical tickets (TKT-450, TKT-451) contain resolutions
  that were actually wrong against current policy/agreements -- the point isn't to catch
  those two specific tickets, but that the same labeling applies uniformly to any
  historical ticket the model encounters.
- When a customer agreement and the general SOP would give different answers, the model is
  told to state the conflict and say which one wins and why, rather than silently picking
  one.
- Under factual uncertainty (fault not established, timing ambiguous -- e.g. the SwiftShip
  webhook-delay known issue, KI-211, which can make an order look un-picked-up when it
  isn't), the model is told not to promise a credit/waiver and to say what's unresolved.
- The internal Insights dashboard (`app/insights.py`) is intentionally *not* LLM-based --
  it runs deterministic keyword/threshold rules over the same data, so its output is
  reproducible and cheap to refresh, at the cost of a coarser severity classification than
  the chat agent's actual policy-grounded reasoning (see Product Note).

## Major trade-offs

- **Gemini over Claude for the agent loop.** Built against Claude's tool-use format
  originally; switched to Gemini function calling because that's the API key available for
  this build. The tool schemas and dispatcher are provider-agnostic (`app/tools/__init__.py`)
  -- only `app/agent.py`'s request/response plumbing is Gemini-specific, so swapping
  providers again would be a contained change.
- **Free-tier model selection.** The newest preview model (`gemini-3.6-flash`) turned out
  to have a 20-requests/day free quota, too tight for iterative development and a live
  demo. Switched to `gemini-3.5-flash-lite`, which has a materially higher free daily quota
  at the cost of some model capability -- an explicit cost/reliability trade documented
  here rather than hidden.
- **Lexical retrieval, not embeddings.** Covered above -- right-sized for six documents,
  would need revisiting at real-product scale.
- **In-memory data, not a real database.** SQLite `:memory:` and in-process dicts
  (sessions, pending actions) reset on restart. Fine for an assessment; a real deployment
  needs persistent storage and a real auth provider, both called out as explicit
  known-gaps in the Product Note.
