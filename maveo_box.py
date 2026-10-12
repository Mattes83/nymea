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

_LOGGER = logging.getLogger(__name__)

COMMAND_TIMEOUT = 10  # seconds to wait for a JSON-RPC response
PAIRING_TIMEOUT = 60  # seconds to wait for the push button press


class NymeaConnectionError(Exception):
    """Raised when communication with the nymea box fails."""


class NymeaPairingError(Exception):
    """Raised when push button pairing fails."""


class MaveoBox:
    """Maveo Box."""

    # Server UUID from the JSONRPC.Hello handshake.
    server_uuid: str | None = None

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        port: int,
        token: str | None = None,
        websocket_port: int = 4445,
    ) -> None:
        """Init maveo box."""
        self._host: str = host
        self._port: int = port  # JSON-RPC port (typically 2223)
        self._ws_port: int = (
            websocket_port  # WebSocket port for notifications (typically 4445)
        )
        self._hass: HomeAssistant = hass
        self._name: str = host
        self._id: str = host.lower()
        self._token: str | None = token
        self._pushButtonAuthAvailable: bool = False
        self._authenticationRequired: bool = True
        self._initialSetupRequired: bool = False
        self._commandId: int = 0

        # JSON-RPC socket for commands; created in init_connection.
        self._sock: socket.socket | None = None
        self._use_ssl: bool = False
        self._recv_buffer: bytes = b""
        self._lock: Lock = Lock()

        # WebSocket connection for notifications (port 4445)
        self._ws_task: asyncio.Task[None] | None = None

        self.maveoSticks: list[Any] = []
        self.things: list[Any] = []

        # Inventory data for dynamic entity generation
        self.thing_classes: list[dict[str, Any]] = []
        self.vendors: dict[str, dict[str, Any]] = {}
        self.raw_things: list[dict[str, Any]] = []
        self.entity_configs: dict[str, list[dict[str, Any]]] = {}

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
        """Test initial connectivity during setup."""

        def _probe() -> bool:
            try:
                with socket.create_connection((self._host, self._port), timeout=5):
                    return True
            except OSError:
                return False

        return await self._hass.async_add_executor_job(_probe)

    def _create_ssl_context(self) -> ssl.SSLContext:
        """Create SSL context with self-signed certificate support."""
        context = ssl.create_default_context()
        # As we are working with self signed certificates disable some cert checks.
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context

    async def init_connection(self) -> str | None:
        """Connect and authenticate; returns the token used for authentication."""
        return await self._hass.async_add_executor_job(self._init_connection_blocking)

    def _init_connection_blocking(self) -> str | None:
        """Blocking connect + handshake + authentication (runs in executor)."""
        with self._lock:
            self._use_ssl = False
            self._connect_socket()
            try:
                # First try without SSL, fall back to SSL.
                handshake = self._send_command_locked("JSONRPC.Hello", {})
            except (NymeaConnectionError, OSError, ValueError):
                _LOGGER.debug("Plain connection failed, retrying with SSL")
                self._use_ssl = True
                self._connect_socket()
                handshake = self._send_command_locked("JSONRPC.Hello", {})

            if handshake is None:
                raise NymeaConnectionError("JSONRPC.Hello handshake failed")

            handshake_data = handshake["params"]
            self.server_uuid = handshake_data.get("uuid")
            self._initialSetupRequired = handshake_data["initialSetupRequired"]
            self._authenticationRequired = handshake_data["authenticationRequired"]
            self._pushButtonAuthAvailable = handshake_data["pushButtonAuthAvailable"]

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

            if self._token is None:
                self._token = self._pushbutton_auth_locked()

            return self._token

    def _connect_socket(self) -> None:
        """(Re)create the JSON-RPC socket. Must be called with the lock held."""
        self._close_socket()
        sock = socket.create_connection(
            (self._host, self._port), timeout=COMMAND_TIMEOUT
        )
        if self._use_ssl:
            sock = self._create_ssl_context().wrap_socket(sock)
        self._sock = sock
        self._recv_buffer = b""

    def _close_socket(self) -> None:
        """Close the JSON-RPC socket if open."""
        if self._sock is not None:
            with contextlib.suppress(OSError):
                self._sock.close()
            self._sock = None

    def _read_message(self) -> dict[str, Any]:
        """Read one newline-delimited JSON message. Must be called with the lock held."""
        if self._sock is None:
            raise NymeaConnectionError("Not connected")
        while True:
            newline = self._recv_buffer.find(b"\n")
            if newline != -1:
                line = self._recv_buffer[:newline]
                self._recv_buffer = self._recv_buffer[newline + 1 :]
                if line.strip():
                    return json.loads(line)
                continue
            chunk = self._sock.recv(4096)
            if chunk == b"":
                raise NymeaConnectionError("Socket connection broken")
            self._recv_buffer += chunk

    def _pushbutton_auth_locked(self) -> str:
        """Authenticate using the push button method. Must be called with the lock held."""
        if self._sock is None:
            raise NymeaConnectionError("Not connected")

        _LOGGER.info("Using push button authentication method")

        command_id = self._commandId
        self._commandId += 1
        command_obj: dict[str, Any] = {
            "id": command_id,
            "params": {"deviceName": "home assistant"},
            "method": "JSONRPC.RequestPushButtonAuth",
        }
        self._sock.send((json.dumps(command_obj) + "\n").encode("utf-8"))

        self._sock.settimeout(PAIRING_TIMEOUT)
        try:
            transaction_id: int | None = None
            while True:
                response = self._read_message()
                if response.get("id") == command_id:
                    params = response.get("params", {})
                    if response.get("status") != "success" or not params.get(
                        "success", True
                    ):
                        raise NymeaPairingError(
                            "Push button authentication request rejected"
                        )
                    transaction_id = params.get("transactionId")
                    _LOGGER.info(
                        "Push button authentication started, waiting for the button press"
                    )
                    continue
                if response.get("notification") == "JSONRPC.PushButtonAuthFinished":
                    params = response.get("params", {})
                    if (
                        transaction_id is not None
                        and params.get("transactionId") != transaction_id
                    ):
                        continue
                    if params.get("success"):
                        _LOGGER.info("Authenticated successfully")
                        return params["token"]
                    raise NymeaPairingError("Push button authentication failed")
        except TimeoutError as ex:
            raise NymeaPairingError(
                "Timed out waiting for the push button press"
            ) from ex
        finally:
            if self._sock is not None:
                self._sock.settimeout(COMMAND_TIMEOUT)

    def send_command(
        self, method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Send a JSON-RPC command and wait for the response (blocking).

        Must not be called from the event loop; use async_send_command there.
        """
        with self._lock:
            try:
                return self._send_command_locked(method, params)
            except (NymeaConnectionError, OSError) as ex:
                _LOGGER.warning(
                    "Connection to %s lost (%s), reconnecting", self._host, ex
                )
                self._connect_socket()
                if self._send_command_locked("JSONRPC.Hello", {}) is None:
                    raise NymeaConnectionError("Reconnect handshake failed") from ex
                return self._send_command_locked(method, params)

    async def async_send_command(
        self, method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Send a JSON-RPC command from the event loop."""
        return await self._hass.async_add_executor_job(
            self.send_command, method, params
        )

    def _send_command_locked(
        self, method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Send a command and wait for its response. Must be called with the lock held."""
        if self._sock is None:
            raise NymeaConnectionError("Not connected")

        command_obj: dict[str, Any] = {"id": self._commandId, "method": method}
        command_id: int = self._commandId
        self._commandId += 1

        if self._authenticationRequired and self._token is not None:
            command_obj["token"] = self._token

        if params is not None and len(params) > 0:
            command_obj["params"] = params

        self._sock.send((json.dumps(command_obj) + "\n").encode("utf-8"))

        while True:
            response = self._read_message()
            if "notification" in response:
                _LOGGER.debug(
                    "Skipping notification on command socket: %s",
                    response["notification"],
                )
                continue
            if response.get("id") != command_id:
                continue
            if response.get("status") != "success":
                _LOGGER.error(
                    "JSON-RPC error for %s: %s", method, response.get("error")
                )
                return None
            return response

    async def _websocket_listener(self) -> None:
        """WebSocket listener with automatic reconnection on disconnect."""
        _LOGGER.debug("Starting WebSocket notification listener")

        # Start with the scheme negotiated on the JSON-RPC socket; flip until
        # the first successful connect, then stick with what worked.
        use_ssl = self._use_ssl
        ssl_context: ssl.SSLContext | None = None
        connected_once = False
        retry_delay = 5  # seconds; doubles on each failure up to 60 s

        while not self._stop_notification_listener:
            try:
                if use_ssl and ssl_context is None:
                    ssl_context = await self._hass.async_add_executor_job(
                        self._create_ssl_context
                    )
                scheme = "wss" if use_ssl else "ws"
                ws_url = f"{scheme}://{self._host}:{self._ws_port}"
                connect_kwargs: dict[str, Any] = {"ssl": ssl_context} if use_ssl else {}
                async with websockets.connect(ws_url, **connect_kwargs) as websocket:
                    connected_once = True
                    retry_delay = 5
                    await self._ws_listen_loop(websocket)

            except asyncio.CancelledError:
                raise
            except Exception as ex:
                if self._stop_notification_listener:
                    break
                _LOGGER.warning(
                    "WebSocket disconnected, retrying in %ds: %s", retry_delay, ex
                )
                if not connected_once:
                    use_ssl = not use_ssl
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)

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

            # Now enable notifications for the Integrations namespace.
            enable_notifications = {
                "id": 2,
                "method": "JSONRPC.SetNotificationStatus",
                "params": {"namespaces": ["Integrations"]},
            }

            # Add token at top level if authentication is required.
            if self._authenticationRequired and self._token:
                enable_notifications["token"] = self._token

            await websocket.send(json.dumps(enable_notifications))
            notif_response = json.loads(await websocket.recv())
            if notif_response.get("status") == "success":
                _LOGGER.debug("WebSocket notifications enabled")
            else:
                _LOGGER.warning("Failed to enable notifications: %s", notif_response)

            # Listen for notifications. Handlers run directly in the event loop.
            while not self._stop_notification_listener:
                message = json.loads(await websocket.recv())

                if "notification" not in message:
                    # Command response on WebSocket (shouldn't happen often).
                    _LOGGER.debug(
                        "Received command response on WebSocket: %s", message
                    )
                    continue

                notification_name = message["notification"]
                params = message.get("params", {})
                _LOGGER.debug(
                    "WebSocket notification: %s with params: %s",
                    notification_name,
                    params,
                )

                handlers = self._notification_handlers.get(notification_name)
                if not handlers:
                    _LOGGER.debug(
                        "No handler registered for: %s", notification_name
                    )
                    continue
                for handler in list(handlers):
                    try:
                        handler(params)
                    except Exception:
                        _LOGGER.exception(
                            "Error in notification handler for %s",
                            notification_name,
                        )

        except websockets.exceptions.ConnectionClosed:
            _LOGGER.warning("WebSocket connection closed")
        finally:
            _LOGGER.debug("WebSocket notification listener stopped")

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
            self._ws_task = self._hass.async_create_background_task(
              self._websocket_listener(),
              name="nymea_websocket_listener",
            )
            _LOGGER.info("Started WebSocket notification listener task")

    async def stop_notification_listener(self) -> None:
        """Stop the WebSocket notification listener."""
        self._stop_notification_listener = True
        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._ws_task
            _LOGGER.debug("Stopped WebSocket notification listener")

    async def close(self) -> None:
        """Stop the notification listener and close the JSON-RPC connection."""
        await self.stop_notification_listener()
        with self._lock:
            self._close_socket()

    def get_thing_class(self, thingclass_id: str) -> dict[str, Any] | None:
        """Return the cached thing class with the given ID."""
        return next(
            (tc for tc in self.thing_classes if tc.get("id") == thingclass_id), None
        )

    async def async_fetch_inventory(self) -> None:
        """Fetch vendors, thing classes and things from the nymea box."""
        vendors_response = await self.async_send_command("Integrations.GetVendors")
        thing_classes_response = await self.async_send_command(
            "Integrations.GetThingClasses"
        )
        things_response = await self.async_send_command("Integrations.GetThings")

        if None in (vendors_response, thing_classes_response, things_response):
            raise NymeaConnectionError("Failed to fetch inventory from nymea box")

        vendors = vendors_response.get("params", {}).get("vendors", [])
        self.vendors = {v["id"]: v for v in vendors}
        self.thing_classes = thing_classes_response.get("params", {}).get(
            "thingClasses", []
        )
        self.raw_things = things_response.get("params", {}).get("things", [])

        _LOGGER.debug(
            "Fetched inventory: %d vendors, %d thing classes, %d things",
            len(self.vendors),
            len(self.thing_classes),
            len(self.raw_things),
        )
