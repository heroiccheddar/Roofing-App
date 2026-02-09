"""Unit tests for decay.py module.

Tests the temporal decay function thoroughly, including edge cases,
timezone handling, and batch processing.
"""

import math
import pytest
from datetime import datetime, timedelta, timezone

from app.scoring.decay import calculate_decay, batch_decay, DECAY_RATE, MAX_AGE_DAYS


class TestCalculateDecay:
    """Tests for calculate_decay() function."""

    def test_decay_at_zero_hours(self):
        """Test that decay returns exactly 1.0 for events at current time."""
        now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        event = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

        decay = calculate_decay(event, now)

        assert decay == 1.0

    def test_decay_at_24_hours(self):
        """Test decay value at 24 hours (1 day) matches expected value.

        Formula: e^(-0.25 * 24/24) = e^(-0.25) ≈ 0.7788
        """
        now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        event = now - timedelta(days=1)

        decay = calculate_decay(event, now)
        expected = math.exp(-DECAY_RATE * 1)  # e^(-0.25)

        assert math.isclose(decay, expected, rel_tol=1e-3)
        assert math.isclose(decay, 0.7788, rel_tol=1e-3)

    def test_decay_at_48_hours(self):
        """Test decay value at 48 hours (2 days) matches expected value.

        Formula: e^(-0.25 * 48/24) = e^(-0.50) ≈ 0.6065
        """
        now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        event = now - timedelta(days=2)

        decay = calculate_decay(event, now)
        expected = math.exp(-DECAY_RATE * 2)  # e^(-0.50)

        assert math.isclose(decay, expected, rel_tol=1e-3)
        assert math.isclose(decay, 0.6065, rel_tol=1e-3)

    def test_decay_at_72_hours(self):
        """Test decay value at 72 hours (3 days) matches expected value.

        Formula: e^(-0.25 * 72/24) = e^(-0.75) ≈ 0.4724
        """
        now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        event = now - timedelta(days=3)

        decay = calculate_decay(event, now)
        expected = math.exp(-DECAY_RATE * 3)  # e^(-0.75)

        assert math.isclose(decay, expected, rel_tol=1e-3)
        assert math.isclose(decay, 0.4724, rel_tol=1e-3)

    def test_decay_at_168_hours(self):
        """Test decay value at 168 hours (7 days) matches expected value.

        Formula: e^(-0.25 * 168/24) = e^(-1.75) ≈ 0.1738
        """
        now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        event = now - timedelta(days=7)

        decay = calculate_decay(event, now)
        expected = math.exp(-DECAY_RATE * 7)  # e^(-1.75)

        assert math.isclose(decay, expected, rel_tol=1e-3)
        assert math.isclose(decay, 0.1738, rel_tol=1e-3)

    def test_decay_at_14_days_returns_zero(self):
        """Test that decay returns exactly 0.0 at MAX_AGE_DAYS (14 days).

        Events at or beyond 14 days are fully decayed (clamped to 0.0).
        """
        now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        event = now - timedelta(days=MAX_AGE_DAYS)

        decay = calculate_decay(event, now)

        assert decay == 0.0

    def test_decay_at_15_days_returns_zero(self):
        """Test that decay returns exactly 0.0 beyond MAX_AGE_DAYS.

        Events older than 14 days remain clamped at 0.0.
        """
        now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        event = now - timedelta(days=15)

        decay = calculate_decay(event, now)

        assert decay == 0.0

    def test_decay_future_event_returns_one(self):
        """Test that future events return 1.0 (no decay).

        Events with negative elapsed time (future events) should have no decay.
        """
        now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        future_event = now + timedelta(days=1)

        decay = calculate_decay(future_event, now)

        assert decay == 1.0

    def test_decay_timezone_naive_handling(self):
        """Test that timezone-naive datetimes are handled correctly.

        Naive datetimes should be treated as UTC.
        """
        now_naive = datetime(2024, 1, 15, 12, 0, 0)  # No timezone
        event_naive = datetime(2024, 1, 14, 12, 0, 0)  # 1 day ago

        decay = calculate_decay(event_naive, now_naive)
        expected = math.exp(-DECAY_RATE * 1)

        assert math.isclose(decay, expected, rel_tol=1e-3)

    def test_decay_timezone_aware_handling(self):
        """Test that timezone-aware datetimes are handled correctly.

        Should work with any timezone, normalized to UTC internally.
        """
        now_utc = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        event_utc = datetime(2024, 1, 14, 12, 0, 0, tzinfo=timezone.utc)

        decay = calculate_decay(event_utc, now_utc)
        expected = math.exp(-DECAY_RATE * 1)

        assert math.isclose(decay, expected, rel_tol=1e-3)

    def test_decay_mixed_timezone_handling(self):
        """Test decay with one naive and one aware datetime.

        Both should be normalized to UTC for consistent comparison.
        """
        now_aware = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        event_naive = datetime(2024, 1, 14, 12, 0, 0)  # No timezone

        decay = calculate_decay(event_naive, now_aware)
        expected = math.exp(-DECAY_RATE * 1)

        assert math.isclose(decay, expected, rel_tol=1e-3)

    def test_decay_defaults_to_current_time(self):
        """Test that current_time defaults to UTC now when not provided."""
        # Create an event from 1 day ago
        event = datetime.now(timezone.utc) - timedelta(days=1)

        decay = calculate_decay(event)

        # Should be approximately e^(-0.25) = 0.7788
        # Use a wider tolerance since exact time varies
        assert 0.77 < decay < 0.79

    def test_decay_curve_monotonic_decreasing(self):
        """Test that decay curve is monotonically decreasing.

        Older events should always have lower decay factors.
        """
        now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

        decays = []
        for days in range(0, 14):
            event = now - timedelta(days=days)
            decay = calculate_decay(event, now)
            decays.append(decay)

        # Each decay should be less than or equal to the previous
        for i in range(1, len(decays)):
            assert decays[i] <= decays[i-1]

    def test_decay_precision_at_6_hours(self):
        """Test decay value at 6 hours for additional precision check."""
        now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        event = now - timedelta(hours=6)

        decay = calculate_decay(event, now)
        expected = math.exp(-DECAY_RATE * 6 / 24)  # e^(-0.0625)

        assert math.isclose(decay, expected, rel_tol=1e-6)

    def test_decay_precision_at_12_hours(self):
        """Test decay value at 12 hours for additional precision check."""
        now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        event = now - timedelta(hours=12)

        decay = calculate_decay(event, now)
        expected = math.exp(-DECAY_RATE * 12 / 24)  # e^(-0.125)

        assert math.isclose(decay, expected, rel_tol=1e-6)


class TestBatchDecay:
    """Tests for batch_decay() function."""

    def test_batch_decay_processes_list_correctly(self):
        """Test that batch_decay processes a list of events correctly."""
        now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

        events = [
            ("event1", now),
            ("event2", now - timedelta(days=1)),
            ("event3", now - timedelta(days=3)),
            ("event4", now - timedelta(days=15)),  # Beyond MAX_AGE_DAYS
        ]

        results = batch_decay(events, now)

        # Check structure
        assert len(results) == 4
        assert all(isinstance(item, tuple) and len(item) == 2 for item in results)

        # Check values
        assert results[0] == ("event1", 1.0)
        assert results[1][0] == "event2"
        assert math.isclose(results[1][1], 0.7788, rel_tol=1e-3)
        assert results[2][0] == "event3"
        assert math.isclose(results[2][1], 0.4724, rel_tol=1e-3)
        assert results[3] == ("event4", 0.0)

    def test_batch_decay_preserves_order(self):
        """Test that batch_decay preserves input order."""
        now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

        events = [
            ("A", now - timedelta(days=5)),
            ("B", now - timedelta(days=2)),
            ("C", now),
            ("D", now - timedelta(days=10)),
        ]

        results = batch_decay(events, now)

        # Check order preserved
        assert [item[0] for item in results] == ["A", "B", "C", "D"]

    def test_batch_decay_empty_list(self):
        """Test that batch_decay handles empty list correctly."""
        now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

        results = batch_decay([], now)

        assert results == []

    def test_batch_decay_single_item(self):
        """Test that batch_decay handles single-item list correctly."""
        now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        event_time = now - timedelta(days=1)

        results = batch_decay([("single", event_time)], now)

        assert len(results) == 1
        assert results[0][0] == "single"
        assert math.isclose(results[0][1], 0.7788, rel_tol=1e-3)

    def test_batch_decay_defaults_to_current_time(self):
        """Test that batch_decay defaults to current time when not provided."""
        event_time = datetime.now(timezone.utc) - timedelta(days=1)
        events = [("test", event_time)]

        results = batch_decay(events)

        assert len(results) == 1
        # Should be approximately e^(-0.25) = 0.7788
        assert 0.77 < results[0][1] < 0.79

    def test_batch_decay_with_various_object_types(self):
        """Test that batch_decay works with various first element types."""
        now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

        # Mix different types as the "item" in (item, timestamp)
        events = [
            (42, now),
            ("string", now - timedelta(days=1)),
            ({"key": "value"}, now - timedelta(days=2)),
            ([1, 2, 3], now - timedelta(days=3)),
            (None, now - timedelta(days=4)),
        ]

        results = batch_decay(events, now)

        # All should process correctly
        assert len(results) == 5
        assert results[0][0] == 42
        assert results[1][0] == "string"
        assert results[2][0] == {"key": "value"}
        assert results[3][0] == [1, 2, 3]
        assert results[4][0] is None
