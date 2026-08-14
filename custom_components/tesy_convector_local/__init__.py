"""The Tesy Convector integration (Cloud & Local)."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    AUTH_TYPE_CLOUD,
    CONF_AUTH_TYPE,
    CONF_IP_ADDRESS,
    CONF_PASSWORD,
    CONF_USER_ID,
    CONF_USERNAME,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import TesyDataUpdateCoordinator
from .tesy_cloud import TesyCloudClient
from .tesy_convector import TesyConvector

_LOGGER = logging.getLogger(__name__)

SERVICE_SET_TEMPERATURE_CORRECTION = "set_temperature_correction"
ATTR_CORRECTION = "correction"

SERVICE_CORRECTION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CORRECTION): vol.Coerce(float),
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Tesy Convector component services."""
    async def async_handle_set_correction(call: ServiceCall) -> None:
        """Handle temperature correction service call."""
        correction = call.data[ATTR_CORRECTION]
        coordinators: dict[str, TesyDataUpdateCoordinator] = hass.data.get(DOMAIN, {})
        for coordinator in coordinators.values():
            if isinstance(coordinator, TesyDataUpdateCoordinator):
                await coordinator.async_set_temperature_correction(correction)

    if not hass.services.has_service(DOMAIN, SERVICE_SET_TEMPERATURE_CORRECTION):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_TEMPERATURE_CORRECTION,
            async_handle_set_correction,
            schema=SERVICE_CORRECTION_SCHEMA,
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Tesy Convector from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    session = async_get_clientsession(hass)
    auth_type = entry.data.get(CONF_AUTH_TYPE, AUTH_TYPE_CLOUD if CONF_USERNAME in entry.data else "local")

    if auth_type == AUTH_TYPE_CLOUD or CONF_USERNAME in entry.data:
        username = entry.data[CONF_USERNAME]
        password = entry.data[CONF_PASSWORD]
        userid = entry.data.get(CONF_USER_ID)
        cloud_api = TesyCloudClient(username, password, userid=userid, session=session)
        coordinator = TesyDataUpdateCoordinator(hass, entry, cloud_api=cloud_api)
    else:
        ip_address = entry.data.get(CONF_IP_ADDRESS, "")
        local_api = TesyConvector(ip_address, session=session)
        coordinator = TesyDataUpdateCoordinator(hass, entry, local_api=local_api)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.warning("Could not reach Tesy device during setup: %s", err)
        raise ConfigEntryNotReady(f"Could not initialize Tesy device: {err}") from err

    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Set up all platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Listen for options changes
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: TesyDataUpdateCoordinator = hass.data[DOMAIN].pop(entry.entry_id, None)
        if coordinator:
            if coordinator.local_api:
                await coordinator.local_api.async_close()
            if coordinator.cloud_api:
                await coordinator.cloud_api.async_close()

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry after options change."""
    await hass.config_entries.async_reload(entry.entry_id)