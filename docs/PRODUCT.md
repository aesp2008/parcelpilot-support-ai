# Product Note

## Which additional client problem I chose

I built **Problem 1, Proactive Issue Detection**, as a standalone internal Insights view
(`app/insights.py` + the frontend's Insights tab). It's deliberately not another LLM call:
it's a deterministic pass over the same ticket/order data that surfaces three things ops
actually needs at a glance --

- any ticket whose subject/description matches security/credential-exposure language,
  surfaced regardless of age or how the queue is normally sorted;
- an SLA watch list, sorted by breach/near-breach, computed against each account's actual
  *effective* SLA (agreement override where one exists, not just the plan default);
- known-issue clusters (bulk-upload failures, SwiftShip webhook delays) grouped across
  accounts, so "three different customers hit the same bug" is visible as one line instead
  of three separate tickets.

I treated **Problem 2, Trust and Reliability**, as answered by the core architecture rather
than as a bolt-on feature -- see `docs/ARCHITECTURE.md`'s "Source reliability and conflict
handling" section. Building a second, separate "trust dashboard" felt like it would
duplicate what the precedence rule and access-control layer already do; the better use of
scope was making sure that logic is actually enforced in code (tests in
`backend/tests/test_data_and_tools.py`) rather than only asserted in a system prompt.

## What else I'd build next, in priority order

1. **Real auth and persistent storage.** Sessions and pending actions are in-process dicts
   today; a restart loses them. This is the first thing that has to change before anything
   here is a real product -- swap mock login for actual customer/staff SSO, and move
   accounts/orders/tickets/action-log into a real database (Postgres) instead of an
   in-memory SQLite copy of a spreadsheet.
2. **A feedback loop from chat to Insights.** Right now the two systems don't talk: a
   pattern the chat agent notices mid-conversation (e.g. "this is the third LumenWorks
   ticket about bulk upload this week") doesn't get logged anywhere the Insights view would
   pick it up faster than its own keyword matching. Having the agent flag "this looks like
   a known-issue match" back into the same table Insights reads would tighten that loop.
3. **A real severity/triage model, not keyword heuristics, for the Insights view.** The
   dashboard's severity classification is intentionally simple (see architecture note) so
   it's cheap and reproducible; the chat agent already does better reasoning per-ticket
   against the actual policy text. Worth closing that gap once there's a stable place to
   evaluate classification accuracy against.
4. **Multi-turn action workflows**, e.g. an escalation that also drafts a customer-facing
   reply, or a follow-up task that's actually assigned into a real ticketing system (Zendesk
   / Linear / whatever ops already uses) instead of a mocked in-memory log.
5. **Usage analytics on the chat agent itself**: which questions get escalated vs. answered
   directly, and how often an escalation gets overturned by a human -- this is close to the
   "one metric" answer below, but as a running dashboard rather than a one-off number.

## What I intentionally left out

- **Streaming responses.** The tool-trace panel already shows what's happening turn-by-turn;
  token-level streaming would improve perceived latency but wasn't worth the added
  complexity for a 5-tool-call-budget assessment build.
- **A second LLM provider as fallback.** The architecture note explains the tool
  layer is provider-agnostic; I didn't wire in an actual failover path (e.g. to Claude) on
  quota/outage, since that's an operational concern beyond this assessment's scope.
- **Rate limiting / abuse protection on the API itself.** A public hosted demo could be
  hammered and exhaust the LLM quota; there's no per-IP throttling here.
- **A richer "which known issue" matcher.** The known-issue clustering in Insights is
  keyword-based against two known issues in the pack. A real version would need this to
  generalize to arbitrarily many known issues without a maintained keyword list.

## One metric I'd use to judge whether this is useful

**Escalation-reversal rate**: of everything the agent proposed as an action (or declined to
answer and instead escalated), what fraction does a human actually confirm as-is vs.
modify/reject? A low reversal rate means the agent's judgment about what needs a human is
actually calibrated; a high one means it's either escalating too aggressively (annoying,
slows down real resolutions) or not aggressively enough (the riskier failure mode, since a
confidently wrong answer is worse than an unnecessary escalation). This is more informative
than a raw "answered vs. escalated" ratio alone, because it's checking whether the *split*
itself is correct, not just that a split exists.
