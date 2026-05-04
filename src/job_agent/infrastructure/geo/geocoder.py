"""Lightweight geocoding with in-memory cache.

Uses geopy Nominatim (OpenStreetMap) — free, no API key required.
Results are cached in-memory for the process lifetime to avoid repeated lookups.
"""

from __future__ import annotations

from math import acos, cos, radians, sin

import structlog
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable  # type: ignore[import-untyped]
from geopy.geocoders import Nominatim  # type: ignore[import-untyped]

log = structlog.get_logger()

_geocoder = Nominatim(user_agent="job-agent/0.1", timeout=2)

# Skip geocoding entirely — use substring matching only.
# Nominatim rate-limits at 1 req/sec which blocks page loads for minutes
# when there are hundreds of unique job locations. Geocoding should be
# done as a background job, not inline during page render.
_GEOCODING_DISABLED = True

# Cache for when geocoding is enabled
_cache: dict[str, tuple[float, float] | None] = {}


def geocode(location: str) -> tuple[float, float] | None:
    """Return (lat, lng) for a location string, or None if not found."""
    if _GEOCODING_DISABLED:
        return None
    if location in _cache:
        return _cache[location]
    try:
        result = _geocoder.geocode(location)
        coords = (result.latitude, result.longitude) if result else None
        _cache[location] = coords
        return coords
    except (GeocoderTimedOut, GeocoderUnavailable, Exception) as exc:
        log.warning("geo.error", location=location, error=str(exc))
        _cache[location] = None
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
