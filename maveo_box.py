"""A nymea 'hub' that connects several devices."""

from __future__ import annotations

import getpass
import json
import logging
import socket
import ssl
from threading import Lock

from homeassistant.core import HomeAssistant

mutex = Lock()


class MaveoBox:
    """Maveo Box."""

    def __init__(
        self, hass: HomeAssistant, host: str, port: int, token: str | None = None
    ) -> None:
        """Init maveo box."""
        self._host = host
        self._port = port
        self._hass = hass
        self._name = host
        self._id = host.lower()
        self._token = token
        self._pushButtonAuthAvailable = False
        self._authenticationRequired = True
        self._initialSetupRequired = False
        self._commandId = 0
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.maveoSticks = []
        self.maveoSensors = []
        self.aqaraSensors = []
        self.online = True
        self.logger = logging.getLogger(__name__)

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
                return True
            except (socket.timeout, socket.error):
                return False

    async def init_connection(self) -> str | None:
        try:
            self._sock.connect((self._host, self._port))

            # Perform initial handshake
            try:
                handshake_message = self.send_command("JSONRPC.Hello", {})
            except:
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                try:
                    self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self._sock.connect((self._host, self._port))
                    self._sock = context.wrap_socket(self._sock)
                    handshake_message = self.send_command("JSONRPC.Hello", {})
                except:
                    self.logger.error("SSL handshake failed.")

            handshake_data = handshake_message["params"]

            self._initialSetupRequired = handshake_data["initialSetupRequired"]
            self._authenticationRequired = handshake_data["authenticationRequired"]
            self._pushButtonAuthAvailable = handshake_data["pushButtonAuthAvailable"]

            # If we don't need any authentication, we are done
            if not self._authenticationRequired:
                return None

            if self._initialSetupRequired and not self._pushButtonAuthAvailable:
                self.logger.error(
                    "We are expecting a configured maveo box, so there should be a user"
                )
                return None

            # Authenticate if no token
            if self._authenticationRequired and self._token == None:
                if self._pushButtonAuthAvailable:
                    self.pushbuttonAuthentication()
                else:
                    self.logger.error(
                        "We do not handle nymea installations without push-button"
                    )

            return self._token
        except OSError:
            self.logger.exception("ERROR: %s -> could not connect to nymea.")
            return None

    def pushbuttonAuthentication(self) -> str | None:
        if self._token != None:
            return self._token

        self.logger.info("Using push button authentication method...")

        params = {"deviceName": "home assistant"}
        command_obj = {
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

        # check response
        self.logger.info(
            "Initialized push button authentication. Please press the pushbutton on the device."
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
                self.logger.info("Notification received:")
                if response["params"]["success"] is True:
                    self.logger.info("Authenticated successfully!")
                    self.logger.info("Token: %s", response["params"]["token"])
                    self._token = response["params"]["token"]
                    return self._token

    def send_command(self, method, params=None):
        with mutex:
            command_obj = {"id": self._commandId, "method": method}

            if self._authenticationRequired and self._token is not None:
                command_obj["token"] = self._token

            if params is not None and len(params) > 0:
                command_obj["params"] = params

            command = json.dumps(command_obj) + "\n"
            try:
                self._sock.send(command.encode("utf-8"))
            except Exception as exc:
                return None

            # wait for the response with id = commandId
            responseId = -1
            while responseId != self._commandId:
                data = b""

                while b"}\n" not in data:
                    chunk = self._sock.recv(4096)
                    if chunk == b"":
                        raise RuntimeError("socket connection broken")
                    data += chunk

                response = json.loads(data.decode("utf-8"))
                if "notification" in response:
                    continue
                responseId = response["id"]
            self._commandId = self._commandId + 1

            # If this call was unautorized, authenticate
            if response["status"] == "unauthorized":
                self.logger.error("Unautorized json call")

            # if this call was not successfull
            if response["status"] != "success":
                self.logger.error("JSON error happened: %s", response["error"])
                return None

            # Call went fine, return the response
            return response
