import json
import pytest
from src.weather_client import decode_wmo_code, ForecastFetchError, get_forecast

def test_decode_wmo_code_valid():
    assert decode_wmo_code(0) == "Clear sky"
    assert decode_wmo_code(61) == "Rain: Slight"

def test_decode_wmo_code_fallback():
    assert decode_wmo_code(999) == "Unknown (999)"

def test_offline_geocoding_fixture():
    with open("fixtures/sample_geocoding.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["results"][0]["name"] == "Dresden"
    assert data["results"][0]["latitude"] == 51.05089

def test_offline_forecast_fixture():
    with open("fixtures/sample_forecast.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data["daily"]["time"]) == 2
    assert data["daily"]["temperature_2m_max"][0] == 16.2

def test_invalid_lat_lon_guard():
    with pytest.raises(ForecastFetchError):
        get_forecast(lat=95.0, lon=10.0)
    with pytest.raises(ForecastFetchError):
        get_forecast(lat=0.0, lon=200.0)