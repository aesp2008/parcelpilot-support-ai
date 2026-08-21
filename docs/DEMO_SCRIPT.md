# Demo Video Script (~5 minutes)

Record this yourself (screen recording + your voice) once the app is running locally or
at the hosted URL. Rough timing below adds to ~5 minutes -- adjust to your own pace.

## 1. Architecture (about 90 seconds)

- One sentence on the problem: ParcelPilot support has to reconcile policies, contracts,
  and operational data that don't always agree, for two audiences (customers, internal
  staff), with real state-changing actions in the mix.
- Show the diagram in your head / on screen: React chat UI -> FastAPI -> one agent loop ->
  four tools (doc search, structured lookup, calculations, mocked actions) -> SQLite (from
  the workbook) + a BM25-indexed PDF pack.
- One sentence on the trust design: signed agreement > current policy/SOP > current
  product docs > historical tickets (context only), enforced in the system prompt *and*
  reflected in how `calculate_metrics` picks account-specific overrides.
- One sentence on access control: enforced in the tool layer (session-scoped SQL filters,
  document-search filtering), not just prompt instructions -- mention the tests.

## 2. Live demo (about 2.5 minutes)

Suggested sequence (swap in your own if something demos better):

1. Log in as **Internal Staff / agent**. Ask: *"Can Northstar cancel ORD-1001 without a
   cancellation fee? Explain why."* -- point out the tool-trace panel showing
   `calculate_metrics` + `query_records` + `search_documents`, and that the answer cites the
   agreement overriding the SOP's 30-minute rule.
2. Ask about a carrier-fault pickup delay (e.g. ORD-2002 for LumenWorks) -- show it applying
   the account's contract-specific credit amount, not the SOP default.
3. Ask about TKT-505 ("possible API key exposure") -- show it classifying P1 and proposing
   an escalation *without executing it*, then click **Confirm** and show the manager-gate
   error when confirming as an `agent` role vs. succeeding as `manager`.
4. Switch to a **Customer** login (e.g. LumenWorks) and ask about a Northstar order or ticket
   -- show it correctly finds nothing, demonstrating account scoping.
5. Open the **Insights** tab (internal only) -- point out the security-flagged ticket at the
   top, the SLA watch list sorted by breach, and the known-issue cluster grouping.

## 3. Key decisions and why (about 1 minute)

Pick 2-3 to talk through out loud (all covered in `docs/ARCHITECTURE.md` if you want exact
wording):

- Why confirmation is a two-phase server-side gate, not a prompt instruction.
- Why BM25 lexical search instead of embeddings (small, fixed document set).
- Why calculations are their own tool instead of trusting the model to do arithmetic.
- The system-prompt fix you made after watching the model burn its tool-call budget
  re-searching for a document that doesn't exist -- good, concrete example of iterating on
  agent behavior, not just code.
- The Gemini free-tier quota issue and how you resolved it (`gemini-3.5-flash-lite`).

## 4. Close (about 15 seconds)

One sentence on what you'd build next if you kept going (see `docs/PRODUCT.md`'s
prioritized list -- real auth/persistent storage is the honest #1).
