"""Pydantic schemas for property parcel data."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PropertyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    parcel_id: str
    address: Optional[str] = None
    owner_name: Optional[str] = None
    year_built: Optional[int] = None
    estimated_roof_age: Optional[int] = None
    assessed_value: Optional[float] = None
    land_value: Optional[float] = None
    improvement_value: Optional[float] = None
    square_footage: Optional[int] = None
    lot_size_acres: Optional[float] = None
    property_type: Optional[str] = None
    zoning: Optional[str] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None
    stories: Optional[int] = None
    last_sale_date: Optional[str] = None
    last_sale_price: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    # Roof geometry (from Google Solar API)
    roof_area_sqft: Optional[float] = None
    roof_facet_count: Optional[int] = None
    roof_avg_pitch_deg: Optional[float] = None
    roof_max_pitch_deg: Optional[float] = None
    has_roof_data: Optional[bool] = None


class PropertyListResponse(BaseModel):
    properties: list[PropertyResponse]
    total: int
    tract_geoid: str
    source_county: Optional[str] = None
    data_freshness: Optional[str] = None
    has_county_adapter: bool


# ---------------------------------------------------------------------------
# GeoJSON schemas (lightweight — for canvass map layer rendering)
# ---------------------------------------------------------------------------


class PropertyGeoJSONProperties(BaseModel):
    """Minimal properties included in each GeoJSON feature."""

    id: str
    address: Optional[str] = None
    disposition: Optional[str] = None
    estimated_roof_age: Optional[int] = None
    year_built: Optional[int] = None


class PropertyGeoJSONFeature(BaseModel):
    """GeoJSON Point feature for a single property parcel."""

    type: str = "Feature"
    geometry: dict
    properties: PropertyGeoJSONProperties


class PropertyGeoJSONResponse(BaseModel):
    """GeoJSON FeatureCollection of property points for canvass map rendering."""

    type: str = "FeatureCollection"
    features: list[PropertyGeoJSONFeature] = []


class RoofFacet(BaseModel):
    area_sqft: float
    pitch_deg: float
    azimuth_deg: float


class RoofDataResponse(BaseModel):
    roof_area_sqft: float
    roof_ground_area_sqft: float | None = None
    roof_facet_count: int
    roof_avg_pitch_deg: float
    roof_max_pitch_deg: float
    roof_facets: list[RoofFacet]
    imagery_date: str | None = None
    imagery_quality: str | None = None
    roof_squares: float
    steep_pitch: bool
    pitch_category: str
