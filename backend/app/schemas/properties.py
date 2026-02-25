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


class PropertyListResponse(BaseModel):
    properties: list[PropertyResponse]
    total: int
    tract_geoid: str
    source_county: Optional[str] = None
    data_freshness: Optional[str] = None
    has_county_adapter: bool
