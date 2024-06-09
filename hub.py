"""A nymea 'hub' that connects several devices."""

from __future__ import annotations

# In a real implementation, this would be in an external library that's on PyPI.
# The PyPI package needs to be included in the `requirements` section of manifest.json
# See https://developers.home-assistant.io/docs/creating_integration_manifest
# for more information.
import asyncio
import random
import json
import socket
import ssl
import getpass

from enum import Enum
from homeassistant.core import HomeAssistant

State = Enum(
    "State", ["unknown", "open", "closed", "opening", "closing", "intermediate"]
)


class Hub:
    """nymea hub."""

    manufacturer = "nymea"

    def __init__(self, hass: HomeAssistant, host: str, port: int) -> None:
        """Init nymea hub."""
        self._host = host
        self._port = port
        self._hass = hass
        self._name = host
        self._id = host.lower()
        self._token = None
        self._pushButtonAuthAvailable = False
        self._authenticationRequired = False
        self._initialSetupRequired = False
        self._commandId = 0
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.rollers = []
        self.online = True

    @property
    def hub_id(self) -> str:
        """ID for nymea hub."""
        return self._id

    async def test_connection(self) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(5)
            try:
                sock.connect((self._host, self._port))
                return True
            except (socket.timeout, socket.error):
                return False

    async def get_devices(self):
        params = {}
        params["thingClassId"] = "ca6baab8-3708-4478-8ca2-7d4d6d542937"
        stateTypes = self.send_command("Integrations.GetStateTypes", params)["params"][
            "stateTypes"
        ]

        statetype_manufacturer = next(
            (
                obj
                for obj in stateTypes
                if obj["displayName"] == "Garage manufacturer name"
            ),
            None,
        )

        statetype_version = next(
            (obj for obj in stateTypes if obj["displayName"] == "maveo-stick version"),
            None,
        )

        things = self.send_command("Integrations.GetThings")["params"]["things"]
        for thing in things:
            if thing["thingClassId"] == "ca6baab8-3708-4478-8ca2-7d4d6d542937":
                manufacturer = next(
                    (
                        obj
                        for obj in thing["states"]
                        if obj["stateTypeId"] == statetype_manufacturer["id"]
                    ),
                    None,
                )["value"]

                version = next(
                    (
                        obj
                        for obj in thing["states"]
                        if obj["stateTypeId"] == statetype_version["id"]
                    ),
                    None,
                )["value"]
                self.rollers.append(
                    Roller(
                        thing["id"],
                        thing["name"],
                        manufacturer,
                        version,
                        thing["id"],
                        self,
                    )
                )

    async def init_connection(self) -> bool:
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
                    print("SSL handshake failed.")

            handshake_data = handshake_message["params"]
            self.print_json_format(handshake_data)
            print(
                (
                    "Connected to",
                    handshake_data["server"],
                    "\nserver version:",
                    handshake_data["version"],
                    "\nprotocol version:",
                    handshake_data["protocol version"],
                    "\n",
                )
            )

            self._initialSetupRequired = handshake_data["initialSetupRequired"]
            self._authenticationRequired = handshake_data["authenticationRequired"]
            self._pushButtonAuthAvailable = handshake_data["pushButtonAuthAvailable"]

            # If we don't need any authentication, we are done
            if not self._authenticationRequired:
                return True

            if self._initialSetupRequired and not self._pushButtonAuthAvailable:
                print("\n\n##############################################")
                print("# Start initial setup:")
                print("##############################################\n\n")
                result = self.createUser()
                while result["params"]["error"] != "UserErrorNoError":
                    print(
                        "Error creating user: %s"
                        % self.userErrorToString(result["params"]["error"])
                    )
                    result = self.createUser()

                print("\n\nUser created successfully.\n\n")

            # Authenticate if no token
            if self._authenticationRequired and self._token == None:
                if self._pushButtonAuthAvailable:
                    self.pushbuttonAuthentication()
                else:
                    login_response = self.login()
                    while login_response["params"]["success"] != True:
                        print("Login failed. Please try again.")
                        login_response = self.login()

                    self._token = login_response["params"]["token"]

            # self.rollers = [
            #     Roller(f"{self._id}_1", f"{self._name} 1", self),
            # ]

            return True
        except socket.error as e:
            print("ERROR:", e[1], " -> could not connect to nymea.")
            print(
                "       Please check if nymea is running on %s:%s"
                % (self._host, self._port)
            )
            return False

    def createUser(self):
        user = input("Please enter email for new user: ")
        if not user:
            user = getpass.getuser()
        pprompt = lambda: (getpass.getpass(), getpass.getpass("Retype password: "))
        p1, p2 = pprompt()
        while p1 != p2:
            print("Passwords do not match. Try again")
            p1, p2 = pprompt()

        params = {}
        params["username"] = user
        params["password"] = p1
        return self.send_command("JSONRPC.CreateUser", params)

    def userErrorToString(self, error):
        return {
            "UserErrorBadPassword": "Password failed character validation",
            "UserErrorBackendError": "Error creating user database",
            "UserErrorInvalidUserId": "Invalid username. Must be an email address",
            "UserErrorDuplicateUserId": "Username does already exist",
            "UserErrorTokenNotFound": "Invalid token supplied",
            "UserErrorPermissionDenied": "Permission denied",
        }[error]

    def login(self):
        print("\n\n##############################################")
        print("# Login:")
        print("##############################################\n\n")
        user = input("Username: ")
        password = getpass.getpass()
        params = {}
        params["username"] = user
        params["password"] = password
        params["deviceName"] = "nymea-cli"
        return self.send_command("JSONRPC.Authenticate", params)

    def pushbuttonAuthentication(self):
        if self._token != None:
            return

        print("\n\nUsing push button authentication method...\n\n")

        params = {"deviceName": "nymea-cli"}
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
        print("Initialized push button authentication. Response:")
        self.print_json_format(response)

        print("\n\n##############################################")
        print("# Please press the pushbutton on the device. #")
        print("##############################################\n\n")
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
                print("Notification received:")
                self.print_json_format(response)
                if response["params"]["success"] == True:
                    print("\nAuthenticated successfully!\n")
                    print(("Token: %s" % response["params"]["token"]))
                    self.debug_stop()
                    token = response["params"]["token"]
                    return

    def send_command(self, method, params=None):
        command_obj = {"id": self._commandId, "method": method}

        if self._authenticationRequired and self._token is not None:
            command_obj["token"] = self._token

        if params is not None and len(params) > 0:
            command_obj["params"] = params

        command = json.dumps(command_obj) + "\n"
        self._sock.send(command.encode("utf-8"))

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
            self.debug_stop()
            print("Unautorized json call")
            if self._pushButtonAuthAvailable:
                self.pushbuttonAuthentication()
                return self.send_command(method, params)
            else:
                login_response = self.login()
                while login_response["params"]["success"] != True:
                    print("Login failed. Please try again.")
                    login_response = self.login()

                token = login_response["params"]["token"]
                return self.send_command(method, params)

        # if this call was not successfull
        if response["status"] != "success":
            print("JSON error happened: %s" % response["error"])
            return None

        # Call went fine, return the response
        return response

    def print_json_format(self, string):
        print(json.dumps(string, sort_keys=True, indent=4, separators=(",", ": ")))
        # print "\n"

    def debug_stop(self):
        input('\nDEBUG STOP: Press "enter" to continue...\n')


class Roller:
    """Dummy roller (device for HA) for Hello World example."""

    def __init__(
        self,
        rollerid: str,
        name: str,
        manufacturer: str,
        version: str,
        thingid: str,
        hub: Hub,
    ) -> None:
        """Init roller."""
        self._id = rollerid
        self.thingid = thingid
        self.thingclassid = "ca6baab8-3708-4478-8ca2-7d4d6d542937"
        self.hub = hub
        self.name = name
        self._callbacks = set()
        self._loop = asyncio.get_event_loop()
        self.state = State.closed

        # Some static information about this device
        self.firmware_version = version
        self.model = manufacturer

    @property
    def roller_id(self) -> str:
        """Return ID for roller."""
        return self._id

    async def delayed_update(self) -> None:
        """Publish updates, with a random delay to emulate interaction with device."""
        await asyncio.sleep(random.randint(1, 10))
        await self.publish_updates()

    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register callback, called when Roller changes state."""
        self._callbacks.add(callback)

    def remove_callback(self, callback: Callable[[], None]) -> None:
        """Remove previously registered callback."""
        self._callbacks.discard(callback)

    # In a real implementation, this library would call it's call backs when it was
    # notified of any state changeds for the relevant device.
    async def publish_updates(self) -> None:
        """Schedule call all registered callbacks."""
        self._current_position = self._target_position
        for callback in self._callbacks:
            callback()

    @property
    def online(self) -> float:
        """Roller is online."""
        return random.random() > 0.1

    @property
    def illuminance(self) -> int:
        """Return a sample illuminance in lux."""
        return random.randint(0, 500)
