"""Config flow for the Backrest integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, CONF_VERIFY_SSL
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
import voluptuous as vol
from yarl import URL

from . import create_client
from .api import BackrestAuthenticationError, BackrestConfig, BackrestError
from .const import DOMAIN, LOGGER

_URL = TextSelector(TextSelectorConfig(type=TextSelectorType.URL))
_PASSWORD = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
_USERNAME = TextSelector(TextSelectorConfig(autocomplete="username"))


def _connection_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_URL, default=defaults.get(CONF_URL, vol.UNDEFINED)): _URL,
            vol.Optional(
                CONF_USERNAME, default=defaults.get(CONF_USERNAME, vol.UNDEFINED)
            ): _USERNAME,
            vol.Optional(CONF_PASSWORD): _PASSWORD,
            vol.Required(
                CONF_VERIFY_SSL, default=defaults.get(CONF_VERIFY_SSL, True)
            ): bool,
        }
    )


def _normalize_url(url: str) -> str:
    """Strip whitespace and trailing slashes; reject non-HTTP URLs."""
    parsed = URL(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.host:
        raise ValueError(url)
    return str(parsed).rstrip("/")


class BackrestConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Backrest."""

    VERSION = 1
    MINOR_VERSION = 1

    async def _async_validate(
        self, user_input: dict[str, Any]
    ) -> tuple[dict[str, Any], BackrestConfig | None, dict[str, str]]:
        """Test the connection; return cleaned data, the config and errors."""
        data = dict(user_input)
        try:
            data[CONF_URL] = _normalize_url(user_input[CONF_URL])
        except ValueError:
            return data, None, {CONF_URL: "invalid_url"}
        try:
            config = await create_client(self.hass, data).get_config()
        except BackrestAuthenticationError:
            return data, None, {"base": "invalid_auth"}
        except BackrestError as err:
            LOGGER.debug("Cannot connect to Backrest at %s: %s", data[CONF_URL], err)
            return data, None, {"base": "cannot_connect"}
        except Exception:
            LOGGER.exception("Unexpected error while connecting to Backrest")
            return data, None, {"base": "unknown"}
        if not config.instance:
            return data, None, {"base": "no_instance"}
        return data, config, {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the URL and credentials of a Backrest instance."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data, config, errors = await self._async_validate(user_input)
            if config is not None:
                await self.async_set_unique_id(config.instance)
                self._abort_if_unique_id_configured(updates={CONF_URL: data[CONF_URL]})
                return self.async_create_entry(
                    title=f"Backrest {config.instance}", data=data
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                _connection_schema({}), user_input
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauthentication after Backrest rejected the credentials."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for new credentials."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data, config, errors = await self._async_validate(
                {**entry.data, **user_input}
            )
            if config is not None:
                await self.async_set_unique_id(config.instance)
                self._abort_if_unique_id_mismatch(reason="wrong_instance")
                return self.async_update_reload_and_abort(entry, data=data)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_USERNAME,
                        default=entry.data.get(CONF_USERNAME, vol.UNDEFINED),
                    ): _USERNAME,
                    vol.Optional(CONF_PASSWORD): _PASSWORD,
                }
            ),
            description_placeholders={"instance": entry.title},
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the URL, credentials or TLS check of an existing entry."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            merged = {**user_input}
            if not merged.get(CONF_PASSWORD) and entry.data.get(CONF_PASSWORD):
                merged[CONF_PASSWORD] = entry.data[CONF_PASSWORD]
            data, config, errors = await self._async_validate(merged)
            if config is not None:
                await self.async_set_unique_id(config.instance)
                self._abort_if_unique_id_mismatch(reason="wrong_instance")
                return self.async_update_reload_and_abort(entry, data=data)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_connection_schema(user_input or entry.data),
            errors=errors,
        )
