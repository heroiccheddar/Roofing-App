"""Mapbox reverse geocoding service for zone display names and property addresses."""

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

MAPBOX_GEOCODING_BASE = "https://api.mapbox.com/geocoding/v5/mapbox.places"

STATE_ABBREV = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
    "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
    "Wisconsin": "WI", "Wyoming": "WY",
    "District of Columbia": "DC",
}


def reverse_geocode(lon: float, lat: float, mapbox_token: str) -> str | None:
    """Reverse geocode coordinates to a human-readable place name.

    Args:
        lon: Longitude (WGS84)
        lat: Latitude (WGS84)
        mapbox_token: Mapbox access token

    Returns:
        Display name like "Plano, TX" or None on failure
    """
    if not mapbox_token:
        return None

    url = f"{MAPBOX_GEOCODING_BASE}/{lon},{lat}.json"
    params = {
        "types": "place,neighborhood",
        "access_token": mapbox_token,
    }

    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        features = data.get("features", [])
        if not features:
            return None

        # Mapbox returns format: "Plano, Texas, United States"
        place_name = features[0].get("place_name", "")
        parts = [p.strip() for p in place_name.split(",")]

        if len(parts) >= 3:
            # "City, State, United States" -> "City, ST"
            city = parts[0]
            state = STATE_ABBREV.get(parts[1], parts[1])
            return f"{city}, {state}"
        elif len(parts) == 2:
            return parts[0]
        else:
            return place_name or None

    except Exception as e:
        logger.warning(f"Geocoding failed for ({lat:.4f}, {lon:.4f}): {e}")
        return None


def reverse_geocode_neighborhood(lon: float, lat: float, mapbox_token: str) -> str | None:
    """Reverse geocode coordinates to a neighborhood or locality name.

    Prioritizes neighborhood-level names over city names for census tract labeling.

    Returns:
        Neighborhood name like "Buckhead" or locality like "Marietta", or None on failure
    """
    if not mapbox_token:
        return None

    url = f"{MAPBOX_GEOCODING_BASE}/{lon},{lat}.json"
    params = {
        "types": "neighborhood,locality,place",
        "access_token": mapbox_token,
    }

    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        features = data.get("features", [])
        if not features:
            return None

        # Mapbox returns most specific first — prefer neighborhood over locality/place
        best = features[0]
        place_type = best.get("place_type", [])
        name = best.get("text", "")

        if not name:
            return None

        # If the best match is a neighborhood, use it directly
        if "neighborhood" in place_type:
            return name

        # For locality/place, return the short name
        return name

    except Exception as e:
        logger.warning(f"Neighborhood geocoding failed for ({lat:.4f}, {lon:.4f}): {e}")
        return None


async def reverse_geocode_address(
    lon: float,
    lat: float,
    mapbox_token: str,
    client: Optional[httpx.AsyncClient] = None,
) -> str | None:
    """Reverse geocode coordinates to a street address.

    Async version for batch processing. Accepts an optional shared
    httpx.AsyncClient to avoid per-request connection overhead.

    Returns:
        Address like "123 Main St, Athens, GA 30601" or None on failure
    """
    if not mapbox_token:
        return None

    url = f"{MAPBOX_GEOCODING_BASE}/{lon},{lat}.json"
    params = {
        "types": "address",
        "access_token": mapbox_token,
        "limit": 1,
    }

    try:
        if client:
            response = await client.get(url, params=params)
        else:
            async with httpx.AsyncClient(timeout=5.0) as c:
                response = await c.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        features = data.get("features", [])
        if not features:
            return None

        # place_name: "123 Main St, Athens, Georgia 30601, United States"
        place_name = features[0].get("place_name", "")
        parts = [p.strip() for p in place_name.split(",")]

        if len(parts) >= 4:
            # "123 Main St", "Athens", "Georgia 30601", "United States"
            street = parts[0]
            city = parts[1]
            state_zip = parts[2]  # "Georgia 30601"
            state_parts = state_zip.split()
            state = STATE_ABBREV.get(state_parts[0], state_parts[0]) if state_parts else ""
            zipcode = state_parts[1] if len(state_parts) > 1 else ""
            return f"{street}, {city}, {state} {zipcode}".strip()
        elif len(parts) >= 2:
            return ", ".join(parts[:-1])  # Drop "United States"

        return place_name or None

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            # Rate limited — signal caller to back off
            raise
        logger.warning("Address geocode failed for (%.4f, %.4f): %s", lat, lon, e)
        return None
    except Exception as e:
        logger.warning("Address geocode failed for (%.4f, %.4f): %s", lat, lon, e)
        return None
