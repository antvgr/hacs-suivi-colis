"""Estimated delivery date and time slot from La Poste (Colissimo).

17track often gives only the day for Colissimo; the public La Poste tracking
service also gives the delivery time slot. Unofficial endpoint (the one the
laposte.fr tracking page uses): any failure is ignored and the 17track data
is kept.
"""

from __future__ import annotations

import logging
from datetime import datetime, time
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.util import dt as dt_util

from .api_17track import _parse_time
from .models import Package

_LOGGER = logging.getLogger(__name__)

LAPOSTE_URL = "https://www.laposte.fr/ssu/sun/back/suivi-unifie/{}?lang=fr"
# Tracking page: opening it first gives the session cookies the service
# requires (a direct call is refused with HTTP 403)
LAPOSTE_PAGE_URL = "https://www.laposte.fr/outils/suivre-vos-envois?code={}"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/158.0.0.0 Safari/537.36"
)
_PAGE_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}
_API_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}
LAPOSTE_SOURCE = "La Poste"
LAPOSTE_CARRIERS = {"colissimo", "laposte"}
LAPOSTE_17TRACK_CODE = 6051
_TIMEOUT = aiohttp.ClientTimeout(total=15)


_SESSION_KEY = "suivi_colis_laposte_session"


def async_get_laposte_session(hass: HomeAssistant) -> aiohttp.ClientSession:
    """Session dedicated to La Poste, keeping its cookies between requests.

    One per Home Assistant instance, reused across reloads and closed by
    Home Assistant when it stops (it must not be closed by the integration).
    """
    session = hass.data.get(_SESSION_KEY)
    if session is None:
        session = async_create_clientsession(hass, cookie_jar=aiohttp.CookieJar())
        hass.data[_SESSION_KEY] = session
    return session


def is_laposte_package(pkg: Package) -> bool:
    """Package delivered by La Poste / Colissimo (at least for the last leg)."""
    return pkg.carrier in LAPOSTE_CARRIERS or pkg.carrier_code == LAPOSTE_17TRACK_CODE


def parse_estimate(payload: Any) -> dict | None:
    """Estimated delivery {from, to} of a suivi-unifie answer, None if unknown.

    The day comes from ``estimDate``; ``estimHourMin``/``estimHourMax`` give
    the hours of the slot. La Poste dates those two with the day the estimate
    was made, not always the delivery day (seen: estimDate Monday 23, slot
    dated Sunday 22 08:30-12:30): only their time of day is used, on the
    estimated day. Without a slot, the whole day is returned.
    """
    item = payload[0] if isinstance(payload, list) and payload else payload
    if not isinstance(item, dict):
        return None
    shipment = item.get("shipment") or {}
    if shipment.get("isFinal"):
        return None
    estimate = _parse_time(shipment.get("estimDate"))
    if estimate is None:
        return None

    day = dt_util.as_local(estimate).date()
    slot_from = _parse_time(shipment.get("estimHourMin"))
    slot_to = _parse_time(shipment.get("estimHourMax"))
    tz = dt_util.get_default_time_zone()
    if slot_from and slot_to:
        start = datetime.combine(day, dt_util.as_local(slot_from).time(), tzinfo=tz)
        end = datetime.combine(day, dt_util.as_local(slot_to).time(), tzinfo=tz)
        if start < end:
            return {"from": start, "to": end}

    return {
        "from": datetime.combine(day, time.min, tzinfo=tz),
        "to": datetime.combine(day, time(23, 59, 59), tzinfo=tz),
    }


async def async_get_estimate(
    session: aiohttp.ClientSession,
    tracking_number: str,
    raw: dict[str, Any] | None = None,
) -> tuple[bool, dict | None]:
    """Ask La Poste like the laposte.fr tracking page does.

    ``session`` must keep cookies (its own cookie jar): the tracking page is
    opened first, then the service is called with the cookies it set.
    Returns (answered, estimate or None). The answer is also stored in
    ``raw`` (by tracking number) when given, for the diagnostics.
    """
    page_url = LAPOSTE_PAGE_URL.format(tracking_number)
    try:
        async with session.get(page_url, headers=_PAGE_HEADERS, timeout=_TIMEOUT) as resp:
            await resp.read()
        async with session.get(
            LAPOSTE_URL.format(tracking_number),
            headers={**_API_HEADERS, "Referer": page_url},
            timeout=_TIMEOUT,
        ) as resp:
            if resp.status != 200:
                _LOGGER.debug("La Poste: HTTP %s for %s", resp.status, tracking_number)
                return False, None
            payload = await resp.json(content_type=None)
            if raw is not None:
                raw[tracking_number] = payload
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        _LOGGER.debug("La Poste: no answer for %s: %s", tracking_number, err)
        return False, None
    return True, parse_estimate(payload)
