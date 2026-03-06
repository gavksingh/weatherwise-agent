from datetime import datetime, timezone

from fastmcp import FastMCP

from config import AQI_LABELS, get_http_client
from schemas import (
    AirQuality,
    AirQualityComponents,
    CurrentWeather,
    Forecast,
    ForecastEntry,
    GeoLocation,
    WeatherAlert,
    WeatherAlerts,
)

mcp = FastMCP("WeatherWise")


@mcp.tool()
async def geocode_location(city_name: str) -> dict:
    """Convert a city name to geographic coordinates (latitude and longitude).

    Always call this FIRST before using any other weather tool. All other tools
    require lat/lon coordinates, so you must geocode the user's city name here
    before calling get_current_weather, get_forecast, get_air_quality, or
    get_weather_alerts.

    Args:
        city_name: Name of the city, optionally with country code (e.g. "London" or "Paris, FR").

    Returns:
        Dict with name, lat, lon, country, and optionally state.
    """
    try:
        async with get_http_client() as client:
            resp = await client.get(
                "/geo/1.0/direct",
                params={"q": city_name, "limit": 1},
            )
            resp.raise_for_status()
            data = resp.json()

            if not data:
                return {"error": f"No location found for '{city_name}'"}

            loc = data[0]
            result = GeoLocation(
                name=loc["name"],
                lat=loc["lat"],
                lon=loc["lon"],
                country=loc["country"],
                state=loc.get("state"),
            )
            return result.model_dump()
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_current_weather(lat: float, lon: float) -> dict:
    """Get current weather conditions at a specific location.

    Use when the user asks about the weather right now, current temperature,
    "what's it like outside", what to wear today, or any present-moment weather
    question. Requires coordinates from geocode_location.

    Args:
        lat: Latitude of the location.
        lon: Longitude of the location.

    Returns:
        Dict with temperature (Celsius), feels_like, humidity, pressure,
        wind speed/direction, weather description, and cloud coverage.
    """
    try:
        async with get_http_client() as client:
            resp = await client.get(
                "/data/2.5/weather",
                params={"lat": lat, "lon": lon, "units": "metric"},
            )
            resp.raise_for_status()
            data = resp.json()

            result = CurrentWeather(
                location=data.get("name", "Unknown"),
                temperature_c=data["main"]["temp"],
                feels_like_c=data["main"]["feels_like"],
                humidity=data["main"]["humidity"],
                pressure_hpa=data["main"]["pressure"],
                wind_speed_ms=data["wind"]["speed"],
                wind_deg=data["wind"].get("deg", 0),
                description=data["weather"][0]["description"],
                icon=data["weather"][0]["icon"],
                visibility_m=data.get("visibility"),
                clouds_pct=data["clouds"]["all"],
            )
            return result.model_dump()
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_forecast(lat: float, lon: float) -> dict:
    """Get a 5-day weather forecast with 3-hour intervals for a location.

    Use when the user asks about future weather, upcoming days, "will it rain
    tomorrow", weekend plans, travel weather, or any question about weather
    beyond the current moment. Requires coordinates from geocode_location.

    Args:
        lat: Latitude of the location.
        lon: Longitude of the location.

    Returns:
        Dict with location name, entry count, and a list of forecast entries.
        Each entry includes datetime, temperature, humidity, description,
        wind speed, and precipitation probability.
    """
    try:
        async with get_http_client() as client:
            resp = await client.get(
                "/data/2.5/forecast",
                params={"lat": lat, "lon": lon, "units": "metric"},
            )
            resp.raise_for_status()
            data = resp.json()

            entries = [
                ForecastEntry(
                    datetime_utc=item["dt_txt"],
                    temperature_c=item["main"]["temp"],
                    feels_like_c=item["main"]["feels_like"],
                    humidity=item["main"]["humidity"],
                    description=item["weather"][0]["description"],
                    icon=item["weather"][0]["icon"],
                    wind_speed_ms=item["wind"]["speed"],
                    precipitation_prob=item.get("pop", 0.0),
                )
                for item in data["list"]
            ]

            result = Forecast(
                location=data["city"]["name"],
                count=len(entries),
                entries=entries,
            )
            return result.model_dump()
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_air_quality(lat: float, lon: float) -> dict:
    """Get air quality index (AQI) and pollutant levels for a location.

    Use when the user asks about air quality, pollution, smog, outdoor exercise
    safety, allergies, breathing conditions, or whether it's safe to be outside.
    Also use proactively alongside current weather when AQI could be relevant
    (e.g. cities known for pollution). Requires coordinates from geocode_location.

    Args:
        lat: Latitude of the location.
        lon: Longitude of the location.

    Returns:
        Dict with AQI (1-5), human-readable label (Good/Fair/Moderate/Poor/Very Poor),
        and pollutant concentrations (CO, NO, NO2, O3, SO2, PM2.5, PM10, NH3).
    """
    try:
        async with get_http_client() as client:
            resp = await client.get(
                "/data/2.5/air_pollution",
                params={"lat": lat, "lon": lon},
            )
            resp.raise_for_status()
            data = resp.json()

            item = data["list"][0]
            aqi = item["main"]["aqi"]
            components = item["components"]

            result = AirQuality(
                aqi=aqi,
                aqi_label=AQI_LABELS.get(aqi, "Unknown"),
                components=AirQualityComponents(
                    co=components["co"],
                    no=components["no"],
                    no2=components["no2"],
                    o3=components["o3"],
                    so2=components["so2"],
                    pm2_5=components["pm2_5"],
                    pm10=components["pm10"],
                    nh3=components["nh3"],
                ),
            )
            return result.model_dump()
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_weather_alerts(lat: float, lon: float) -> dict:
    """Get active severe weather alerts and warnings for a location.

    Use when the user asks about storm warnings, severe weather, safety concerns,
    travel advisories, or "is it dangerous outside". Also call proactively when
    current weather or forecasts suggest extreme conditions (storms, heat waves,
    flooding). Requires coordinates from geocode_location.
    Note: Requires an OpenWeatherMap OneCall 3.0 subscription.

    Args:
        lat: Latitude of the location.
        lon: Longitude of the location.

    Returns:
        Dict with lat, lon, and a list of active alerts. Each alert includes
        sender, event type, start/end times (UTC), description, and tags.
        Returns an empty alerts list if no alerts are active.
    """
    try:
        async with get_http_client() as client:
            resp = await client.get(
                "/data/3.0/onecall",
                params={
                    "lat": lat,
                    "lon": lon,
                    "exclude": "minutely,hourly,daily",
                },
            )

            if resp.status_code in (401, 403):
                return {
                    "error": (
                        "Weather alerts require an OpenWeatherMap OneCall 3.0 "
                        "subscription. Please upgrade your API key at "
                        "https://openweathermap.org/api/one-call-3"
                    )
                }

            resp.raise_for_status()
            data = resp.json()

            alerts = [
                WeatherAlert(
                    sender=a.get("sender_name", "Unknown"),
                    event=a["event"],
                    start_utc=datetime.fromtimestamp(
                        a["start"], tz=timezone.utc
                    ).isoformat(),
                    end_utc=datetime.fromtimestamp(
                        a["end"], tz=timezone.utc
                    ).isoformat(),
                    description=a.get("description", ""),
                    tags=a.get("tags", []),
                )
                for a in data.get("alerts", [])
            ]

            result = WeatherAlerts(lat=lat, lon=lon, alerts=alerts)
            return result.model_dump()
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=8001)
