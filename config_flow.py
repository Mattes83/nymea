"""Config flow for nymea integration."""

from __future__ import annotations

import logging
import re
from typing import Any

from homeassistant import config_entries, exceptions
from homeassistant.components import zeroconf
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN
from homeassistant.core import HomeAssistant
import voluptuous as vol

from .const import CONF_WEBSOCKET_PORT, DOMAIN  # pylint:disable=unused-import
from .maveo_box import MaveoBox

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default="192.168.2.179"): str,
        vol.Required(CONF_PORT, default=2222): int,  # JSON-RPC port for commands and pairing
        vol.Required(CONF_WEBSOCKET_PORT, default=4444): int,  # WebSocket port for notifications
    },
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Validate the user input allows us to connect.

    Args:
        hass: Home Assistant instance.
        data: User input data with keys from DATA_SCHEMA.

    Raises:
        InvalidHost: If the hostname format is invalid.
        CannotConnect: If connection to the device fails.
    """
    # Validate the data can be used to set up a connection.
    pattern: str = r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.[A-Za-z0-9-]{1,63})*$"
    if not re.match(pattern, data[CONF_HOST]):
        raise InvalidHost

    hub: MaveoBox = MaveoBox(hass, data[CONF_HOST], data[CONF_PORT])
    success: bool = await hub.test_connection()
    if not success:
        # If there is an error, raise an exception to notify HA that there was a
        # problem. The UI will also show there was a problem.
        raise CannotConnect


class NymeaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a nymea config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the nymea config flow."""
        self.data: dict[str, Any] = {}
        self.discovery_info: zeroconf.ZeroconfServiceInfo | None = None

    async def async_step_zeroconf(
        self, discovery_info: zeroconf.ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle zeroconf discovery.

        Args:
            discovery_info: Zeroconf service discovery information.

        Returns:
            ConfigFlowResult with next step or abort reason.
        """
        _LOGGER.debug("Zeroconf discovery: %s", discovery_info)

        # We only want to handle JSON-RPC TCP discoveries, not WebSocket.
        # WebSocket is used for notifications, but pairing requires JSON-RPC.
        if "_ws._tcp" in discovery_info.type:
            _LOGGER.debug("Ignoring WebSocket discovery, we need JSON-RPC TCP")
            return self.async_abort(reason="not_supported")

        host = discovery_info.host
        port = discovery_info.port or 2223  # Use JSON-RPC port by default.
        websocket_port = 4444  # WebSocket port for notifications.

        # Check if already configured.
        await self.async_set_unique_id(discovery_info.hostname.replace(".local.", ""))
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})

        # Store discovery info for later use.
        self.discovery_info = discovery_info

        # Validate connection.
        try:
            await validate_input(self.hass, {CONF_HOST: host, CONF_PORT: port})
        except (CannotConnect, InvalidHost):
            return self.async_abort(reason="cannot_connect")

        # Store the discovered data.
        self.data = {CONF_HOST: host, CONF_PORT: port, CONF_WEBSOCKET_PORT: websocket_port}
        _LOGGER.info("Discovered nymea device at %s:%s", host, port)

        # Show confirmation form with discovered host.
        self.context["title_placeholders"] = {"name": f"nymea ({host})"}
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm discovery."""
        _LOGGER.debug("Zeroconf confirm step, user_input: %s", user_input)
        if user_input is None:
            return self.async_show_form(
                step_id="zeroconf_confirm",
                description_placeholders={"host": self.data.get(CONF_HOST, "unknown")},
            )

        # User confirmed, proceed to link step
        _LOGGER.debug("User confirmed discovery, proceeding to link")
        return await self.async_step_link()


    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        _LOGGER.debug("User config step, user_input: %s", user_input)
        errors = {}
        if user_input is not None:
            try:
                await validate_input(self.hass, user_input)
                self.data = user_input
                _LOGGER.info("Manual configuration validated for %s:%s", user_input[CONF_HOST], user_input[CONF_PORT])
                return await self.async_step_link()
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidHost:
                errors["host"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        # If there is no user input or there were errors, show the form again, including any errors that were found with the input.
        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )

    async def async_step_link(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Attempt to link with the nymea bridge.

        Given a configured host, will ask the user to press the link button
        to connect to the bridge.
        """
        # Show form if no input provided yet (first time showing the form)
        if user_input is None:
            _LOGGER.debug("Showing link form")
            return self.async_show_form(step_id="link")

        # User confirmed (submitted form, even if empty dict), proceed with pairing
        _LOGGER.info("Starting pairing process for %s:%s", self.data.get(CONF_HOST), self.data.get(CONF_PORT))

        if not self.data or CONF_HOST not in self.data:
            _LOGGER.error("Configuration data missing in link step: %s", self.data)
            return self.async_abort(reason="unknown")

        box: MaveoBox = MaveoBox(
            self.hass,
            self.data[CONF_HOST],
            self.data[CONF_PORT],
            websocket_port=self.data.get(CONF_WEBSOCKET_PORT, 4444)
        )
        token: str | None = await box.init_connection()
        self.data[CONF_TOKEN] = token

        return self.async_create_entry(
            title=f"nymea({self.data[CONF_HOST]})", data=self.data
        )


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidHost(exceptions.HomeAssistantError):
    """Error to indicate there is an invalid hostname."""
