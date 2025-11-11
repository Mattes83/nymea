"""Nymea hub communication module using JSON-RPC and WebSocket."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import contextlib
import json
import logging
import socket
import ssl
from threading import Lock
from typing import Any

from homeassistant.core import HomeAssistant
import websockets

# from .nymea import Nymea

_LOGGER = logging.getLogger(__name__)

mutex: Lock = Lock()


class MaveoBox:
    """Maveo Box."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        port: int,
        token: str | None = None,
        websocket_port: int = 4444,
    ) -> None:
        """Init maveo box."""
        self._host: str = host
        self._port: int = port  # JSON-RPC port (typically 2222)
        self._ws_port: int = (
            websocket_port  # WebSocket port for notifications (typically 4444)
        )
        self._hass: HomeAssistant = hass
        self._name: str = host
        self._id: str = host.lower()
        self._token: str | None = token
        self._pushButtonAuthAvailable: bool = False
        self._authenticationRequired: bool = True
        self._initialSetupRequired: bool = False
        self._commandId: int = 0

        # JSON-RPC socket for commands (port 2222)
        self._sock: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # WebSocket connection for notifications (port 4444)
        self._ws: Any = None
        self._ws_task: asyncio.Task[None] | None = None

        self.maveoSticks: list[Any] = []
        self.things: list[Any] = []
        self.online: bool = True

        # Thing classes data for dynamic entity generation
        self.thing_classes: list[dict[str, Any]] = []
        self.vendors: dict[str, dict[str, Any]] = {}

        # Notification system
        self._notification_handlers: dict[
            str, list[Callable[[dict[str, Any]], None]]
        ] = {}
        self._stop_notification_listener: bool = False

    @property
    def hub_id(self) -> str:
        """ID for nymea hub."""
        return self._id

    async def test_connection(self) -> bool:
        """Tests initial connectivity during setup."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(5)
            try:
                sock.connect((self._host, self._port))
                return True  # noqa: TRY300
            except (TimeoutError, OSError):
                return False

    def _create_ssl_context(self) -> ssl.SSLContext:
        """Create SSL context with self-signed certificate support."""
        context = ssl.create_default_context()
        # As we are working with self signed certificates disable some cert checks.
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context

    async def init_connection(self) -> str | None:
        """Inits the connection to the maveo box and returns a token used for authentication."""
        # Run blocking socket operations in executor
        loop = self._hass.loop

        # Connect to socket in executor (blocking I/O)
        await loop.run_in_executor(None, self._sock.connect, (self._host, self._port))

        # Perform initial handshake
        try:
            # first try without ssl
            handshake_message = self.send_command("JSONRPC.Hello", {})
        except Exception:
            # on case of error try with ssl
            # Create SSL context in executor to avoid blocking
            context = await loop.run_in_executor(None, self._create_ssl_context)

            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            await loop.run_in_executor(
                None, self._sock.connect, (self._host, self._port)
            )

            # Wrap socket with SSL in executor
            self._sock = await loop.run_in_executor(
                None, context.wrap_socket, self._sock
            )
            handshake_message = self.send_command("JSONRPC.Hello", {})

        handshake_data = handshake_message["params"]

        self._initialSetupRequired = handshake_data["initialSetupRequired"]
        self._authenticationRequired = handshake_data["authenticationRequired"]
        self._pushButtonAuthAvailable = handshake_data["pushButtonAuthAvailable"]

        # If we don't need any authentication, we are done
        if not self._authenticationRequired:
            _LOGGER.warning(
                "Maveo box is configured to allow unauthenticated requests, skipping authentication"
            )
            return None

        if self._initialSetupRequired:
            raise NotImplementedError(
                "An uninitialized maveo box is currently not supported"
            )

        if not self._pushButtonAuthAvailable:
            raise NotImplementedError(
                "A maveo box without push button is currently not supported"
            )

        # Authenticate if no token
        if self._authenticationRequired and self._token is None:
            self._token = self._pushbuttonAuthentication()

        # Enable notifications for the Integrations namespace
        self._enable_notifications()

        # Note: Notification listener will be started later from __init__.py
        # to avoid blocking during initialization

        return self._token

    def _pushbuttonAuthentication(self) -> str | None:
        """Authenticate using push button method."""
        if self._token is not None:
            return self._token

        _LOGGER.info("Using push button authentication method")

        params: dict[str, str] = {"deviceName": "home assistant"}
        command_obj: dict[str, Any] = {
            "id": self._commandId,
            "params": params,
            "method": "JSONRPC.RequestPushButtonAuth",
        }

        command = json.dumps(command_obj) + "\n"
        self._sock.send(command.encode("utf-8"))

        # wait for the response with id = commandId
        response_id = -1
        while response_id != self._commandId:
            data = b""
            while b"}\n" not in data:
                chunk = self._sock.recv(4096)
                if chunk == b"":
                    raise RuntimeError("socket connection broken")
                data += chunk

            response = json.loads(data.decode("utf-8"))
            response_id = response["id"]

        self._commandId = self._commandId + 1

        # Check response.
        _LOGGER.info(
            "Initialized push button authentication, please press the pushbutton on the device"
        )

        # wait for push button notification
        while True:
            data = b""
            while b"}\n" not in data:
                chunk = self._sock.recv(4096)
                if chunk == b"":
                    raise RuntimeError("socket connection broken")
                data += chunk

            response = json.loads(data.decode("utf-8"))
            if ("notification" in response) and response[
                "notification"
            ] == "JSONRPC.PushButtonAuthFinished":
                _LOGGER.info("Notification received")
                if response["params"]["success"] is True:
                    _LOGGER.info("Authenticated successfully")
                    return response["params"]["token"]

    def _enable_notifications(self) -> None:
        """Enable notifications for relevant namespaces."""
        # In Nymea, notifications are automatically enabled after authentication.
        # There's no need to explicitly enable them via API call.
        # The notification listener will receive all notifications once started.
        _LOGGER.info("Notifications are enabled by default after authentication")

    def send_command(
        self, method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Send a command via JSON-RPC socket and wait for response."""
        with mutex:
            command_obj: dict[str, Any] = {"id": self._commandId, "method": method}
            command_id: int = self._commandId
            self._commandId += 1

            if self._authenticationRequired and self._token is not None:
                command_obj["token"] = self._token

            if params is not None and len(params) > 0:
                command_obj["params"] = params

            # Send via JSON-RPC socket (port 2223).
            command: str = json.dumps(command_obj) + "\n"
            self._sock.send(command.encode("utf-8"))

            # Wait for the response with id = commandId.
            responseId: int = -1
            while responseId != command_id:
                data: bytes = b""

                while b"}\n" not in data:
                    chunk: bytes = self._sock.recv(4096)
                    if chunk == b"":
                        raise RuntimeError("socket connection broken")
                    data += chunk

                response: dict[str, Any] = json.loads(data.decode("utf-8"))
                # Skip notifications (should rarely happen on command socket now).
                if "notification" in response:
                    _LOGGER.warning(
                        "Received notification on command socket: %s",
                        response["notification"],
                    )
                    continue
                responseId = response["id"]

            if response["status"] != "success":
                _LOGGER.error("JSON error happened: %s", response.get("error"))
                return None

            # Call went fine, return the response.
            return response

    async def _websocket_listener(self) -> None:
        """WebSocket listener for push notifications from Nymea (port 4444)."""
        _LOGGER.info("Starting WebSocket notification listener")

        # Determine if we need SSL.
        ws_url: str = f"ws://{self._host}:{self._ws_port}"
        ssl_context: ssl.SSLContext | None = None

        try:
            # Try non-SSL first.
            async with websockets.connect(ws_url) as websocket:
                await self._ws_listen_loop(websocket)
        except (websockets.exceptions.WebSocketException, OSError) as ex:
            _LOGGER.info("Non-SSL WebSocket failed, trying SSL: %s", ex)
            # Try with SSL - create SSL context in executor to avoid blocking.
            loop = self._hass.loop
            ssl_context = await loop.run_in_executor(None, self._create_ssl_context)
            ws_url = f"wss://{self._host}:{self._ws_port}"

            try:
                async with websockets.connect(ws_url, ssl=ssl_context) as websocket:
                    await self._ws_listen_loop(websocket)
            except Exception as ex:
                _LOGGER.error("Failed to connect WebSocket: %s", ex)
                self.online = False

    async def _ws_listen_loop(self, websocket: Any) -> None:
        """Main WebSocket listening loop."""
        try:
            # First, send JSONRPC.Hello handshake on WebSocket (without token).
            hello_message: dict[str, Any] = {
                "id": 0,
                "method": "JSONRPC.Hello",
                "params": {},
            }
            await websocket.send(json.dumps(hello_message))
            hello_response: dict[str, Any] = json.loads(await websocket.recv())

            if hello_response.get("status") != "success":
                _LOGGER.error("WebSocket handshake failed: %s", hello_response)
                return

            _LOGGER.debug(
                "WebSocket handshake successful: %s", hello_response.get("params", {})
            )

            # If authentication is required, send Hello again WITH the token.
            # This authenticates the WebSocket session.
            if self._authenticationRequired and self._token:
                auth_hello = {
                    "id": 1,
                    "method": "JSONRPC.Hello",
                    "params": {},
                    "token": self._token,
                }
                await websocket.send(json.dumps(auth_hello))
                auth_response = json.loads(await websocket.recv())

                if auth_response.get("status") != "success":
                    _LOGGER.error(
                        "WebSocket token authentication failed: %s", auth_response
                    )
                    return

                _LOGGER.info("WebSocket authenticated with token")

            # Now enable notifications (after authentication).
            enable_notifications = {
                "id": 2,
                "method": "JSONRPC.SetNotificationStatus",
                "params": {"enabled": True},
            }

            # Add token at top level if authentication is required.
            if self._authenticationRequired and self._token:
                enable_notifications["token"] = self._token

            await websocket.send(json.dumps(enable_notifications))
            notif_response = json.loads(await websocket.recv())
            if notif_response.get("status") == "success":
                _LOGGER.info("WebSocket notifications enabled")
            else:
                _LOGGER.warning("Failed to enable notifications: %s", notif_response)

            # Listen for notifications.
            while not self._stop_notification_listener:
                try:
                    message_str = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    message = json.loads(message_str)

                    # Only process notifications (not command responses).
                    if "notification" in message:
                        notification_name = message["notification"]
                        params = message.get("params", {})
                        _LOGGER.info(
                            "WebSocket notification: %s with params: %s",
                            notification_name,
                            params,
                        )

                        # Dispatch to registered handlers.
                        if notification_name in self._notification_handlers:
                            for handler in self._notification_handlers[
                                notification_name
                            ]:
                                try:
                                    # Call handler in Home Assistant's event loop.
                                    self._hass.loop.call_soon_threadsafe(
                                        handler, params
                                    )
                                except Exception as ex:
                                    _LOGGER.error(
                                        "Error calling notification handler: %s", ex
                                    )
                        else:
                            _LOGGER.debug(
                                "No handler registered for: %s", notification_name
                            )
                    else:
                        # Command response on WebSocket (shouldn't happen often).
                        _LOGGER.debug(
                            "Received command response on WebSocket: %s", message
                        )

                except TimeoutError:
                    # Normal timeout, continue loop.
                    continue
                except websockets.exceptions.ConnectionClosed:
                    _LOGGER.warning("WebSocket connection closed")
                    break
                except Exception as ex:
                    _LOGGER.exception("Error in WebSocket listener: %s", ex)
                    break

        except Exception as ex:
            _LOGGER.exception("WebSocket listen loop error: %s", ex)
        finally:
            _LOGGER.info("WebSocket notification listener stopped")

    def register_notification_handler(
        self, notification_name: str, handler: Callable[[dict[str, Any]], None]
    ) -> None:
        """Register a handler for a specific notification type."""
        if notification_name not in self._notification_handlers:
            self._notification_handlers[notification_name] = []
        self._notification_handlers[notification_name].append(handler)
        _LOGGER.debug("Registered handler for notification: %s", notification_name)

    def unregister_notification_handler(
        self, notification_name: str, handler: Callable[[dict[str, Any]], None]
    ) -> None:
        """Unregister a notification handler."""
        if notification_name in self._notification_handlers:
            self._notification_handlers[notification_name].remove(handler)
            if not self._notification_handlers[notification_name]:
                del self._notification_handlers[notification_name]
            _LOGGER.debug(
                "Unregistered handler for notification: %s", notification_name
            )

    def start_notification_listener(self) -> None:
        """Start the WebSocket notification listener."""
        if self._ws_task is None or self._ws_task.done():
            self._stop_notification_listener = False
            self._ws_task = self._hass.async_create_task(self._websocket_listener())
            _LOGGER.info("Started WebSocket notification listener task")

    async def stop_notification_listener(self) -> None:
        """Stop the WebSocket notification listener."""
        self._stop_notification_listener = True
        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._ws_task
            _LOGGER.info("Stopped WebSocket notification listener")
            _LOGGER.info("Stopped WebSocket notification listener")

    def get_thing_class_name(self, thingclass_id: str) -> str | None:
        """Get the display name of a thing class by its ID."""
        for thing_class in self.thing_classes:
            if thing_class.get("id") == thingclass_id:
                return thing_class.get("displayName")
        return None

    async def discover_and_log_all_things(self) -> None:
        """Discover and log all available thing classes and things from the Nymea system."""
        try:
            # Get all vendors
            loop = self._hass.loop
            vendors_response = await loop.run_in_executor(
                None, self.send_command, "Integrations.GetVendors", None
            )
            vendors = vendors_response.get("params", {}).get("vendors", [])

            # Create vendor lookup and store
            vendor_map = {v["id"]: v for v in vendors}
            self.vendors = vendor_map

            # Get all thing classes
            thing_classes_response = await loop.run_in_executor(
                None, self.send_command, "Integrations.GetThingClasses", None
            )
            thing_classes = thing_classes_response.get("params", {}).get(
                "thingClasses", []
            )

            # Store thing classes for dynamic entity generation
            self.thing_classes = thing_classes

            # Get all things
            things_response = await loop.run_in_executor(
                None, self.send_command, "Integrations.GetThings", None
            )
            things = things_response.get("params", {}).get("things", [])

            # Build output as strings to reduce number of log calls
            output = []
            output.append("=" * 80)
            output.append("NYMEA DISCOVERY STARTING")
            output.append("=" * 80)
            output.append(
                f"Found {len(vendors)} vendors, {len(thing_classes)} thing classes, {len(things)} things (devices)"
            )
            output.append("-" * 80)
            output.append("THING CLASSES AVAILABLE:")
            output.append("-" * 80)

            # Log each thing class with detailed info
            for tc in thing_classes:
                vendor = vendor_map.get(tc.get("vendorId"), {})
                vendor_name = vendor.get("displayName", "Unknown")

                output.append("")
                output.append(f"Thing Class: {tc.get('displayName', 'N/A')}")
                output.append(f"  - ID: {tc.get('id', 'N/A')}")
                output.append(f"  - Vendor: {vendor_name}")
                output.append(f"  - Vendor ID: {tc.get('vendorId', 'N/A')}")

                # Log available state types
                state_types = tc.get("stateTypes", [])
                if state_types:
                    output.append(f"  - State Types ({len(state_types)}):")
                    for st in state_types:
                        output.append(
                            f"      * {st.get('displayName', 'N/A')} (ID: {st.get('id', 'N/A')}, Type: {st.get('type', 'N/A')})"
                        )

                # Log available action types
                action_types = tc.get("actionTypes", [])
                if action_types:
                    output.append(f"  - Action Types ({len(action_types)}):")
                    for at in action_types:
                        output.append(
                            f"      * {at.get('displayName', 'N/A')} (ID: {at.get('id', 'N/A')})"
                        )

                # Log available event types
                event_types = tc.get("eventTypes", [])
                if event_types:
                    output.append(f"  - Event Types ({len(event_types)}):")
                    for et in event_types:
                        output.append(
                            f"      * {et.get('displayName', 'N/A')} (ID: {et.get('id', 'N/A')})"
                        )

            output.append("")
            output.append("-" * 80)
            output.append("THINGS (DEVICES) CONFIGURED:")
            output.append("-" * 80)

            # Log each thing instance
            for thing in things:
                thing_class = next(
                    (
                        tc
                        for tc in thing_classes
                        if tc["id"] == thing.get("thingClassId")
                    ),
                    None,
                )

                output.append("")
                output.append(f"Device: {thing.get('name', 'N/A')}")
                output.append(f"  - Thing ID: {thing.get('id', 'N/A')}")
                output.append(f"  - Thing Class ID: {thing.get('thingClassId', 'N/A')}")

                if thing_class:
                    vendor = vendor_map.get(thing_class.get("vendorId"), {})
                    output.append(
                        f"  - Thing Class: {thing_class.get('displayName', 'N/A')}"
                    )
                    output.append(f"  - Vendor: {vendor.get('displayName', 'Unknown')}")

                # Get current states for this thing
                states_response = await loop.run_in_executor(
                    None,
                    self.send_command,
                    "Integrations.GetStateValues",
                    {"thingId": thing.get("id")},
                )

                if states_response:
                    values = states_response.get("params", {}).get("values", [])
                    if values:
                        output.append("  - Current States:")
                        for state_value in values:
                            state_type_id = state_value.get("stateTypeId")
                            value = state_value.get("value")

                            # Try to find the state type name
                            state_type_name = "Unknown"
                            if thing_class:
                                state_types = thing_class.get("stateTypes", [])
                                state_type = next(
                                    (
                                        st
                                        for st in state_types
                                        if st["id"] == state_type_id
                                    ),
                                    None,
                                )
                                if state_type:
                                    state_type_name = state_type.get(
                                        "displayName", "Unknown"
                                    )

                            output.append(f"      * {state_type_name}: {value}")

            output.append("")
            output.append("=" * 80)
            output.append("NYMEA DISCOVERY COMPLETE")
            output.append("=" * 80)

            # Log everything as a single multi-line message
            _LOGGER.info("Nymea Discovery Results:\n%s", "\n".join(output))

        except Exception:
            _LOGGER.exception("Error during Nymea discovery")
