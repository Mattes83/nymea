"""Test the nymea config flow."""

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
                CONF_PORT: 2223,
                CONF_WEBSOCKET_PORT: 4445,
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
                CONF_PORT: 2223,
                CONF_WEBSOCKET_PORT: 4445,
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
                CONF_PORT: 2223,
                CONF_WEBSOCKET_PORT: 4445,
            },
        )

    assert result2["type"] == FlowResultType.FORM
    assert result2["errors"] == {"host": "cannot_connect"}


async def test_form_link_step(
    hass: HomeAssistant, mock_maveo_box, mock_setup_entry
) -> None:
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
                CONF_PORT: 2223,
                CONF_WEBSOCKET_PORT: 4445,
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
        CONF_PORT: 2223,
        CONF_WEBSOCKET_PORT: 4445,
        CONF_TOKEN: "test_token_12345",
    }


async def test_zeroconf_discovery(hass: HomeAssistant, mock_maveo_box) -> None:
    """Test zeroconf discovery."""
    discovery_info = ZeroconfServiceInfo(
        ip_address="192.168.2.179",
        ip_addresses=["192.168.2.179"],
        hostname="nymea-device.local.",
        name="nymea._jsonrpc._tcp.local.",
        port=2223,
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
    discovery_info = ZeroconfServiceInfo(
        ip_address="192.168.2.179",
        ip_addresses=["192.168.2.179"],
        hostname="nymea-device.local.",
        name="nymea._jsonrpc._tcp.local.",
        port=2223,
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
    discovery_info = ZeroconfServiceInfo(
        ip_address="192.168.2.179",
        ip_addresses=["192.168.2.179"],
        hostname="nymea-device.local.",
        name="nymea._ws._tcp.local.",  # WebSocket, not JSON-RPC
        port=4445,
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
    discovery_info = ZeroconfServiceInfo(
        ip_address="192.168.2.179",
        ip_addresses=["192.168.2.179"],
        hostname="nymea-device.local.",
        name="nymea._jsonrpc._tcp.local.",
        port=2223,
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


BOX_UUID_TXT = "{5DEC6CE8-59e8-49d1-9345-6715e1301195}"
BOX_UUID = "5dec6ce8-59e8-49d1-9345-6715e1301195"


def _discovery(hostname: str = "maveo-box-3.local.", uuid: str | None = BOX_UUID_TXT):
    """Build a JSON-RPC zeroconf discovery like the maveo box sends it."""
    return ZeroconfServiceInfo(
        ip_address="192.168.2.179",
        ip_addresses=["192.168.2.179"],
        hostname=hostname,
        name="nymea-tcp-external._jsonrpc._tcp.local.",
        port=2223,
        type="_jsonrpc._tcp.local.",
        properties={"uuid": uuid} if uuid else {},
    )


async def test_zeroconf_uses_server_uuid(hass: HomeAssistant, mock_maveo_box) -> None:
    """The unique ID comes from the TXT uuid, not the mDNS hostname."""
    with patch(
        "custom_components.nymea.config_flow.MaveoBox",
        return_value=mock_maveo_box,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=_discovery(),
        )

    assert result["type"] == FlowResultType.FORM
    flow = hass.config_entries.flow.async_get(result["flow_id"])
    assert flow["context"]["unique_id"] == BOX_UUID


async def test_zeroconf_falls_back_to_hostname(
    hass: HomeAssistant, mock_maveo_box
) -> None:
    """Without a uuid in the TXT record the hostname is used."""
    with patch(
        "custom_components.nymea.config_flow.MaveoBox",
        return_value=mock_maveo_box,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=_discovery(uuid=None),
        )

    flow = hass.config_entries.flow.async_get(result["flow_id"])
    assert flow["context"]["unique_id"] == "maveo-box-3"


async def test_zeroconf_known_uuid_renamed_host_aborts_without_connecting(
    hass: HomeAssistant,
) -> None:
    """A configured box that renamed itself is recognised by its uuid."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.2.50", CONF_PORT: 2223, CONF_TOKEN: "t"},
        unique_id=BOX_UUID,
    )
    entry.add_to_hass(hass)

    with patch("custom_components.nymea.config_flow.MaveoBox") as mock_box:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=_discovery(hostname="maveo-box-7.local."),
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    mock_box.assert_not_called()
    # Changed IP is taken over.
    assert entry.data[CONF_HOST] == "192.168.2.179"


async def test_zeroconf_migrates_legacy_hostname_entry(hass: HomeAssistant) -> None:
    """An entry with the old hostname-based unique ID is migrated by host."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.2.179", CONF_PORT: 2223, CONF_TOKEN: "t"},
        unique_id="maveo-box-2",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.nymea.config_flow.MaveoBox") as mock_box:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=_discovery(hostname="maveo-box-3.local."),
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    mock_box.assert_not_called()
    assert entry.unique_id == BOX_UUID


async def test_link_step_normalizes_server_uuid(
    hass: HomeAssistant, mock_maveo_box, mock_setup_entry
) -> None:
    """Manual setup stores the same uuid format as zeroconf."""
    mock_maveo_box.server_uuid = BOX_UUID_TXT
    with patch(
        "custom_components.nymea.config_flow.MaveoBox",
        return_value=mock_maveo_box,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "192.168.2.179", CONF_PORT: 2223, CONF_WEBSOCKET_PORT: 4445},
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == BOX_UUID
