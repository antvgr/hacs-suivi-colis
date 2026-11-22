"""Estimated delivery day and slot from La Poste (Colissimo)."""

import copy
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from custom_components.suivi_colis.laposte import (
    LAPOSTE_PAGE_URL,
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


def _track(status="in_transit", est_from=None, est_to=None, source=""):
    """Parsed 17track data, as _apply_track_data receives it."""
    return {
        "status": status, "info_text": "", "location": "", "events": [],
        "estimated_delivery_from": est_from, "estimated_delivery_to": est_to,
        "estimated_delivery_source": source,
    }


DAY_23 = datetime.fromisoformat("2026-11-23T01:00:00+01:00")
DAY_24 = datetime.fromisoformat("2026-11-24T01:00:00+01:00")
SLOT_23 = {"estimHourMin": "2026-11-23T08:30:00+01:00", "estimHourMax": "2026-11-23T12:30:00+01:00"}
URL = LAPOSTE_URL.format("CC240206309DE")
PAGE = LAPOSTE_PAGE_URL.format("CC240206309DE")


def _mock_laposte(aioclient_mock, **kwargs):
    """The tracking page, then the service."""
    aioclient_mock.get(PAGE, text="<html></html>")
    aioclient_mock.get(URL, **kwargs)


def _service_calls(aioclient_mock):
    return [c for c in aioclient_mock.mock_calls if "suivi-unifie" in str(c[1])]


async def test_laposte_not_asked_without_announcement(hass, aioclient_mock):
    """No estimate and not out for delivery: La Poste is not polled."""
    pkg = Package("CC240206309DE", carrier="colissimo", status="in_transit")
    coord = _coord(hass, pkg)
    _mock_laposte(aioclient_mock, json=_answer(**SLOT_23))

    coord._apply_track_data(pkg, _track(), datetime.now())
    await coord._update_laposte_estimates()

    assert len(_service_calls(aioclient_mock)) == 0


async def test_laposte_asked_once_per_17track_announcement(hass, aioclient_mock):
    pkg = Package("CC240206309DE", carrier="colissimo", status="in_transit")
    coord = _coord(hass, pkg)
    _mock_laposte(aioclient_mock, json=_answer(**SLOT_23))

    # 17track announces the 23rd: La Poste gives the slot
    coord._apply_track_data(pkg, _track(est_from=DAY_23, source="Official"), datetime.now())
    await coord._update_laposte_estimates()
    assert len(_service_calls(aioclient_mock)) == 1
    assert pkg.estimated_delivery_source == LAPOSTE_SOURCE
    assert pkg.estimated_delivery_from.isoformat() == "2026-11-23T08:30:00+01:00"

    # Same 17track estimate again (poll or webhook): slot kept, La Poste not asked
    coord._apply_track_data(pkg, _track(est_from=DAY_23, source="Official"), datetime.now())
    await coord._update_laposte_estimates()
    assert len(_service_calls(aioclient_mock)) == 1
    assert pkg.estimated_delivery_source == LAPOSTE_SOURCE

    # 17track moves the delivery to the 24th: La Poste asked again
    aioclient_mock.clear_requests()
    _mock_laposte(aioclient_mock, status=503)
    coord._apply_track_data(pkg, _track(est_from=DAY_24, source="Official"), datetime.now())
    await coord._update_laposte_estimates()
    assert len(_service_calls(aioclient_mock)) == 1
    # La Poste failed: the new 17track date is kept, not the old slot
    assert pkg.estimated_delivery_source == "Official"
    assert pkg.estimated_delivery_from == DAY_24


async def test_laposte_asked_when_out_for_delivery(hass, aioclient_mock):
    pkg = Package("CC240206309DE", carrier="colissimo", status="in_transit")
    coord = _coord(hass, pkg)
    _mock_laposte(aioclient_mock, json=_answer(**SLOT_23))

    coord._apply_track_data(pkg, _track(status="out_for_delivery"), datetime.now())
    await coord._update_laposte_estimates()

    assert len(_service_calls(aioclient_mock)) == 1
    assert pkg.estimated_delivery_to.isoformat() == "2026-11-23T12:30:00+01:00"


async def test_other_carriers_never_ask_laposte(hass, aioclient_mock):
    pkg = Package("1ZWV49986892191508", carrier="ups", status="in_transit")
    coord = _coord(hass, pkg)

    coord._apply_track_data(pkg, _track(status="out_for_delivery", est_from=DAY_23), datetime.now())
    await coord._update_laposte_estimates()

    assert len(_service_calls(aioclient_mock)) == 0
    assert pkg.estimated_delivery_from == DAY_23


async def test_laposte_called_like_the_tracking_page(hass, aioclient_mock):
    """Tracking page first (session cookies), then the service with its Referer."""
    pkg = Package("CC240206309DE", carrier="colissimo", status="in_transit")
    coord = _coord(hass, pkg)
    _mock_laposte(aioclient_mock, json=_answer(**SLOT_23))

    coord._apply_track_data(pkg, _track(status="out_for_delivery"), datetime.now())
    await coord._update_laposte_estimates()

    (_, page_url, _, page_headers), (_, api_url, _, api_headers) = aioclient_mock.mock_calls
    assert str(page_url) == PAGE and "Mozilla" in page_headers["User-Agent"]
    assert str(api_url).endswith("/suivi-unifie/CC240206309DE?lang=fr")
    assert api_headers["Referer"] == PAGE
    assert api_headers["Accept"].startswith("application/json")
    assert pkg.estimated_delivery_source == LAPOSTE_SOURCE
