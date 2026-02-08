"""Unit tests for scoring weights module.

Tests weight configuration, serialization, score band classification,
and predicted conversion rate lookups.
"""

import pytest
from datetime import datetime
from app.scoring.weights import (
    DamageWeights,
    LeadQualityWeights,
    CompositeWeights,
    ScoreBand,
    ModelVersion,
    CURRENT_MODEL_VERSION,
    get_score_band,
    get_predicted_conversion_rate,
    get_predicted_conversion_for_band,
)


class TestDamageWeights:
    """Tests for DamageWeights dataclass."""

    def test_sum(self):
        """Test that sum() correctly adds all weights."""
        weights = DamageWeights(
            hail_diameter=0.40,
            wind_speed=0.25,
            radar_confidence=0.20,
            report_corroboration=0.15,
        )
        assert weights.sum() == 1.0


class TestLeadQualityWeights:
    """Tests for LeadQualityWeights dataclass."""

    def test_sum(self):
        """Test that sum() correctly adds all weights."""
        weights = LeadQualityWeights(
            owner_occupied_pct=0.35,
            median_home_value=0.30,
            median_year_built=0.25,
            housing_density=0.10,
        )
        assert weights.sum() == 1.0


class TestCompositeWeights:
    """Tests for CompositeWeights dataclass."""

    def test_sum(self):
        """Test that sum() correctly adds all weights."""
        weights = CompositeWeights(
            damage_prob=0.50,
            lead_quality=0.30,
            density_bonus=0.20,
        )
        assert weights.sum() == 1.0


class TestScoreBand:
    """Tests for ScoreBand enum."""

    def test_hot_band_properties(self):
        """Test HOT band has correct properties."""
        band = ScoreBand.HOT
        assert band.band_name == "hot"
        assert band.min_score == 80
        assert band.max_score == 100
        assert band.conversion_rate == 0.12

    def test_warm_band_properties(self):
        """Test WARM band has correct properties."""
        band = ScoreBand.WARM
        assert band.band_name == "warm"
        assert band.min_score == 60
        assert band.max_score == 79
        assert band.conversion_rate == 0.07

    def test_cool_band_properties(self):
        """Test COOL band has correct properties."""
        band = ScoreBand.COOL
        assert band.band_name == "cool"
        assert band.min_score == 40
        assert band.max_score == 59
        assert band.conversion_rate == 0.03

    def test_skip_band_properties(self):
        """Test SKIP band has correct properties."""
        band = ScoreBand.SKIP
        assert band.band_name == "skip"
        assert band.min_score == 0
        assert band.max_score == 39
        assert band.conversion_rate == 0.01

    @pytest.mark.parametrize("score,expected_band", [
        (0, ScoreBand.SKIP),
        (39, ScoreBand.SKIP),
        (39.9, ScoreBand.SKIP),
        (40, ScoreBand.COOL),
        (50, ScoreBand.COOL),
        (59, ScoreBand.COOL),
        (59.9, ScoreBand.COOL),
        (60, ScoreBand.WARM),
        (70, ScoreBand.WARM),
        (79, ScoreBand.WARM),
        (79.9, ScoreBand.WARM),
        (80, ScoreBand.HOT),
        (90, ScoreBand.HOT),
        (100, ScoreBand.HOT),
    ])
    def test_from_score(self, score, expected_band):
        """Test score band classification at boundaries and ranges."""
        assert ScoreBand.from_score(score) == expected_band

    @pytest.mark.parametrize("score", [-10, -1, -0.1, 100.1, 150, 1000])
    def test_from_score_edge_cases(self, score):
        """Test score band classification for out-of-range scores."""
        # Negative scores should be SKIP
        if score < 0:
            assert ScoreBand.from_score(score) == ScoreBand.SKIP
        # Scores > 100 should be HOT
        elif score > 100:
            assert ScoreBand.from_score(score) == ScoreBand.HOT


class TestModelVersion:
    """Tests for ModelVersion dataclass."""

    @pytest.fixture
    def valid_model(self):
        """Create a valid model version for testing."""
        return ModelVersion(
            version="1.0.0",
            damage_weights=DamageWeights(
                hail_diameter=0.40,
                wind_speed=0.25,
                radar_confidence=0.20,
                report_corroboration=0.15,
            ),
            lead_quality_weights=LeadQualityWeights(
                owner_occupied_pct=0.35,
                median_home_value=0.30,
                median_year_built=0.25,
                housing_density=0.10,
            ),
            composite_weights=CompositeWeights(
                damage_prob=0.50,
                lead_quality=0.30,
                density_bonus=0.20,
            ),
            created_at=datetime(2025, 1, 1, 0, 0, 0),
            description="Test model",
        )

    def test_validate_success(self, valid_model):
        """Test that validation passes for valid weights."""
        valid_model.validate()  # Should not raise

    def test_validate_damage_weights_invalid(self, valid_model):
        """Test that validation fails when damage weights don't sum to 1.0."""
        valid_model.damage_weights.hail_diameter = 0.50  # Now sums to 1.10
        with pytest.raises(ValueError, match="Damage weights sum"):
            valid_model.validate()

    def test_validate_lead_quality_weights_invalid(self, valid_model):
        """Test that validation fails when lead quality weights don't sum to 1.0."""
        valid_model.lead_quality_weights.owner_occupied_pct = 0.20  # Now sums to 0.85
        with pytest.raises(ValueError, match="Lead quality weights sum"):
            valid_model.validate()

    def test_validate_composite_weights_invalid(self, valid_model):
        """Test that validation fails when composite weights don't sum to 1.0."""
        valid_model.composite_weights.damage_prob = 0.60  # Now sums to 1.10
        with pytest.raises(ValueError, match="Composite weights sum"):
            valid_model.validate()

    def test_validate_with_custom_tolerance(self, valid_model):
        """Test validation with custom tolerance."""
        # Slightly off but within default tolerance
        valid_model.damage_weights.hail_diameter = 0.4005
        valid_model.validate(tolerance=0.001)  # Should pass

        # Should fail with tighter tolerance
        with pytest.raises(ValueError):
            valid_model.validate(tolerance=0.0001)

    def test_to_snapshot(self, valid_model):
        """Test serialization to JSON-compatible dict."""
        snapshot = valid_model.to_snapshot()

        assert snapshot["version"] == "1.0.0"
        assert snapshot["description"] == "Test model"
        assert snapshot["created_at"] == "2025-01-01T00:00:00"

        # Check damage weights
        assert snapshot["damage_weights"]["hail_diameter"] == 0.40
        assert snapshot["damage_weights"]["wind_speed"] == 0.25
        assert snapshot["damage_weights"]["radar_confidence"] == 0.20
        assert snapshot["damage_weights"]["report_corroboration"] == 0.15

        # Check lead quality weights
        assert snapshot["lead_quality_weights"]["owner_occupied_pct"] == 0.35
        assert snapshot["lead_quality_weights"]["median_home_value"] == 0.30
        assert snapshot["lead_quality_weights"]["median_year_built"] == 0.25
        assert snapshot["lead_quality_weights"]["housing_density"] == 0.10

        # Check composite weights
        assert snapshot["composite_weights"]["damage_prob"] == 0.50
        assert snapshot["composite_weights"]["lead_quality"] == 0.30
        assert snapshot["composite_weights"]["density_bonus"] == 0.20

    def test_to_snapshot_is_json_serializable(self, valid_model):
        """Test that snapshot output is JSON-serializable."""
        import json
        snapshot = valid_model.to_snapshot()
        # Should not raise
        json.dumps(snapshot)

    def test_from_snapshot(self, valid_model):
        """Test deserialization from snapshot."""
        snapshot = valid_model.to_snapshot()
        restored = ModelVersion.from_snapshot(snapshot)

        assert restored.version == valid_model.version
        assert restored.description == valid_model.description
        assert restored.created_at == valid_model.created_at

        # Check damage weights
        assert restored.damage_weights.hail_diameter == valid_model.damage_weights.hail_diameter
        assert restored.damage_weights.wind_speed == valid_model.damage_weights.wind_speed
        assert restored.damage_weights.radar_confidence == valid_model.damage_weights.radar_confidence
        assert restored.damage_weights.report_corroboration == valid_model.damage_weights.report_corroboration

        # Check lead quality weights
        assert restored.lead_quality_weights.owner_occupied_pct == valid_model.lead_quality_weights.owner_occupied_pct
        assert restored.lead_quality_weights.median_home_value == valid_model.lead_quality_weights.median_home_value
        assert restored.lead_quality_weights.median_year_built == valid_model.lead_quality_weights.median_year_built
        assert restored.lead_quality_weights.housing_density == valid_model.lead_quality_weights.housing_density

        # Check composite weights
        assert restored.composite_weights.damage_prob == valid_model.composite_weights.damage_prob
        assert restored.composite_weights.lead_quality == valid_model.composite_weights.lead_quality
        assert restored.composite_weights.density_bonus == valid_model.composite_weights.density_bonus

    def test_round_trip(self, valid_model):
        """Test that to_snapshot() and from_snapshot() are inverse operations."""
        snapshot = valid_model.to_snapshot()
        restored = ModelVersion.from_snapshot(snapshot)
        snapshot2 = restored.to_snapshot()

        assert snapshot == snapshot2


class TestCurrentModelVersion:
    """Tests for CURRENT_MODEL_VERSION constant."""

    def test_version_is_v1_0_0(self):
        """Test that current model version is 1.0.0."""
        assert CURRENT_MODEL_VERSION.version == "1.0.0"

    def test_damage_weights_match_spec(self):
        """Test that v1.0.0 damage weights match specification."""
        weights = CURRENT_MODEL_VERSION.damage_weights
        assert weights.hail_diameter == 0.40
        assert weights.wind_speed == 0.25
        assert weights.radar_confidence == 0.20
        assert weights.report_corroboration == 0.15

    def test_lead_quality_weights_match_spec(self):
        """Test that v1.0.0 lead quality weights match specification."""
        weights = CURRENT_MODEL_VERSION.lead_quality_weights
        assert weights.owner_occupied_pct == 0.35
        assert weights.median_home_value == 0.30
        assert weights.median_year_built == 0.25
        assert weights.housing_density == 0.10

    def test_composite_weights_match_spec(self):
        """Test that v1.0.0 composite weights match specification."""
        weights = CURRENT_MODEL_VERSION.composite_weights
        assert weights.damage_prob == 0.50
        assert weights.lead_quality == 0.30
        assert weights.density_bonus == 0.20

    def test_all_weights_sum_to_one(self):
        """Test that all v1.0.0 weight groups sum to 1.0."""
        assert CURRENT_MODEL_VERSION.damage_weights.sum() == 1.0
        assert CURRENT_MODEL_VERSION.lead_quality_weights.sum() == 1.0
        assert CURRENT_MODEL_VERSION.composite_weights.sum() == 1.0

    def test_validate_passes(self):
        """Test that v1.0.0 passes validation."""
        CURRENT_MODEL_VERSION.validate()  # Should not raise

    def test_description_exists(self):
        """Test that v1.0.0 has a description."""
        assert CURRENT_MODEL_VERSION.description
        assert len(CURRENT_MODEL_VERSION.description) > 0


class TestGetScoreBand:
    """Tests for get_score_band() function."""

    @pytest.mark.parametrize("score,expected_band", [
        (0, ScoreBand.SKIP),
        (39, ScoreBand.SKIP),
        (40, ScoreBand.COOL),
        (59, ScoreBand.COOL),
        (60, ScoreBand.WARM),
        (79, ScoreBand.WARM),
        (80, ScoreBand.HOT),
        (100, ScoreBand.HOT),
    ])
    def test_score_band_boundaries(self, score, expected_band):
        """Test score band classification at exact boundaries."""
        assert get_score_band(score) == expected_band

    @pytest.mark.parametrize("score", [-100, -10, -1, -0.1])
    def test_negative_scores(self, score):
        """Test that negative scores return SKIP band."""
        assert get_score_band(score) == ScoreBand.SKIP

    @pytest.mark.parametrize("score", [100.1, 150, 1000])
    def test_scores_above_100(self, score):
        """Test that scores above 100 return HOT band."""
        assert get_score_band(score) == ScoreBand.HOT


class TestGetPredictedConversionRate:
    """Tests for get_predicted_conversion_rate() function."""

    @pytest.mark.parametrize("score,expected_rate", [
        (0, 0.01),
        (39, 0.01),
        (40, 0.03),
        (59, 0.03),
        (60, 0.07),
        (79, 0.07),
        (80, 0.12),
        (100, 0.12),
    ])
    def test_conversion_rate_lookup(self, score, expected_rate):
        """Test that predicted conversion rates match specification."""
        assert get_predicted_conversion_rate(score) == expected_rate

    def test_skip_band_conversion(self):
        """Test SKIP band (0-39) has 1% conversion rate."""
        for score in [0, 10, 20, 30, 39]:
            assert get_predicted_conversion_rate(score) == 0.01

    def test_cool_band_conversion(self):
        """Test COOL band (40-59) has 3% conversion rate."""
        for score in [40, 45, 50, 55, 59]:
            assert get_predicted_conversion_rate(score) == 0.03

    def test_warm_band_conversion(self):
        """Test WARM band (60-79) has 7% conversion rate."""
        for score in [60, 65, 70, 75, 79]:
            assert get_predicted_conversion_rate(score) == 0.07

    def test_hot_band_conversion(self):
        """Test HOT band (80-100) has 12% conversion rate."""
        for score in [80, 85, 90, 95, 100]:
            assert get_predicted_conversion_rate(score) == 0.12


class TestGetPredictedConversionForBand:
    """Tests for get_predicted_conversion_for_band() function."""

    def test_hot_band(self):
        """Test conversion rate for HOT band."""
        assert get_predicted_conversion_for_band(ScoreBand.HOT) == 0.12

    def test_warm_band(self):
        """Test conversion rate for WARM band."""
        assert get_predicted_conversion_for_band(ScoreBand.WARM) == 0.07

    def test_cool_band(self):
        """Test conversion rate for COOL band."""
        assert get_predicted_conversion_for_band(ScoreBand.COOL) == 0.03

    def test_skip_band(self):
        """Test conversion rate for SKIP band."""
        assert get_predicted_conversion_for_band(ScoreBand.SKIP) == 0.01
