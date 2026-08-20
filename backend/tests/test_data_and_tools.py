import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from app.data_loader import load_workbook_to_sqlite
from app.documents import DocumentIndex
from app.session import create_customer_session, create_internal_session
from app.tools import records, metrics
from app.business_hours import add_business_hours, business_hours_elapsed
from datetime import datetime
from app.config import IST


@pytest.fixture
def conn():
    return load_workbook_to_sqlite()


@pytest.fixture
def doc_index():
    return DocumentIndex()


# --- access control -----------------------------------------------------

def test_customer_cannot_read_another_accounts_order(conn):
    lumenworks = create_customer_session("ACCT-002", "LumenWorks")
    rows = records.query_records(conn, lumenworks, "orders", {"order_id": "ORD-1001"})
    assert rows == []  # ORD-1001 belongs to Northstar (ACCT-001)


def test_customer_query_is_pinned_to_own_account_even_without_filter(conn):
    northstar = create_customer_session("ACCT-001", "Northstar Logistics")
    rows = records.query_records(conn, northstar, "orders", {})
    assert rows, "expected at least one order"
    assert all(r["account_id"] == "ACCT-001" for r in rows)


def test_internal_session_can_query_any_account(conn):
    staff = create_internal_session("agent", "Rohit")
    rows = records.query_records(conn, staff, "orders", {"order_id": "ORD-2001"})
    assert len(rows) == 1
    assert rows[0]["account_id"] == "ACCT-002"


def test_customer_document_search_excludes_other_accounts_agreement(doc_index):
    results = doc_index.search("cancellation waiver", top_k=10,
                                account_id="ACCT-002", is_customer=True)
    assert not any(c.source_file.startswith("05_Northstar") for c in results)


def test_ticket_lookup_flags_historical_resolution_as_unverified(conn):
    staff = create_internal_session("agent", "Rohit")
    rows = records.query_records(conn, staff, "tickets", {"ticket_id": "TKT-450"})
    assert rows[0].get("historical_resolution_warning")


# --- calculations --------------------------------------------------------

def test_northstar_cancellation_fee_waived_regardless_of_time(conn):
    staff = create_internal_session("agent", "Rohit")
    result = metrics.cancellation_eligibility(conn, staff, "ORD-1001")
    assert result["eligible"] is True
    assert result["fee_inr"] == 0


def test_lumenworks_service_credit_uses_contract_override(conn):
    staff = create_internal_session("agent", "Rohit")
    result = metrics.service_credit_eligibility(conn, staff, "ORD-2002")
    assert result["eligible"] is True
    assert result["credit_amount_inr"] == 300  # LumenWorks fixed override, not SOP default


def test_service_credit_withheld_when_fault_unresolved(conn):
    # ORD-2001: carrier_fault is False in the data -- must not promise a credit.
    staff = create_internal_session("agent", "Rohit")
    result = metrics.service_credit_eligibility(conn, staff, "ORD-2001")
    assert result["eligible"] is False


# --- business hours --------------------------------------------------------

def test_business_hours_elapsed_excludes_overnight_gap():
    start = datetime(2026, 8, 14, 17, 0, tzinfo=IST)  # Friday 5pm
    end = datetime(2026, 8, 17, 10, 0, tzinfo=IST)     # Monday 10am
    elapsed = business_hours_elapsed(start, end)
    assert elapsed == pytest.approx(2.0)  # 1h Friday + 1h Monday, weekend excluded


def test_add_business_hours_skips_weekend():
    start = datetime(2026, 8, 14, 17, 30, tzinfo=IST)  # Friday 5:30pm
    deadline = add_business_hours(start, 1)
    assert deadline == datetime(2026, 8, 17, 9, 30, tzinfo=IST)  # rolls to Monday 9:30am
