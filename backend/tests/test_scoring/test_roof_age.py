"""Unit tests for roof age scoring engine.

Tests compute_roof_age_score() — a pure function that scores zones based on
housing age demographics without requiring any database connection.
"""

import math

from app.scoring.roof_age_engine import compute_roof_age_score


class TestComputeRoofAgeScore:
    """Tests for compute_roof_age_score pure function."""

    def test_returns_expected_keys(self):
        result = compute_roof_age_score({})
        assert "composite_score" in result
        assert "lead_quality" in result
        assert "damage_prob" in result
        assert "density_bonus" in result
        assert "roof_age_score" in result
        assert "owner_score" in result
        assert "value_score" in result
        assert "density_score" in result

    def test_empty_demographics_defaults_to_50(self):
        """Missing keys default to 50.0; weights sum to 1.0, so score = 50."""
        result = compute_roof_age_score({})
        assert math.isclose(result["composite_score"], 50.0, abs_tol=0.1)

    def test_all_zero_percentiles(self):
        """All percentiles at 0 → composite_score = 0."""
        demographics = {
            "pctile_roof_age": 0.0,
            "pctile_pre1980_housing": 0.0,
            "pctile_owner_occupied": 0.0,
            "pctile_home_value": 0.0,
            "pctile_income": 0.0,
            "pctile_low_cost_burden": 0.0,
            "pctile_density": 0.0,
            "pctile_single_family": 0.0,
            "pctile_climate_weathering": 0.0,
            "pctile_canopy_risk": 0.0,
            "pctile_fema_risk": 0.0,
            "pctile_age_clustering": 0.0,
            "pctile_hpi_appreciation": 0.0,
            "pctile_svi_vulnerability": 0.0,
            "pctile_market_activity": 0.0,
        }
        result = compute_roof_age_score(demographics)
        assert result["composite_score"] == 0.0

    def test_all_100_percentiles(self):
        """All percentiles at 100 → composite_score = 100."""
        demographics = {
            "pctile_roof_age": 100.0,
            "pctile_pre1980_housing": 100.0,
            "pctile_owner_occupied": 100.0,
            "pctile_home_value": 100.0,
            "pctile_income": 100.0,
            "pctile_low_cost_burden": 100.0,
            "pctile_density": 100.0,
            "pctile_single_family": 100.0,
            "pctile_climate_weathering": 100.0,
            "pctile_canopy_risk": 100.0,
            "pctile_fema_risk": 100.0,
            "pctile_age_clustering": 100.0,
            "pctile_hpi_appreciation": 100.0,
            "pctile_svi_vulnerability": 100.0,
            "pctile_market_activity": 100.0,
        }
        result = compute_roof_age_score(demographics)
        assert result["composite_score"] == 100.0

    def test_roof_age_is_dominant_weight(self):
        """roof_age has weight 0.22 — setting it high should increase score."""
        # Only roof_age at 100, rest missing (default 50)
        high_roof_age = compute_roof_age_score({"pctile_roof_age": 100.0})
        low_roof_age = compute_roof_age_score({"pctile_roof_age": 0.0})
        # Difference should be 100 * 0.22 = 22 points
        diff = high_roof_age["composite_score"] - low_roof_age["composite_score"]
        assert math.isclose(diff, 22.0, abs_tol=0.1)

    def test_known_input_composite(self):
        """Verify composite with known inputs."""
        demographics = {
            "pctile_roof_age": 80.0,
            "pctile_pre1980_housing": 70.0,
            "pctile_owner_occupied": 60.0,
            "pctile_home_value": 50.0,
            "pctile_income": 40.0,
            "pctile_low_cost_burden": 30.0,
            "pctile_density": 20.0,
            "pctile_single_family": 10.0,
            "pctile_climate_weathering": 90.0,
            "pctile_canopy_risk": 55.0,
            "pctile_fema_risk": 45.0,
            "pctile_age_clustering": 65.0,
            "pctile_hpi_appreciation": 35.0,
            "pctile_svi_vulnerability": 25.0,
            "pctile_market_activity": 75.0,
        }
        result = compute_roof_age_score(demographics)
        # Manual: 80*0.22 + 70*0.08 + 60*0.10 + 50*0.08 + 40*0.09 + 30*0.07
        #       + 20*0.06 + 10*0.04 + 90*0.06 + 55*0.04 + 45*0.03 + 65*0.04
        #       + 35*0.03 + 25*0.02 + 75*0.04
        expected = (
            80 * 0.22 + 70 * 0.08 + 60 * 0.10 + 50 * 0.08 + 40 * 0.09 +
            30 * 0.07 + 20 * 0.06 + 10 * 0.04 + 90 * 0.06 + 55 * 0.04 +
            45 * 0.03 + 65 * 0.04 + 35 * 0.03 + 25 * 0.02 + 75 * 0.04
        )
        assert math.isclose(result["composite_score"], expected, abs_tol=0.01)

    def test_composite_clamped_to_range(self):
        """Score should always be in [0, 100]."""
        result = compute_roof_age_score({})
        assert 0.0 <= result["composite_score"] <= 100.0

    def test_damage_prob_always_zero(self):
        """Roof age zones have no storm damage component."""
        result = compute_roof_age_score({"pctile_roof_age": 95.0})
        assert result["damage_prob"] == 0.0

    def test_lead_quality_equals_composite(self):
        """lead_quality is set to composite_score for compatibility."""
        result = compute_roof_age_score({"pctile_roof_age": 75.0})
        assert result["lead_quality"] == result["composite_score"]

    def test_density_bonus_from_percentile(self):
        """density_bonus comes from pctile_density."""
        result = compute_roof_age_score({"pctile_density": 80.0})
        assert result["density_bonus"] == 80.0

    def test_density_bonus_defaults_to_50(self):
        result = compute_roof_age_score({})
        assert result["density_bonus"] == 50.0

    def test_current_year_param_ignored(self):
        """current_year is unused but shouldn't cause errors."""
        r1 = compute_roof_age_score({}, current_year=2025)
        r2 = compute_roof_age_score({}, current_year=None)
        assert r1["composite_score"] == r2["composite_score"]

    def test_partial_demographics(self):
        """Only some pctile keys present; others default to 50."""
        result = compute_roof_age_score({
            "pctile_roof_age": 90.0,
            "pctile_income": 70.0,
        })
        # roof_age: 90 * 0.22 = 19.8
        # income: 70 * 0.09 = 6.3
        # all others: 50 * remaining_weight = 50 * (1.0 - 0.22 - 0.09) = 50 * 0.69 = 34.5
        expected = 19.8 + 6.3 + 34.5
        assert math.isclose(result["composite_score"], expected, abs_tol=0.1)
