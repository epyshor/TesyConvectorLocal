"""Switch platform for Tesy Convector."""
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Callable, Coroutine

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_NAME, DOMAIN
from .coordinator import TesyDataUpdateCoordinator
from .tesy_convector import TesyConvector

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class TesySwitchEntityDescription(SwitchEntityDescription):
    """Class describing Tesy switch entities."""

    is_on_fn: Callable[[dict[str, Any]], bool]
    set_fn: Callable[[TesyConvector, bool], Coroutine[Any, Any, Any]]


SWITCH_DESCRIPTIONS: tuple[TesySwitchEntityDescription, ...] = (
    TesySwitchEntityDescription(
        key="lock_device",
        translation_key="lock_device",
        name="Child Lock",
        icon="mdi:lock",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda data: bool(data.get("lock_device")),
        set_fn=lambda api, enabled: api.async_set_lock_device(enabled),
    ),
    TesySwitchEntityDescription(
        key="anti_frost",
        translation_key="anti_frost",
        name="Anti-Frost Protection",
        icon="mdi:snowflake-alert",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda data: bool(data.get("anti_frost")),
        set_fn=lambda api, enabled: api.async_set_anti_frost(enabled),
    ),
    TesySwitchEntityDescription(
        key="adaptive_start",
        translation_key="adaptive_start",
        name="Adaptive Start",
        icon="mdi:timer-sand",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda data: bool(data.get("adaptive_start")),
        set_fn=lambda api, enabled: api.async_set_adaptive_start(enabled),
    ),
    TesySwitchEntityDescription(
        key="opened_window",
        translation_key="opened_window",
        name="Open Window Detection",
        icon="mdi:window-open-variant",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda data: bool(data.get("opened_window")),
        set_fn=lambda api, enabled: api.async_set_opened_window(enabled),
    ),
    TesySwitchEntityDescription(
        key="uv",
        translation_key="uv",
        name="Air Care UV",
        icon="mdi:weather-sunny-alert",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda data: bool(data.get("uv")),
        set_fn=lambda api, enabled: api.async_set_uv(enabled),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Tesy Convector switches."""
    coordinator: TesyDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        TesyConvectorSwitch(coordinator, entry, description)
        for description in SWITCH_DESCRIPTIONS
    ]
    async_add_entities(entities)


class TesyConvectorSwitch(CoordinatorEntity[TesyDataUpdateCoordinator], SwitchEntity):
    """Representation of a Tesy Convector switch."""

    entity_description: TesySwitchEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TesyDataUpdateCoordinator,
        entry: ConfigEntry,
        description: TesySwitchEntityDescription,
    ) -> None:
        """Initialize the switch."""
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
    def is_on(self) -> bool:
        """Return True if entity is on."""
        if not self.coordinator.data:
            return False
        return self.entity_description.is_on_fn(self.coordinator.data)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch."""
        await self.entity_description.set_fn(self.coordinator.api, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        await self.entity_description.set_fn(self.coordinator.api, False)
        await self.coordinator.async_request_refresh()
