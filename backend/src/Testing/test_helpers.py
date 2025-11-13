"""
Comprehensive unit tests for Helper modules (ISO_Parser and Calc_Months).
Tests date parsing and month calculation functionality with 100% coverage.
"""
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Import after adding to path
from Helpers.ISO_Parser import _parse_iso8601  # noqa: E402
from Helpers.Calc_Months import _months_between  # noqa: E402


class TestISOParser:
    """Test cases for ISO 8601 date parsing with complete coverage."""

    def test_parse_iso8601_basic(self):
        """Test parsing basic ISO 8601 date with time and Z."""
        date_str = "2023-01-15T10:30:00Z"
        result = _parse_iso8601(date_str)
        
        assert result is not None
        assert result.year == 2023
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 10
        assert result.minute == 30

    def test_parse_iso8601_with_timezone_offset(self):
        """Test parsing ISO 8601 date with timezone offset."""
        date_str = "2023-06-20T14:45:30+05:00"
        result = _parse_iso8601(date_str)
        
        assert result is not None
        assert result.year == 2023
        assert result.month == 6
        assert result.day == 20

    def test_parse_iso8601_date_only(self):
        """Test parsing ISO 8601 date without time (no 'T' separator)."""
        date_str = "2023-12-25"
        result = _parse_iso8601(date_str)
        
        assert result is not None
        assert result.year == 2023
        assert result.month == 12
        assert result.day == 25
        assert result.hour == 0
        assert result.minute == 0
        assert result.second == 0

    def test_parse_iso8601_with_microseconds(self):
        """Test parsing ISO 8601 date with microseconds."""
        date_str = "2023-03-10T08:15:30.123456Z"
        result = _parse_iso8601(date_str)
        
        assert result is not None
        assert result.year == 2023
        assert result.month == 3
        assert result.day == 10
        assert result.microsecond == 123456

    def test_parse_iso8601_with_fractional_seconds(self):
        """Test parsing ISO 8601 date with fractional seconds."""
        date_str = "2023-03-10T08:15:30.999Z"
        result = _parse_iso8601(date_str)
        
        assert result is not None
        assert result.microsecond > 0

    def test_parse_iso8601_without_timezone(self):
        """Test parsing ISO 8601 datetime without timezone marker."""
        date_str = "2023-06-15T14:30:45"
        result = _parse_iso8601(date_str)
        
        assert result is not None
        assert result.year == 2023
        assert result.month == 6
        assert result.day == 15

    def test_parse_iso8601_invalid_format_no_match(self):
        """Test parsing strings that don't match ISO 8601 regex."""
        invalid_dates = [
            "invalid-date",
            "2023/01/15",  # Wrong separator
            "2023-1-15",   # Single digit month (doesn't match regex)
            "23-01-15",    # Two-digit year
            "",            # Empty string
        ]
        
        for invalid_date in invalid_dates:
            result = _parse_iso8601(invalid_date)
            assert result is None

    def test_parse_iso8601_invalid_values(self):
        """Test parsing strings that match regex but have invalid values."""
        invalid_dates = [
            "2023-13-01",  # Invalid month
            "2023-01-32",  # Invalid day
            "2023-02-30",  # Invalid date for February
        ]
        
        for invalid_date in invalid_dates:
            result = _parse_iso8601(invalid_date)
            # Should return None due to exception handling
            assert result is None

    def test_parse_iso8601_none_input(self):
        """Test parsing None value - should raise AttributeError."""
        try:
            result = _parse_iso8601(None)
            # If it doesn't raise, it should return None
            assert result is None
        except (AttributeError, TypeError):
            # Expected - regex can't match None
            pass

    def test_parse_iso8601_leap_year(self):
        """Test parsing leap year date."""
        result = _parse_iso8601("2024-02-29T12:00:00Z")
        assert result is not None
        assert result.year == 2024
        assert result.month == 2
        assert result.day == 29

    def test_parse_iso8601_end_of_year(self):
        """Test parsing end of year date."""
        result = _parse_iso8601("2023-12-31T23:59:59Z")
        assert result is not None
        assert result.year == 2023
        assert result.month == 12
        assert result.day == 31
        assert result.hour == 23
        assert result.minute == 59
        assert result.second == 59


class TestCalcMonths:
    """Test cases for month calculation with complete coverage."""

    def test_months_between_same_date(self):
        """Test months between identical dates (0 difference)."""
        date = datetime(2023, 6, 15, tzinfo=timezone.utc)
        result = _months_between(date, date)
        assert result == 0.0

    def test_months_between_one_month_exact(self):
        """Test months between dates exactly one month apart (same day)."""
        date1 = datetime(2023, 1, 15, tzinfo=timezone.utc)
        date2 = datetime(2023, 2, 15, tzinfo=timezone.utc)
        result = _months_between(date1, date2)
        assert abs(result - 1.0) < 0.01

    def test_months_between_one_year(self):
        """Test months between dates one year apart."""
        date1 = datetime(2023, 6, 15, tzinfo=timezone.utc)
        date2 = datetime(2024, 6, 15, tzinfo=timezone.utc)
        result = _months_between(date1, date2)
        assert abs(result - 12.0) < 0.01

    def test_months_between_reverse_order(self):
        """Test months between dates in reverse order (tests swap logic)."""
        date1 = datetime(2023, 6, 15, tzinfo=timezone.utc)
        date2 = datetime(2023, 3, 15, tzinfo=timezone.utc)
        result = _months_between(date1, date2)
        # Function swaps internally to always return positive
        assert abs(result - 3.0) < 0.01

    def test_months_between_positive_day_diff(self):
        """Test months between with positive day difference (later day)."""
        # Jan 15 to Feb 20 = 1 month + 5 days
        date1 = datetime(2023, 1, 15, tzinfo=timezone.utc)
        date2 = datetime(2023, 2, 20, tzinfo=timezone.utc)
        result = _months_between(date1, date2)
        # Should be slightly more than 1 month
        assert 1.0 < result < 1.2

    def test_months_between_negative_day_diff(self):
        """Test months between with negative day difference (earlier day)."""
        # Jan 31 to Feb 28 = 1 month - 3 days
        date1 = datetime(2023, 1, 31, tzinfo=timezone.utc)
        date2 = datetime(2023, 2, 28, tzinfo=timezone.utc)
        result = _months_between(date1, date2)
        # Should be slightly less than 1 month
        assert 0.9 < result < 1.1

    def test_months_between_cross_year_boundary(self):
        """Test months between dates crossing year boundary."""
        date1 = datetime(2022, 10, 15, tzinfo=timezone.utc)
        date2 = datetime(2023, 3, 15, tzinfo=timezone.utc)
        result = _months_between(date1, date2)
        assert abs(result - 5.0) < 0.01

    def test_months_between_multiple_years(self):
        """Test months between dates multiple years apart."""
        date1 = datetime(2020, 1, 1, tzinfo=timezone.utc)
        date2 = datetime(2023, 1, 1, tzinfo=timezone.utc)
        result = _months_between(date1, date2)
        assert abs(result - 36.0) < 0.01

    def test_months_between_partial_month(self):
        """Test months between with partial month (mid-month)."""
        date1 = datetime(2023, 6, 1, tzinfo=timezone.utc)
        date2 = datetime(2023, 6, 16, tzinfo=timezone.utc)
        result = _months_between(date1, date2)
        # ~15 days = ~0.5 months
        assert 0.4 < result < 0.6

    def test_months_between_different_timezones(self):
        """Test months between dates with different timezones."""
        date1 = datetime(2023, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        tz_offset = timezone(timedelta(hours=5))
        date2 = datetime(2023, 2, 15, 17, 0, 0, tzinfo=tz_offset)
        
        result = _months_between(date1, date2)
        # Should be approximately 1 month
        assert abs(result - 1.0) < 0.1

    def test_months_between_none_first_arg(self):
        """Test months between with None as first argument."""
        date = datetime(2023, 6, 15, tzinfo=timezone.utc)
        result = _months_between(None, date)
        assert result == 0.0

    def test_months_between_none_second_arg(self):
        """Test months between with None as second argument."""
        date = datetime(2023, 6, 15, tzinfo=timezone.utc)
        result = _months_between(date, None)
        assert result == 0.0

    def test_months_between_both_none(self):
        """Test months between with both arguments as None."""
        result = _months_between(None, None)
        assert result == 0.0

    def test_months_between_precision(self):
        """Test months between calculation precision."""
        date1 = datetime(2023, 1, 1, tzinfo=timezone.utc)
        date2 = datetime(2023, 7, 1, tzinfo=timezone.utc)
        result = _months_between(date1, date2)
        assert abs(result - 6.0) < 0.01
        
        # Test with mid-month dates
        date1 = datetime(2023, 1, 15, tzinfo=timezone.utc)
        date2 = datetime(2023, 7, 15, tzinfo=timezone.utc)
        result = _months_between(date1, date2)
        assert abs(result - 6.0) < 0.01

    def test_months_between_leap_year(self):
        """Test months between with leap year dates."""
        date1 = datetime(2024, 1, 29, tzinfo=timezone.utc)
        date2 = datetime(2024, 2, 29, tzinfo=timezone.utc)
        result = _months_between(date1, date2)
        assert abs(result - 1.0) < 0.1
        
        # Cross leap year boundary
        date1 = datetime(2023, 12, 15, tzinfo=timezone.utc)
        date2 = datetime(2024, 3, 15, tzinfo=timezone.utc)
        result = _months_between(date1, date2)
        assert abs(result - 3.0) < 0.01

    def test_months_between_very_small_difference(self):
        """Test months between with very small time difference (same day)."""
        date1 = datetime(2023, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        date2 = datetime(2023, 6, 15, 12, 0, 1, tzinfo=timezone.utc)
        result = _months_between(date1, date2)
        # Same day, so day_diff = 0, result should be 0.0
        assert result == 0.0

    def test_months_between_large_gap(self):
        """Test months between with large time gap."""
        date1 = datetime(2020, 1, 1, tzinfo=timezone.utc)
        date2 = datetime(2023, 12, 31, tzinfo=timezone.utc)
        result = _months_between(date1, date2)
        # Almost 4 years
        assert result > 47
        assert result < 49

    def test_months_between_end_of_month(self):
        """Test months between end-of-month dates."""
        date1 = datetime(2023, 1, 31, tzinfo=timezone.utc)
        date2 = datetime(2023, 3, 31, tzinfo=timezone.utc)
        result = _months_between(date1, date2)
        assert abs(result - 2.0) < 0.01