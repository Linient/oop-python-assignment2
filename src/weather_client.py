"""
src/weather_client.py
Logic for Open-Meteo geocoding and forecast retrieval.
"""

import time
from typing import Any, Dict, List, Optional
import requests


class WeatherAPIError(Exception):
    """Base error for weather client."""
    pass


class GeocodingError(WeatherAPIError):
    """Raised when geocoding fails or returns zero matches."""
    pass


class ForecastFetchError(WeatherAPIError):
    """Raised when retrieving forecast data fails."""
    pass


# WMO weather code dictionary
WMO_CODE_MAP = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    51: "Drizzle: Light",
    61: "Rain: Slight",
    63: "Rain: Moderate",
    65: "Rain: Heavy",
    71: "Snow fall: Slight",
    80: "Rain showers: Slight",
    95: "Thunderstorm",
}


def decode_wmo_code(code: int) -> str:
    """Converts a numerical WMO weather code into readable text."""
    return WMO_CODE_MAP.get(int(code), f"Unknown ({code})")


def make_resilient_request(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 5.0,
    max_retries: int = 3,
    backoff_factor: float = 1.0,
) -> requests.Response:
    """Sends an HTTP GET request with retry cap and exponential backoff."""
    attempt = 0
    while attempt < max_retries:
        try:
            response = requests.get(url, params=params, headers=headers, timeout=timeout)
            if 500 <= response.status_code < 600:
                raise requests.exceptions.HTTPError(f"Server error {response.status_code}")
            response.raise_for_status()
            return response
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                requests.exceptions.HTTPError) as exc:
            attempt += 1
            if attempt >= max_retries:
                raise WeatherAPIError(f"Failed after {max_retries} attempts: {exc}") from exc
            time.sleep(backoff_factor * (2 ** (attempt - 1)))

    raise WeatherAPIError("Unexpected retry loop termination.")


def geocode(name: str, user_email: str, count: int = 5, timeout: float = 5.0) -> List[Dict[str, Any]]:
    """Geocodes a location name to candidate coordinates."""
    if not name or not name.strip():
        raise GeocodingError("Location name cannot be empty.")

    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {"name": name.strip(), "count": count, "language": "en", "format": "json"}
    headers = {"User-Agent": f"WeatherMiniProject/1.0 ({user_email})"}

    try:
        response = make_resilient_request(url, params=params, headers=headers, timeout=timeout)
        data = response.json()
    except WeatherAPIError as err:
        raise GeocodingError(f"Geocoding request failed: {err}") from err

    candidates = data.get("results")
    if not candidates:
        raise GeocodingError(f"No coordinates found for location: '{name}'.")
    return candidates


def get_forecast(
    lat: float,
    lon: float,
    days: int = 7,
    timezone: str = "auto",
    user_email: str = "student@ucu.ac.ug",
    timeout: float = 5.0,
) -> Dict[str, Any]:
    """Fetches daily forecast data from Open-Meteo."""
    if not (-90.0 <= lat <= 90.0):
        raise ForecastFetchError(f"Invalid latitude: {lat}")
    if not (-180.0 <= lon <= 180.0):
        raise ForecastFetchError(f"Invalid longitude: {lon}")

    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": [
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_sum",
            "wind_speed_10m_max",
            "weather_code",
        ],
        "forecast_days": days,
        "timezone": timezone,
    }
    headers = {"User-Agent": f"WeatherMiniProject/1.0 ({user_email})"}

    try:
        response = make_resilient_request(url, params=params, headers=headers, timeout=timeout)
        return response.json()
    except WeatherAPIError as err:
        raise ForecastFetchError(f"Failed to fetch forecast: {err}") from err