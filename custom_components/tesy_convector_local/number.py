"""Number platform for Tesy Convector."""
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Callable, Coroutine

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_NAME, DOMAIN, MAX_TEMP, MIN_TEMP, TEMP_STEP
from .coordinator import TesyDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class TesyNumberEntityDescription(NumberEntityDescription):
    """Class describing Tesy number entities."""

    value_fn: Callable[[dict[str, Any]], float | None]
    set_fn: Callable[[TesyDataUpdateCoordinator, float], Coroutine[Any, Any, Any]]


NUMBER_DESCRIPTIONS: tuple[TesyNumberEntityDescription, ...] = (
    TesyNumberEntityDescription(
        key="target_temperature",
        translation_key="target_temperature",
        name="Target Temperature",
        icon="mdi:thermometer-chevron-up",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_min_value=MIN_TEMP,
        native_max_value=MAX_TEMP,
        native_step=TEMP_STEP,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        mode=NumberMode.SLIDER,
        value_fn=lambda data: float(data.get("target_temp")) if data.get("target_temp") is not None else 21.0,
        set_fn=lambda coordinator, value: coordinator.async_set_temperature(value),
    ),
    TesyNumberEntityDescription(
        key="temperature_correction",
        translation_key="temperature_correction",
        name="Temperature Calibration",
        icon="mdi:thermometer-lines",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_min_value=-4.0,
        native_max_value=4.0,
        native_step=0.5,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda data: float(data.get("temp_correction", 0.0)),
        set_fn=lambda coordinator, value: coordinator.async_set_temperature_correction(value),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Tesy Convector numbers."""
    coordinator: TesyDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        TesyConvectorNumber(coordinator, entry, description)
        for description in NUMBER_DESCRIPTIONS
    ]
    async_add_entities(entities)


class TesyConvectorNumber(CoordinatorEntity[TesyDataUpdateCoordinator], NumberEntity):
    """Representation of a Tesy Convector number entity."""

    entity_description: TesyNumberEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TesyDataUpdateCoordinator,
        entry: ConfigEntry,
        description: TesyNumberEntityDescription,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

        device_name = coordinator.data.get("name") or coordinator.device_name
        model_name = coordinator.data.get("model", "Convector Heater")
        sw_version = str(coordinator.data.get("sw_version", "1.0"))

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=device_name,
            manufacturer="Tesy",
            model=model_name,
            sw_version=sw_version,
            configuration_url=f"http://{coordinator.device_id}" if not coordinator.is_cloud else "https://mytesy.com",
        )

    @property
    def native_value(self) -> float | None:
        """Return the entity value."""
        if not self.coordinator.data:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    async def async_set_native_value(self, value: float) -> None:
        """Set new value."""
        await self.entity_description.set_fn(self.coordinator, value)
