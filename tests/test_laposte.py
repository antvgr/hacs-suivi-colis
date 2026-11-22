"""Estimated delivery day and slot from La Poste (Colissimo)."""

import copy
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from homeassistant.util import dt as dt_util

from custom_components.suivi_colis.laposte import (
    LAPOSTE_SOURCE,
    LAPOSTE_URL,
    is_laposte_package,
    parse_estimate,
)
from custom_components.suivi_colis.models import Package

from .test_push_and_carrier import _coordinator, _store

# Real answer of the suivi-unifie service (trimmed)
ANSWER = [
    {
        "lang": "fr_FR",
        "returnCode": 200,
        "shipment": {
            "idShip": "CC240206309DE",
            "product": "colissimo",
            "isFinal": False,
            "estimDate": "2026-11-23T01:00:00+01:00",
            "estimHourMax": "2026-11-22T12:30:00+01:00",
            "estimHourMin": "2026-11-22T08:30:00+01:00",
        },
    }
]


@pytest.fixture(autouse=True)
async def paris(hass):
    """Home Assistant in the Paris time zone, like the user's."""
    await hass.config.async_set_time_zone("Europe/Paris")


def _answer(**shipment):
    answer = copy.deepcopy(ANSWER)
    answer[0]["shipment"].update(shipment)
    return answer


def test_slot_on_another_day_gives_the_whole_estimated_day():
    """The 22/11 slot does not match the 23/11 estimate: whole day of the 23rd."""
    est = parse_estimate(ANSWER)
    assert est["from"].isoformat() == "2026-11-23T00:00:00+01:00"
    assert est["to"].isoformat() == "2026-11-23T23:59:59+01:00"


def test_slot_on_the_estimated_day_is_used():
    est = parse_estimate(_answer(
        estimHourMin="2026-11-23T08:30:00+01:00", estimHourMax="2026-11-23T12:30:00+01:00"
    ))
    assert est["from"].isoformat() == "2026-11-23T08:30:00+01:00"
    assert est["to"].isoformat() == "2026-11-23T12:30:00+01:00"


def test_no_estimate():
    assert parse_estimate(_answer(isFinal=True)) is None
    assert parse_estimate(_answer(estimDate=None)) is None
    assert parse_estimate([]) is None and parse_estimate({"error": "x"}) is None


def test_laposte_packages():
    assert is_laposte_package(Package("CC240206309DE", carrier="colissimo", carrier_code=7041))
    assert is_laposte_package(Package("6A12345678901", carrier="", carrier_code=6051))
    assert not is_laposte_package(Package("1ZWV49986892191508", carrier="ups"))


def _coord(hass, pkg):
    return _coordinator(hass, _store(pkg), MagicMock())


async def test_coordinator_uses_laposte_and_keeps_it_on_17track_updates(hass, aioclient_mock):
    pkg = Package("CC240206309DE", carrier="colissimo", status="in_transit",
                  estimated_delivery_from=datetime.fromisoformat("2026-11-23T01:00:00+01:00"),
                  estimated_delivery_source="Official")
    coord = _coord(hass, pkg)
    aioclient_mock.get(LAPOSTE_URL.format("CC240206309DE"), json=_answer(
        estimHourMin="2026-11-23T08:30:00+01:00", estimHourMax="2026-11-23T12:30:00+01:00"
    ))

    await coord._update_laposte_estimates()

    assert pkg.estimated_delivery_source == LAPOSTE_SOURCE
    assert pkg.estimated_delivery_to.isoformat() == "2026-11-23T12:30:00+01:00"

    # A 17track update (poll or webhook) does not replace the precise slot
    coord._apply_track_data(pkg, {
        "status": "in_transit", "info_text": "", "location": "", "events": [],
        "estimated_delivery_from": datetime.fromisoformat("2026-11-23T01:00:00+01:00"),
        "estimated_delivery_to": None, "estimated_delivery_source": "Official",
    }, datetime.now())
    assert pkg.estimated_delivery_source == LAPOSTE_SOURCE
    assert pkg.estimated_delivery_from.isoformat() == "2026-11-23T08:30:00+01:00"


async def test_coordinator_keeps_17track_when_laposte_fails(hass, aioclient_mock):
    pkg = Package("CC240206309DE", carrier="colissimo", status="in_transit",
                  estimated_delivery_from=dt_util.now(), estimated_delivery_source="Official")
    coord = _coord(hass, pkg)
    aioclient_mock.get(LAPOSTE_URL.format("CC240206309DE"), status=403)

    await coord._update_laposte_estimates()

    assert pkg.estimated_delivery_source == "Official"


async def test_coordinator_drops_laposte_estimate_when_gone(hass, aioclient_mock):
    pkg = Package("CC240206309DE", carrier="colissimo", status="in_transit",
                  estimated_delivery_from=dt_util.now(), estimated_delivery_source=LAPOSTE_SOURCE)
    coord = _coord(hass, pkg)
    aioclient_mock.get(LAPOSTE_URL.format("CC240206309DE"), json=_answer(isFinal=True))

    await coord._update_laposte_estimates()

    assert pkg.estimated_delivery_source == "" and pkg.estimated_delivery_from is None
