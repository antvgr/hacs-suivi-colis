"""Calendar of the expected deliveries (one event per package)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import SuiviColisCoordinator
from .entity import SuiviColisEntity
from .models import Package, PackageStatus


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the deliveries calendar."""
    coordinator: SuiviColisCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SuiviColisCalendar(coordinator, entry)])


def delivery_event(pkg: Package) -> CalendarEvent | None:
    """Calendar event of the expected delivery of a package, None if unknown.

    A precise slot (La Poste, carrier) gives a timed event; a day only
    (whole-day range, or a single date as 17track often gives) gives an
    all-day event.
    """
    if pkg.archived or pkg.status == PackageStatus.DELIVERED:
        return None
    start = pkg.estimated_delivery_from or pkg.estimated_delivery_to
    if start is None:
        return None
    end = pkg.estimated_delivery_to or start
    start, end = dt_util.as_local(start), dt_util.as_local(end)
    if end < start:
        start, end = end, start

    details = [f"Numéro de suivi : {pkg.tracking_number}"]
    if pkg.carrier:
        details.append(f"Transporteur : {pkg.carrier}")
    if pkg.info_text:
        details.append(f"Dernier événement : {pkg.info_text}")
    if pkg.estimated_delivery_source:
        details.append(f"Source de l'estimation : {pkg.estimated_delivery_source}")

    if _date_only(start) and (end == start or _date_only(end) or _end_of_day(end)):
        # Day(s) only: all-day event, end date excluded
        event_start: date | datetime = _day(start)
        event_end: date | datetime = max(_day(end), event_start) + timedelta(days=1)
    else:
        event_start, event_end = start, end
        if event_end == event_start:
            event_end = event_start + timedelta(hours=1)

    return CalendarEvent(
        start=event_start,
        end=event_end,
        summary=f"Livraison : {pkg.display_name}",
        description="\n".join(details),
        uid=f"{DOMAIN}_{pkg.tracking_number}",
    )


def _date_only(value: datetime) -> bool:
    """A date without time of day: local or UTC midnight (17track uses UTC)."""
    return value.time() == time.min or dt_util.as_utc(value).time() == time.min


def _day(value: datetime) -> date:
    """The day of a date-only value (a UTC midnight is that UTC day)."""
    if value.time() == time.min or _end_of_day(value):
        return value.date()
    return dt_util.as_utc(value).date()


def _end_of_day(value: datetime) -> bool:
    return value.time() >= time(23, 59)


def _event_bounds(event: CalendarEvent) -> tuple[datetime, datetime]:
    """Start/end of an event as aware datetimes, for comparisons."""
    return event.start_datetime_local, event.end_datetime_local


class SuiviColisCalendar(SuiviColisEntity, CalendarEntity):
    """Expected deliveries: the day, or the time slot when known."""

    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: SuiviColisCoordinator, entry: ConfigEntry) -> None:
        """Initialize."""
        super().__init__(coordinator, entry, "deliveries")

    def _events(self) -> list[CalendarEvent]:
        events = [
            event
            for pkg in self.coordinator.store.active_packages.values()
            if (event := delivery_event(pkg)) is not None
        ]
        return sorted(events, key=lambda e: _event_bounds(e)[0])

    @property
    def event(self) -> CalendarEvent | None:
        """Current or next delivery."""
        now = dt_util.now()
        for event in self._events():
            if _event_bounds(event)[1] > now:
                return event
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Deliveries overlapping the requested period."""
        return [
            event
            for event in self._events()
            if _event_bounds(event)[0] < end_date and _event_bounds(event)[1] > start_date
        ]
