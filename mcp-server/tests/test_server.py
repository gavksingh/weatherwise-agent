import pytest

from server import (
    geocode_location,
    get_current_weather,
    get_forecast,
    get_air_quality,
    get_weather_alerts,
)


# ── geocode_location ──


@pytest.mark.asyncio
async def test_geocode_location_success(mock_client):
    client, make_resp = mock_client
    client.get.return_value = make_resp([{
        "name": "London",
        "lat": 51.5074,
        "lon": -0.1278,
        "country": "GB",
        "state": "England",
    }])

    result = await geocode_location("London")
    assert result["name"] == "London"
    assert result["lat"] == 51.5074
    assert result["lon"] == -0.1278
    assert result["country"] == "GB"
    assert result["state"] == "England"


@pytest.mark.asyncio
async def test_geocode_location_not_found(mock_client):
    client, make_resp = mock_client
    client.get.return_value = make_resp([])

    result = await geocode_location("NonexistentCity12345")
    assert "error" in result
    assert "No location found" in result["error"]


@pytest.mark.asyncio
async def test_geocode_location_http_error(mock_client):
    client, make_resp = mock_client
    client.get.return_value = make_resp({}, status_code=500)

    result = await geocode_location("London")
    assert "error" in result


# ── get_current_weather ──


CURRENT_WEATHER_RESPONSE = {
    "name": "London",
    "main": {"temp": 15.2, "feels_like": 14.0, "humidity": 72, "pressure": 1013},
    "wind": {"speed": 3.5, "deg": 220},
    "weather": [{"description": "overcast clouds", "icon": "04d"}],
    "visibility": 10000,
    "clouds": {"all": 90},
}


@pytest.mark.asyncio
async def test_get_current_weather_success(mock_client):
    client, make_resp = mock_client
    client.get.return_value = make_resp(CURRENT_WEATHER_RESPONSE)

    result = await get_current_weather(51.5074, -0.1278)
    assert result["location"] == "London"
    assert result["temperature_c"] == 15.2
    assert result["feels_like_c"] == 14.0
    assert result["humidity"] == 72
    assert result["description"] == "overcast clouds"
    assert result["wind_speed_ms"] == 3.5
    assert result["clouds_pct"] == 90


@pytest.mark.asyncio
async def test_get_current_weather_http_error(mock_client):
    client, make_resp = mock_client
    client.get.return_value = make_resp({}, status_code=500)

    result = await get_current_weather(0.0, 0.0)
    assert "error" in result


# ── get_forecast ──


FORECAST_RESPONSE = {
    "city": {"name": "London"},
    "list": [
        {
            "dt_txt": "2025-01-15 12:00:00",
            "main": {"temp": 12.5, "feels_like": 11.0, "humidity": 65},
            "weather": [{"description": "light rain", "icon": "10d"}],
            "wind": {"speed": 4.1},
            "pop": 0.8,
        },
        {
            "dt_txt": "2025-01-15 15:00:00",
            "main": {"temp": 11.0, "feels_like": 9.5, "humidity": 70},
            "weather": [{"description": "cloudy", "icon": "04d"}],
            "wind": {"speed": 3.2},
            "pop": 0.3,
        },
    ],
}


@pytest.mark.asyncio
async def test_get_forecast_success(mock_client):
    client, make_resp = mock_client
    client.get.return_value = make_resp(FORECAST_RESPONSE)

    result = await get_forecast(51.5074, -0.1278)
    assert result["location"] == "London"
    assert result["count"] == 2
    assert len(result["entries"]) == 2
    assert result["entries"][0]["temperature_c"] == 12.5
    assert result["entries"][0]["precipitation_prob"] == 0.8
    assert result["entries"][1]["description"] == "cloudy"


@pytest.mark.asyncio
async def test_get_forecast_http_error(mock_client):
    client, make_resp = mock_client
    client.get.return_value = make_resp({}, status_code=500)

    result = await get_forecast(0.0, 0.0)
    assert "error" in result


# ── get_air_quality ──


AIR_QUALITY_RESPONSE = {
    "list": [{
        "main": {"aqi": 2},
        "components": {
            "co": 201.94, "no": 0.01, "no2": 0.77, "o3": 68.66,
            "so2": 0.64, "pm2_5": 0.5, "pm10": 0.54, "nh3": 0.12,
        },
    }],
}


@pytest.mark.asyncio
async def test_get_air_quality_success(mock_client):
    client, make_resp = mock_client
    client.get.return_value = make_resp(AIR_QUALITY_RESPONSE)

    result = await get_air_quality(51.5074, -0.1278)
    assert result["aqi"] == 2
    assert result["aqi_label"] == "Fair"
    assert result["components"]["pm2_5"] == 0.5
    assert result["components"]["o3"] == 68.66


@pytest.mark.asyncio
async def test_get_air_quality_http_error(mock_client):
    client, make_resp = mock_client
    client.get.return_value = make_resp({}, status_code=500)

    result = await get_air_quality(0.0, 0.0)
    assert "error" in result


# ── get_weather_alerts ──


@pytest.mark.asyncio
async def test_get_weather_alerts_with_alerts(mock_client):
    client, make_resp = mock_client
    client.get.return_value = make_resp({
        "lat": 51.5074,
        "lon": -0.1278,
        "alerts": [{
            "sender_name": "Met Office",
            "event": "Heavy Rain Warning",
            "start": 1705312800,
            "end": 1705356000,
            "description": "Heavy rain expected across southern England.",
            "tags": ["Rain"],
        }],
    })

    result = await get_weather_alerts(51.5074, -0.1278)
    assert result["lat"] == 51.5074
    assert len(result["alerts"]) == 1
    assert result["alerts"][0]["event"] == "Heavy Rain Warning"
    assert result["alerts"][0]["sender"] == "Met Office"
    assert "2024" in result["alerts"][0]["start_utc"]


@pytest.mark.asyncio
async def test_get_weather_alerts_no_alerts(mock_client):
    client, make_resp = mock_client
    client.get.return_value = make_resp({"lat": 51.5074, "lon": -0.1278})

    result = await get_weather_alerts(51.5074, -0.1278)
    assert result["alerts"] == []


@pytest.mark.asyncio
async def test_get_weather_alerts_subscription_required(mock_client):
    client, make_resp = mock_client
    resp = make_resp({}, status_code=401)
    # Override raise_for_status since we check status_code before calling it
    resp.raise_for_status.side_effect = None
    client.get.return_value = resp

    result = await get_weather_alerts(51.5074, -0.1278)
    assert "error" in result
    assert "OneCall 3.0" in result["error"]
