"""Proactive issue detection for the internal Insights view (Problem 1). Deterministic
rules over the structured data -- no LLM call, so this is cheap to refresh and its output
is reproducible, which matters for something ops will use to triage.

Severity classification here is a simple keyword heuristic, not the same careful reasoning
the chat agent does per-ticket against the actual policy text. That's a real trade-off
(see product note): good enough to sort a queue, not a substitute for a policy-grounded
answer to a specific customer.
"""
import sqlite3
from collections import defaultdict

from app.data_loader import get_snapshot_time, parse_db_ts
from app.business_hours import business_hours_elapsed
from app import policy_rules

_SEVERITY_KEYWORDS = [
    ("P1", ["security", "credential", "exposure", "breach", "all shipment", "outage",
            "every user", "cannot create"]),
    ("P2", ["fails", "failing", "still shows", "webhook", "degraded", "bulk upload"]),
]

_KNOWN_ISSUE_KEYWORDS = {
    "KI-208": ["bulk upload", "csv", "rows"],
    "KI-211": ["swiftship", "webhook", "still shows booked", "shows booked"],
}


def _classify_severity(subject: str, description: str) -> str:
    text = f"{subject} {description}".lower()
    for severity, keywords in _SEVERITY_KEYWORDS:
        if any(k in text for k in keywords):
            return severity
    return "P3"


def _match_known_issue(subject: str, description: str) -> str | None:
    text = f"{subject} {description}".lower()
    for ki, keywords in _KNOWN_ISSUE_KEYWORDS.items():
        if any(k in text for k in keywords):
            return ki
    return None


def build_insights(conn: sqlite3.Connection) -> dict:
    conn.row_factory = sqlite3.Row
    accounts = {r["account_id"]: dict(r) for r in conn.execute("SELECT * FROM accounts")}
    tickets = [dict(r) for r in conn.execute("SELECT * FROM tickets WHERE status = 'open'")]
    now = get_snapshot_time()

    sla_rows = []
    clusters = defaultdict(list)
    security_flags = []

    for t in tickets:
        account = accounts.get(t["account_id"], {})
        severity = _classify_severity(t["subject"], t["description"])
        created = parse_db_ts(t["created_at"])
        hours, is_business, source = policy_rules.get_sla_target(
            account.get("plan", "Standard"), t["account_id"], severity)
        elapsed = business_hours_elapsed(created, now) if is_business else \
            (now - created).total_seconds() / 3600
        breached = elapsed >= hours
        near_breach = not breached and elapsed >= 0.8 * hours

        row = {
            "ticket_id": t["ticket_id"], "account_id": t["account_id"],
            "account_name": account.get("account_name", t["account_id"]),
            "subject": t["subject"], "severity_heuristic": severity,
            "elapsed_hours": round(elapsed, 2), "target_hours": hours,
            "breached": breached, "near_breach": near_breach, "sla_source": source,
        }
        sla_rows.append(row)

        ki = _match_known_issue(t["subject"], t["description"])
        if ki:
            clusters[ki].append({"ticket_id": t["ticket_id"], "account_id": t["account_id"],
                                  "account_name": account.get("account_name", t["account_id"])})

        if severity == "P1" and any(k in f"{t['subject']} {t['description']}".lower()
                                     for k in ["security", "credential", "exposure"]):
            security_flags.append({"ticket_id": t["ticket_id"], "account_id": t["account_id"],
                                    "subject": t["subject"]})

    sla_rows.sort(key=lambda r: (not r["breached"], not r["near_breach"], -r["elapsed_hours"]))

    cross_account_clusters = [
        {"known_issue": ki, "tickets": tks, "accounts_affected": len({t["account_id"] for t in tks})}
        for ki, tks in clusters.items() if len(tks) >= 1
    ]
    cross_account_clusters.sort(key=lambda c: c["accounts_affected"], reverse=True)

    return {
        "generated_at_reference": now.isoformat(),
        "security_flags": security_flags,
        "sla_watch": sla_rows,
        "known_issue_clusters": cross_account_clusters,
        "open_ticket_count": len(tickets),
    }
