import sqlite3
from datetime import datetime

import pandas as pd

from app.config import WORKBOOK_PATH, IST

_TIME_COLUMNS = {
    "orders": ["booked_at", "pickup_window_start", "pickup_window_end", "pickup_actual_at",
               "cancellation_requested_at"],
    "tickets": ["created_at", "last_customer_message_at"],
}


def _to_sqlite_ts(value):
    if pd.isna(value):
        return None
    return pd.Timestamp(value).strftime("%Y-%m-%d %H:%M:%S")


def load_workbook_to_sqlite(db_path: str = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    xls = pd.ExcelFile(WORKBOOK_PATH)

    accounts = pd.read_excel(xls, "accounts")
    orders = pd.read_excel(xls, "orders")
    tickets = pd.read_excel(xls, "tickets")

    for col in _TIME_COLUMNS["orders"]:
        orders[col] = orders[col].apply(_to_sqlite_ts)
    for col in _TIME_COLUMNS["tickets"]:
        tickets[col] = tickets[col].apply(_to_sqlite_ts)

    accounts.to_sql("accounts", conn, index=False, if_exists="replace")
    orders.to_sql("orders", conn, index=False, if_exists="replace")
    tickets.to_sql("tickets", conn, index=False, if_exists="replace")
    conn.commit()
    return conn


def get_snapshot_time() -> datetime:
    from app.config import SNAPSHOT_TIME_IST
    naive = datetime.strptime(SNAPSHOT_TIME_IST, "%Y-%m-%d %H:%M:%S")
    return naive.replace(tzinfo=IST)


def parse_db_ts(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
