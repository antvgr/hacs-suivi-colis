"""Tests for the 17track v2.4 features: lang, sub-status, ETA, delivery time, quota."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.util import dt as dt_util

from custom_components.suivi_colis.api_17track import (
    Api17TrackClient,
    to_17track_lang,
)
from custom_components.suivi_colis.const import API_17TRACK_REGISTER
from custom_components.suivi_colis.coordinator import SuiviColisCoordinator
from custom_components.suivi_colis.models import Package
from custom_components.suivi_colis.sensor import SuiviColisQuotaSensor, SuiviColisSensor

# Shape taken from the v2.4 doc (gettrackinfo accepted[].track_info)
TRACK_INFO = {
    "latest_status": {"status": "Delivered", "sub_status": "Delivered_Other", "sub_status_descr": None},
    "latest_event": {
        "time_iso": "2026-11-10T14:32:00+01:00",
        "description": "Delivered",
        "description_translation": {"lang": "fr", "description": "Votre colis a été livré"},
        "location": "PARIS",
    },
    "time_metrics": {
        "estimated_delivery_date": {"source": "Official", "from": "2026-11-10T00:00:00+01:00", "to": "2026-11-11T00:00:00+01:00"}
    },
    "milestone": [{"key_stage": "Delivered", "time_iso": "2026-11-10T14:32:00+01:00"}],
    "misc_info": None,
    "tracking": {"providers": [{
        "provider": {"key": 6051, "name": "La Poste"},
        "events": [
            {"time_iso": "2026-11-10T14:32:00+01:00", "description": "Delivered", "sub_status": "Delivered_Other",
             "description_translation": {"lang": "fr", "description": "Votre colis a été livré"}},
            {"time_iso": "2026-11-10T08:01:00+01:00", "description": "Out for delivery", "sub_status": "OutForDelivery_Other",
             "description_translation": None},
        ],
    }]},
}


def test_api_base_is_v24():
    assert API_17TRACK_REGISTER == "https://api.17track.net/track/v2.4/register"


@pytest.mark.parametrize(
    "ha,expected",
    [("fr", "fr"), ("en-GB", "en"), ("pt-BR", "pt"), ("zh-Hant", "zh-hant"), ("zh-Hans", "zh-hans"),
     ("zh-TW", "zh-hant"), ("nb", "no"), ("ca", None), (None, None)],
)
def test_lang_mapping(ha, expected):
    assert to_17track_lang(ha) == expected


async def test_register_sends_lang():
    c = Api17TrackClient(None, "k", lang="fr")
    c._request = AsyncMock(return_value={"code": 0, "data": {"accepted": [{"number": "N"}], "rejected": []}})
    await c.register_package("6A12345678901", "colissimo")
    assert c._request.call_args.args[1] == [{"number": "6A12345678901", "carrier": 6051, "lang": "fr"}]


def test_parse_v24_fields():
    out = Api17TrackClient(None, "k")._parse_track_data(TRACK_INFO)
    assert out["status"] == "delivered"
    assert out["carrier"] == "colissimo"
    assert out["info_text"] == "Votre colis a été livré"  # translated text wins
    assert [e.description for e in out["events"]] == ["Votre colis a été livré", "Out for delivery"]
    assert out["sub_status"] == "Delivered_Other" and out["sub_status_descr"] == ""
    assert out["delivered_time"] == datetime(2026, 11, 10, 13, 32, tzinfo=UTC)
    assert out["estimated_delivery_from"].isoformat() == "2026-11-10T00:00:00+01:00"
    assert out["estimated_delivery_source"] == "Official"


def test_parse_minimal_payload():
    out = Api17TrackClient(None, "k")._parse_track_data({})
    assert out["status"] == "not_found"
    assert out["delivered_time"] is None and out["estimated_delivery_to"] is None


def test_milestone_fallback_for_delivery_time():
    info = {"latest_status": {"status": "Delivered"},
            "milestone": [{"key_stage": "Delivered", "time_utc": "2026-11-09T10:00:00Z"}]}
    out = Api17TrackClient(None, "k")._parse_track_data(info)
    assert out["delivered_time"] == datetime(2026, 11, 9, 10, tzinfo=UTC)


def test_package_roundtrip_new_fields():
    pkg = Package("N", sub_status="Exception_Delayed",
                  estimated_delivery_from=datetime(2026, 11, 12, tzinfo=UTC))
    back = Package.from_dict(pkg.to_dict())
    assert back.sub_status == "Exception_Delayed"
    assert back.estimated_delivery_from == pkg.estimated_delivery_from
    # data stored by the previous version still loads
    old = {"tracking_number": "N", "added_at": "2026-11-01T10:00:00"}
    assert Package.from_dict(old).estimated_delivery_to is None


def _coordinator(hass, store, api):
    from homeassistant.config_entries import current_entry
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    current_entry.set(MockConfigEntry(domain="suivi_colis"))
    with patch("homeassistant.helpers.frame.report_usage"):
        return SuiviColisCoordinator(hass, api, store, {"api_key": "k"}, {})


async def test_coordinator_uses_real_delivery_time_and_quota(hass):
    await hass.config.async_set_time_zone("Europe/Paris")
    pkg = Package("6A12345678901", status="out_for_delivery")
    store = MagicMock()
    store.active_packages = {pkg.tracking_number: pkg}
    store.packages = store.active_packages
    store.get_package = lambda n: store.active_packages.get(n)
    store.async_save = AsyncMock()
    parsed = Api17TrackClient(None, "k")._parse_track_data(TRACK_INFO)
    api = MagicMock()
    api.get_track_info = AsyncMock(return_value={pkg.tracking_number: parsed})
    api.get_quota = AsyncMock(return_value={"quota_total": 200, "quota_used": 3, "quota_remain": 197, "today_used": 1})

    coord = _coordinator(hass, store, api)
    await coord._update_tracking()
    await coord._update_quota()

    assert pkg.status == "delivered"
    assert pkg.delivered_at == datetime(2026, 11, 10, 14, 32)  # local Paris time, naive
    assert pkg.sub_status == "Delivered_Other"
    assert pkg.estimated_delivery_source == "Official"
    assert coord.quota["quota_remain"] == 197

    sensor = SuiviColisSensor(coord, pkg, MagicMock())
    attrs = sensor.extra_state_attributes
    assert attrs["sub_status"] == "Delivered_Other"
    assert attrs["estimated_delivery_to"] == "2026-11-11T00:00:00+01:00"
    assert attrs["delivered_at"] == "2026-11-10T14:32:00"

    quota = SuiviColisQuotaSensor(coord, MagicMock(entry_id="e"))
    coord.last_update_success = True
    assert quota.available and quota.native_value == 197
    assert quota.extra_state_attributes == {"quota_total": 200, "quota_used": 3, "today_used": 1}
    assert "tracking_number" not in quota.extra_state_attributes  # card ignores it


async def test_quota_error_keeps_sensor_unavailable(hass):
    from custom_components.suivi_colis.api_17track import Api17TrackError

    api = MagicMock()
    api.get_quota = AsyncMock(side_effect=Api17TrackError("401"))
    coord = _coordinator(hass, MagicMock(), api)
    await coord._update_quota()
    assert coord.quota is None
    assert not SuiviColisQuotaSensor(coord, MagicMock(entry_id="e")).available
