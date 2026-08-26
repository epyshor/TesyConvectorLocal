"""MyTESY Cloud API and MQTT client for Tesy convectors and water heaters."""
from __future__ import annotations

import asyncio
import json
import logging
import struct
from typing import Any
import uuid
from urllib.parse import urlencode

import aiohttp

_LOGGER = logging.getLogger(__name__)

CLOUD_BASE_URL = "https://ad.mytesy.com/rest"
REQUEST_TIMEOUT = 15

MQTT_HOST = "mqtt.tesy.com"
MQTT_PORT = 1883
MQTT_USER = "client1"
MQTT_PASS = "123"

HEADERS = {
    "authority": "ad.mytesy.com",
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9,ro;q=0.8,bg;q=0.7",
    "content-type": "application/json",
    "dnt": "1",
    "origin": "https://v4.mytesy.com",
    "referer": "https://v4.mytesy.com/",
}


def _encode_remaining_length(rem_len: int) -> bytes:
    """Encode MQTT remaining length field."""
    rem_bytes = bytearray()
    while True:
        byte = rem_len % 128
        rem_len = rem_len // 128
        if rem_len > 0:
            byte |= 0x80
        rem_bytes.append(byte)
        if rem_len == 0:
            break
    return bytes(rem_bytes)


class TesyMqttClient:
    """Lightweight asynchronous MQTT client for publishing Tesy device commands."""

    def __init__(self) -> None:
        """Initialize the MQTT client."""
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False
        self._lock = asyncio.Lock()

    async def async_connect(self) -> bool:
        """Connect to the Tesy MQTT broker."""
        async with self._lock:
            if self._connected and self._writer and not self._writer.is_closing():
                return True

            try:
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(MQTT_HOST, MQTT_PORT),
                    timeout=10,
                )

                client_id = f"ha_{uuid.uuid4().hex[:8]}"
                proto_name = b"MQTT"
                proto_level = 4
                flags = 0xC2  # username + password + clean session
                keepalive = 60

                var_header = (
                    struct.pack("!H", len(proto_name))
                    + proto_name
                    + bytes([proto_level, flags])
                    + struct.pack("!H", keepalive)
                )
                payload = (
                    struct.pack("!H", len(client_id))
                    + client_id.encode("utf-8")
                    + struct.pack("!H", len(MQTT_USER))
                    + MQTT_USER.encode("utf-8")
                    + struct.pack("!H", len(MQTT_PASS))
                    + MQTT_PASS.encode("utf-8")
                )

                rem_len = len(var_header) + len(payload)
                pkt = bytes([0x10]) + _encode_remaining_length(rem_len) + var_header + payload

                self._writer.write(pkt)
                await self._writer.drain()

                resp = await asyncio.wait_for(self._reader.read(4), timeout=10)
                if len(resp) >= 4 and resp[0] == 0x20 and resp[3] == 0x00:
                    _LOGGER.debug("Connected to Tesy MQTT broker %s:%s", MQTT_HOST, MQTT_PORT)
                    self._connected = True
                    return True
                else:
                    _LOGGER.warning("Unexpected MQTT CONNACK from %s: %s", MQTT_HOST, resp.hex())
                    await self.async_close()
                    return False

            except Exception as err:
                _LOGGER.warning("Could not connect to Tesy MQTT broker: %s", err)
                await self.async_close()
                return False

    async def async_publish(self, topic: str, payload_data: dict[str, Any]) -> bool:
        """Publish a command message to Tesy MQTT topic."""
        try:
            if not self._connected:
                ok = await self.async_connect()
                if not ok:
                    return False

            topic_bytes = topic.encode("utf-8")
            payload_str = json.dumps(payload_data)
            payload_bytes = payload_str.encode("utf-8")

            var_header = struct.pack("!H", len(topic_bytes)) + topic_bytes
            rem_len = len(var_header) + len(payload_bytes)
            pkt = bytes([0x30]) + _encode_remaining_length(rem_len) + var_header + payload_bytes

            async with self._lock:
                if self._writer and not self._writer.is_closing():
                    self._writer.write(pkt)
                    await self._writer.drain()
                    _LOGGER.info("Published MQTT command to topic %s: %s", topic, payload_str)
                    return True
                else:
                    self._connected = False
                    return False

        except Exception as err:
            _LOGGER.warning("Failed to publish MQTT command to %s: %s", topic, err)
            self._connected = False
            return False

    async def async_close(self) -> None:
        """Close the MQTT connection."""
        self._connected = False
        if self._writer and not self._writer.is_closing():
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
        self._writer = None
        self._reader = None


class TesyCloudError(Exception):
    """Base exception for Tesy Cloud errors."""


class TesyCloudAuthError(TesyCloudError):
    """Exception raised when authentication fails."""


class TesyCloudConnectionError(TesyCloudError):
    """Exception raised when connection to MyTESY cloud fails."""


class TesyCloudClient:
    """Client for communicating with MyTESY Cloud (mytesy.com) via REST and MQTT."""

    def __init__(
        self,
        username: str,
        password: str,
        userid: int | str | None = None,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        """Initialize the MyTESY Cloud client."""
        self.username = username.strip()
        self.password = password
        self.userid = str(userid).strip() if userid is not None else None
        self._session = session
        self._close_session = False

        self.acc_session: str | None = None
        self.acc_alt: str | None = None
        self._cached_devices: dict[str, dict[str, Any]] = {}
        self.mqtt_client = TesyMqttClient()

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp ClientSession."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._close_session = True
        return self._session

    async def async_close(self) -> None:
        """Close the session and MQTT connection."""
        await self.mqtt_client.async_close()
        if self._close_session and self._session and not self._session.closed:
            await self._session.close()

    async def async_login(self) -> dict[str, Any]:
        """Authenticate with MyTESY Cloud and retrieve session tokens and userID."""
        session = await self._get_session()

        # Method 1: Modern MyTESY V4 API login (app-user-login)
        url_v4 = f"{CLOUD_BASE_URL}/app-user-login"
        payload_v4 = {
            "email": self.username,
            "password": self.password,
        }

        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with session.post(url_v4, json=payload_v4, headers=HEADERS) as response:
                    if response.status in (200, 201):
                        data = await response.json(content_type=None)
                        if isinstance(data, dict) and not data.get("errors") and not data.get("error"):
                            user_id_val = (
                                data.get("userID")
                                or data.get("id")
                                or data.get("userId")
                                or data.get("user_id")
                            )
                            if user_id_val is not None:
                                self.userid = str(user_id_val)

                            self.acc_session = data.get("acc_session") or data.get("session") or data.get("PHPSESSID")
                            self.acc_alt = data.get("acc_alt") or data.get("alt") or data.get("ALT")
                            _LOGGER.debug("MyTESY V4 login successful for %s (userID: %s)", self.username, self.userid)
                            return data
        except Exception as err:
            _LOGGER.debug("app-user-login attempt error: %s. Trying old-app-login fallback...", err)

        # Method 2: Legacy old-app-login endpoint
        url_old = f"{CLOUD_BASE_URL}/old-app-login"
        payload_old = {
            "email": self.username,
            "password": self.password,
            "userEmail": self.username,
            "userPass": self.password,
            "lang": "en",
        }
        if self.userid:
            payload_old["userID"] = self.userid

        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with session.post(url_old, json=payload_old, headers=HEADERS) as response:
                    if response.status not in (200, 201):
                        raise TesyCloudConnectionError(f"HTTP {response.status} from MyTESY Cloud login")

                    data = await response.json(content_type=None)

                    if not isinstance(data, dict):
                        raise TesyCloudAuthError("Invalid response received during MyTESY login")

                    if data.get("error") or data.get("status") == "error" or data.get("res") == "error":
                        error_msg = data.get("error") or data.get("msg") or "Invalid email or password"
                        raise TesyCloudAuthError(str(error_msg))

                    self.acc_session = data.get("acc_session") or data.get("session") or data.get("PHPSESSID")
                    self.acc_alt = data.get("acc_alt") or data.get("alt") or data.get("ALT")

                    if not self.userid:
                        user_id_val = (
                            data.get("id")
                            or data.get("userID")
                            or data.get("userId")
                            or data.get("user_id")
                        )
                        if user_id_val is not None:
                            self.userid = str(user_id_val)

                    _LOGGER.debug(
                        "MyTESY legacy login successful for %s (userID: %s)",
                        self.username,
                        self.userid,
                    )
                    return data

        except asyncio.TimeoutError as err:
            raise TesyCloudConnectionError("Timeout connecting to MyTESY Cloud") from err
        except aiohttp.ClientError as err:
            raise TesyCloudConnectionError(f"Network error connecting to MyTESY: {err}") from err

    async def async_get_devices(self) -> dict[str, dict[str, Any]]:
        """Fetch all devices registered on the user's MyTESY account."""
        session = await self._get_session()

        if not self.userid or not self.acc_session:
            await self.async_login()

        # Method 1: Try get-my-devices endpoint
        if self.userid:
            params = {
                "userID": self.userid,
                "userEmail": self.username,
                "userPass": self.password,
                "lang": "en",
            }
            url = f"{CLOUD_BASE_URL}/get-my-devices?{urlencode(params)}"
            try:
                async with asyncio.timeout(REQUEST_TIMEOUT):
                    async with session.get(url, headers=HEADERS) as response:
                        if response.status == 200:
                            data = await response.json(content_type=None)
                            if data:
                                devices = self._normalize_devices_dict(data)
                                if devices:
                                    self._cached_devices = devices
                                    return devices
            except Exception as err:
                _LOGGER.debug("get-my-devices attempt error: %s. Trying old-app-devices fallback...", err)

        # Method 2: Fallback to old-app-devices endpoint
        url_post = f"{CLOUD_BASE_URL}/old-app-devices"
        payload = {
            "ALT": self.acc_alt,
            "CURRENT_SESSION": None,
            "PHPSESSID": self.acc_session,
            "last_login_username": self.username,
        }

        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with session.post(url_post, json=payload, headers=HEADERS) as response:
                    if response.status != 200:
                        raise TesyCloudConnectionError(f"HTTP {response.status} fetching devices from MyTESY")

                    data = await response.json(content_type=None)
                    devices = self._normalize_devices_dict(data)
                    self._cached_devices = devices
                    return devices

        except asyncio.TimeoutError as err:
            raise TesyCloudConnectionError("Timeout fetching devices from MyTESY Cloud") from err
        except aiohttp.ClientError as err:
            raise TesyCloudConnectionError(f"Network error fetching MyTESY devices: {err}") from err

    def _normalize_devices_dict(self, raw_data: Any) -> dict[str, dict[str, Any]]:
        """Normalize devices dictionary/list from MyTESY into a clean format."""
        normalized: dict[str, dict[str, Any]] = {}
        if not raw_data:
            return normalized

        container: Any = raw_data

        # If raw_data is a dict, check for subkeys containing list or dict of devices
        if isinstance(raw_data, dict):
            # First check if raw_data itself is already a single device object
            is_single_device = any(
                k in raw_data for k in ("deviceName", "dev_name", "mac", "MAC", "DeviceStatus", "model", "token")
            )
            if not is_single_device:
                for key in ("device", "devices", "data", "result", "list", "items"):
                    val = raw_data.get(key)
                    if isinstance(val, (dict, list)) and val:
                        container = val
                        break

        items_list: list[tuple[Any, Any]] = []
        if isinstance(container, dict):
            # Check if container is a single device object or a map of devices
            if any(k in container for k in ("deviceName", "dev_name", "mac", "MAC", "DeviceStatus", "model", "token")):
                items_list = [(container.get("id") or container.get("mac") or "0", container)]
            else:
                items_list = list(container.items())
        elif isinstance(container, list):
            items_list = [(idx, item) for idx, item in enumerate(container)]
        else:
            return normalized

        for key, item in items_list:
            if not isinstance(item, dict):
                continue

            state_obj = item.get("state") or item.get("DeviceStatus") or item.get("status") or {}
            if not isinstance(state_obj, dict):
                state_obj = {}

            numeric_id = (
                item.get("id")
                or item.get("deviceID")
                or item.get("device_id")
                or state_obj.get("id")
                or (int(key) if str(key).isdigit() else None)
            )

            mac = (
                item.get("mac")
                or item.get("MAC")
                or item.get("mac_address")
                or item.get("dev_mac")
                or state_obj.get("mac")
                or (key if not str(key).isdigit() and ":" in str(key) else None)
            )

            primary_id = str(mac or numeric_id or item.get("id") or key)

            name = (
                item.get("deviceName")
                or item.get("name")
                or item.get("dev_name")
                or item.get("alias")
                or state_obj.get("deviceName")
                or state_obj.get("name")
                or f"Tesy {item.get('model', 'Heater')} ({primary_id})"
            )

            model = item.get("model") or item.get("device_type") or item.get("dev_type") or "cn05uv"
            token = item.get("token") or item.get("device_token")
            fw_version = item.get("firmware_version") or item.get("sw_version") or item.get("fw_ver")

            dev_data = {
                "id": str(primary_id),
                "numeric_id": str(numeric_id) if numeric_id is not None else str(primary_id),
                "name": str(name),
                "mac": str(mac) if mac else str(primary_id),
                "model": str(model),
                "token": token,
                "firmware_version": fw_version,
                "raw_item": item,
                "state": state_obj,
            }

            normalized[str(primary_id)] = dev_data

        return normalized

    async def async_get_device_status(self, device_id: str) -> dict[str, Any]:
        """Fetch the latest status for a specific device."""
        devices = await self.async_get_devices()
        str_id = str(device_id)

        # 1. Direct match
        dev_info = devices.get(str_id)
        if dev_info:
            return dev_info

        # 2. Search by id, numeric_id, mac, or sanitized MAC (case-insensitive)
        clean_target = str_id.replace(":", "").lower()
        for d in devices.values():
            if (
                d.get("id") == str_id
                or d.get("numeric_id") == str_id
                or d.get("mac") == str_id
                or str(d.get("mac", "")).replace(":", "").lower() == clean_target
                or str(d.get("id", "")).replace(":", "").lower() == clean_target
            ):
                return d

        raise TesyCloudError(f"Device ID {device_id} not found in MyTESY account")

    def _format_mac_with_colons(self, mac_str: str) -> str:
        """Format MAC address as XX:XX:XX:XX:XX:XX uppercase (as expected by MyTESY app-log endpoint)."""
        clean = str(mac_str).replace(":", "").replace("-", "").strip().upper()
        if len(clean) == 12:
            return ":".join(clean[i:i+2] for i in range(0, 12, 2))
        return str(mac_str).upper()

    async def _async_send_app_log(
        self, device_id: str, dev_info: dict[str, Any], command: str, payload_dict: dict[str, Any]
    ) -> bool:
        """Send command to official MyTESY V4 REST app-log endpoint reverse-engineered from MyTESY app."""
        session = await self._get_session()

        raw_mac = dev_info.get("mac") or dev_info.get("id") or str(device_id)
        mac_formatted = self._format_mac_with_colons(raw_mac)

        user_id_val: Any = self.userid
        if isinstance(self.userid, str) and self.userid.isdigit():
            user_id_val = int(self.userid)

        payload = {
            "command": command,
            "lang": "en",
            "mac": mac_formatted,
            "payload": payload_dict,
            "userEmail": self.username,
            "userID": user_id_val,
            "userPass": self.password,
        }

        endpoints = [
            f"{CLOUD_BASE_URL}/app-log",
            f"{CLOUD_BASE_URL}/user-device-log",
        ]

        success = False
        for endpoint in endpoints:
            try:
                async with asyncio.timeout(REQUEST_TIMEOUT):
                    async with session.post(endpoint, json=payload, headers=HEADERS) as response:
                        _LOGGER.debug("REST app-log %s command '%s' payload %s status: %s", endpoint, command, payload_dict, response.status)
                        if response.status in (200, 201):
                            success = True
            except Exception as err:
                _LOGGER.warning("REST app-log error for %s command '%s': %s", endpoint, command, err)

        return success

    async def async_send_command(
        self,
        device_id: str,
        mqtt_command: str,
        mqtt_payload: dict[str, Any],
        rest_command: str | None = None,
        rest_value: Any = None,
    ) -> bool:
        """Send command via official MyTESY Cloud app-log REST endpoint and MQTT broker."""
        dev_info = self._cached_devices.get(str(device_id))
        if not dev_info:
            try:
                dev_info = await self.async_get_device_status(device_id)
            except Exception:
                dev_info = {}

        # 1. Primary Method: Official MyTESY V4 REST app-log API (exact payload format from MyTESY web app)
        app_log_ok = await self._async_send_app_log(device_id, dev_info, mqtt_command, mqtt_payload)

        # Legacy fallback REST endpoint
        if rest_command is None:
            rest_command = mqtt_command
        if rest_value is None and "status" in mqtt_payload:
            rest_value = mqtt_payload["status"]
        if rest_value is None and "temp" in mqtt_payload:
            rest_value = mqtt_payload["temp"]
        if rest_value is None and "mode" in mqtt_payload:
            rest_value = mqtt_payload["mode"]

        rest_ok = await self._async_send_rest_fallback(device_id, dev_info, rest_command, rest_value)

        # 2. Secondary Method: MQTT with clean MAC format
        raw_mac = dev_info.get("mac") or str(device_id)
        clean_mac_upper = str(raw_mac).replace(":", "").upper()
        clean_mac_lower = str(raw_mac).replace(":", "").lower()
        model = dev_info.get("model") or "cn05uv"
        token = dev_info.get("token")

        mqtt_ok = False
        if token:
            msg_payload = {
                "app_id": f"ha_{uuid.uuid4().hex[:7]}",
                **mqtt_payload,
            }
            topic_upper = f"v1/{clean_mac_upper}/request/{model}/{token}/{mqtt_command}"
            topic_lower = f"v1/{clean_mac_lower}/request/{model}/{token}/{mqtt_command}"
            res_u = await self.mqtt_client.async_publish(topic_upper, msg_payload)
            res_l = await self.mqtt_client.async_publish(topic_lower, msg_payload)
            mqtt_ok = res_u or res_l

        return app_log_ok or rest_ok or mqtt_ok

    async def _async_send_rest_fallback(
        self, device_id: str, dev_info: dict[str, Any], command: str, value: Any
    ) -> bool:
        """Send command to MyTESY REST endpoints using all candidate keys and ID formats for high compatibility."""
        session = await self._get_session()
        if not self.acc_session or not self.acc_alt:
            await self.async_login()

        numeric_id = dev_info.get("numeric_id")
        raw_mac = dev_info.get("mac") or str(device_id)
        clean_mac = str(raw_mac).replace(":", "").upper()
        target_id = numeric_id or dev_info.get("id") or str(device_id)

        endpoints = [
            f"{CLOUD_BASE_URL}/old-app-set-device-status",
            f"{CLOUD_BASE_URL}/app-set-device-status",
            f"{CLOUD_BASE_URL}/set-device-status",
        ]

        commands_to_try = [command]
        if command in ("tmpT", "req_temp", "setTemp", "ref_gradus"):
            commands_to_try = ["req_temp", "setTemp", "tmpT", "ref_gradus"]
        elif command in ("mode", "setMode"):
            commands_to_try = ["mode", "setMode"]
        elif command in ("power_sw", "onOff", "power"):
            commands_to_try = ["power_sw", "onOff", "power"]

        success = False
        for endpoint in endpoints:
            for cmd in commands_to_try:
                payload = {
                    "ALT": self.acc_alt,
                    "CURRENT_SESSION": None,
                    "PHPSESSID": self.acc_session,
                    "last_login_username": self.username,
                    "id": target_id,
                    "deviceID": numeric_id or target_id,
                    "device_id": numeric_id or target_id,
                    "mac": raw_mac,
                    "MAC": clean_mac,
                    "apiVersion": "apiv1",
                    "command": cmd,
                    "value": str(value) if isinstance(value, (int, float)) else value,
                    "val": value,
                    "status": str(value),
                    "userID": self.userid,
                    "userEmail": self.username,
                    "userPass": self.password,
                    "lang": "en",
                }

                try:
                    async with asyncio.timeout(REQUEST_TIMEOUT):
                        async with session.post(endpoint, json=payload, headers=HEADERS) as response:
                            _LOGGER.debug("REST %s '%s'=%s status: %s", endpoint, cmd, value, response.status)
                            if response.status in (200, 201):
                                success = True
                except Exception as err:
                    _LOGGER.debug("REST error for %s %s: %s", endpoint, cmd, err)

        return success

    # High-level Device Actions via MQTT & REST
    async def async_turn_on(self, device_id: str) -> bool:
        """Turn on the convector."""
        return await self.async_send_command(
            device_id,
            mqtt_command="onOff",
            mqtt_payload={"status": "on"},
            rest_command="power_sw",
            rest_value="on",
        )

    async def async_turn_off(self, device_id: str) -> bool:
        """Turn off the convector."""
        return await self.async_send_command(
            device_id,
            mqtt_command="onOff",
            mqtt_payload={"status": "off"},
            rest_command="power_sw",
            rest_value="off",
        )

    async def async_set_temperature(self, device_id: str, temp: float | int) -> bool:
        """Set target temperature (sets mode to manual first then sets setComfortTemp and setTemp)."""
        target = round(float(temp))
        # 1. Ensure manual mode
        await self.async_send_command(
            device_id,
            mqtt_command="setMode",
            mqtt_payload={"mode": "manual"},
            rest_command="mode",
            rest_value="manual",
        )
        # 2. Set comfort mode target temperature (from official MyTESY app payload capture)
        await self.async_send_command(
            device_id,
            mqtt_command="setComfortTemp",
            mqtt_payload={"temp": target},
            rest_command="setComfortTemp",
            rest_value=target,
        )
        # 3. Set main target temperature
        return await self.async_send_command(
            device_id,
            mqtt_command="setTemp",
            mqtt_payload={"temp": target},
            rest_command="req_temp",
            rest_value=target,
        )

    async def async_set_boost(self, device_id: str, enabled: bool) -> bool:
        """Set boost mode."""
        status = "on" if enabled else "off"
        return await self.async_send_command(
            device_id,
            mqtt_command="setBoost",
            mqtt_payload={"status": status},
            rest_command="boost_sw",
            rest_value=status,
        )

    async def async_set_lock_device(self, device_id: str, enabled: bool) -> bool:
        """Set child lock."""
        status = "on" if enabled else "off"
        return await self.async_send_command(
            device_id,
            mqtt_command="setLockDevice",
            mqtt_payload={"status": status},
            rest_command="lockDevice",
            rest_value=status,
        )

    async def async_set_anti_frost(self, device_id: str, enabled: bool) -> bool:
        """Set anti-frost."""
        status = "on" if enabled else "off"
        return await self.async_send_command(
            device_id,
            mqtt_command="setAntiFrost",
            mqtt_payload={"status": status},
            rest_command="antiFrost",
            rest_value=status,
        )

    async def async_set_adaptive_start(self, device_id: str, enabled: bool) -> bool:
        """Set adaptive start."""
        status = "on" if enabled else "off"
        return await self.async_send_command(
            device_id,
            mqtt_command="setAdaptiveStart",
            mqtt_payload={"status": status},
            rest_command="adaptiveStart",
            rest_value=status,
        )

    async def async_set_opened_window(self, device_id: str, enabled: bool) -> bool:
        """Set opened window detection."""
        status = "on" if enabled else "off"
        return await self.async_send_command(
            device_id,
            mqtt_command="setOpenedWindow",
            mqtt_payload={"status": status},
            rest_command="openedWindow",
            rest_value=status,
        )

    async def async_set_uv(self, device_id: str, enabled: bool) -> bool:
        """Set UV / Air Care."""
        status = "on" if enabled else "off"
        return await self.async_send_command(
            device_id,
            mqtt_command="setUV",
            mqtt_payload={"status": status},
            rest_command="uv",
            rest_value=status,
        )

    async def async_set_temperature_correction(self, device_id: str, offset: float | int) -> bool:
        """Set temperature calibration offset."""
        return await self.async_send_command(
            device_id,
            mqtt_command="setTCorrection",
            mqtt_payload={"temp": round(float(offset))},
            rest_command="TCorrection",
            rest_value=round(float(offset)),
        )
