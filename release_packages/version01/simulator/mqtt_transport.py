"""Authenticated MQTT device publisher for the local telemetry contract."""

import json
import threading
from pathlib import Path


def device_message(event: dict) -> bytes:
    """Encode one device reading; gateway receipt time belongs to the gateway."""
    payload = {"schema_version": 1}
    payload.update(
        (key, value) for key, value in event.items() if key != "gateway_received_at"
    )
    return json.dumps(payload, allow_nan=False, separators=(",", ":")).encode("utf-8")


def validate_mqtt_target(
    device_id: str, host: str, port: int, username: str, password_file: Path
) -> str:
    if any(character in device_id for character in ("/", "+", "#")):
        raise ValueError("MQTT device_id must be one topic level without /, + or #")
    if not host or any(character.isspace() for character in host):
        raise ValueError("mqtt_host must be a nonempty hostname without whitespace")
    if not 1 <= port <= 65535:
        raise ValueError("mqtt_port must be from 1 to 65535")
    if not username or "\0" in username:
        raise ValueError("mqtt_username must be nonempty and contain no NUL")
    try:
        password = password_file.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise ValueError("Cannot read MQTT password file") from None
    if password.endswith("\n"):
        password = password[:-1]
        if password.endswith("\r"):
            password = password[:-1]
    if not password or "\n" in password or "\r" in password:
        raise ValueError("MQTT password file must contain one nonempty line")
    return password


class MqttPublisher:
    """One in-flight QoS 1 publish at a time; no automatic retry on uncertainty."""

    def __init__(
        self, host: str, port: int, username: str, password: str, timeout: float
    ) -> None:
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            raise RuntimeError(
                "MQTT mode requires paho-mqtt; install simulator/requirements.txt"
            ) from None

        self._mqtt = mqtt
        self._host = host
        self._port = port
        self._timeout = timeout
        self._connected = threading.Event()
        self._connect_reason = None
        self._started = False
        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            protocol=mqtt.MQTTv311,
            reconnect_on_failure=False,
        )
        self._client.username_pw_set(username, password)
        self._client.on_connect = self._on_connect

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        self._connect_reason = reason_code
        self._connected.set()

    def _ensure_connected(self) -> None:
        if self._started:
            return
        self._started = True
        result = self._client.connect(self._host, self._port, keepalive=60)
        if result != self._mqtt.MQTT_ERR_SUCCESS:
            raise OSError("MQTT connection failed")
        self._client.loop_start()
        if not self._connected.wait(self._timeout):
            raise TimeoutError("MQTT connection acknowledgement timed out")
        if self._connect_reason != 0:
            raise OSError("MQTT broker rejected the connection")

    def publish(self, event: dict) -> None:
        self._ensure_connected()
        topic = f"equipment/{event['device_id']}/telemetry"
        info = self._client.publish(topic, device_message(event), qos=1, retain=False)
        if info.rc != self._mqtt.MQTT_ERR_SUCCESS:
            raise OSError("MQTT publish failed")
        info.wait_for_publish(timeout=self._timeout)
        if not info.is_published():
            raise TimeoutError("MQTT PUBACK timed out")

    def close(self) -> None:
        if self._started:
            self._client.disconnect()
            self._client.loop_stop()
