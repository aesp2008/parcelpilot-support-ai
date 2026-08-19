"""Business-hours math for SLA calculations.

Every plan's response target in the policy pack is expressed either in wall-clock hours
(e.g. "30 minutes, 24x7") or in business hours/days (e.g. "2 business days"). We treat a
target as wall-clock if its unit says "hours"/"minutes" with no "business" qualifier or is
explicitly 24x7, and as business-hours otherwise. See config.BUSINESS_DAY_START_HOUR /
END_HOUR / BUSINESS_DAYS for the assumed calendar.
"""
from datetime import datetime, timedelta

from app.config import BUSINESS_DAY_START_HOUR, BUSINESS_DAY_END_HOUR, BUSINESS_DAYS


def _day_bounds(day: datetime) -> tuple[datetime, datetime]:
    start = day.replace(hour=BUSINESS_DAY_START_HOUR, minute=0, second=0, microsecond=0)
    end = day.replace(hour=BUSINESS_DAY_END_HOUR, minute=0, second=0, microsecond=0)
    return start, end


def add_business_hours(start: datetime, hours: float) -> datetime:
    """Return the timestamp `hours` business-hours after `start`."""
    remaining = timedelta(hours=hours)
    cursor = start
    while remaining > timedelta(0):
        if cursor.weekday() not in BUSINESS_DAYS:
            cursor = (cursor + timedelta(days=1)).replace(
                hour=BUSINESS_DAY_START_HOUR, minute=0, second=0, microsecond=0
            )
            continue
        day_start, day_end = _day_bounds(cursor)
        if cursor < day_start:
            cursor = day_start
        if cursor >= day_end:
            cursor = (cursor + timedelta(days=1)).replace(
                hour=BUSINESS_DAY_START_HOUR, minute=0, second=0, microsecond=0
            )
            continue
        available_today = day_end - cursor
        if available_today <= remaining:
            remaining -= available_today
            cursor = (cursor + timedelta(days=1)).replace(
                hour=BUSINESS_DAY_START_HOUR, minute=0, second=0, microsecond=0
            )
        else:
            cursor = cursor + remaining
            remaining = timedelta(0)
    return cursor


def business_hours_elapsed(start: datetime, end: datetime) -> float:
    """Business hours elapsed between two timestamps (end must be >= start)."""
    if end <= start:
        return 0.0
    total = timedelta(0)
    cursor = start
    while cursor < end:
        if cursor.weekday() not in BUSINESS_DAYS:
            cursor = (cursor + timedelta(days=1)).replace(
                hour=BUSINESS_DAY_START_HOUR, minute=0, second=0, microsecond=0
            )
            continue
        day_start, day_end = _day_bounds(cursor)
        window_start = max(cursor, day_start)
        window_end = min(end, day_end)
        if window_end > window_start:
            total += window_end - window_start
        cursor = (cursor + timedelta(days=1)).replace(
            hour=BUSINESS_DAY_START_HOUR, minute=0, second=0, microsecond=0
        )
    return total.total_seconds() / 3600


def parse_target_to_hours(target_text: str) -> tuple[float, bool]:
    """Parse a target string like '2 business hours', '1 business day', '30 minutes, 24x7'
    into (hours, is_business_hours). Wall-clock/24x7 targets return is_business_hours=False.
    """
    text = target_text.lower().strip()
    is_business = "business" in text
    if "day" in text:
        n = float(text.split()[0])
        hours = n * (BUSINESS_DAY_END_HOUR - BUSINESS_DAY_START_HOUR) if is_business else n * 24
    elif "hour" in text:
        n = float(text.split()[0])
        hours = n
    elif "minute" in text:
        n = float(text.split()[0])
        hours = n / 60
    else:
        raise ValueError(f"Cannot parse SLA target: {target_text!r}")
    return hours, is_business
