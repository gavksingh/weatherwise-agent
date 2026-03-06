from typing import Optional

from pydantic import BaseModel


# --- geocode_location ---

class GeoLocation(BaseModel):
    name: str
    lat: float
    lon: float
    country: str
    state: Optional[str] = None


# --- get_current_weather ---

class CurrentWeather(BaseModel):
    location: str
    temperature_c: float
    feels_like_c: float
    humidity: int
    pressure_hpa: int
    wind_speed_ms: float
    wind_deg: int
    description: str
    icon: str
    visibility_m: Optional[int] = None
    clouds_pct: int


# --- get_forecast ---

class ForecastEntry(BaseModel):
    datetime_utc: str
    temperature_c: float
    feels_like_c: float
    humidity: int
    description: str
    icon: str
    wind_speed_ms: float
    precipitation_prob: float


class Forecast(BaseModel):
    location: str
    count: int
    entries: list[ForecastEntry]


# --- get_air_quality ---

class AirQualityComponents(BaseModel):
    co: float
    no: float
    no2: float
    o3: float
    so2: float
    pm2_5: float
    pm10: float
    nh3: float


class AirQuality(BaseModel):
    aqi: int
    aqi_label: str
    components: AirQualityComponents


# --- get_weather_alerts ---

class WeatherAlert(BaseModel):
    sender: str
    event: str
    start_utc: str
    end_utc: str
    description: str
    tags: list[str]


class WeatherAlerts(BaseModel):
    lat: float
    lon: float
    alerts: list[WeatherAlert]
