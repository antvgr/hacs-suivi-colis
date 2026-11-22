"""Deliveries calendar."""

from datetime import date, datetime

import pytest

from custom_components.suivi_colis.calendar import delivery_event
from custom_components.suivi_colis.models import Package


@pytest.fixture(autouse=True)
async def paris(hass):
    await hass.config.async_set_time_zone("Europe/Paris")


def _pkg(est_from=None, est_to=None, status="in_transit", **kw):
    return Package(
        "CC240206309DE", friendly_name="Chaussures", carrier="colissimo", status=status,
        estimated_delivery_from=datetime.fromisoformat(est_from) if est_from else None,
        estimated_delivery_to=datetime.fromisoformat(est_to) if est_to else None, **kw,
    )


async def test_17track_date_only_is_an_all_day_event(hass):
    """17track gives a UTC midnight: the 23rd, all day (winter and summer)."""
    for value in ("2026-11-23T01:00:00+01:00", "2026-06-23T02:00:00+02:00"):
        event = delivery_event(_pkg(value))
        assert event.start == date.fromisoformat(value[:10])
        assert (event.end - event.start).days == 1
        assert event.summary == "Livraison : Chaussures"
        assert "CC240206309DE" in event.description


async def test_whole_day_range_is_an_all_day_event(hass):
    event = delivery_event(_pkg("2026-11-23T00:00:00+01:00", "2026-11-23T23:59:59+01:00"))
    assert (event.start, event.end) == (date(2026, 11, 23), date(2026, 11, 24))


async def test_multi_day_range(hass):
    event = delivery_event(_pkg("2026-11-23T00:00:00+00:00", "2026-11-25T00:00:00+00:00"))
    assert (event.start, event.end) == (date(2026, 11, 23), date(2026, 11, 26))


async def test_time_slot_is_a_timed_event(hass):
    event = delivery_event(_pkg("2026-11-23T08:30:00+01:00", "2026-11-23T12:30:00+01:00",
                                estimated_delivery_source="La Poste"))
    assert event.start.isoformat() == "2026-11-23T08:30:00+01:00"
    assert event.end.isoformat() == "2026-11-23T12:30:00+01:00"
    assert "La Poste" in event.description


async def test_no_event(hass):
    assert delivery_event(_pkg()) is None
    assert delivery_event(_pkg("2026-11-23T08:30:00+01:00", status="delivered")) is None
    assert delivery_event(_pkg("2026-11-23T08:30:00+01:00", archived=True)) is None
