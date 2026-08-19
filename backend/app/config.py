import os
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_PACK_DIR = BASE_DIR / "data_pack"
WORKBOOK_PATH = DATA_PACK_DIR / "ParcelPilot_Assessment_Data.xlsx"

IST = ZoneInfo("Asia/Kolkata")

# The workbook README pins the dataset snapshot at 2026-08-16 11:00 IST. All "how much
# time has passed" questions (SLA elapsed, pickup delay, etc.) are answered against this
# fixed instant rather than wall-clock time, since the data itself is frozen there.
SNAPSHOT_TIME_IST = "2026-08-16 11:00:00"

# Business hours used for every "business hour(s)" / "business day(s)" SLA target in the
# policy pack. Not stated explicitly anywhere in the docs, so this is a documented
# assumption (see architecture note): Mon-Fri, 09:00-18:00 IST. This also lines up with
# the LumenWorks agreement's "no weekend or after-hours support coverage" clause.
BUSINESS_DAY_START_HOUR = 9
BUSINESS_DAY_END_HOUR = 18
BUSINESS_DAYS = {0, 1, 2, 3, 4}  # Monday=0 ... Sunday=6

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")

CURRENCY = "INR"
MANAGER_APPROVAL_THRESHOLD_INR = 1000
