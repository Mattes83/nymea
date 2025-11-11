"""Common test fixtures for nymea integration tests."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nymea.const import CONF_WEBSOCKET_PORT, DOMAIN

pytest_plugins = "pytest_homeassistant_custom_component"


# Configure pytest-asyncio
def pytest_configure(config):
    """Configure pytest."""
    config.option.asyncio_mode = "auto"


# Tell pytest-homeassistant-custom-component that we have a custom component to load
@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for all tests."""
    yield


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Override async_setup_entry."""
    with patch(
        "custom_components.nymea.async_setup_entry", return_value=True
    ) as mock_setup_entry:
        yield mock_setup_entry


@pytest.fixture
def mock_maveo_box():
    """Mock MaveoBox."""
    with patch(
        "custom_components.nymea.config_flow.MaveoBox", autospec=True
    ) as mock_box:
        box_instance = mock_box.return_value
        box_instance.test_connection = AsyncMock(return_value=True)
        box_instance.init_connection = AsyncMock(return_value="test_token_12345")
        box_instance.send_command = MagicMock(
            return_value={"params": {"value": "test"}}
        )
        box_instance.start_notification_listener = MagicMock()
        box_instance.stop_notification_listener = AsyncMock()
        box_instance.maveoSticks = []
        box_instance.things = []
        box_instance.online = True
        yield box_instance


@pytest.fixture
def mock_config_entry():
    """Mock ConfigEntry."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "192.168.2.179",
            CONF_PORT: 2222,
            CONF_WEBSOCKET_PORT: 4444,
            CONF_TOKEN: "test_token_12345",
        },
        unique_id="nymea-device",
    )
