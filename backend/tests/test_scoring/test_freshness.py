"""Unit tests for freshness computation module.

Tests compute_freshness() and its label formatting helpers for both
storm-boosted and base-scored zone freshness classification.
"""

from datetime import datetime, timedelta, timezone

from app.scoring.freshness import compute_freshness, _format_storm_label, _format_base_label


NOW = datetime(2026, 2, 24, 12, 0, 0, tzinfo=timezone.utc)


class TestComputeFreshnessStormBranch:
    """Tests for storm zone freshness (has_active_storm=True)."""

    def test_fresh_storm_1_day_ago(self):
        result = compute_freshness(
            has_active_storm=True,
            primary_event_timestamp=NOW - timedelta(days=1),
            base_scored_at=None,
            updated_at=NOW - timedelta(days=60),
            current_time=NOW,
        )
        assert result["status"] == "fresh"
        assert result["age_days"] == 1.0

    def test_fresh_storm_just_happened(self):
        result = compute_freshness(
            has_active_storm=True,
            primary_event_timestamp=NOW - timedelta(hours=6),
            base_scored_at=None,
            updated_at=NOW,
            current_time=NOW,
        )
        assert result["status"] == "fresh"
        assert result["age_days"] == 0.2  # 6h / 24h = 0.25, rounded to 0.2

    def test_aging_storm_at_exactly_3_days(self):
        result = compute_freshness(
            has_active_storm=True,
            primary_event_timestamp=NOW - timedelta(days=3),
            base_scored_at=None,
            updated_at=NOW,
            current_time=NOW,
        )
        assert result["status"] == "aging"
        assert result["age_days"] == 3.0

    def test_aging_storm_5_days(self):
        result = compute_freshness(
            has_active_storm=True,
            primary_event_timestamp=NOW - timedelta(days=5),
            base_scored_at=None,
            updated_at=NOW,
            current_time=NOW,
        )
        assert result["status"] == "aging"
        assert result["age_days"] == 5.0

    def test_stale_storm_at_exactly_7_days(self):
        result = compute_freshness(
            has_active_storm=True,
            primary_event_timestamp=NOW - timedelta(days=7),
            base_scored_at=None,
            updated_at=NOW,
            current_time=NOW,
        )
        assert result["status"] == "stale"
        assert result["age_days"] == 7.0

    def test_stale_storm_14_days(self):
        result = compute_freshness(
            has_active_storm=True,
            primary_event_timestamp=NOW - timedelta(days=14),
            base_scored_at=None,
            updated_at=NOW,
            current_time=NOW,
        )
        assert result["status"] == "stale"
        assert result["age_days"] == 14.0

    def test_storm_label_sub_day_shows_hours(self):
        result = compute_freshness(
            has_active_storm=True,
            primary_event_timestamp=NOW - timedelta(hours=12),
            base_scored_at=None,
            updated_at=NOW,
            current_time=NOW,
        )
        assert result["label"] == "Storm 12h ago"

    def test_storm_label_multi_day(self):
        result = compute_freshness(
            has_active_storm=True,
            primary_event_timestamp=NOW - timedelta(days=4),
            base_scored_at=None,
            updated_at=NOW,
            current_time=NOW,
        )
        assert result["label"] == "Storm 4d ago"

    def test_storm_without_timestamp_uses_base_branch(self):
        """has_active_storm=True but no primary_event_timestamp falls to base branch."""
        result = compute_freshness(
            has_active_storm=True,
            primary_event_timestamp=None,
            base_scored_at=NOW - timedelta(days=10),
            updated_at=NOW,
            current_time=NOW,
        )
        assert result["status"] == "fresh"  # 10 days < 30 → fresh (base branch)


class TestComputeFreshnessBaseBranch:
    """Tests for base zone freshness (has_active_storm=False)."""

    def test_fresh_base_scored_today(self):
        result = compute_freshness(
            has_active_storm=False,
            primary_event_timestamp=None,
            base_scored_at=NOW - timedelta(hours=6),
            updated_at=NOW - timedelta(days=100),
            current_time=NOW,
        )
        assert result["status"] == "fresh"
        assert result["label"] == "Scored today"

    def test_fresh_base_15_days_ago(self):
        result = compute_freshness(
            has_active_storm=False,
            primary_event_timestamp=None,
            base_scored_at=NOW - timedelta(days=15),
            updated_at=NOW,
            current_time=NOW,
        )
        assert result["status"] == "fresh"
        assert result["age_days"] == 15.0

    def test_aging_at_exactly_30_days(self):
        result = compute_freshness(
            has_active_storm=False,
            primary_event_timestamp=None,
            base_scored_at=NOW - timedelta(days=30),
            updated_at=NOW,
            current_time=NOW,
        )
        assert result["status"] == "aging"
        assert result["age_days"] == 30.0

    def test_aging_at_60_days(self):
        result = compute_freshness(
            has_active_storm=False,
            primary_event_timestamp=None,
            base_scored_at=NOW - timedelta(days=60),
            updated_at=NOW,
            current_time=NOW,
        )
        assert result["status"] == "aging"
        assert result["age_days"] == 60.0

    def test_stale_at_exactly_90_days(self):
        result = compute_freshness(
            has_active_storm=False,
            primary_event_timestamp=None,
            base_scored_at=NOW - timedelta(days=90),
            updated_at=NOW,
            current_time=NOW,
        )
        assert result["status"] == "stale"
        assert result["age_days"] == 90.0

    def test_stale_at_400_days(self):
        result = compute_freshness(
            has_active_storm=False,
            primary_event_timestamp=None,
            base_scored_at=NOW - timedelta(days=400),
            updated_at=NOW,
            current_time=NOW,
        )
        assert result["status"] == "stale"

    def test_fallback_to_updated_at_when_base_scored_at_none(self):
        result = compute_freshness(
            has_active_storm=False,
            primary_event_timestamp=None,
            base_scored_at=None,
            updated_at=NOW - timedelta(days=45),
            current_time=NOW,
        )
        assert result["status"] == "aging"  # 45 days → aging
        assert result["age_days"] == 45.0

    def test_base_label_days(self):
        result = compute_freshness(
            has_active_storm=False,
            primary_event_timestamp=None,
            base_scored_at=NOW - timedelta(days=10),
            updated_at=NOW,
            current_time=NOW,
        )
        assert result["label"] == "Scored 10d ago"

    def test_base_label_months(self):
        result = compute_freshness(
            has_active_storm=False,
            primary_event_timestamp=None,
            base_scored_at=NOW - timedelta(days=60),
            updated_at=NOW,
            current_time=NOW,
        )
        assert result["label"] == "Scored 2mo ago"

    def test_base_label_years(self):
        result = compute_freshness(
            has_active_storm=False,
            primary_event_timestamp=None,
            base_scored_at=NOW - timedelta(days=400),
            updated_at=NOW,
            current_time=NOW,
        )
        assert result["label"] == "Scored 1.1yr ago"


class TestComputeFreshnessReturnShape:
    """Tests for return value structure."""

    def test_returns_all_keys(self):
        result = compute_freshness(
            has_active_storm=False,
            primary_event_timestamp=None,
            base_scored_at=NOW,
            updated_at=NOW,
            current_time=NOW,
        )
        assert "status" in result
        assert "age_days" in result
        assert "label" in result

    def test_status_is_valid_literal(self):
        for days in [0, 3, 7, 30, 90, 365]:
            result = compute_freshness(
                has_active_storm=False,
                primary_event_timestamp=None,
                base_scored_at=NOW - timedelta(days=days),
                updated_at=NOW,
                current_time=NOW,
            )
            assert result["status"] in ("fresh", "aging", "stale")

    def test_age_days_is_rounded(self):
        result = compute_freshness(
            has_active_storm=True,
            primary_event_timestamp=NOW - timedelta(hours=7),
            base_scored_at=None,
            updated_at=NOW,
            current_time=NOW,
        )
        # 7h = 0.29166... days → rounded to 0.3
        assert result["age_days"] == 0.3

    def test_defaults_to_utc_now_when_current_time_none(self):
        """Passing current_time=None should not raise."""
        result = compute_freshness(
            has_active_storm=False,
            primary_event_timestamp=None,
            base_scored_at=datetime.now(timezone.utc) - timedelta(days=1),
            updated_at=datetime.now(timezone.utc),
        )
        assert result["status"] == "fresh"


class TestFormatStormLabel:
    """Tests for _format_storm_label helper."""

    def test_sub_hour(self):
        assert _format_storm_label(0.02) == "Storm 0h ago"  # ~30 min

    def test_6_hours(self):
        assert _format_storm_label(0.25) == "Storm 6h ago"

    def test_23_hours(self):
        assert _format_storm_label(23 / 24) == "Storm 23h ago"

    def test_exactly_1_day(self):
        assert _format_storm_label(1.0) == "Storm 1d ago"

    def test_multi_day(self):
        assert _format_storm_label(5.0) == "Storm 5d ago"


class TestFormatBaseLabel:
    """Tests for _format_base_label helper."""

    def test_today(self):
        assert _format_base_label(0.5) == "Scored today"

    def test_1_day(self):
        assert _format_base_label(1.0) == "Scored 1d ago"

    def test_29_days(self):
        assert _format_base_label(29.0) == "Scored 29d ago"

    def test_30_days(self):
        assert _format_base_label(30.0) == "Scored 1mo ago"

    def test_60_days(self):
        assert _format_base_label(60.0) == "Scored 2mo ago"

    def test_364_days(self):
        assert _format_base_label(364.0) == "Scored 12mo ago"

    def test_365_days(self):
        assert _format_base_label(365.0) == "Scored 1.0yr ago"

    def test_730_days(self):
        assert _format_base_label(730.0) == "Scored 2.0yr ago"
