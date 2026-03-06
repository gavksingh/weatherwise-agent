import os

# Must be set before config.py is imported (it validates on import)
os.environ["OPENWEATHER_API_KEY"] = "test_api_key_12345"

import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_response():
    """Factory fixture to create mock httpx responses."""
    def _make(json_data, status_code=200):
        response = MagicMock(spec=httpx.Response)
        response.status_code = status_code
        response.json.return_value = json_data
        if status_code >= 400:
            response.raise_for_status.side_effect = httpx.HTTPStatusError(
                f"HTTP {status_code}",
                request=MagicMock(),
                response=response,
            )
        else:
            response.raise_for_status.return_value = None
        return response
    return _make


@pytest.fixture
def mock_client(mock_response):
    """Patch get_http_client so tools use a mock async client."""
    client = AsyncMock(spec=httpx.AsyncClient)

    ctx = AsyncMock()
    ctx.__aenter__.return_value = client
    ctx.__aexit__.return_value = False

    with patch("server.get_http_client", return_value=ctx):
        yield client, mock_response
