"""Options-flow tests — menu routing, general settings, advanced mode.

HA-gated; skipped when homeassistant isn't installed.

xfail note: like test_config_flow.py, these need the HA integration
loader to resolve the `tapelectric` domain under `custom_components/`.
Written against the correct intended flow; will pass once loader
plumbing is in place.
"""
# TODO v1.2.0: fix HA integration loader plumbing so these tests
# actually pass. Currently all 7 tests in this module xfail because
# the test environment can't locate custom_components/tapelectric/.
# See: pytest-homeassistant-custom-component custom integration
# discovery patterns (mock_integration / enable_custom_integrations).
from __future__ import annotations

import pytest

pytestmark = [
    pytest.mark.requires_ha,
    pytest.mark.xfail(
        reason="HA integration loader can't find tapelectric under custom_components/ — separate follow-up",
        strict=False,
    ),
]


async def test_options_menu_entry_point(hass):
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from tapelectric.const import DOMAIN

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"api_key": "sk_ok", "advanced_mode": False},
        version=2,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "menu"
    assert result["step_id"] == "init"


async def test_options_general_updates_options(hass):
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from tapelectric.const import DOMAIN

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"api_key": "sk_ok", "advanced_mode": False},
        version=2,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "general"},
    )
    assert result["type"] == "form"
    assert result["step_id"] == "general"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "scan_interval_active_s": 45,
            "scan_interval_idle_s": 300,
            "sessions_history_limit": 50,
            "meter_data_limit": 100,
            "stale_threshold_minutes": 15,
            "round_energy_decimals": 3,
            "round_power_decimals": 2,
            "write_enabled": True,
        },
    )
    assert result["type"] == "create_entry"


async def test_options_advanced_disable(hass):
    """Flipping advanced_mode off clears the refresh token."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from tapelectric.const import DOMAIN

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "api_key": "sk_ok",
            "advanced_mode": True,
            "advanced_email": "e@x.com",
            "advanced_refresh_token": "rt",
        },
        version=2,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "advanced_menu"},
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "advanced_disable"},
    )
    assert entry.data.get("advanced_mode") is False
    assert entry.data.get("advanced_refresh_token") in (None, "")


# ── advanced_remote (remote start/stop) step ─────────────────────────────
#
# The step builds its form dynamically from the running coordinator's
# charger list. These tests stash a minimal coordinator stub in
# hass.data[DOMAIN][entry_id]["coordinator"] so the form renders with
# realistic per-charger outlet_id fields without standing up the full
# integration.

def _install_fake_coordinator(hass, entry_id, chargers):
    from types import SimpleNamespace

    from tapelectric.const import DOMAIN

    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        "coordinator": SimpleNamespace(
            data=SimpleNamespace(chargers=list(chargers)),
        ),
    }


async def _open_remote_form(hass, entry):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "advanced_menu"},
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "advanced_remote"},
    )
    return result


async def test_remote_settings_form_prefills_existing_values(hass):
    """Form must surface stored id_tag, profile_id, and outlet IDs."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from tapelectric.const import (
        CONF_ADVANCED_PROFILE_ID,
        CONF_DEFAULT_ID_TAG,
        DATA_DEFAULT_OUTLET_IDS,
        DOMAIN,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "api_key": "sk_ok",
            "advanced_mode": True,
            CONF_DEFAULT_ID_TAG: "TAP-123456-7",
            CONF_ADVANCED_PROFILE_ID: "usr_existing",
            DATA_DEFAULT_OUTLET_IDS: {"EVB-P22208163": "ou_" + "a" * 32},
        },
        version=2,
    )
    entry.add_to_hass(hass)
    _install_fake_coordinator(
        hass, entry.entry_id,
        [{"id": "EVB-P22208163", "name": "Garage"}],
    )

    result = await _open_remote_form(hass, entry)
    assert result["type"] == "form"
    assert result["step_id"] == "advanced_remote"

    schema = result["data_schema"].schema
    defaults = {
        getattr(key, "schema", key): key.default()
        for key in schema
        if hasattr(key, "default")
    }
    assert defaults.get(CONF_DEFAULT_ID_TAG) == "TAP-123456-7"
    assert defaults.get(CONF_ADVANCED_PROFILE_ID) == "usr_existing"
    outlet_label = "Outlet ID for Garage (EVB-P22208163)"
    assert defaults.get(outlet_label) == "ou_" + "a" * 32


async def test_remote_settings_no_chargers_renders_two_fields(hass):
    """Without a coordinator the form still renders id_tag + profile_id."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from tapelectric.const import (
        CONF_ADVANCED_PROFILE_ID,
        CONF_DEFAULT_ID_TAG,
        DOMAIN,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"api_key": "sk_ok", "advanced_mode": True},
        version=2,
    )
    entry.add_to_hass(hass)
    # Deliberately no fake coordinator — simulates a freshly-installed
    # entry whose first refresh hasn't populated data yet.

    result = await _open_remote_form(hass, entry)
    assert result["type"] == "form"
    keys = {
        getattr(key, "schema", key) for key in result["data_schema"].schema
    }
    assert CONF_DEFAULT_ID_TAG in keys
    assert CONF_ADVANCED_PROFILE_ID in keys
    # No outlet fields when the coordinator can't tell us which chargers exist.
    assert not any(
        isinstance(k, str) and k.startswith("Outlet ID for ") for k in keys
    )


async def test_remote_settings_multi_charger_renders_one_field_each(hass):
    """One outlet_id field per known charger."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from tapelectric.const import DOMAIN

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"api_key": "sk_ok", "advanced_mode": True},
        version=2,
    )
    entry.add_to_hass(hass)
    _install_fake_coordinator(
        hass, entry.entry_id,
        [
            {"id": "EVB-P22208163", "name": "Garage"},
            {"id": "EVB-P22208164", "name": "Driveway"},
        ],
    )

    result = await _open_remote_form(hass, entry)
    keys = {
        getattr(key, "schema", key) for key in result["data_schema"].schema
    }
    assert "Outlet ID for Garage (EVB-P22208163)" in keys
    assert "Outlet ID for Driveway (EVB-P22208164)" in keys


async def test_remote_settings_save_persists_to_entry_data(hass):
    """Submitting the form writes id_tag, profile_id, and per-charger
    outlet IDs into entry.data."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from tapelectric.const import (
        CONF_ADVANCED_PROFILE_ID,
        CONF_DEFAULT_ID_TAG,
        DATA_DEFAULT_OUTLET_IDS,
        DOMAIN,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"api_key": "sk_ok", "advanced_mode": True},
        version=2,
    )
    entry.add_to_hass(hass)
    _install_fake_coordinator(
        hass, entry.entry_id,
        [{"id": "EVB-P22208163", "name": "Garage"}],
    )

    result = await _open_remote_form(hass, entry)
    outlet_label = "Outlet ID for Garage (EVB-P22208163)"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_DEFAULT_ID_TAG: "TAP-555555-5",
            outlet_label: "ou_" + "b" * 32,
            CONF_ADVANCED_PROFILE_ID: "",
        },
    )
    assert result["type"] == "create_entry"
    assert entry.data.get(CONF_DEFAULT_ID_TAG) == "TAP-555555-5"
    assert entry.data.get(DATA_DEFAULT_OUTLET_IDS) == {
        "EVB-P22208163": "ou_" + "b" * 32,
    }
    assert entry.data.get(CONF_ADVANCED_PROFILE_ID) in (None, "")
