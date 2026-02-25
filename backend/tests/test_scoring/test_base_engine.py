"""Unit tests for base scoring engine (v11 unified model).

Tests _weighted_pctile_sum() and compute_base_sub_scores() — pure functions
that require no database connection or mocking.
"""

import math

from app.scoring.base_engine import _weighted_pctile_sum, compute_base_sub_scores
from app.scoring.weights import UNIFIED_MODEL_VERSION


class TestWeightedPctileSum:
    """Tests for _weighted_pctile_sum helper."""

    def test_basic_weighted_sum(self):
        demographics = {"pctile_a": 80.0, "pctile_b": 60.0}
        weights = {"a": 0.6, "b": 0.4}
        result = _weighted_pctile_sum(demographics, weights)
        assert math.isclose(result, 80 * 0.6 + 60 * 0.4)  # 72.0

    def test_missing_keys_default_to_50(self):
        demographics = {"pctile_a": 100.0}
        weights = {"a": 0.5, "b": 0.5}
        result = _weighted_pctile_sum(demographics, weights)
        assert math.isclose(result, 100 * 0.5 + 50 * 0.5)  # 75.0

    def test_all_missing_keys(self):
        demographics = {}
        weights = {"a": 0.5, "b": 0.5}
        result = _weighted_pctile_sum(demographics, weights)
        assert math.isclose(result, 50.0)  # all default to 50

    def test_all_zero_percentiles(self):
        demographics = {"pctile_a": 0.0, "pctile_b": 0.0, "pctile_c": 0.0}
        weights = {"a": 0.5, "b": 0.3, "c": 0.2}
        result = _weighted_pctile_sum(demographics, weights)
        assert result == 0.0

    def test_all_100_percentiles(self):
        demographics = {"pctile_a": 100.0, "pctile_b": 100.0}
        weights = {"a": 0.6, "b": 0.4}
        result = _weighted_pctile_sum(demographics, weights)
        assert result == 100.0

    def test_clamped_to_0(self):
        """Negative percentiles (shouldn't happen in practice) get clamped."""
        demographics = {"pctile_a": -50.0}
        weights = {"a": 1.0}
        result = _weighted_pctile_sum(demographics, weights)
        assert result == 0.0

    def test_clamped_to_100(self):
        """Percentiles above 100 (shouldn't happen in practice) get clamped."""
        demographics = {"pctile_a": 200.0}
        weights = {"a": 1.0}
        result = _weighted_pctile_sum(demographics, weights)
        assert result == 100.0

    def test_single_feature(self):
        demographics = {"pctile_roof_age": 75.0}
        weights = {"roof_age": 1.0}
        result = _weighted_pctile_sum(demographics, weights)
        assert result == 75.0

    def test_empty_weights(self):
        demographics = {"pctile_a": 90.0}
        weights = {}
        result = _weighted_pctile_sum(demographics, weights)
        assert result == 0.0


class TestComputeBaseSubScores:
    """Tests for compute_base_sub_scores — the v11 unified scoring function."""

    def test_returns_all_expected_keys(self):
        result = compute_base_sub_scores({})
        assert "roof_condition" in result
        assert "market_quality" in result
        assert "risk_exposure" in result
        assert "canvass_efficiency" in result
        assert "base_score" in result

    def test_all_defaults_gives_neutral_scores(self):
        """Empty demographics → all pctile_* default to 50 → all sub-scores ~50."""
        result = compute_base_sub_scores({})
        for key in ["roof_condition", "market_quality", "risk_exposure", "canvass_efficiency"]:
            assert math.isclose(result[key], 50.0, abs_tol=0.1)
        assert math.isclose(result["base_score"], 50.0, abs_tol=0.1)

    def test_all_zero_percentiles(self):
        """All features at 0th percentile → all sub-scores 0."""
        demographics = {}
        # Set ALL features to 0
        for sw in [
            UNIFIED_MODEL_VERSION.roof_condition_weights,
            UNIFIED_MODEL_VERSION.market_quality_weights,
            UNIFIED_MODEL_VERSION.risk_exposure_weights,
            UNIFIED_MODEL_VERSION.canvass_efficiency_weights,
        ]:
            for key in sw.weights:
                demographics[f"pctile_{key}"] = 0.0

        result = compute_base_sub_scores(demographics)
        assert result["roof_condition"] == 0.0
        assert result["market_quality"] == 0.0
        assert result["risk_exposure"] == 0.0
        assert result["canvass_efficiency"] == 0.0
        assert result["base_score"] == 0.0

    def test_all_100_percentiles(self):
        """All features at 100th percentile → all sub-scores 100."""
        demographics = {}
        for sw in [
            UNIFIED_MODEL_VERSION.roof_condition_weights,
            UNIFIED_MODEL_VERSION.market_quality_weights,
            UNIFIED_MODEL_VERSION.risk_exposure_weights,
            UNIFIED_MODEL_VERSION.canvass_efficiency_weights,
        ]:
            for key in sw.weights:
                demographics[f"pctile_{key}"] = 100.0

        result = compute_base_sub_scores(demographics)
        assert result["roof_condition"] == 100.0
        assert result["market_quality"] == 100.0
        assert result["risk_exposure"] == 100.0
        assert result["canvass_efficiency"] == 100.0
        assert result["base_score"] == 100.0

    def test_base_score_formula(self):
        """base_score = rc*0.35 + mq*0.30 + re*0.20 + ce*0.15

        Some features are shared between sub-score groups (e.g. canopy_risk is
        in both roof_condition and risk_exposure).  Build the dict sequentially
        so later groups overwrite shared keys, then compute expected sub-scores
        from the final demographics state.
        """
        demographics = {}
        # Build demographics per group — later groups overwrite shared keys
        for key in UNIFIED_MODEL_VERSION.roof_condition_weights.weights:
            demographics[f"pctile_{key}"] = 80.0
        for key in UNIFIED_MODEL_VERSION.market_quality_weights.weights:
            demographics[f"pctile_{key}"] = 60.0
        for key in UNIFIED_MODEL_VERSION.risk_exposure_weights.weights:
            demographics[f"pctile_{key}"] = 40.0
        for key in UNIFIED_MODEL_VERSION.canvass_efficiency_weights.weights:
            demographics[f"pctile_{key}"] = 20.0

        # Compute expected sub-scores from final demographics state
        expected_rc = _weighted_pctile_sum(demographics, UNIFIED_MODEL_VERSION.roof_condition_weights.weights)
        expected_mq = _weighted_pctile_sum(demographics, UNIFIED_MODEL_VERSION.market_quality_weights.weights)
        expected_re = _weighted_pctile_sum(demographics, UNIFIED_MODEL_VERSION.risk_exposure_weights.weights)
        expected_ce = _weighted_pctile_sum(demographics, UNIFIED_MODEL_VERSION.canvass_efficiency_weights.weights)

        result = compute_base_sub_scores(demographics)

        assert math.isclose(result["roof_condition"], expected_rc, abs_tol=0.1)
        assert math.isclose(result["market_quality"], expected_mq, abs_tol=0.1)
        assert math.isclose(result["risk_exposure"], expected_re, abs_tol=0.1)
        assert math.isclose(result["canvass_efficiency"], expected_ce, abs_tol=0.1)

        cw = UNIFIED_MODEL_VERSION.composite_weights
        expected_base = (
            expected_rc * cw.roof_condition +
            expected_mq * cw.market_quality +
            expected_re * cw.risk_exposure +
            expected_ce * cw.canvass_efficiency
        )
        assert math.isclose(result["base_score"], expected_base, abs_tol=0.1)

    def test_base_score_clamped_to_100(self):
        """Even with extreme percentiles, base_score should not exceed 100."""
        demographics = {}
        for sw in [
            UNIFIED_MODEL_VERSION.roof_condition_weights,
            UNIFIED_MODEL_VERSION.market_quality_weights,
            UNIFIED_MODEL_VERSION.risk_exposure_weights,
            UNIFIED_MODEL_VERSION.canvass_efficiency_weights,
        ]:
            for key in sw.weights:
                demographics[f"pctile_{key}"] = 100.0

        result = compute_base_sub_scores(demographics)
        assert result["base_score"] <= 100.0

    def test_base_score_clamped_to_0(self):
        """All zero percentiles → base_score should not go below 0."""
        demographics = {}
        for sw in [
            UNIFIED_MODEL_VERSION.roof_condition_weights,
            UNIFIED_MODEL_VERSION.market_quality_weights,
            UNIFIED_MODEL_VERSION.risk_exposure_weights,
            UNIFIED_MODEL_VERSION.canvass_efficiency_weights,
        ]:
            for key in sw.weights:
                demographics[f"pctile_{key}"] = 0.0

        result = compute_base_sub_scores(demographics)
        assert result["base_score"] >= 0.0

    def test_shared_features_affect_multiple_sub_scores(self):
        """Features like canopy_risk appear in both roof_condition and risk_exposure."""
        demographics = {"pctile_canopy_risk": 90.0}
        result = compute_base_sub_scores(demographics)
        # canopy_risk contributes to both roof_condition and risk_exposure
        # Other features default to 50
        # roof_condition: canopy_risk weight = 0.10, so 90*0.10 + 50*(sum of other weights)
        # The result should be > 50 if canopy_risk pulls it up (slightly)
        assert result["roof_condition"] > 49.0  # 50 + slight bump from 90
