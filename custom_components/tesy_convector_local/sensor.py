"""Sensor platform for Tesy Convector."""
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_NAME, DOMAIN
from .coordinator import TesyDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class TesySensorEntityDescription(SensorEntityDescription):
    """Class describing Tesy sensor entities."""

    value_fn: Callable[[dict[str, Any]], Any]


SENSOR_DESCRIPTIONS: tuple[TesySensorEntityDescription, ...] = (
    TesySensorEntityDescription(
        key="mode",
        translation_key="mode",
        name="Operating Mode",
        icon="mdi:tune",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.get("mode"),
    ),
    TesySensorEntityDescription(
        key="internal_temperature",
        translation_key="internal_temperature",
        name="Internal Temperature",
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.get("current_temp"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Tesy Convector sensors."""
    coordinator: TesyDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        TesyConvectorSensor(coordinator, entry, description)
        for description in SENSOR_DESCRIPTIONS
    ]
    async_add_entities(entities)


class TesyConvectorSensor(CoordinatorEntity[TesyDataUpdateCoordinator], SensorEntity):
    """Representation of a Tesy Convector sensor."""

    entity_description: TesySensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TesyDataUpdateCoordinator,
        entry: ConfigEntry,
        description: TesySensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"{DEFAULT_NAME} ({coordinator.ip_address})",
            manufacturer="Tesy",
            model=coordinator.data.get("model", "Convector Heater"),
            sw_version=str(coordinator.data.get("sw_version") or "Local API"),
            configuration_url=f"http://{coordinator.ip_address}",
        )

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
