from datetime import datetime


def _months_between(a: datetime, b: datetime) -> float:
    """
    Calculate the approximate number of months between two datetime objects.
    Args:
        a: The first datetime (typically the later date)
        b: The second datetime (typically the earlier date)
    Returns:
        The approximate number of months between the two dates.
        Returns absolute difference in months.
    """
    if a is None or b is None:
        return 0.0

    if a < b:
        a, b = b, a

    year_diff = a.year - b.year
    month_diff = a.month - b.month
    day_diff = a.day - b.day
    total_months = year_diff * 12 + month_diff

    if day_diff > 0:
        days_in_month = 30.44
        total_months += day_diff / days_in_month
    elif day_diff < 0:
        total_months -= abs(day_diff) / 30.44

    return max(0.0, abs(total_months))
