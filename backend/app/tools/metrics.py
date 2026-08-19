"""Calculation tool: cancellation eligibility, service-credit eligibility, and SLA
business-hours math. Kept as its own tool (separate from `query_records`) so the model
reaches for arithmetic it's told to run rather than eyeballing numbers out of raw rows.

Every calculation here re-applies the same precedence rule the docs state: an account's
signed agreement (app.policy_rules ACCOUNT_* overrides) beats the SOP/policy default.
"""
import sqlite3
from datetime import datetime, timedelta

from app.business_hours import add_business_hours, business_hours_elapsed
from app.data_loader import get_snapshot_time, parse_db_ts
from app.session import Session
from app.tools.records import query_records
from app import policy_rules


def _get_own_order(conn: sqlite3.Connection, session: Session, order_id: str) -> dict | None:
    rows = query_records(conn, session, "orders", {"order_id": order_id}, limit=1)
    return rows[0] if rows else None


def _get_account(conn: sqlite3.Connection, session: Session, account_id: str) -> dict | None:
    # accounts lookup by id is always allowed for the account's own record; internal
    # sessions can look up any account.
    if session.kind == "customer" and account_id != session.account_id:
        return None
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM accounts WHERE account_id = ?", (account_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def cancellation_eligibility(conn: sqlite3.Connection, session: Session, order_id: str) -> dict:
    order = _get_own_order(conn, session, order_id)
    if order is None:
        return {"error": f"Order {order_id} not found or not accessible to this session."}

    status = order["status"]
    account_id = order["account_id"]
    waived = account_id in policy_rules.ACCOUNTS_WITH_UNLIMITED_CANCELLATION_WAIVER

    if status == "DELIVERED":
        return {"order_id": order_id, "eligible": False, "fee_inr": None,
                "reason": "Shipment is DELIVERED. Cannot be cancelled.",
                "source": "03_Cancellation_and_Service_Credit_SOP_v4.pdf"}
    if status == "PICKED_UP":
        return {"order_id": order_id, "eligible": False, "fee_inr": None,
                "reason": "Shipment already PICKED_UP. Use the return-to-origin workflow "
                          "instead of cancellation.",
                "source": "03_Cancellation_and_Service_Credit_SOP_v4.pdf"}
    if status == "DRAFT":
        return {"order_id": order_id, "eligible": True, "fee_inr": 0,
                "reason": "DRAFT shipments may be cancelled with no fee.",
                "source": "03_Cancellation_and_Service_Credit_SOP_v4.pdf"}

    # BOOKED, not yet picked up
    if waived:
        return {"order_id": order_id, "eligible": True, "fee_inr": 0,
                "reason": f"{account_id}'s signed agreement waives the cancellation fee for "
                          "any BOOKED shipment cancelled before pickup, regardless of "
                          "elapsed time.",
                "source": "05_Northstar_Logistics_Enterprise_Agreement.pdf"}

    booked_at = parse_db_ts(order["booked_at"])
    requested_at_raw = order["cancellation_requested_at"]
    reference = parse_db_ts(requested_at_raw) if requested_at_raw else get_snapshot_time()
    minutes_since_booking = (reference - booked_at).total_seconds() / 60

    if minutes_since_booking <= policy_rules.CANCELLATION_GRACE_MINUTES:
        return {"order_id": order_id, "eligible": True, "fee_inr": 0,
                "minutes_since_booking": round(minutes_since_booking, 1),
                "reason": "Cancellation requested within the 30-minute no-fee grace window.",
                "source": "03_Cancellation_and_Service_Credit_SOP_v4.pdf"}
    return {"order_id": order_id, "eligible": True,
            "fee_inr": policy_rules.CANCELLATION_FEE_INR,
            "minutes_since_booking": round(minutes_since_booking, 1),
            "reason": f"Cancellation requested {minutes_since_booking:.0f} minutes after "
                      "booking, past the 30-minute grace window, and no agreement waives "
                      f"the fee for this account. INR {policy_rules.CANCELLATION_FEE_INR} "
                      "cancellation fee applies.",
            "source": "03_Cancellation_and_Service_Credit_SOP_v4.pdf"}


def service_credit_eligibility(conn: sqlite3.Connection, session: Session, order_id: str) -> dict:
    order = _get_own_order(conn, session, order_id)
    if order is None:
        return {"error": f"Order {order_id} not found or not accessible to this session."}

    account_id = order["account_id"]
    rule = policy_rules.get_credit_rule(account_id)

    if order["pickup_actual_at"]:
        return {"order_id": order_id, "eligible": False,
                "reason": "Pickup already confirmed; there is no failed-pickup delay to "
                          "evaluate.", "source": rule["source"]}

    window_end = parse_db_ts(order["pickup_window_end"])
    now = get_snapshot_time()
    delay_hours = (now - window_end).total_seconds() / 3600

    carrier_fault = bool(order["carrier_fault"])
    customer_fault = bool(order["customer_fault"])

    if delay_hours < 0:
        return {"order_id": order_id, "eligible": False,
                "reason": "Pickup window has not yet elapsed at the reference snapshot "
                          "time.", "source": rule["source"]}

    threshold = rule["delay_threshold_hours"]
    if delay_hours <= threshold:
        return {"order_id": order_id, "eligible": False,
                "delay_hours": round(delay_hours, 2), "threshold_hours": threshold,
                "reason": f"Pickup is {delay_hours:.1f}h past the window end, which does "
                          f"not exceed the {threshold}h threshold for this account.",
                "source": rule["source"]}

    if not carrier_fault or customer_fault:
        return {"order_id": order_id, "eligible": False, "needs_verification": True,
                "delay_hours": round(delay_hours, 2),
                "carrier_fault": carrier_fault, "customer_fault": customer_fault,
                "reason": "Delay exceeds the threshold, but fault attribution is not "
                          "confirmed as carrier-at-fault-only. Per SOP section 3, do not "
                          "promise a credit while fault is unknown or customer is at fault "
                          "-- verify with carrier/ops before responding.",
                "source": "03_Cancellation_and_Service_Credit_SOP_v4.pdf"}

    if rule["credit_formula"] == "fixed":
        amount = rule["fixed_amount_inr"]
    else:
        amount = min(rule["fixed_amount_inr"], rule["percent_of_shipment_fee"] * order["shipment_fee_inr"])

    result = {"order_id": order_id, "eligible": True, "delay_hours": round(delay_hours, 2),
              "credit_amount_inr": round(amount, 2), "source": rule["source"],
              "reason": f"Pickup delay of {delay_hours:.1f}h exceeds the {threshold}h "
                        f"threshold, carrier is at fault, customer is not at fault. Credit: "
                        f"INR {amount:.2f}."}

    if amount > policy_rules.MANAGER_APPROVAL_THRESHOLD_INR:
        result["requires_manager_approval"] = True
        result["reason"] += (f" This exceeds the INR {policy_rules.MANAGER_APPROVAL_THRESHOLD_INR} "
                              "manager-approval threshold.")

    cap = policy_rules.ACCOUNT_MONTHLY_CREDIT_CAP_INR.get(account_id)
    if cap is not None:
        result["monthly_cap_inr"] = cap
        result["reason"] += f" Note: this account has a monthly aggregate credit cap of INR {cap}."

    return result


def sla_status(conn: sqlite3.Connection, session: Session, account_id: str, severity: str,
                reference_time_iso: str | None = None, ticket_id: str | None = None) -> dict:
    account = _get_account(conn, session, account_id)
    if account is None:
        return {"error": f"Account {account_id} not found or not accessible to this session."}
    if severity not in ("P1", "P2", "P3"):
        return {"error": "severity must be one of P1, P2, P3"}

    start = None
    if ticket_id:
        rows = query_records(conn, session, "tickets", {"ticket_id": ticket_id}, limit=1)
        if rows:
            start = parse_db_ts(rows[0]["created_at"])
    if start is None and reference_time_iso:
        start = parse_db_ts(reference_time_iso)
    if start is None:
        return {"error": "Provide either ticket_id or reference_time_iso to anchor the SLA clock."}

    hours, is_business, source = policy_rules.get_sla_target(account["plan"], account_id, severity)
    now = get_snapshot_time()

    if is_business:
        elapsed = business_hours_elapsed(start, now)
        deadline = add_business_hours(start, hours)
    else:
        elapsed = (now - start).total_seconds() / 3600
        deadline = start + timedelta(hours=hours)

    breached = now >= deadline
    return {
        "account_id": account_id, "severity": severity, "target_hours": hours,
        "is_business_hours": is_business, "elapsed_hours": round(elapsed, 2),
        "deadline": deadline.isoformat(), "reference_now": now.isoformat(),
        "breached": breached, "source": source,
        "reason": (f"{'BREACHED' if breached else 'Within target'}: {severity} target for "
                   f"{account_id} is {hours}{' business' if is_business else ''} hours "
                   f"(source: {source}), deadline {deadline.isoformat()}, current "
                   f"reference time {now.isoformat()}."),
    }


def dispatch(conn: sqlite3.Connection, session: Session, kind: str, args: dict) -> dict:
    if kind == "cancellation_eligibility":
        return cancellation_eligibility(conn, session, args["order_id"])
    if kind == "service_credit_eligibility":
        return service_credit_eligibility(conn, session, args["order_id"])
    if kind == "sla_status":
        return sla_status(conn, session, args["account_id"], args["severity"],
                           args.get("reference_time_iso"), args.get("ticket_id"))
    return {"error": f"Unknown calculation kind: {kind}"}
