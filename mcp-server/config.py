import os

from dotenv import load_dotenv
import httpx

load_dotenv()

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
if not OPENWEATHER_API_KEY or OPENWEATHER_API_KEY == "your_openweather_api_key_here":
    raise ValueError(
        "OPENWEATHER_API_KEY environment variable is required. "
        "Copy .env.example to .env and set your API key."
    )

BASE_URL = "https://api.openweathermap.org"

AQI_LABELS = {
    1: "Good",
    2: "Fair",
    3: "Moderate",
    4: "Poor",
    5: "Very Poor",
}


def get_http_client() -> httpx.AsyncClient:
    """Create a new async HTTP client with OWM base URL and API key pre-configured."""
    return httpx.AsyncClient(
        base_url=BASE_URL,
        params={"appid": OPENWEATHER_API_KEY},
        timeout=10.0,
    )
