# AI Tool Usage

I built this with **Claude Code** (Anthropic's CLI coding agent) as my primary tool, used
interactively end-to-end: reading and reasoning about the supplied data pack, drafting the
architecture, writing the backend (data loader, document indexing, tools, agent loop, API)
and frontend (React chat UI, insights dashboard), writing tests, and drafting these notes.

How I used it, concretely:

- **Reading the source pack.** Had it read all six PDFs and the workbook directly and
  summarize the precedence/override structure (deprecated policy, contract overrides, the
  intentionally-wrong historical ticket resolutions, the security-incident ticket) before
  any code was written, so the design decisions in `docs/ARCHITECTURE.md` are grounded in
  what's actually in the pack rather than assumptions about it.
- **Iterating on the agent's behavior, not just its code.** An early version of the system
  prompt caused the model to burn its whole tool-call budget re-searching for a security
  procedure document that doesn't exist in the pack instead of escalating. I asked Claude
  Code to diagnose this from a live trace and tighten the prompt; verified the fix with a
  second real run rather than taking the diff on faith.
- **Enforcing access control in code, and checking it.** Asked for the customer/internal
  scoping to be enforced at the tool layer (not just described in the system prompt), then
  had it write and run tests that actually try to break it (a LumenWorks customer session
  querying a Northstar order, an agent-role session trying to execute a manager-gated
  action) rather than trusting the implementation description.
- **Switching LLM providers mid-build.** Originally wired up against Claude's tool-use
  format; switched to Gemini function calling when that was the available API key, and hit
  a very tight free-tier quota on the newest preview model. Had it identify an
  available lighter model with a higher free quota and re-verify the tool-calling flow
  against it before continuing.

I reviewed the actual diffs and ran the tests/manual checks described in
`docs/ARCHITECTURE.md` myself rather than accepting generated output unverified -- the
example queries from the assessment brief and the adversarial access-control cases were
run against the live system, not assumed to work from the code alone.
