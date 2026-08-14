"""DataUpdateCoordinator for Tesy Convector."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL, DOMAIN
from .tesy_convector import TesyConvector, TesyError

_LOGGER = logging.getLogger(__name__)


def _extract_payload_val(container: Any, key: str, fallback: Any = None) -> Any:
    """Helper to safely extract a nested payload value from Tesy's JSON structure."""
    if not isinstance(container, dict):
        return fallback

    item = container.get(key)
    if isinstance(item, dict):
        inner_payload = item.get("payload")
        if isinstance(inner_payload, dict):
            # E.g. {"status": "on"} or {"temp": 22} or {"name": "manual"}
            if "status" in inner_payload:
                return inner_payload["status"]
            if "temp" in inner_payload:
                return inner_payload["temp"]
            if "name" in inner_payload:
                return inner_payload["name"]
            return inner_payload
        if "status" in item:
            return item["status"]
        if "temp" in item:
            return item["temp"]
        if "name" in item:
            return item["name"]
        return item
    return item if item is not None else fallback


class TesyDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching Tesy Convector data."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        api: TesyConvector,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        self.api = api
        self.ip_address = api.ip_address
        self.config_entry = config_entry

        update_interval_sec = config_entry.options.get(
            CONF_UPDATE_INTERVAL,
            config_entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        )

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({self.ip_address})",
            update_interval=timedelta(seconds=update_interval_sec),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Tesy Convector."""
        try:
            raw_data = await self.api.async_get_status()
        except TesyError as err:
            raise UpdateFailed(f"Error communicating with Tesy Convector at {self.ip_address}: {err}") from err

        _LOGGER.debug("Raw data received from Tesy Convector (%s): %s", self.ip_address, raw_data)

        payload = raw_data.get("payload", {})
        if not isinstance(payload, dict):
            payload = raw_data

        # Normalize parsed values
        parsed: dict[str, Any] = {
            "raw": raw_data,
            "is_on": _extract_payload_val(payload, "onOff", "off") == "on",
            "target_temp": _extract_payload_val(payload, "setTemp"),
            "current_temp": _extract_payload_val(payload, "currentTemp")
            or _extract_payload_val(payload, "gradus")
            or _extract_payload_val(payload, "temp"),
            "mode": _extract_payload_val(payload, "mode", "manual"),
            "lock_device": _extract_payload_val(payload, "lockDevice", "off") == "on",
            "anti_frost": _extract_payload_val(payload, "antiFrost", "off") == "on",
            "adaptive_start": _extract_payload_val(payload, "adaptiveStart", "off") == "on",
            "opened_window": _extract_payload_val(payload, "openedWindow", "off") == "on",
            "uv": _extract_payload_val(payload, "uv", "off") == "on",
            "device_id": payload.get("devId") or payload.get("id") or self.ip_address,
            "sw_version": payload.get("version") or payload.get("firmware"),
            "model": payload.get("model") or "Convector Heater",
        }

        # Format target_temp to float if valid
        if parsed["target_temp"] is not None:
            try:
                parsed["target_temp"] = float(parsed["target_temp"])
            except (ValueError, TypeError):
                parsed["target_temp"] = None

        if parsed["current_temp"] is not None:
            try:
                parsed["current_temp"] = float(parsed["current_temp"])
            except (ValueError, TypeError):
                parsed["current_temp"] = None

        return parsed
