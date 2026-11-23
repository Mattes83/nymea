"""Test unique ID migration on setup."""

from unittest.mock import MagicMock

from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nymea import _migrate_unique_id
from custom_components.nymea.const import DOMAIN, normalize_uuid

BOX_UUID = "5dec6ce8-59e8-49d1-9345-6715e1301195"


def _hub(server_uuid: str | None) -> MagicMock:
    hub = MagicMock()
    hub.server_uuid = server_uuid
    return hub


def test_normalize_uuid() -> None:
    """Braces and case are removed; empty values give None."""
    assert normalize_uuid("{5DEC6CE8-59e8-49d1-9345-6715e1301195}") == BOX_UUID
    assert normalize_uuid(BOX_UUID) == BOX_UUID
    assert normalize_uuid("") is None
    assert normalize_uuid(None) is None
    assert normalize_uuid("{}") is None


async def test_migrates_hostname_unique_id(hass: HomeAssistant) -> None:
    """A hostname-based unique ID is replaced by the server uuid."""
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_HOST: "192.168.2.179"}, unique_id="maveo-box-2"
    )
    entry.add_to_hass(hass)

    _migrate_unique_id(hass, entry, _hub("{5dec6ce8-59e8-49d1-9345-6715e1301195}"))

    assert entry.unique_id == BOX_UUID


async def test_no_migration_without_uuid(hass: HomeAssistant) -> None:
    """Without a uuid from the box the unique ID stays as it is."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, unique_id="maveo-box-2")
    entry.add_to_hass(hass)

    _migrate_unique_id(hass, entry, _hub(None))

    assert entry.unique_id == "maveo-box-2"


async def test_no_migration_on_collision(hass: HomeAssistant) -> None:
    """Never give two entries the same unique ID."""
    other = MockConfigEntry(domain=DOMAIN, data={}, unique_id=BOX_UUID)
    other.add_to_hass(hass)
    entry = MockConfigEntry(domain=DOMAIN, data={}, unique_id="maveo-box-2")
    entry.add_to_hass(hass)

    _migrate_unique_id(hass, entry, _hub(BOX_UUID))

    assert entry.unique_id == "maveo-box-2"
    assert other.unique_id == BOX_UUID
