"""MyTESY Cloud API client for Tesy convectors and water heaters."""
from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import urlencode

import aiohttp

_LOGGER = logging.getLogger(__name__)

CLOUD_BASE_URL = "https://ad.mytesy.com/rest"
REQUEST_TIMEOUT = 15

HEADERS = {
    "authority": "ad.mytesy.com",
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9,ro;q=0.8,bg;q=0.7",
    "content-type": "application/json",
    "dnt": "1",
    "origin": "https://v4.mytesy.com",
    "referer": "https://v4.mytesy.com/",
}


class TesyCloudError(Exception):
    """Base exception for Tesy Cloud errors."""


class TesyCloudAuthError(TesyCloudError):
    """Exception raised when authentication fails."""


class TesyCloudConnectionError(TesyCloudError):
    """Exception raised when connection to MyTESY cloud fails."""


class TesyCloudClient:
    """Client for communicating with MyTESY Cloud (mytesy.com)."""

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

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp ClientSession."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._close_session = True
        return self._session

    async def async_close(self) -> None:
        """Close the session if it was created internally."""
        if self._close_session and self._session and not self._session.closed:
            await self._session.close()

    async def async_login(self) -> dict[str, Any]:
        """Authenticate with MyTESY Cloud and retrieve session tokens."""
        session = await self._get_session()
        url = f"{CLOUD_BASE_URL}/old-app-login"

        payload = {
            "email": self.username,
            "password": self.password,
            "userEmail": self.username,
            "userPass": self.password,
            "lang": "en",
        }
        if self.userid:
            payload["userID"] = self.userid

        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with session.post(url, json=payload, headers=HEADERS) as response:
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
                        "MyTESY login successful for %s (userID: %s, session: %s)",
                        self.username,
                        self.userid,
                        bool(self.acc_session),
                    )
                    return data

        except asyncio.TimeoutError as err:
            raise TesyCloudConnectionError("Timeout connecting to MyTESY Cloud") from err
        except aiohttp.ClientError as err:
            raise TesyCloudConnectionError(f"Network error connecting to MyTESY: {err}") from err

    async def async_get_devices(self) -> dict[str, dict[str, Any]]:
        """Fetch all devices registered on the user's MyTESY account."""
        session = await self._get_session()

        if not self.acc_session or not self.acc_alt:
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
                            if isinstance(data, dict) and data:
                                devices = self._normalize_devices_dict(data)
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
            "userID": self.userid,
            "userEmail": self.username,
            "userPass": self.password,
            "lang": "en",
        }

        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with session.post(url_post, json=payload, headers=HEADERS) as response:
                    if response.status != 200:
                        raise TesyCloudConnectionError(f"HTTP {response.status} fetching devices from MyTESY")

                    data = await response.json(content_type=None)
                    if isinstance(data, dict):
                        devices_container = data.get("device") or data
                        devices = self._normalize_devices_dict(devices_container)
                        self._cached_devices = devices
                        return devices

                    return {}

        except asyncio.TimeoutError as err:
            raise TesyCloudConnectionError("Timeout fetching devices from MyTESY Cloud") from err
        except aiohttp.ClientError as err:
            raise TesyCloudConnectionError(f"Network error fetching MyTESY devices: {err}") from err

    def _normalize_devices_dict(self, raw_devices: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Normalize devices dictionary from MyTESY into a clean format."""
        normalized: dict[str, dict[str, Any]] = {}

        for key, item in raw_devices.items():
            if not isinstance(item, dict):
                continue

            state_obj = item.get("state") or item.get("DeviceStatus") or {}
            if not isinstance(state_obj, dict):
                state_obj = {}

            # Extract numeric id and mac
            numeric_id = (
                item.get("id")
                or state_obj.get("id")
                or (int(key) if str(key).isdigit() else None)
            )

            mac = item.get("mac") or (key if not str(key).isdigit() else None)

            device_id = str(numeric_id or mac or key)

            name = (
                item.get("deviceName")
                or item.get("name")
                or item.get("dev_name")
                or state_obj.get("deviceName")
                or state_obj.get("name")
                or f"Tesy {item.get('model', 'Heater')} ({device_id})"
            )

            model = item.get("model") or item.get("device_type") or "Convector"
            token = item.get("token")
            fw_version = item.get("firmware_version") or item.get("sw_version")

            dev_data = {
                "id": str(device_id),
                "numeric_id": str(numeric_id) if numeric_id is not None else str(device_id),
                "name": name,
                "mac": str(mac or device_id),
                "model": model,
                "token": token,
                "firmware_version": fw_version,
                "raw_item": item,
                "state": state_obj,
            }

            normalized[str(device_id)] = dev_data
            if mac and str(mac) != str(device_id):
                normalized[str(mac)] = dev_data
            if numeric_id and str(numeric_id) != str(device_id):
                normalized[str(numeric_id)] = dev_data

        return normalized

    async def async_get_device_status(self, device_id: str) -> dict[str, Any]:
        """Fetch the latest status for a specific device."""
        devices = await self.async_get_devices()
        dev_info = devices.get(str(device_id))
        if not dev_info:
            # Try searching by numeric_id or mac
            for d in devices.values():
                if d.get("id") == str(device_id) or d.get("numeric_id") == str(device_id) or d.get("mac") == str(device_id):
                    return d
            raise TesyCloudError(f"Device ID {device_id} not found in MyTESY account")
        return dev_info

    async def async_send_command(
        self,
        device_id: str,
        command: str,
        value: Any,
        api_version: str = "apiv1",
    ) -> bool:
        """Send a control command to a device via MyTESY Cloud with multiple fallback formats."""
        session = await self._get_session()

        if not self.acc_session or not self.acc_alt:
            await self.async_login()

        # Find target device information
        dev_info = self._cached_devices.get(str(device_id))
        if not dev_info:
            try:
                dev_info = await self.async_get_device_status(device_id)
            except Exception:
                dev_info = {}

        target_id = dev_info.get("numeric_id") or dev_info.get("id") or str(device_id)

        # Endpoints to try
        endpoints = [
            f"{CLOUD_BASE_URL}/old-app-set-device-status",
            f"{CLOUD_BASE_URL}/set-device-status",
        ]

        # Payloads with different ID formats
        payload_base = {
            "ALT": self.acc_alt,
            "CURRENT_SESSION": None,
            "PHPSESSID": self.acc_session,
            "last_login_username": self.username,
            "apiVersion": api_version,
            "command": command,
            "value": value,
            "userID": self.userid,
            "userEmail": self.username,
            "userPass": self.password,
            "lang": "en",
        }

        success = False

        for url in endpoints:
            # Try with numeric target_id first, then with raw device_id
            ids_to_try = [target_id]
            if str(device_id) != str(target_id):
                ids_to_try.append(str(device_id))

            for current_id in ids_to_try:
                payload = dict(payload_base)
                payload["id"] = current_id

                try:
                    async with asyncio.timeout(REQUEST_TIMEOUT):
                        async with session.post(url, json=payload, headers=HEADERS) as response:
                            resp_text = await response.text()
                            _LOGGER.info(
                                "MyTESY Cloud command [%s=%s] to %s (id: %s) -> HTTP %s: %s",
                                command,
                                value,
                                url.split("/")[-1],
                                current_id,
                                response.status,
                                resp_text[:120],
                            )
                            if response.status == 200:
                                success = True
                                return True
                except Exception as err:
                    _LOGGER.warning("Error sending command to %s with id %s: %s", url, current_id, err)

        return success

    # High level commands
    async def async_turn_on(self, device_id: str) -> bool:
        """Turn on the convector via MyTESY Cloud."""
        # Try power_sw and onOff
        res = await self.async_send_command(device_id, "power_sw", "on")
        if not res:
            res = await self.async_send_command(device_id, "onOff", "on")
        return res

    async def async_turn_off(self, device_id: str) -> bool:
        """Turn off the convector via MyTESY Cloud."""
        res = await self.async_send_command(device_id, "power_sw", "off")
        if not res:
            res = await self.async_send_command(device_id, "onOff", "off")
        return res

    async def async_set_temperature(self, device_id: str, temp: float | int) -> bool:
        """Set target temperature via MyTESY Cloud."""
        target = round(float(temp))
        # Try tmpT and setTemp
        res = await self.async_send_command(device_id, "tmpT", target)
        if not res:
            res = await self.async_send_command(device_id, "setTemp", target)
        return res

    async def async_set_boost(self, device_id: str, enabled: bool) -> bool:
        """Set boost mode via MyTESY Cloud."""
        status = "on" if enabled else "off"
        return await self.async_send_command(device_id, "boost_sw", status)

    async def async_set_lock_device(self, device_id: str, enabled: bool) -> bool:
        """Set child lock via MyTESY Cloud."""
        status = "on" if enabled else "off"
        res = await self.async_send_command(device_id, "lockDevice", status)
        if not res:
            res = await self.async_send_command(device_id, "lock_device", status)
        return res

    async def async_set_anti_frost(self, device_id: str, enabled: bool) -> bool:
        """Set anti-frost via MyTESY Cloud."""
        status = "on" if enabled else "off"
        res = await self.async_send_command(device_id, "antiFrost", status)
        if not res:
            res = await self.async_send_command(device_id, "anti_frost", status)
        return res

    async def async_set_adaptive_start(self, device_id: str, enabled: bool) -> bool:
        """Set adaptive start via MyTESY Cloud."""
        status = "on" if enabled else "off"
        res = await self.async_send_command(device_id, "adaptiveStart", status)
        if not res:
            res = await self.async_send_command(device_id, "adaptive_start", status)
        return res

    async def async_set_opened_window(self, device_id: str, enabled: bool) -> bool:
        """Set opened window detection via MyTESY Cloud."""
        status = "on" if enabled else "off"
        res = await self.async_send_command(device_id, "openedWindow", status)
        if not res:
            res = await self.async_send_command(device_id, "opened_window", status)
        return res

    async def async_set_uv(self, device_id: str, enabled: bool) -> bool:
        """Set UV / Air Care via MyTESY Cloud."""
        status = "on" if enabled else "off"
        res = await self.async_send_command(device_id, "uv", status)
        if not res:
            res = await self.async_send_command(device_id, "setUV", status)
        return res
