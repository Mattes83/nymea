"""Test the nymea config flow."""

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.components import zeroconf
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest

from custom_components.nymea.config_flow import (
    CannotConnect,
    InvalidHost,
    NymeaConfigFlow,
)
from custom_components.nymea.const import CONF_WEBSOCKET_PORT, DOMAIN


async def test_form_user(hass: HomeAssistant, mock_maveo_box) -> None:
    """Test we get the user form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {}
    assert result["step_id"] == "user"

    # Test successful configuration
    with patch(
        "custom_components.nymea.config_flow.MaveoBox",
        return_value=mock_maveo_box,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "192.168.2.179",
                CONF_PORT: 2222,
                CONF_WEBSOCKET_PORT: 4444,
            },
        )
        await hass.async_block_till_done()

    # Should move to link step
    assert result2["type"] == FlowResultType.FORM
    assert result2["step_id"] == "link"


async def test_form_user_cannot_connect(hass: HomeAssistant) -> None:
    """Test we handle cannot connect error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.nymea.config_flow.MaveoBox"
    ) as mock_box:
        mock_instance = mock_box.return_value
        mock_instance.test_connection = AsyncMock(return_value=False)

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "192.168.2.179",
                CONF_PORT: 2222,
                CONF_WEBSOCKET_PORT: 4444,
            },
        )

    assert result2["type"] == FlowResultType.FORM
    assert result2["errors"] == {"base": "cannot_connect"}


async def test_form_user_invalid_host(hass: HomeAssistant) -> None:
    """Test we handle invalid host error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.nymea.config_flow.MaveoBox"
    ) as mock_box:
        mock_instance = mock_box.return_value
        mock_instance.test_connection = AsyncMock(return_value=True)

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "-invalid-host-",  # Invalid hostname
                CONF_PORT: 2222,
                CONF_WEBSOCKET_PORT: 4444,
            },
        )

    assert result2["type"] == FlowResultType.FORM
    assert result2["errors"] == {"host": "cannot_connect"}


async def test_form_link_step(hass: HomeAssistant, mock_maveo_box) -> None:
    """Test the link step works."""
    # Start user flow
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.nymea.config_flow.MaveoBox",
        return_value=mock_maveo_box,
    ):
        # Configure with host
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "192.168.2.179",
                CONF_PORT: 2222,
                CONF_WEBSOCKET_PORT: 4444,
            },
        )

        # Should be at link step
        assert result2["type"] == FlowResultType.FORM
        assert result2["step_id"] == "link"

        # Complete the link step (push button pairing)
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {},  # User confirms by submitting
        )

    # Should create entry
    assert result3["type"] == FlowResultType.CREATE_ENTRY
    assert result3["title"] == "nymea(192.168.2.179)"
    assert result3["data"] == {
        CONF_HOST: "192.168.2.179",
        CONF_PORT: 2222,
        CONF_WEBSOCKET_PORT: 4444,
        CONF_TOKEN: "test_token_12345",
    }


async def test_zeroconf_discovery(hass: HomeAssistant, mock_maveo_box) -> None:
    """Test zeroconf discovery."""
    discovery_info = zeroconf.ZeroconfServiceInfo(
        ip_address="192.168.2.179",
        ip_addresses=["192.168.2.179"],
        hostname="nymea-device.local.",
        name="nymea._jsonrpc._tcp.local.",
        port=2222,
        type="_jsonrpc._tcp.local.",
        properties={},
    )

    with patch(
        "custom_components.nymea.config_flow.MaveoBox",
        return_value=mock_maveo_box,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=discovery_info,
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "zeroconf_confirm"
    assert result["description_placeholders"] == {"host": "192.168.2.179"}


async def test_zeroconf_confirm_step(hass: HomeAssistant, mock_maveo_box) -> None:
    """Test zeroconf confirmation step."""
    discovery_info = zeroconf.ZeroconfServiceInfo(
        ip_address="192.168.2.179",
        ip_addresses=["192.168.2.179"],
        hostname="nymea-device.local.",
        name="nymea._jsonrpc._tcp.local.",
        port=2222,
        type="_jsonrpc._tcp.local.",
        properties={},
    )

    with patch(
        "custom_components.nymea.config_flow.MaveoBox",
        return_value=mock_maveo_box,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=discovery_info,
        )

        # Confirm discovery
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {},
        )

    # Should move to link step
    assert result2["type"] == FlowResultType.FORM
    assert result2["step_id"] == "link"


async def test_zeroconf_websocket_ignored(hass: HomeAssistant) -> None:
    """Test that WebSocket zeroconf discoveries are ignored."""
    discovery_info = zeroconf.ZeroconfServiceInfo(
        ip_address="192.168.2.179",
        ip_addresses=["192.168.2.179"],
        hostname="nymea-device.local.",
        name="nymea._ws._tcp.local.",  # WebSocket, not JSON-RPC
        port=4444,
        type="_ws._tcp.local.",
        properties={},
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=discovery_info,
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "not_supported"


async def test_zeroconf_cannot_connect(hass: HomeAssistant) -> None:
    """Test zeroconf discovery with connection failure."""
    discovery_info = zeroconf.ZeroconfServiceInfo(
        ip_address="192.168.2.179",
        ip_addresses=["192.168.2.179"],
        hostname="nymea-device.local.",
        name="nymea._jsonrpc._tcp.local.",
        port=2222,
        type="_jsonrpc._tcp.local.",
        properties={},
    )

    with patch(
        "custom_components.nymea.config_flow.MaveoBox"
    ) as mock_box:
        mock_instance = mock_box.return_value
        mock_instance.test_connection = AsyncMock(return_value=False)

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=discovery_info,
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"
