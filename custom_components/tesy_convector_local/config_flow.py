"""Config flow and Options flow for Tesy Convector (Cloud & Local)."""
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
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    AUTH_TYPE_CLOUD,
    AUTH_TYPE_LOCAL,
    CONF_AUTH_TYPE,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_IP_ADDRESS,
    CONF_PASSWORD,
    CONF_TEMPERATURE_ENTITY,
    CONF_UPDATE_INTERVAL,
    CONF_USER_ID,
    CONF_USERNAME,
    DEFAULT_NAME,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MAX_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
)
from .tesy_cloud import (
    TesyCloudAuthError,
    TesyCloudClient,
    TesyCloudConnectionError,
    TesyCloudError,
)
from .tesy_convector import TesyConnectionError, TesyConvector, TesyInvalidResponseError

_LOGGER = logging.getLogger(__name__)


class TesyConvectorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Tesy Convector."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize config flow."""
        self._cloud_credentials: dict[str, Any] = {}
        self._discovered_devices: dict[str, dict[str, Any]] = {}
        self._cloud_client: TesyCloudClient | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial choice step (Cloud or Local)."""
        if user_input is not None:
            auth_type = user_input.get(CONF_AUTH_TYPE, AUTH_TYPE_CLOUD)
            if auth_type == AUTH_TYPE_CLOUD:
                return await self.async_step_cloud()
            return await self.async_step_local()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_AUTH_TYPE, default=AUTH_TYPE_CLOUD): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                {"value": AUTH_TYPE_CLOUD, "label": "MyTESY Cloud (mytesy.com)"},
                                {"value": AUTH_TYPE_LOCAL, "label": "Local Network (IP Address)"},
                            ],
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
        )

    async def async_step_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle MyTESY Cloud login step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD]
            userid = user_input.get(CONF_USER_ID)
            if userid:
                userid = str(userid).strip()

            session = async_get_clientsession(self.hass)
            client = TesyCloudClient(username, password, userid=userid, session=session)

            try:
                await client.async_login()
                devices = await client.async_get_devices()
            except TesyCloudAuthError:
                errors["base"] = "invalid_auth"
            except TesyCloudConnectionError:
                errors["base"] = "cannot_connect"
            except Exception as err:
                _LOGGER.exception("Unexpected error logging in to MyTESY Cloud: %s", err)
                errors["base"] = "unknown"
            else:
                if not devices:
                    errors["base"] = "no_devices"
                else:
                    self._cloud_credentials = {
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                        CONF_USER_ID: client.userid,
                        CONF_TEMPERATURE_ENTITY: user_input.get(CONF_TEMPERATURE_ENTITY),
                    }
                    self._discovered_devices = devices
                    self._cloud_client = client

                    # If only one device on account, create directly
                    if len(devices) == 1:
                        device_id = next(iter(devices))
                        dev_info = devices[device_id]
                        return await self._create_cloud_entry(device_id, dev_info)

                    # Otherwise, go to device selection step
                    return await self.async_step_select_device()

        return self.async_show_form(
            step_id="cloud",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.EMAIL)
                    ),
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                    vol.Optional(CONF_USER_ID): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.TEXT)
                    ),
                    vol.Optional(CONF_TEMPERATURE_ENTITY): EntitySelector(
                        EntitySelectorConfig(domain="sensor")
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_select_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle selecting one device from multiple discovered devices."""
        errors: dict[str, str] = {}

        if user_input is not None:
            device_id = user_input[CONF_DEVICE_ID]
            dev_info = self._discovered_devices.get(device_id, {})
            return await self._create_cloud_entry(device_id, dev_info)

        options = [
            {
                "value": dev_id,
                "label": f"{info.get('name')} ({info.get('model', 'Heater')}) - ID: {dev_id}",
            }
            for dev_id, info in self._discovered_devices.items()
        ]

        return self.async_show_form(
            step_id="select_device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_ID): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def _create_cloud_entry(
        self, device_id: str, dev_info: dict[str, Any]
    ) -> FlowResult:
        """Create a config entry for a cloud device."""
        await self.async_set_unique_id(f"tesy_cloud_{device_id}")
        self._abort_if_unique_id_configured()

        dev_name = dev_info.get("name") or f"Tesy {device_id}"

        entry_data = {
            CONF_AUTH_TYPE: AUTH_TYPE_CLOUD,
            CONF_USERNAME: self._cloud_credentials[CONF_USERNAME],
            CONF_PASSWORD: self._cloud_credentials[CONF_PASSWORD],
            CONF_USER_ID: self._cloud_credentials.get(CONF_USER_ID),
            CONF_DEVICE_ID: str(device_id),
            CONF_DEVICE_NAME: dev_name,
            CONF_TEMPERATURE_ENTITY: self._cloud_credentials.get(CONF_TEMPERATURE_ENTITY),
        }

        return self.async_create_entry(
            title=f"{dev_name} (MyTESY)",
            data=entry_data,
        )

    async def async_step_local(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle local direct IP connection step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            ip_address = user_input[CONF_IP_ADDRESS].strip()

            await self.async_set_unique_id(f"tesy_local_{ip_address}")
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            client = TesyConvector(ip_address, session=session)

            try:
                await client.async_get_status()
            except TesyConnectionError:
                errors["base"] = "cannot_connect"
            except TesyInvalidResponseError:
                errors["base"] = "invalid_response"
            except Exception as err:
                _LOGGER.exception("Unexpected error testing local Tesy connection: %s", err)
                errors["base"] = "unknown"
            else:
                entry_data = {
                    CONF_AUTH_TYPE: AUTH_TYPE_LOCAL,
                    CONF_IP_ADDRESS: ip_address,
                    CONF_DEVICE_NAME: f"{DEFAULT_NAME} ({ip_address})",
                    CONF_TEMPERATURE_ENTITY: user_input.get(CONF_TEMPERATURE_ENTITY),
                }
                return self.async_create_entry(
                    title=f"{DEFAULT_NAME} ({ip_address})",
                    data=entry_data,
                )

        return self.async_show_form(
            step_id="local",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_IP_ADDRESS): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.TEXT)
                    ),
                    vol.Optional(CONF_TEMPERATURE_ENTITY): EntitySelector(
                        EntitySelectorConfig(domain="sensor")
                    ),
                }
            ),
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