"""Model calibration tracking.

Stores aggregated feedback metrics by region and hail size to track
prediction accuracy and bias. Enables continuous model improvement.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    DateTime,
    Float,
    Integer,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class ModelCalibration(Base):
    """Scoring model calibration metrics."""

    __tablename__ = "model_calibration"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Model version
    model_version = Column(String, nullable=False)

    # Segmentation
    region = Column(String, nullable=False)  # State abbreviation
    hail_size_bucket = Column(
        String, nullable=False
    )  # '1.00-1.49', '1.50-1.99', '2.00-2.74', '2.75+'

    # Prediction metrics
    avg_predicted_conversion = Column(Float, nullable=False)
    avg_actual_conversion = Column(Float, nullable=False)
    prediction_bias = Column(Float, nullable=False)  # predicted minus actual

    # Context metrics
    avg_competitor_saturation = Column(Float, nullable=True)

    # Sample statistics
    sample_size = Column(Integer, nullable=False)

    # Time period
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)

    # Computation metadata
    computed_at = Column(DateTime(timezone=True), nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        # Composite index for lookup by model version + region + hail size
        Index(
            'ix_model_calibration_lookup',
            'model_version',
            'region',
            'hail_size_bucket',
        ),
        # Index on period_end for finding latest calibrations
        Index('ix_model_calibration_period_end', 'period_end'),
        # Index on computed_at for tracking calibration runs
        Index('ix_model_calibration_computed_at', 'computed_at'),
    )

    def __repr__(self):
        return f"<ModelCalibration(id={self.id}, version={self.model_version}, region={self.region}, bucket={self.hail_size_bucket})>"
