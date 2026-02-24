"""Mapbox reverse geocoding service for zone display names."""

import logging

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
