"""Shared geographic utility functions."""

import math


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in kilometres between two WGS84 points."""
    r = 6371.0  # Earth mean radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))
