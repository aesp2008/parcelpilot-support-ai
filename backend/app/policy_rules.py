"""Structured, authoritative policy numbers used by the calculation tool.

Why this exists alongside document search: `calculate_metrics` needs exact numbers to do
arithmetic, and re-parsing tables out of PDF text at call time is fragile. So the CURRENT
values from Support Policy v3, the Cancellation & Service Credit SOP v4, and the two active
customer agreements are transcribed here once, each entry tagged with its source file so
the agent can still cite where a number came from. `search_documents` remains the source of
truth for anything narrative (definitions, escalation language, exceptions) and for
surfacing the deprecated v2 policy when someone asks about it. If a document changes, this
file and the PDF drift apart -- that's a real trade-off, called out in the architecture note.

account_id is None for the default/global rule; an account-specific entry overrides the
default per the precedence rule (signed agreement > current policy/SOP).
"""

DEFAULT_SLA_HOURS = {
    # plan -> severity -> (hours, is_business_hours, source)
    "Enterprise": {
        "P1": (0.5, False, "01_Support_Policy_v3_CURRENT.pdf"),
        "P2": (2, False, "01_Support_Policy_v3_CURRENT.pdf"),
        "P3": (8, True, "01_Support_Policy_v3_CURRENT.pdf"),  # 1 business day = 8 biz hrs
    },
    "Growth": {
        "P1": (2, True, "01_Support_Policy_v3_CURRENT.pdf"),
        "P2": (4, True, "01_Support_Policy_v3_CURRENT.pdf"),
        "P3": (16, True, "01_Support_Policy_v3_CURRENT.pdf"),  # 2 business days
    },
    "Standard": {
        "P1": (4, True, "01_Support_Policy_v3_CURRENT.pdf"),
        "P2": (8, True, "01_Support_Policy_v3_CURRENT.pdf"),  # 1 business day
        "P3": (16, True, "01_Support_Policy_v3_CURRENT.pdf"),  # 2 business days
    },
}

# Account-specific SLA overrides from signed agreements. These replace the plan default
# entirely for that account (precedence tier 1).
ACCOUNT_SLA_OVERRIDES = {
    "ACCT-001": {  # Northstar Logistics Enterprise Agreement
        "P1": (0.25, False, "05_Northstar_Logistics_Enterprise_Agreement.pdf"),
        "P2": (1, False, "05_Northstar_Logistics_Enterprise_Agreement.pdf"),
        "P3": (8, True, "05_Northstar_Logistics_Enterprise_Agreement.pdf"),
    },
    "ACCT-002": {  # LumenWorks Service Agreement
        "P1": (2, True, "06_LumenWorks_Service_Agreement.pdf"),
        "P2": (4, True, "06_LumenWorks_Service_Agreement.pdf"),
        "P3": (16, True, "06_LumenWorks_Service_Agreement.pdf"),  # 2 business days
    },
}

# Default failed-pickup service-credit rule (SOP v4 section 2).
DEFAULT_CREDIT_RULE = {
    "delay_threshold_hours": 2,
    "credit_formula": "lower_of_fixed_or_percent",
    "fixed_amount_inr": 500,
    "percent_of_shipment_fee": 0.10,
    "source": "03_Cancellation_and_Service_Credit_SOP_v4.pdf",
}

# Account-specific credit overrides (agreement replaces SOP default per SOP section 2 and
# each agreement's own text).
ACCOUNT_CREDIT_OVERRIDES = {
    "ACCT-002": {  # LumenWorks: fixed INR 300 at >4 hours, carrier at fault, no cust. fault
        "delay_threshold_hours": 4,
        "credit_formula": "fixed",
        "fixed_amount_inr": 300,
        "source": "06_LumenWorks_Service_Agreement.pdf",
    },
}

# Monthly aggregate credit caps per account (only Northstar's agreement states one).
ACCOUNT_MONTHLY_CREDIT_CAP_INR = {
    "ACCT-001": 5000,
}

MANAGER_APPROVAL_THRESHOLD_INR = 1000

# Cancellation rules by shipment status (SOP v4 section 1).
CANCELLATION_FEE_INR = 250
CANCELLATION_GRACE_MINUTES = 30

# Account-specific cancellation waivers.
ACCOUNTS_WITH_UNLIMITED_CANCELLATION_WAIVER = {
    "ACCT-001",  # Northstar: any BOOKED shipment, any time before pickup, no fee
}


def get_sla_target(plan: str, account_id: str, severity: str):
    """Returns (hours, is_business_hours, source_file) applying agreement override first."""
    if account_id in ACCOUNT_SLA_OVERRIDES and severity in ACCOUNT_SLA_OVERRIDES[account_id]:
        return ACCOUNT_SLA_OVERRIDES[account_id][severity]
    return DEFAULT_SLA_HOURS[plan][severity]


def get_credit_rule(account_id: str):
    if account_id in ACCOUNT_CREDIT_OVERRIDES:
        return {**DEFAULT_CREDIT_RULE, **ACCOUNT_CREDIT_OVERRIDES[account_id]}
    return DEFAULT_CREDIT_RULE
