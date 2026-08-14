"""Config flow and Options flow for Tesy Convector Local integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_IP_ADDRESS,
    CONF_TEMPERATURE_ENTITY,
    CONF_UPDATE_INTERVAL,
    DEFAULT_NAME,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MAX_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
)
from .tesy_convector import TesyConvector, TesyConnectionError, TesyInvalidResponseError

_LOGGER = logging.getLogger(__name__)


def build_user_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Build the configuration schema for user step."""
    if defaults is None:
        defaults = {}

    return vol.Schema(
        {
            vol.Required(
                CONF_IP_ADDRESS,
                default=defaults.get(CONF_IP_ADDRESS, ""),
            ): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT)),
            vol.Optional(
                CONF_TEMPERATURE_ENTITY,
                description={"suggested_value": defaults.get(CONF_TEMPERATURE_ENTITY)},
            ): EntitySelector(
                EntitySelectorConfig(domain="sensor")
            ),
        }
    )


class TesyConvectorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Tesy Convector."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            ip_address = user_input[CONF_IP_ADDRESS].strip()

            await self.async_set_unique_id(ip_address)
            self._abort_if_unique_id_configured()

            # Test connection to the device
            session = async_get_clientsession(self.hass)
            client = TesyConvector(ip_address, session=session)

            try:
                data = await client.async_get_status()
                _LOGGER.debug("Successfully connected during setup: %s", data)
            except TesyConnectionError:
                errors["base"] = "cannot_connect"
            except TesyInvalidResponseError:
                errors["base"] = "invalid_response"
            except Exception as err:
                _LOGGER.exception("Unexpected error testing Tesy connection: %s", err)
                errors["base"] = "unknown"
            else:
                user_input[CONF_IP_ADDRESS] = ip_address
                return self.async_create_entry(
                    title=f"{DEFAULT_NAME} ({ip_address})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=build_user_schema(user_input),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return TesyConvectorOptionsFlowHandler(config_entry)


class TesyConvectorOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Tesy Convector."""

    def __init__(self, config_entry: config_entries.ConfigEntry | None = None) -> None:
        """Initialize options flow."""
        if config_entry is not None:
            self._config_entry = config_entry

    @property
    def config_entry(self) -> config_entries.ConfigEntry:
        """Return the config entry."""
        if hasattr(self, "_config_entry"):
            return self._config_entry
        return super().config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage integration options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_ext_temp = self.config_entry.options.get(
            CONF_TEMPERATURE_ENTITY,
            self.config_entry.data.get(CONF_TEMPERATURE_ENTITY),
        )
        current_update_interval = self.config_entry.options.get(
            CONF_UPDATE_INTERVAL,
            self.config_entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        )

        options_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_TEMPERATURE_ENTITY,
                    description={"suggested_value": current_ext_temp},
                ): EntitySelector(
                    EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(
                    CONF_UPDATE_INTERVAL,
                    default=current_update_interval,
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_UPDATE_INTERVAL,
                        max=MAX_UPDATE_INTERVAL,
                        step=1,
                        unit_of_measurement="s",
                        mode=NumberSelectorMode.SLIDER,
                    )
                ),
            }
        )

        return self.async_show_form(step_id="init", data_schema=options_schema)