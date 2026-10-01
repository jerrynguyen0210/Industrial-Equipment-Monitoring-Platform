"""Provision device MQTT accounts through Mosquitto Dynamic Security."""

import json
import os
import secrets
import threading
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt

CONTROL_TOPIC = "$CONTROL/dynamic-security/v1"
DEVICE_ROLE = "iemp-device-publisher"
DEVICE_ACL = "equipment/%u/telemetry"


class BrokerUnavailable(Exception):
    """The broker did not confirm a requested change."""


class BrokerConflict(Exception):
    """A broker identity is owned by another account or policy."""


class BrokerAdmin:
    def __init__(
        self,
        host: str,
        port: int,
        admin_password_file: Path,
        legacy_password_file: Path,
    ) -> None:
        self.host = host
        self.port = port
        self.admin_password_file = admin_password_file
        self.legacy_password_file = legacy_password_file

    @classmethod
    def from_environment(cls) -> "BrokerAdmin":
        return cls(
            os.environ.get("MQTT_HOST", "mosquitto"),
            int(os.environ.get("MQTT_PORT", "1883")),
            Path(
                os.environ.get(
                    "MQTT_ADMIN_PASSWORD_FILE", "/mosquitto-auth/admin.password"
                )
            ),
            Path(os.environ.get("MQTT_LEGACY_PASSWORD_FILE", "/mosquitto-auth/passwd")),
        )

    def _legacy_account_exists(self, username: str) -> bool:
        try:
            lines = self.legacy_password_file.read_text(encoding="utf-8").splitlines()
        except OSError as error:
            raise BrokerUnavailable("MQTT credentials are unavailable") from error
        return any(line.partition(":")[0] == username for line in lines)

    def _verify_login(self, username: str, password: str) -> bool:
        """Confirm an existing file-based account without reading its hash format."""
        finished = threading.Event()
        accepted: bool | None = None
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.username_pw_set(username, password)

        def on_connect(
            _client: mqtt.Client,
            _userdata: object,
            _flags: object,
            reason_code: mqtt.ReasonCode,
            _properties: object,
        ) -> None:
            nonlocal accepted
            accepted = not reason_code.is_failure
            finished.set()

        client.on_connect = on_connect
        client.on_connect_fail = lambda _client, _userdata: finished.set()
        try:
            client.connect_async(self.host, self.port, keepalive=10)
            client.loop_start()
            finished.wait(6)
        except (OSError, ValueError) as error:
            raise BrokerUnavailable("MQTT broker is unavailable") from error
        finally:
            client.disconnect()
            client.loop_stop()
        if accepted is None:
            raise BrokerUnavailable("MQTT broker did not confirm the login")
        return accepted

    def _request(self, commands: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Wait for the matching broker response; never put passwords in logs."""
        try:
            password = self.admin_password_file.read_text(encoding="utf-8").strip()
        except OSError as error:
            raise BrokerUnavailable("MQTT administration is unavailable") from error
        if not password:
            raise BrokerUnavailable("MQTT administration is unavailable")

        prepared = [
            {**command, "correlationData": secrets.token_hex(16)}
            for command in commands
        ]
        expected = {command["correlationData"] for command in prepared}
        finished = threading.Event()
        result: list[dict[str, Any]] | None = None
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.username_pw_set("admin", password)

        def on_connect(
            client: mqtt.Client,
            _userdata: object,
            _flags: object,
            reason_code: mqtt.ReasonCode,
            _properties: object,
        ) -> None:
            if reason_code.is_failure:
                finished.set()
                return
            client.subscribe(f"{CONTROL_TOPIC}/response", qos=1)

        def on_subscribe(
            client: mqtt.Client,
            _userdata: object,
            _mid: int,
            reason_codes: list[mqtt.ReasonCode],
            _properties: object,
        ) -> None:
            if any(reason.is_failure for reason in reason_codes):
                finished.set()
                return
            info = client.publish(
                CONTROL_TOPIC, json.dumps({"commands": prepared}), qos=1
            )
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                finished.set()

        def on_message(
            _client: mqtt.Client, _userdata: object, message: mqtt.MQTTMessage
        ) -> None:
            nonlocal result
            try:
                payload = json.loads(message.payload)
                responses = payload.get("responses")
                if (
                    not isinstance(responses, list)
                    or {
                        item.get("correlationData")
                        for item in responses
                        if isinstance(item, dict)
                    }
                    != expected
                ):
                    return
                result = responses
            except (UnicodeDecodeError, ValueError, TypeError):
                return
            finished.set()

        client.on_connect = on_connect
        client.on_subscribe = on_subscribe
        client.on_message = on_message
        client.on_connect_fail = lambda _client, _userdata: finished.set()
        try:
            client.connect_async(self.host, self.port, keepalive=10)
            client.loop_start()
            finished.wait(6)
        except (OSError, ValueError) as error:
            raise BrokerUnavailable("MQTT broker is unavailable") from error
        finally:
            client.disconnect()
            client.loop_stop()
        if result is None:
            raise BrokerUnavailable("MQTT broker did not confirm the change")
        return result

    def _one(self, command: dict[str, Any]) -> dict[str, Any]:
        response = self._request([command])[0]
        if response.get("command") != command["command"]:
            raise BrokerUnavailable("Unexpected MQTT broker response")
        return response

    def _get_client(self, username: str) -> dict[str, Any] | None:
        response = self._one({"command": "getClient", "username": username})
        if response.get("error") == "Client not found":
            return None
        if "error" in response:
            raise BrokerUnavailable("MQTT account lookup failed")
        client = response.get("data", {}).get("client")
        if not isinstance(client, dict):
            raise BrokerUnavailable("Invalid MQTT account response")
        return client

    @staticmethod
    def _is_managed(client: dict[str, Any]) -> bool:
        return any(
            role.get("rolename") == DEVICE_ROLE
            for role in client.get("roles", [])
            if isinstance(role, dict)
        )

    def _ensure_role(self) -> None:
        response = self._one({"command": "getRole", "rolename": DEVICE_ROLE})
        if "error" not in response:
            return
        if response["error"] != "Role not found":
            raise BrokerUnavailable("MQTT role lookup failed")
        response = self._one(
            {
                "command": "createRole",
                "rolename": DEVICE_ROLE,
                "acls": [
                    {
                        "acltype": "publishClientSend",
                        "topic": DEVICE_ACL,
                        "priority": 1,
                        "allow": True,
                    }
                ],
            }
        )
        if response.get("error") not in (None, "Role already exists"):
            raise BrokerUnavailable("MQTT role creation failed")

    def create_device(self, device_id: str, password: str) -> bool:
        """Return whether a new managed account was created."""
        existing = self._get_client(device_id)
        if existing is not None:
            if existing.get("disabled") and self._is_managed(existing):
                self.delete_device(device_id)
            else:
                raise BrokerConflict("An MQTT account already uses this Device ID")
        if self._legacy_account_exists(device_id):
            if self._verify_login(device_id, password):
                return False
            raise BrokerConflict("Existing MQTT account uses a different password")
        self._ensure_role()
        response = self._one(
            {
                "command": "createClient",
                "username": device_id,
                "password": password,
                "roles": [{"rolename": DEVICE_ROLE, "priority": 1}],
            }
        )
        if response.get("error") == "Client already exists":
            raise BrokerConflict("An MQTT account already uses this Device ID")
        if "error" in response:
            raise BrokerUnavailable("MQTT account creation failed")
        return True

    def ensure_device(self, device_id: str, password: str) -> bool:
        """Set up an older registration or align its broker password."""
        existing = self._get_client(device_id)
        if existing is None:
            return self.create_device(device_id, password)
        if not self._is_managed(existing):
            raise BrokerConflict("An MQTT account already uses this Device ID")
        response = self._one(
            {
                "command": "setClientPassword",
                "username": device_id,
                "password": password,
            }
        )
        if "error" in response:
            raise BrokerUnavailable("MQTT password update failed")
        if existing.get("disabled"):
            self.enable_device(device_id)
        return True

    def disable_device(self, device_id: str) -> bool:
        existing = self._get_client(device_id)
        if existing is None:
            return False
        if not self._is_managed(existing):
            raise BrokerConflict("MQTT account is not managed by device registration")
        response = self._one({"command": "disableClient", "username": device_id})
        if "error" in response:
            raise BrokerUnavailable("MQTT account disable failed")
        return True

    def enable_device(self, device_id: str) -> None:
        response = self._one({"command": "enableClient", "username": device_id})
        if "error" in response:
            raise BrokerUnavailable("MQTT account enable failed")

    def delete_device(self, device_id: str) -> None:
        response = self._one({"command": "deleteClient", "username": device_id})
        if response.get("error") not in (None, "Client not found"):
            raise BrokerUnavailable("MQTT account removal failed")
