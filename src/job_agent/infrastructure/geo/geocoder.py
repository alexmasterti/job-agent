"""Lightweight geocoding with in-memory cache.

Uses geopy Nominatim (OpenStreetMap) — free, no API key required.
Results are cached in-memory for the process lifetime to avoid repeated lookups.
"""

from __future__ import annotations

import functools
from math import acos, cos, radians, sin

import structlog
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable  # type: ignore[import-untyped]
from geopy.geocoders import Nominatim  # type: ignore[import-untyped]

log = structlog.get_logger()

_geocoder = Nominatim(user_agent="job-agent/0.1", timeout=5)


@functools.lru_cache(maxsize=512)
def geocode(location: str) -> tuple[float, float] | None:
    """Return (lat, lng) for a location string, or None if not found."""
    try:
        result = _geocoder.geocode(location)
        if result is None:
            log.debug("geo.not_found", location=location)
            return None
        return (result.latitude, result.longitude)
    except (GeocoderTimedOut, GeocoderUnavailable, Exception) as exc:
        log.warning("geo.error", location=location, error=str(exc))
        return None


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in miles between two (lat, lon) points."""
    r = 3958.8  # Earth radius in miles
    lat1, lon1, lat2, lon2 = radians(lat1), radians(lon1), radians(lat2), radians(lon2)
    cos_angle = sin(lat1) * sin(lat2) + cos(lat1) * cos(lat2) * cos(lon2 - lon1)
    # Clamp for floating-point safety
    cos_angle = max(-1.0, min(1.0, cos_angle))
    return r * acos(cos_angle)


def is_within_radius(
    job_location: str,
    preferred_name: str,
    radius_miles: float,
) -> bool:
    """Check if a job location is within radius_miles of a preferred location.

    Falls back to substring matching if either location can't be geocoded.
    """
    pref_coords = geocode(preferred_name)
    job_coords = geocode(job_location)

    if pref_coords is None or job_coords is None:
        # Fallback: substring match
        return (
            preferred_name.lower() in job_location.lower()
            or job_location.lower() in preferred_name.lower()
        )

    distance = haversine_miles(pref_coords[0], pref_coords[1], job_coords[0], job_coords[1])
    return distance <= radius_miles
