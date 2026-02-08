"""Internal admin schemas for model calibration and deployment.

Handles prediction accuracy reporting, weight adjustment proposals,
and model deployment for continuous improvement.
"""

from datetime import datetime

from pydantic import BaseModel, Field, ConfigDict


class CalibrationEntry(BaseModel):
    """Single calibration data point for a region/hail bucket."""

    model_config = ConfigDict(from_attributes=True)

    model_version: str = Field(..., description="Model version")
    region: str = Field(..., description="State abbreviation")
    hail_size_bucket: str = Field(
        ..., description="Hail size bucket: '1.00-1.49', '1.50-1.99', '2.00-2.74', '2.75+'"
    )

    # Prediction metrics
    avg_predicted_conversion: float = Field(
        ..., description="Average predicted conversion rate"
    )
    avg_actual_conversion: float = Field(
        ..., description="Average actual conversion rate from feedback"
    )
    prediction_bias: float = Field(
        ..., description="Prediction bias (predicted - actual)"
    )

    # Sample statistics
    sample_size: int = Field(..., description="Number of feedback sessions in sample")
    computed_at: datetime = Field(..., description="When calibration was computed")


class CalibrationReport(BaseModel):
    """Full calibration report across all regions and hail buckets."""

    entries: list[CalibrationEntry] = Field(
        default_factory=list, description="Calibration entries by region/hail bucket"
    )
    model_version: str = Field(..., description="Model version being evaluated")
    total_sample_size: int = Field(
        ..., description="Total feedback sessions across all entries"
    )


class WeightChange(BaseModel):
    """Proposed change to a single scoring weight."""

    weight_name: str = Field(..., description="Name of the weight parameter")
    current_value: float = Field(..., description="Current weight value")
    proposed_value: float = Field(..., description="Proposed new weight value")
    reason: str = Field(..., description="Explanation for the change")


class WeightProposal(BaseModel):
    """Proposed weight adjustments based on calibration data."""

    current_weights: dict[str, float] = Field(
        ..., description="Current weight configuration"
    )
    proposed_weights: dict[str, float] = Field(
        ..., description="Proposed weight configuration"
    )
    changes: list[WeightChange] = Field(
        default_factory=list, description="List of individual weight changes with rationale"
    )


class ModelDeployRequest(BaseModel):
    """Request schema for deploying a new model version."""

    proposed_weights: dict[str, float] = Field(
        ..., description="New weight configuration to deploy"
    )
    notes: str | None = Field(
        None, description="Optional deployment notes (rationale, testing results, etc.)"
    )


class ModelDeployResponse(BaseModel):
    """Response schema for successful model deployment."""

    model_version: str = Field(..., description="Newly deployed model version")
    deployed_at: datetime = Field(..., description="Deployment timestamp")
    weights: dict[str, float] = Field(..., description="Active weight configuration")
