"""Tests for the Backrest config flow."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.backrest.api import (
    BackrestAuthenticationError,
    BackrestConfig,
    BackrestConnectionError,
)
from custom_components.backrest.const import DOMAIN

from .conftest import ENTRY_DATA

USER_INPUT = {
    CONF_URL: " http://10.0.3.50:9898/ ",
    CONF_USERNAME: "ha",
    CONF_PASSWORD: "hunter2",
    CONF_VERIFY_SSL: True,
}


@pytest.fixture(autouse=True)
def no_setup() -> object:
    """Do not set up the integration after the flow finishes."""
    with patch("custom_components.backrest.async_setup_entry", return_value=True) as m:
        yield m


async def test_user_flow(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """A valid instance creates an entry named after the instance."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Backrest dockervm"
    assert result["result"].unique_id == "dockervm"
    assert result["data"] == ENTRY_DATA


@pytest.mark.parametrize(
    ("side_effect", "error"),
    [
        (BackrestConnectionError("down"), {"base": "cannot_connect"}),
        (BackrestAuthenticationError("nope"), {"base": "invalid_auth"}),
        (RuntimeError("boom"), {"base": "unknown"}),
    ],
)
async def test_user_flow_errors(
    hass: HomeAssistant,
    mock_client: MagicMock,
    side_effect: Exception,
    error: dict[str, str],
) -> None:
    """Errors are shown and the flow recovers once Backrest answers."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    config = mock_client.get_config.return_value
    mock_client.get_config.side_effect = side_effect
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == error

    mock_client.get_config.side_effect = None
    mock_client.get_config.return_value = config
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_invalid_url(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """A URL without http(s) is refused before connecting."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_URL: "backrest.local"}
    )
    assert result["errors"] == {CONF_URL: "invalid_url"}
    mock_client.get_config.assert_not_called()


async def test_user_flow_no_instance(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """A Backrest that was never set up has no instance name."""
    mock_client.get_config.return_value = BackrestConfig("", (), ())
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["errors"] == {"base": "no_instance"}


async def test_user_flow_already_configured(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """The same instance cannot be added twice."""
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_URL: "http://10.0.3.51:9898"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert mock_config_entry.data[CONF_URL] == "http://10.0.3.51:9898"


async def test_reauth(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """New credentials are stored after a successful reauth."""
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    mock_client.get_config.side_effect = BackrestAuthenticationError("nope")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: "ha", CONF_PASSWORD: "wrong"}
    )
    assert result["errors"] == {"base": "invalid_auth"}

    mock_client.get_config.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: "ha", CONF_PASSWORD: "new"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_PASSWORD] == "new"


async def test_reconfigure_keeps_password(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Reconfigure changes the URL and keeps the password when left empty."""
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_URL: "https://backrest.example",
            CONF_USERNAME: "ha",
            CONF_VERIFY_SSL: False,
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data[CONF_URL] == "https://backrest.example"
    assert mock_config_entry.data[CONF_PASSWORD] == "hunter2"
    assert mock_config_entry.data[CONF_VERIFY_SSL] is False


async def test_reconfigure_wrong_instance(
    hass: HomeAssistant, mock_client: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Pointing an entry at another instance is refused."""
    mock_config_entry.add_to_hass(hass)
    mock_client.get_config.return_value = BackrestConfig("elektra", (), ())
    result = await mock_config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_URL: "http://10.0.3.20:9898"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_instance"
    assert mock_config_entry.data[CONF_URL] == "http://10.0.3.50:9898"
