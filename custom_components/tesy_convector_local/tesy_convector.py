"""Local API client for Tesy Convector."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = 10


class TesyError(Exception):
    """Base exception for Tesy Convector errors."""


class TesyConnectionError(TesyError):
    """Exception raised when connection to Tesy convector fails."""


class TesyInvalidResponseError(TesyError):
    """Exception raised when Tesy convector returns an unexpected response."""


class TesyConvector:
    """API client for controlling a Tesy convector locally over HTTP."""

    def __init__(self, ip_address: str, session: aiohttp.ClientSession | None = None) -> None:
        """Initialize the client."""
        self.ip_address = ip_address.strip()
        self.base_url = f"http://{self.ip_address}"
        self._session = session
        self._close_session = False

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

    async def async_send_command(self, endpoint: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send a command to the Tesy convector endpoint and return parsed JSON."""
        url = f"{self.base_url}/{endpoint}"
        if payload is None:
            payload = {}

        session = await self._get_session()

        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with session.post(url, json=payload) as response:
                    if response.status != 200:
                        _LOGGER.warning(
                            "Tesy convector at %s returned HTTP status %s for endpoint %s",
                            self.ip_address,
                            response.status,
                            endpoint,
                        )

                    try:
                        data = await response.json(content_type=None)
                    except (aiohttp.ContentTypeError, ValueError) as err:
                        text_response = await response.text()
                        _LOGGER.error(
                            "Unexpected response format from %s/%s: %s (err: %s)",
                            self.ip_address,
                            endpoint,
                            text_response,
                            err,
                        )
                        raise TesyInvalidResponseError(
                            f"Invalid JSON response from {endpoint}: {text_response[:100]}"
                        ) from err

                    if not isinstance(data, dict):
                        raise TesyInvalidResponseError(f"Expected dict response from {endpoint}, got {type(data)}")

                    return data

        except asyncio.TimeoutError as err:
            _LOGGER.error("Timeout connecting to Tesy convector at %s (%s)", self.ip_address, endpoint)
            raise TesyConnectionError(f"Timeout communicating with Tesy convector at {self.ip_address}") from err
        except aiohttp.ClientError as err:
            _LOGGER.error("Client error communicating with Tesy convector at %s: %s", self.ip_address, err)
            raise TesyConnectionError(f"HTTP error communicating with Tesy convector at {self.ip_address}: {err}") from err
        except Exception as err:
            if isinstance(err, (TesyError, asyncio.CancelledError)):
                raise
            _LOGGER.error("Unexpected error communicating with Tesy convector at %s: %s", self.ip_address, err)
            raise TesyConnectionError(f"Unexpected error communicating with {self.ip_address}: {err}") from err

    async def async_get_status(self) -> dict[str, Any]:
        """Fetch current status from the convector."""
        return await self.async_send_command("getStatus", {})

    async def async_turn_on(self) -> dict[str, Any]:
        """Turn on the convector."""
        return await self.async_send_command("onOff", {"status": "on"})

    async def async_turn_off(self) -> dict[str, Any]:
        """Turn off the convector."""
        return await self.async_send_command("onOff", {"status": "off"})

    async def async_set_mode(self, mode: str) -> dict[str, Any]:
        """Set the operation mode (e.g., 'manual', 'eco', 'comfort', 'program')."""
        return await self.async_send_command("setMode", {"name": mode})

    async def async_set_temperature(self, temp: float | int) -> dict[str, Any]:
        """Set target temperature (usually 10 to 30 C). Switch to manual mode first."""
        try:
            await self.async_set_mode("manual")
        except Exception as err:
            _LOGGER.debug("Could not set local mode to manual before setting temp: %s", err)
        try:
            await self.async_set_comfort_temperature(temp)
        except Exception as err:
            _LOGGER.debug("Could not set local comfort temp: %s", err)
        return await self.async_send_command("setTemp", {"temp": round(float(temp))})

    async def async_set_adaptive_start(self, enabled: bool) -> dict[str, Any]:
        """Enable or disable adaptive start."""
        status = "on" if enabled else "off"
        return await self.async_send_command("setAdaptiveStart", {"status": status})

    async def async_set_opened_window(self, enabled: bool) -> dict[str, Any]:
        """Enable or disable open window detection."""
        status = "on" if enabled else "off"
        return await self.async_send_command("setOpenedWindow", {"status": status})

    async def async_set_anti_frost(self, enabled: bool) -> dict[str, Any]:
        """Enable or disable anti-frost mode."""
        status = "on" if enabled else "off"
        return await self.async_send_command("setAntiFrost", {"status": status})

    async def async_set_lock_device(self, enabled: bool) -> dict[str, Any]:
        """Enable or disable child lock (keyboard lock)."""
        status = "on" if enabled else "off"
        return await self.async_send_command("setLockDevice", {"status": status})

    async def async_set_uv(self, enabled: bool) -> dict[str, Any]:
        """Enable or disable UV / Air Care lamp (if supported)."""
        status = "on" if enabled else "off"
        return await self.async_send_command("setUV", {"status": status})

    async def async_set_temperature_correction(self, temp_offset: float | int) -> dict[str, Any]:
        """Set temperature calibration offset."""
        return await self.async_send_command("setTCorrection", {"temp": float(temp_offset)})

    async def async_set_comfort_temperature(self, temp: float | int) -> dict[str, Any]:
        """Set comfort mode target temperature."""
        return await self.async_send_command("setComfortTemp", {"temp": round(float(temp))})

    async def async_set_eco_temperature(self, temp: float | int, time_minutes: int = 0) -> dict[str, Any]:
        """Set eco mode target temperature and duration."""
        return await self.async_send_command("setEcoTemp", {"temp": round(float(temp)), "time": time_minutes})

    async def async_set_sleep_temperature(self, temp: float | int, time_minutes: int = 0) -> dict[str, Any]:
        """Set sleep mode target temperature and duration."""
        return await self.async_send_command("setSleepTemp", {"temp": round(float(temp)), "time": time_minutes})

    async def async_set_delayed_start(self, time_minutes: int, temp: float | int, enabled: bool = True) -> dict[str, Any]:
        """Set delayed start timer."""
        status = "on" if enabled else "off"
        return await self.async_send_command("setDelayedStart", {"status": status, "time": time_minutes, "temp": round(float(temp))})