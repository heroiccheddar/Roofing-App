"""Unit tests for engine.py module.

Tests the scoring engine with mocked database and spatial functions.
Does not require a live database connection.
"""

import pytest
import math
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timedelta, timezone

from app.scoring.engine import score_single_zone, run_scoring_pipeline, compute_storm_boost
from app.scoring.weights import CURRENT_MODEL_VERSION


def _mock_session_for_scoring():
    """Create an AsyncMock session configured for score_single_zone tests.

    Returns a session where execute() returns a MagicMock (not AsyncMock)
    so that sync methods like .scalar_one_or_none() work correctly.
    """
    session = AsyncMock()
    mock_exec_result = MagicMock()
    mock_exec_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_exec_result
    return session


class TestScoringFormula:
    """Tests for scoring formula components."""

    @pytest.mark.asyncio
    async def test_scoring_formula_composite(self):
        """Test that composite score formula is: damage*0.50 + quality*0.30 + density*0.20."""
        # Create mock event with location
        from shapely.geometry import Point
        from geoalchemy2.shape import from_shape

        mock_event = MagicMock()
        mock_event.id = 1
        mock_event.event_timestamp = datetime.now(timezone.utc)
        mock_event.hail_diameter = 2.0  # 2" hail -> 50 damage score
        mock_event.wind_speed = 0
        mock_event.corroborated = False
        mock_event.location = from_shape(Point(-104.9903, 39.7392), srid=4326)

        # Mock session and tract data
        session = _mock_session_for_scoring()

        mock_tract = MagicMock()
        mock_tract.area_sq_km = 10.0
        mock_tract.owner_occupied_pct = 100.0  # 100% -> 40 pts
        mock_tract.median_home_value = 150000  # 150000/5000 = 30 pts
        mock_tract.median_year_built = 1980  # (2000-1980)*0.5 = 10 pts -> total quality = 80
        mock_tract.housing_units = 500  # 500/10 = 50 density -> 5 after /10
        mock_tract.population = 1000

        # Mock spatial functions
        with patch('app.scoring.engine.build_zone_boundary') as mock_boundary, \
             patch('app.scoring.engine.get_intersecting_tracts') as mock_tracts:

            mock_boundary.return_value = ("POLYGON(...)", "POINT(...)")
            mock_tracts.return_value = [mock_tract]

            zone = await score_single_zone(session, "test_h3", [mock_event])

        # Damage: 50 (hail) + 5 (1 event * 5) = 55
        # Quality: 40 (owner) + 30 (value) + 10 (age) = 80
        # Density: 50 / 10 = 5
        # Composite: 55*0.50 + 80*0.30 + 5*0.20 = 27.5 + 24 + 1 = 52.5
        # Decay: 1.0 (current event)
        # Final: 52.5

        assert zone is not None
        assert math.isclose(zone.composite_score, 52.5, rel_tol=0.01)

    @pytest.mark.asyncio
    async def test_score_band_assignment(self):
        """Test that score bands are assigned correctly: Hot 80-100, Warm 60-79, Cool 40-59, Skip 0-39.

        Composite = damage*0.50 + quality*0.30 + density*0.20, so all three
        sub-scores must be considered to reach each band.
        """
        from shapely.geometry import Point
        from geoalchemy2.shape import from_shape

        async def create_zone(hail, owner_pct, home_value, year_built, housing_units):
            mock_event = MagicMock()
            mock_event.id = 1
            mock_event.event_timestamp = datetime.now(timezone.utc)
            mock_event.hail_diameter = hail
            mock_event.wind_speed = 0
            mock_event.corroborated = False
            mock_event.location = from_shape(Point(-104.9903, 39.7392), srid=4326)

            session = _mock_session_for_scoring()
            mock_tract = MagicMock()
            mock_tract.area_sq_km = 10.0
            mock_tract.owner_occupied_pct = owner_pct
            mock_tract.median_home_value = home_value
            mock_tract.median_year_built = year_built
            mock_tract.housing_units = housing_units
            mock_tract.population = 2000

            with patch('app.scoring.engine.build_zone_boundary') as mock_boundary, \
                 patch('app.scoring.engine.get_intersecting_tracts') as mock_tracts:

                mock_boundary.return_value = ("POLYGON(...)", "POINT(...)")
                mock_tracts.return_value = [mock_tract]

                return await score_single_zone(session, "test_h3", [mock_event])

        # HOT: damage=100(cap), quality=100, density=50 → 50+30+10=90
        zone_hot = await create_zone(4.0, 100.0, 200000, 1940, 5000)
        assert zone_hot.score_band == "hot"

        # WARM: damage=100(cap), quality=35, density=5 → 50+10.5+1=61.5
        zone_warm = await create_zone(4.0, 50.0, 50000, 1990, 500)
        assert zone_warm.score_band == "warm"

        # COOL: damage=80, quality=35, density=5 → 40+10.5+1=51.5
        zone_cool = await create_zone(3.0, 50.0, 50000, 1990, 500)
        assert zone_cool.score_band == "cool"

        # SKIP: damage=30, quality=0, density=0 → 15+0+0=15
        zone_skip = await create_zone(1.0, 0.0, 0, 2020, 0)
        assert zone_skip.score_band == "skip"

    @pytest.mark.asyncio
    async def test_decay_applied_to_composite(self):
        """Test that composite score is multiplied by decay factor."""
        from shapely.geometry import Point
        from geoalchemy2.shape import from_shape

        # Create event from 1 day ago (decay factor ~0.7788)
        old_event = MagicMock()
        old_event.id = 1
        old_event.event_timestamp = datetime.now(timezone.utc) - timedelta(days=1)
        old_event.hail_diameter = 4.0  # 4" hail -> 100 damage
        old_event.wind_speed = 0
        old_event.corroborated = False
        old_event.location = from_shape(Point(-104.9903, 39.7392), srid=4326)

        session = _mock_session_for_scoring()
        mock_tract = MagicMock()
        mock_tract.area_sq_km = 10.0
        mock_tract.owner_occupied_pct = 0.0
        mock_tract.median_home_value = 0
        mock_tract.median_year_built = 2020
        mock_tract.housing_units = 0
        mock_tract.population = 0

        with patch('app.scoring.engine.build_zone_boundary') as mock_boundary, \
             patch('app.scoring.engine.get_intersecting_tracts') as mock_tracts:

            mock_boundary.return_value = ("POLYGON(...)", "POINT(...)")
            mock_tracts.return_value = [mock_tract]

            zone = await score_single_zone(session, "test_h3", [old_event])

        # Base damage: 100 (hail) + 5 (event count) = 105 -> capped at 100
        # Composite: 100*0.50 + 0*0.30 + 0*0.20 = 50
        # Decay: ~0.7788 (1 day old)
        # Final: 50 * 0.7788 = ~38.94

        assert zone is not None
        assert zone.composite_score < 50  # Should be less due to decay
        assert math.isclose(zone.composite_score, 38.94, rel_tol=0.05)

    @pytest.mark.asyncio
    async def test_score_capped_at_100(self):
        """Test that score never exceeds 100."""
        from shapely.geometry import Point
        from geoalchemy2.shape import from_shape

        # Create events with excessive damage values
        mock_event = MagicMock()
        mock_event.id = 1
        mock_event.event_timestamp = datetime.now(timezone.utc)
        mock_event.hail_diameter = 10.0  # 10" hail -> 250 (uncapped)
        mock_event.wind_speed = 200  # 200mph -> (200-50)*2 = 300 (uncapped)
        mock_event.corroborated = True
        mock_event.location = from_shape(Point(-104.9903, 39.7392), srid=4326)

        session = _mock_session_for_scoring()
        mock_tract = MagicMock()
        mock_tract.area_sq_km = 10.0
        mock_tract.owner_occupied_pct = 100.0
        mock_tract.median_home_value = 1000000
        mock_tract.median_year_built = 1900
        mock_tract.housing_units = 5000
        mock_tract.population = 10000

        with patch('app.scoring.engine.build_zone_boundary') as mock_boundary, \
             patch('app.scoring.engine.get_intersecting_tracts') as mock_tracts:

            mock_boundary.return_value = ("POLYGON(...)", "POINT(...)")
            mock_tracts.return_value = [mock_tract]

            zone = await score_single_zone(session, "test_h3", [mock_event])

        assert zone is not None
        assert zone.composite_score <= 100

    @pytest.mark.asyncio
    async def test_score_floored_at_0(self):
        """Test that score never goes below 0."""
        from shapely.geometry import Point
        from geoalchemy2.shape import from_shape

        # Create event with minimal damage, very old
        old_event = MagicMock()
        old_event.id = 1
        old_event.event_timestamp = datetime.now(timezone.utc) - timedelta(days=20)  # Beyond decay
        old_event.hail_diameter = 0
        old_event.wind_speed = 0
        old_event.corroborated = False
        old_event.location = from_shape(Point(-104.9903, 39.7392), srid=4326)

        session = _mock_session_for_scoring()
        mock_tract = MagicMock()
        mock_tract.area_sq_km = 10.0
        mock_tract.owner_occupied_pct = 0.0
        mock_tract.median_home_value = 0
        mock_tract.median_year_built = 2020
        mock_tract.housing_units = 0
        mock_tract.population = 0

        with patch('app.scoring.engine.build_zone_boundary') as mock_boundary, \
             patch('app.scoring.engine.get_intersecting_tracts') as mock_tracts:

            mock_boundary.return_value = ("POLYGON(...)", "POINT(...)")
            mock_tracts.return_value = [mock_tract]

            zone = await score_single_zone(session, "test_h3", [old_event])

        assert zone is not None
        assert zone.composite_score >= 0


class TestDamageProbCalculation:
    """Tests for damage_prob sub-score calculation."""

    @pytest.mark.asyncio
    async def test_damage_prob_from_hail(self):
        """Test that damage_prob from hail is: max_hail_diameter * 25, capped at 100."""
        from shapely.geometry import Point
        from geoalchemy2.shape import from_shape

        async def test_hail_damage(diameter, expected_base):
            mock_event = MagicMock()
            mock_event.id = 1
            mock_event.event_timestamp = datetime.now(timezone.utc)
            mock_event.hail_diameter = diameter
            mock_event.wind_speed = 0
            mock_event.corroborated = False
            mock_event.location = from_shape(Point(-104.9903, 39.7392), srid=4326)

            session = _mock_session_for_scoring()
            mock_tract = MagicMock()
            mock_tract.area_sq_km = 10.0
            mock_tract.owner_occupied_pct = 0.0
            mock_tract.median_home_value = 0
            mock_tract.median_year_built = 2020
            mock_tract.housing_units = 0
            mock_tract.population = 0

            with patch('app.scoring.engine.build_zone_boundary') as mock_boundary, \
                 patch('app.scoring.engine.get_intersecting_tracts') as mock_tracts:

                mock_boundary.return_value = ("POLYGON(...)", "POINT(...)")
                mock_tracts.return_value = [mock_tract]

                zone = await score_single_zone(session, "test_h3", [mock_event])

            # Expected: hail_score + event_count_bonus (5)
            expected_damage = min(expected_base + 5, 100)
            return zone.damage_prob, expected_damage

        # Test 1" hail: 1 * 25 = 25
        actual, expected = await test_hail_damage(1.0, 25)
        assert math.isclose(actual, expected, rel_tol=0.01)

        # Test 2" hail: 2 * 25 = 50
        actual, expected = await test_hail_damage(2.0, 50)
        assert math.isclose(actual, expected, rel_tol=0.01)

        # Test 4" hail: 4 * 25 = 100
        actual, expected = await test_hail_damage(4.0, 100)
        assert actual == 100  # Capped at 100 (100 + 5 = 105, capped to 100)

        # Test 10" hail: 10 * 25 = 250 -> capped at 100
        actual, expected = await test_hail_damage(10.0, 250)
        assert actual == 100

    @pytest.mark.asyncio
    async def test_damage_prob_from_wind(self):
        """Test that damage_prob from wind is: (max_wind_speed - 50) * 2, capped at 100."""
        from shapely.geometry import Point
        from geoalchemy2.shape import from_shape

        async def test_wind_damage(wind_speed, expected_base):
            mock_event = MagicMock()
            mock_event.id = 1
            mock_event.event_timestamp = datetime.now(timezone.utc)
            mock_event.hail_diameter = 0
            mock_event.wind_speed = wind_speed
            mock_event.corroborated = False
            mock_event.location = from_shape(Point(-104.9903, 39.7392), srid=4326)

            session = _mock_session_for_scoring()
            mock_tract = MagicMock()
            mock_tract.area_sq_km = 10.0
            mock_tract.owner_occupied_pct = 0.0
            mock_tract.median_home_value = 0
            mock_tract.median_year_built = 2020
            mock_tract.housing_units = 0
            mock_tract.population = 0

            with patch('app.scoring.engine.build_zone_boundary') as mock_boundary, \
                 patch('app.scoring.engine.get_intersecting_tracts') as mock_tracts:

                mock_boundary.return_value = ("POLYGON(...)", "POINT(...)")
                mock_tracts.return_value = [mock_tract]

                zone = await score_single_zone(session, "test_h3", [mock_event])

            # Wind score: max(0, (speed - 50) * 2)
            # Add event count bonus: +5
            wind_score = max(0, (wind_speed - 50) * 2)
            expected_damage = min(wind_score + 5, 100)
            return zone.damage_prob, expected_damage

        # Test 40 mph (below threshold): 0
        actual, expected = await test_wind_damage(40, 0)
        assert actual == 5  # Just the event count bonus

        # Test 75 mph: (75-50)*2 = 50
        actual, expected = await test_wind_damage(75, 50)
        assert math.isclose(actual, expected, rel_tol=0.01)

        # Test 100 mph: (100-50)*2 = 100
        actual, expected = await test_wind_damage(100, 100)
        assert actual == 100

        # Test 200 mph: (200-50)*2 = 300 -> capped at 100
        actual, expected = await test_wind_damage(200, 300)
        assert actual == 100

    @pytest.mark.asyncio
    async def test_corroboration_bonus(self):
        """Test that +10 is added for corroborated events."""
        from shapely.geometry import Point
        from geoalchemy2.shape import from_shape

        # Event without corroboration
        event_no_corr = MagicMock()
        event_no_corr.id = 1
        event_no_corr.event_timestamp = datetime.now(timezone.utc)
        event_no_corr.hail_diameter = 2.0  # 50 base
        event_no_corr.wind_speed = 0
        event_no_corr.corroborated = False
        event_no_corr.location = from_shape(Point(-104.9903, 39.7392), srid=4326)

        # Event with corroboration
        event_with_corr = MagicMock()
        event_with_corr.id = 2
        event_with_corr.event_timestamp = datetime.now(timezone.utc)
        event_with_corr.hail_diameter = 2.0  # 50 base
        event_with_corr.wind_speed = 0
        event_with_corr.corroborated = True
        event_with_corr.location = from_shape(Point(-104.9903, 39.7392), srid=4326)

        session = _mock_session_for_scoring()
        mock_tract = MagicMock()
        mock_tract.area_sq_km = 10.0
        mock_tract.owner_occupied_pct = 0.0
        mock_tract.median_home_value = 0
        mock_tract.median_year_built = 2020
        mock_tract.housing_units = 0
        mock_tract.population = 0

        with patch('app.scoring.engine.build_zone_boundary') as mock_boundary, \
             patch('app.scoring.engine.get_intersecting_tracts') as mock_tracts:

            mock_boundary.return_value = ("POLYGON(...)", "POINT(...)")
            mock_tracts.return_value = [mock_tract]

            zone_no_corr = await score_single_zone(session, "test_h3_1", [event_no_corr])
            zone_with_corr = await score_single_zone(session, "test_h3_2", [event_with_corr])

        # Difference should be exactly 10 (corroboration bonus)
        # Base: 50 (hail) + 5 (event count) = 55
        # With corroboration: 50 + 5 + 10 = 65
        assert zone_no_corr.damage_prob == 55
        assert zone_with_corr.damage_prob == 65

    @pytest.mark.asyncio
    async def test_event_count_bonus(self):
        """Test that event count adds: min(count * 5, 20) to damage_prob."""
        from shapely.geometry import Point
        from geoalchemy2.shape import from_shape

        async def test_count_bonus(num_events, expected_bonus):
            events = []
            for i in range(num_events):
                event = MagicMock()
                event.id = i
                event.event_timestamp = datetime.now(timezone.utc)
                event.hail_diameter = 2.0  # 50 base
                event.wind_speed = 0
                event.corroborated = False
                event.location = from_shape(Point(-104.9903, 39.7392), srid=4326)
                events.append(event)

            session = _mock_session_for_scoring()
            mock_tract = MagicMock()
            mock_tract.area_sq_km = 10.0
            mock_tract.owner_occupied_pct = 0.0
            mock_tract.median_home_value = 0
            mock_tract.median_year_built = 2020
            mock_tract.housing_units = 0
            mock_tract.population = 0

            with patch('app.scoring.engine.build_zone_boundary') as mock_boundary, \
                 patch('app.scoring.engine.get_intersecting_tracts') as mock_tracts:

                mock_boundary.return_value = ("POLYGON(...)", "POINT(...)")
                mock_tracts.return_value = [mock_tract]

                zone = await score_single_zone(session, "test_h3", events)

            # Base: 50 (max hail from any event) + expected_bonus
            expected_damage = 50 + expected_bonus
            return zone.damage_prob, expected_damage

        # 1 event: 1 * 5 = 5
        actual, expected = await test_count_bonus(1, 5)
        assert actual == expected

        # 2 events: 2 * 5 = 10
        actual, expected = await test_count_bonus(2, 10)
        assert actual == expected

        # 4 events: 4 * 5 = 20 (at cap)
        actual, expected = await test_count_bonus(4, 20)
        assert actual == expected

        # 10 events: 10 * 5 = 50 -> capped at 20
        actual, expected = await test_count_bonus(10, 20)
        assert actual == expected


class TestLeadQualityCalculation:
    """Tests for lead_quality sub-score calculation."""

    @pytest.mark.asyncio
    async def test_lead_quality_owner_occupied(self):
        """Test that owner_occupied_pct contributes: owner_occupied_pct * 0.4 (max 40 pts)."""
        from shapely.geometry import Point
        from geoalchemy2.shape import from_shape

        mock_event = MagicMock()
        mock_event.id = 1
        mock_event.event_timestamp = datetime.now(timezone.utc)
        mock_event.hail_diameter = 0
        mock_event.wind_speed = 0
        mock_event.corroborated = False
        mock_event.location = from_shape(Point(-104.9903, 39.7392), srid=4326)

        session = _mock_session_for_scoring()
        mock_tract = MagicMock()
        mock_tract.area_sq_km = 10.0
        mock_tract.owner_occupied_pct = 75.0  # 75 * 0.4 = 30
        mock_tract.median_home_value = 0
        mock_tract.median_year_built = 2020
        mock_tract.housing_units = 0
        mock_tract.population = 0

        with patch('app.scoring.engine.build_zone_boundary') as mock_boundary, \
             patch('app.scoring.engine.get_intersecting_tracts') as mock_tracts:

            mock_boundary.return_value = ("POLYGON(...)", "POINT(...)")
            mock_tracts.return_value = [mock_tract]

            zone = await score_single_zone(session, "test_h3", [mock_event])

        # Expected: 75 * 0.4 = 30
        assert math.isclose(zone.lead_quality, 30.0, rel_tol=0.01)

    @pytest.mark.asyncio
    async def test_lead_quality_home_value(self):
        """Test that home_value contributes: min(value / 5000, 30)."""
        from shapely.geometry import Point
        from geoalchemy2.shape import from_shape

        async def test_value_contrib(home_value, expected_contrib):
            mock_event = MagicMock()
            mock_event.id = 1
            mock_event.event_timestamp = datetime.now(timezone.utc)
            mock_event.hail_diameter = 0
            mock_event.wind_speed = 0
            mock_event.corroborated = False
            mock_event.location = from_shape(Point(-104.9903, 39.7392), srid=4326)

            session = _mock_session_for_scoring()
            mock_tract = MagicMock()
            mock_tract.area_sq_km = 10.0
            mock_tract.owner_occupied_pct = 0.0
            mock_tract.median_home_value = home_value
            mock_tract.median_year_built = 2020
            mock_tract.housing_units = 0
            mock_tract.population = 0

            with patch('app.scoring.engine.build_zone_boundary') as mock_boundary, \
                 patch('app.scoring.engine.get_intersecting_tracts') as mock_tracts:

                mock_boundary.return_value = ("POLYGON(...)", "POINT(...)")
                mock_tracts.return_value = [mock_tract]

                zone = await score_single_zone(session, "test_h3", [mock_event])

            return zone.lead_quality

        # $100,000: 100000 / 5000 = 20
        quality = await test_value_contrib(100000, 20)
        assert math.isclose(quality, 20.0, rel_tol=0.01)

        # $150,000: 150000 / 5000 = 30 (at cap)
        quality = await test_value_contrib(150000, 30)
        assert math.isclose(quality, 30.0, rel_tol=0.01)

        # $500,000: 500000 / 5000 = 100 -> capped at 30
        quality = await test_value_contrib(500000, 30)
        assert math.isclose(quality, 30.0, rel_tol=0.01)

    @pytest.mark.asyncio
    async def test_lead_quality_roof_age(self):
        """Test that roof_age contributes: min((2000 - year) * 0.5, 30) for pre-2000 homes."""
        from shapely.geometry import Point
        from geoalchemy2.shape import from_shape

        async def test_age_contrib(year_built, expected_contrib):
            mock_event = MagicMock()
            mock_event.id = 1
            mock_event.event_timestamp = datetime.now(timezone.utc)
            mock_event.hail_diameter = 0
            mock_event.wind_speed = 0
            mock_event.corroborated = False
            mock_event.location = from_shape(Point(-104.9903, 39.7392), srid=4326)

            session = _mock_session_for_scoring()
            mock_tract = MagicMock()
            mock_tract.area_sq_km = 10.0
            mock_tract.owner_occupied_pct = 0.0
            mock_tract.median_home_value = 0
            mock_tract.median_year_built = year_built
            mock_tract.housing_units = 0
            mock_tract.population = 0

            with patch('app.scoring.engine.build_zone_boundary') as mock_boundary, \
                 patch('app.scoring.engine.get_intersecting_tracts') as mock_tracts:

                mock_boundary.return_value = ("POLYGON(...)", "POINT(...)")
                mock_tracts.return_value = [mock_tract]

                zone = await score_single_zone(session, "test_h3", [mock_event])

            return zone.lead_quality

        # 1990: (2000-1990) * 0.5 = 5
        quality = await test_age_contrib(1990, 5)
        assert math.isclose(quality, 5.0, rel_tol=0.01)

        # 1980: (2000-1980) * 0.5 = 10
        quality = await test_age_contrib(1980, 10)
        assert math.isclose(quality, 10.0, rel_tol=0.01)

        # 1940: (2000-1940) * 0.5 = 30 (at cap)
        quality = await test_age_contrib(1940, 30)
        assert math.isclose(quality, 30.0, rel_tol=0.01)

        # 1900: (2000-1900) * 0.5 = 50 -> capped at 30
        quality = await test_age_contrib(1900, 30)
        assert math.isclose(quality, 30.0, rel_tol=0.01)

        # 2010: No contribution (post-2000)
        quality = await test_age_contrib(2010, 0)
        assert math.isclose(quality, 0.0, rel_tol=0.01)


class TestRunScoringPipeline:
    """Tests for run_scoring_pipeline() orchestration function."""

    @pytest.mark.asyncio
    async def test_pipeline_returns_stats(self):
        """Test that pipeline returns stats dict with expected keys."""
        session = AsyncMock()

        # Mock empty result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        session.execute.return_value = mock_result

        stats = await run_scoring_pipeline(session)

        assert "events_processed" in stats
        assert "zones_created" in stats
        assert "zones_updated" in stats
        assert "errors" in stats

    @pytest.mark.asyncio
    async def test_pipeline_no_events(self):
        """Test that pipeline handles no unscored events gracefully."""
        session = AsyncMock()

        # Mock empty result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        session.execute.return_value = mock_result

        stats = await run_scoring_pipeline(session)

        assert stats["events_processed"] == 0
        assert stats["zones_created"] == 0
        assert stats["zones_updated"] == 0
        assert stats["errors"] == 0


def _make_event(hail=0.0, wind=0.0, corroborated=False):
    """Create a minimal mock StormEvent for compute_storm_boost tests."""
    from types import SimpleNamespace
    return SimpleNamespace(
        hail_diameter=hail,
        wind_speed=wind,
        corroborated=corroborated,
    )


class TestComputeStormBoost:
    """Tests for compute_storm_boost() pure function.

    Uses SimpleNamespace mocks — no database or async required.
    """

    def test_hail_score_formula(self):
        """hail_score = min(diameter * 25, 100)."""
        # 2" hail → 50
        boost, max_hail, max_wind = compute_storm_boost(
            [_make_event(hail=2.0)], {}
        )
        # event_damage = max(50, 0) = 50, + count bonus 5 = 55
        assert max_hail == 2.0
        assert boost >= 55.0

    def test_hail_capped_at_100(self):
        """4" hail → 100 (capped)."""
        boost, max_hail, _ = compute_storm_boost(
            [_make_event(hail=4.0)], {}
        )
        assert max_hail == 4.0
        # event_damage = 100 + 5 (count) = 105, then capped at 100 by outer min
        assert boost <= 100.0

    def test_wind_score_formula(self):
        """wind_score = min(max((speed - 50) * 2, 0), 100)."""
        # 75 mph → (75-50)*2 = 50
        boost, _, max_wind = compute_storm_boost(
            [_make_event(wind=75.0)], {}
        )
        assert max_wind == 75.0
        assert boost >= 55.0  # 50 + 5 count bonus

    def test_wind_below_threshold(self):
        """Wind < 50 mph produces zero wind score."""
        boost, _, max_wind = compute_storm_boost(
            [_make_event(wind=40.0)], {}
        )
        assert max_wind == 40.0
        # event_damage = max(0, 0) = 0 + count 5 = 5
        assert boost >= 5.0

    def test_wind_capped_at_100(self):
        """200 mph → (200-50)*2 = 300 → capped at 100."""
        boost, _, _ = compute_storm_boost(
            [_make_event(wind=200.0)], {}
        )
        assert boost <= 100.0

    def test_hail_vs_wind_takes_max(self):
        """event_damage = max(hail_score, wind_score)."""
        # hail=2 → 50, wind=75 → 50 → both equal, should be 50
        boost1, _, _ = compute_storm_boost(
            [_make_event(hail=2.0, wind=75.0)], {}
        )
        # hail=3 → 75, wind=60 → 20 → hail wins
        boost2, _, _ = compute_storm_boost(
            [_make_event(hail=3.0, wind=60.0)], {}
        )
        assert boost2 > boost1  # 75 > 50

    def test_corroboration_bonus(self):
        """Corroborated events add +10."""
        no_corr = compute_storm_boost([_make_event(hail=2.0)], {})[0]
        with_corr = compute_storm_boost(
            [_make_event(hail=2.0, corroborated=True)], {}
        )[0]
        assert math.isclose(with_corr - no_corr, 10.0, abs_tol=0.1)

    def test_event_count_bonus(self):
        """Count bonus = min(count * 5, 20)."""
        one_event = compute_storm_boost([_make_event(hail=2.0)], {})[0]
        two_events = compute_storm_boost(
            [_make_event(hail=2.0), _make_event(hail=1.0)], {}
        )[0]
        # 2 events → 10 bonus vs 1 event → 5 bonus = +5 difference
        assert math.isclose(two_events - one_event, 5.0, abs_tol=0.1)

    def test_event_count_bonus_capped_at_20(self):
        """10 events should still only get +20 bonus (not 50)."""
        events = [_make_event(hail=2.0) for _ in range(10)]
        boost_10 = compute_storm_boost(events, {})[0]
        events_4 = [_make_event(hail=2.0) for _ in range(4)]
        boost_4 = compute_storm_boost(events_4, {})[0]
        # Both should have +20 count bonus (4*5=20, 10*5=50→capped at 20)
        assert math.isclose(boost_10, boost_4, abs_tol=0.1)

    def test_nri_risk_modifier(self):
        """NRI frequency data adds up to 15 bonus points."""
        demographics = {
            "avg_nri_hail_afreq": 1.0,
            "avg_nri_swnd_afreq": 1.0,
            "avg_nri_trnd_afreq": 0.5,
        }
        boost_with = compute_storm_boost([_make_event(hail=1.0)], demographics)[0]
        boost_without = compute_storm_boost([_make_event(hail=1.0)], {})[0]
        # NRI: 1.0*5 + 1.0*2.5 + 0.5*10 = 12.5 points
        assert boost_with > boost_without

    def test_empty_events_returns_zeros(self):
        """No events → storm_boost=0, max_hail=0, max_wind=0."""
        boost, max_hail, max_wind = compute_storm_boost([], {})
        assert boost == 0.0
        assert max_hail == 0.0
        assert max_wind == 0.0

    def test_overall_cap_at_100(self):
        """Storm boost should never exceed 100 even with all modifiers maxed."""
        events = [
            _make_event(hail=5.0, wind=200.0, corroborated=True),
            _make_event(hail=4.0, wind=150.0),
            _make_event(hail=3.0, wind=120.0),
            _make_event(hail=3.0, wind=100.0),
            _make_event(hail=2.0, wind=80.0),
        ]
        demographics = {
            "avg_nri_hail_afreq": 3.0,
            "avg_nri_swnd_afreq": 3.0,
            "avg_nri_trnd_afreq": 1.5,
            "avg_hail_exposure_score": 100.0,
            "avg_fema_disaster_score": 100.0,
            "avg_tree_canopy_risk_score": 100.0,
            "avg_verified_damage_5yr_usd": 10_000_000,
            "avg_climate_weathering_score": 100.0,
            "avg_svi_overall": 1.0,
        }
        boost, _, _ = compute_storm_boost(events, demographics)
        assert boost == 100.0

    def test_returns_correct_max_values(self):
        """Max hail and wind should come from the highest-value event."""
        events = [
            _make_event(hail=1.5, wind=60.0),
            _make_event(hail=2.5, wind=90.0),
            _make_event(hail=2.0, wind=70.0),
        ]
        _, max_hail, max_wind = compute_storm_boost(events, {})
        assert max_hail == 2.5
        assert max_wind == 90.0
