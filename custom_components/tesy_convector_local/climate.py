"""Climate platform for Tesy Convector."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.components.climate.const import (
    ATTR_TEMPERATURE,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_TEMPERATURE_ENTITY,
    DEFAULT_NAME,
    DOMAIN,
    MAX_TEMP,
    MIN_TEMP,
    TEMP_STEP,
)
from .coordinator import TesyDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Tesy Convector climate entity from config entry."""
    coordinator: TesyDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([TesyConvectorClimate(coordinator, entry)])


class TesyConvectorClimate(CoordinatorEntity[TesyDataUpdateCoordinator], ClimateEntity):
    """Representation of a Tesy Convector Climate Entity."""

    _attr_has_entity_name = True
    _attr_name = None  # Primary entity takes device name
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = MIN_TEMP
    _attr_max_temp = MAX_TEMP
    _attr_target_temperature_step = TEMP_STEP
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
    )
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(
        self,
        coordinator: TesyDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_climate"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"{DEFAULT_NAME} ({coordinator.ip_address})",
            manufacturer="Tesy",
            model=coordinator.data.get("model", "Convector Heater"),
            sw_version=str(coordinator.data.get("sw_version") or "Local API"),
            configuration_url=f"http://{coordinator.ip_address}",
        )

    @property
    def temperature_entity(self) -> str | None:
        """Return the external temperature sensor entity if configured."""
        return self.entry.options.get(
            CONF_TEMPERATURE_ENTITY,
            self.entry.data.get(CONF_TEMPERATURE_ENTITY),
        )

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current HVAC mode."""
        if not self.coordinator.data:
            return HVACMode.OFF
        return HVACMode.HEAT if self.coordinator.data.get("is_on") else HVACMode.OFF

    @property
    def current_temperature(self) -> float | None:
        """Return the current ambient temperature."""
        ext_sensor = self.temperature_entity
        if ext_sensor and self.hass:
            state = self.hass.states.get(ext_sensor)
            if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    return float(state.state)
                except (ValueError, TypeError):
                    _LOGGER.warning("Could not convert external temp sensor state %s to float", state.state)

        # Fallback to device reported current temp or target temp
        if self.coordinator.data:
            current = self.coordinator.data.get("current_temp")
            if current is not None:
                return current
            return self.coordinator.data.get("target_temp")

        return None

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        if self.coordinator.data:
            return self.coordinator.data.get("target_temp")
        return None

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target HVAC mode."""
        if hvac_mode == HVACMode.HEAT:
            await self.coordinator.api.async_turn_on()
        elif hvac_mode == HVACMode.OFF:
            await self.coordinator.api.async_turn_off()
        else:
            _LOGGER.error("Unsupported HVAC mode: %s", hvac_mode)
            return

        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        """Turn on the convector (Heat mode)."""
        await self.coordinator.api.async_turn_on()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        """Turn off the convector."""
        await self.coordinator.api.async_turn_off()
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return

        await self.coordinator.api.async_set_temperature(temperature)
        await self.coordinator.async_request_refresh()
