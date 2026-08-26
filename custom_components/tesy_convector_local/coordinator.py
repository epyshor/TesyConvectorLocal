"""DataUpdateCoordinator for Tesy Convector (Cloud & Local)."""
from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    AUTH_TYPE_CLOUD,
    CONF_AUTH_TYPE,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_IP_ADDRESS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_NAME,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from .tesy_cloud import TesyCloudClient, TesyCloudError
from .tesy_convector import TesyConvector, TesyError

_LOGGER = logging.getLogger(__name__)


def _extract_payload_val(container: Any, key: str, fallback: Any = None) -> Any:
    """Helper to safely extract a nested payload value from Tesy's local JSON structure."""
    if not isinstance(container, dict):
        return fallback

    item = container.get(key)
    if isinstance(item, dict):
        inner_payload = item.get("payload")
        if isinstance(inner_payload, dict):
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
    """Class to manage fetching Tesy Convector data from Cloud or Local."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        local_api: TesyConvector | None = None,
        cloud_api: TesyCloudClient | None = None,
    ) -> None:
        """Initialize the coordinator."""
        self.config_entry = config_entry
        self.local_api = local_api
        self.cloud_api = cloud_api
        self.is_cloud = config_entry.data.get(CONF_AUTH_TYPE) == AUTH_TYPE_CLOUD or cloud_api is not None

        self.device_id = str(config_entry.data.get(CONF_DEVICE_ID) or config_entry.data.get(CONF_IP_ADDRESS) or "tesy")
        self.device_name = config_entry.data.get(CONF_DEVICE_NAME) or DEFAULT_NAME

        update_interval_sec = config_entry.options.get(
            CONF_UPDATE_INTERVAL,
            config_entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        )

        coord_name = f"{DOMAIN} ({'Cloud: ' + self.device_id if self.is_cloud else 'Local: ' + self.device_id})"

        super().__init__(
            hass,
            _LOGGER,
            name=coord_name,
            update_interval=timedelta(seconds=update_interval_sec),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Tesy via Cloud or Local."""
        if self.is_cloud and self.cloud_api:
            return await self._async_update_cloud()
        elif self.local_api:
            return await self._async_update_local()
        else:
            raise UpdateFailed("No valid API client configured for Tesy coordinator")

    async def _async_update_cloud(self) -> dict[str, Any]:
        """Fetch data from MyTESY Cloud."""
        assert self.cloud_api is not None
        try:
            device_info = await self.cloud_api.async_get_device_status(self.device_id)
        except TesyCloudError as err:
            raise UpdateFailed(f"Error fetching from MyTESY Cloud for device {self.device_id}: {err}") from err

        raw_state = device_info.get("state", {})
        if not isinstance(raw_state, dict):
            raw_state = {}

        dev_status = raw_state.get("DeviceStatus") if isinstance(raw_state.get("DeviceStatus"), dict) else raw_state

        power_val = (
            dev_status.get("power_sw")
            or dev_status.get("power")
            or dev_status.get("onOff")
            or dev_status.get("status")
            or dev_status.get("state")
        )
        is_on = str(power_val).lower() in ("on", "1", "true")

        target_temp = (
            dev_status.get("ref_gradus")
            or dev_status.get("tmpT")
            or dev_status.get("setTemp")
            or dev_status.get("temp")
            or dev_status.get("target_temp")
            or dev_status.get("req_temp")
        )
        current_temp = (
            dev_status.get("gradus")
            or dev_status.get("current_temp")
            or dev_status.get("currentTemp")
            or dev_status.get("curr_temp")
            or dev_status.get("temp_current")
        )

        parsed: dict[str, Any] = {
            "is_on": is_on,
            "target_temp": float(target_temp) if target_temp is not None else None,
            "current_temp": float(current_temp) if current_temp is not None else None,
            "mode": dev_status.get("mode") or "manual",
            "boost": str(dev_status.get("boost_sw", "")).lower() in ("on", "1"),
            "heater_state": "HEATING" if (str(dev_status.get("heating", "")).lower() in ("on", "1") or str(dev_status.get("heater_state", "")).upper() == "HEATING") else ("READY" if is_on else "INACTIVE"),
            "model": device_info.get("model") or "cn05uv",
            "name": device_info.get("name") or self.device_name,
            "mac": device_info.get("mac"),
            "sw_version": device_info.get("firmware_version") or "MyTESY Cloud",
            "device_id": self.device_id,
            "lock_device": str(dev_status.get("lockDevice", "")).lower() in ("on", "1"),
            "anti_frost": str(dev_status.get("antiFrost", "")).lower() in ("on", "1"),
            "adaptive_start": str(dev_status.get("adaptiveStart", "")).lower() in ("on", "1"),
            "opened_window": str(dev_status.get("openedWindow", "")).lower() in ("on", "1"),
            "uv": str(dev_status.get("uv", "")).lower() in ("on", "1"),
            "temp_correction": float(dev_status.get("TCorrection", 0.0) or 0.0),
        }
        return parsed

    async def _async_update_local(self) -> dict[str, Any]:
        """Fetch data from Local Convector API."""
        assert self.local_api is not None
        try:
            raw_data = await self.local_api.async_get_status()
        except TesyError as err:
            raise UpdateFailed(f"Error communicating with local Tesy at {self.device_id}: {err}") from err

        payload = raw_data.get("payload", {})
        if not isinstance(payload, dict):
            payload = raw_data

        target_t = _extract_payload_val(payload, "setTemp")
        current_t = (
            _extract_payload_val(payload, "currentTemp")
            or _extract_payload_val(payload, "gradus")
            or _extract_payload_val(payload, "temp")
        )

        parsed: dict[str, Any] = {
            "is_on": _extract_payload_val(payload, "onOff", "off") == "on",
            "target_temp": float(target_t) if target_t is not None else None,
            "current_temp": float(current_t) if current_t is not None else None,
            "mode": _extract_payload_val(payload, "mode", "manual"),
            "boost": False,
            "heater_state": "HEATING" if _extract_payload_val(payload, "onOff", "off") == "on" else "READY",
            "lock_device": _extract_payload_val(payload, "lockDevice", "off") == "on",
            "anti_frost": _extract_payload_val(payload, "antiFrost", "off") == "on",
            "adaptive_start": _extract_payload_val(payload, "adaptiveStart", "off") == "on",
            "opened_window": _extract_payload_val(payload, "openedWindow", "off") == "on",
            "uv": _extract_payload_val(payload, "uv", "off") == "on",
            "model": payload.get("model") or "Convector Heater",
            "name": self.device_name,
            "sw_version": payload.get("version") or "Local API",
            "device_id": self.device_id,
            "temp_correction": 0.0,
        }
        return parsed

    def _optimistic_update(self, updates: dict[str, Any]) -> None:
        """Apply optimistic state updates to the coordinator data immediately."""
        if self.data is not None:
            new_data = dict(self.data)
            new_data.update(updates)
            self.async_set_updated_data(new_data)

    # Unified Action Helpers with Optimistic Updates
    async def async_turn_on(self) -> None:
        """Turn on the convector."""
        self._optimistic_update({"is_on": True, "heater_state": "HEATING"})
        if self.cloud_api:
            await self.cloud_api.async_turn_on(self.device_id)
        if self.local_api:
            await self.local_api.async_turn_on()
        self.hass.async_create_task(self._delayed_refresh())

    async def async_turn_off(self) -> None:
        """Turn off the convector."""
        self._optimistic_update({"is_on": False, "heater_state": "READY"})
        if self.cloud_api:
            await self.cloud_api.async_turn_off(self.device_id)
        if self.local_api:
            await self.local_api.async_turn_off()
        self.hass.async_create_task(self._delayed_refresh())

    async def async_set_temperature(self, temp: float | int) -> None:
        """Set target temperature."""
        target = float(round(float(temp)))
        self._optimistic_update({"target_temp": target})
        if self.cloud_api:
            await self.cloud_api.async_set_temperature(self.device_id, target)
        if self.local_api:
            await self.local_api.async_set_temperature(target)
        self.hass.async_create_task(self._delayed_refresh())

    async def async_set_boost(self, enabled: bool) -> None:
        """Set boost mode."""
        self._optimistic_update({"boost": enabled})
        if self.cloud_api:
            await self.cloud_api.async_set_boost(self.device_id, enabled)
        self.hass.async_create_task(self._delayed_refresh())

    async def async_set_lock_device(self, enabled: bool) -> None:
        """Set child lock."""
        self._optimistic_update({"lock_device": enabled})
        if self.cloud_api:
            await self.cloud_api.async_set_lock_device(self.device_id, enabled)
        if self.local_api:
            await self.local_api.async_set_lock_device(enabled)
        self.hass.async_create_task(self._delayed_refresh())

    async def async_set_anti_frost(self, enabled: bool) -> None:
        """Set anti-frost."""
        self._optimistic_update({"anti_frost": enabled})
        if self.cloud_api:
            await self.cloud_api.async_set_anti_frost(self.device_id, enabled)
        if self.local_api:
            await self.local_api.async_set_anti_frost(enabled)
        self.hass.async_create_task(self._delayed_refresh())

    async def async_set_adaptive_start(self, enabled: bool) -> None:
        """Set adaptive start."""
        self._optimistic_update({"adaptive_start": enabled})
        if self.cloud_api:
            await self.cloud_api.async_set_adaptive_start(self.device_id, enabled)
        if self.local_api:
            await self.local_api.async_set_adaptive_start(enabled)
        self.hass.async_create_task(self._delayed_refresh())

    async def async_set_opened_window(self, enabled: bool) -> None:
        """Set opened window detection."""
        self._optimistic_update({"opened_window": enabled})
        if self.cloud_api:
            await self.cloud_api.async_set_opened_window(self.device_id, enabled)
        if self.local_api:
            await self.local_api.async_set_opened_window(enabled)
        self.hass.async_create_task(self._delayed_refresh())

    async def async_set_uv(self, enabled: bool) -> None:
        """Set UV / Air Care."""
        self._optimistic_update({"uv": enabled})
        if self.cloud_api:
            await self.cloud_api.async_set_uv(self.device_id, enabled)
        if self.local_api:
            await self.local_api.async_set_uv(enabled)
        self.hass.async_create_task(self._delayed_refresh())

    async def async_set_temperature_correction(self, offset: float | int) -> None:
        """Set temperature calibration offset."""
        self._optimistic_update({"temp_correction": float(offset)})
        if self.cloud_api:
            await self.cloud_api.async_set_temperature_correction(self.device_id, offset)
        if self.local_api:
            await self.local_api.async_set_temperature_correction(offset)
        self.hass.async_create_task(self._delayed_refresh())

    async def _delayed_refresh(self) -> None:
        """Wait a moment for the device to apply changes in cloud, then refresh."""
        await asyncio.sleep(5)
        await self.async_request_refresh()
