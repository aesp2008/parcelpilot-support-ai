"""Structured-data lookup tool: query accounts / orders / tickets.

Access control is enforced here, not left to the model. A customer session's filters are
ANDed with their own account_id no matter what the model asks for, so there is no way for
a crafted query to pull another account's rows out through this tool.
"""
import sqlite3

from app.session import Session

_ALLOWED_COLUMNS = {
    "accounts": {"account_id", "account_name", "plan", "status", "csm", "premium_support"},
    "orders": {"order_id", "account_id", "carrier", "status", "booked_at",
               "pickup_window_start", "pickup_window_end", "pickup_actual_at",
               "shipment_fee_inr", "carrier_fault", "customer_fault",
               "cancellation_requested_at"},
    "tickets": {"ticket_id", "account_id", "created_at", "status", "subject",
                "assigned_to", "last_customer_message_at"},
}

_ENTITY_TABLE = {"accounts": "accounts", "orders": "orders", "tickets": "tickets"}


def query_records(conn: sqlite3.Connection, session: Session, entity: str,
                   filters: dict | None = None, limit: int = 20) -> list[dict]:
    if entity not in _ENTITY_TABLE:
        raise ValueError(f"Unknown entity: {entity}")

    filters = dict(filters or {})

    if session.kind == "customer":
        # Hard scope: whatever the model asked for, the account_id is pinned to the
        # caller's own account. This line is the actual access-control enforcement --
        # everything else here is just query building.
        if entity == "accounts":
            filters["account_id"] = session.account_id
        else:
            filters["account_id"] = session.account_id

    table = _ENTITY_TABLE[entity]
    allowed = _ALLOWED_COLUMNS[entity]
    clauses, params = [], []
    for col, val in filters.items():
        if col not in allowed:
            continue  # silently drop unknown/disallowed filter keys rather than erroring
        clauses.append(f"{col} = ?")
        params.append(val)

    sql = f"SELECT * FROM {table}"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += f" LIMIT {int(limit)}"

    conn.row_factory = sqlite3.Row
    cur = conn.execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]

    if entity == "tickets":
        rows = _attach_ticket_context(conn, rows)

    return rows


def _attach_ticket_context(conn: sqlite3.Connection, rows: list[dict]) -> list[dict]:
    """Pull historical_resolution separately and label it clearly as unverified context --
    never presented as current policy or a guaranteed-correct precedent."""
    conn.row_factory = sqlite3.Row
    for row in rows:
        cur = conn.execute(
            "SELECT historical_resolution, description, channel FROM tickets WHERE ticket_id = ?",
            (row["ticket_id"],),
        )
        extra = cur.fetchone()
        row["description"] = extra["description"]
        row["channel"] = extra["channel"]
        if extra["historical_resolution"]:
            row["historical_resolution"] = extra["historical_resolution"]
            row["historical_resolution_warning"] = (
                "This is a past agent's resolution note, not a verified or current policy "
                "source. It may be incorrect -- confirm against current policy/SOP/agreement "
                "before relying on it."
            )
    return rows
