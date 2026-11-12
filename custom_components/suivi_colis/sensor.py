"""Sensor platform for Suivi de Colis."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, STATUS_ICONS
from .coordinator import SuiviColisCoordinator
from .models import Package

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Suivi de Colis sensors from config entry."""
    coordinator: SuiviColisCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Track which sensors exist
    tracked: set[str] = set()

    @callback
    def _async_add_new_sensors() -> None:
        """Add sensors for newly discovered packages."""
        new_entities: list[SuiviColisSensor] = []

        for tracking_number, package in coordinator.store.active_packages.items():
            if tracking_number not in tracked:
                tracked.add(tracking_number)
                new_entities.append(
                    SuiviColisSensor(coordinator, package, entry)
                )

        # Remove archived from tracking set
        active_numbers = set(coordinator.store.active_packages.keys())
        archived = tracked - active_numbers
        for number in archived:
            tracked.discard(number)

        if new_entities:
            async_add_entities(new_entities)

    # Account-level sensor: 17track quota
    async_add_entities([SuiviColisQuotaSensor(coordinator, entry)])

    # Add existing packages
    _async_add_new_sensors()

    # Listen for new packages on each update
    entry.async_on_unload(
        coordinator.async_add_listener(_async_add_new_sensors)
    )


class SuiviColisSensor(CoordinatorEntity[SuiviColisCoordinator], SensorEntity):
    """Sensor for a single tracked package."""

    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: SuiviColisCoordinator,
        package: Package,
        entry: ConfigEntry,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._tracking_number = package.tracking_number
        self._attr_unique_id = f"{DOMAIN}_{package.tracking_number}"
        self._attr_name = package.tracking_number

    @property
    def _package(self) -> Package | None:
        """Get the current package data."""
        return self.coordinator.store.get_package(self._tracking_number)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._package is not None and not self._package.archived

    @property
    def native_value(self) -> str | None:
        """Return the package status."""
        pkg = self._package
        return pkg.status if pkg else None

    @property
    def icon(self) -> str:
        """Return icon based on status."""
        pkg = self._package
        status = pkg.status if pkg else "unknown"
        return STATUS_ICONS.get(status, "mdi:package-variant")

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra attributes."""
        pkg = self._package
        if not pkg:
            return {}

        attrs = {
            "tracking_number": pkg.tracking_number,
            "carrier": pkg.carrier,
            "friendly_name": pkg.friendly_name,
            "info_text": pkg.info_text,
            "location": pkg.location,
            "source": pkg.source,
            "added_at": pkg.added_at.isoformat() if pkg.added_at else None,
            "last_updated": pkg.last_updated.isoformat() if pkg.last_updated else None,
            "delivered_at": pkg.delivered_at.isoformat() if pkg.delivered_at else None,
            "sub_status": pkg.sub_status,
            "sub_status_descr": pkg.sub_status_descr,
            "estimated_delivery_from": _iso(pkg.estimated_delivery_from),
            "estimated_delivery_to": _iso(pkg.estimated_delivery_to),
            "estimated_delivery_source": pkg.estimated_delivery_source,
            "events_count": len(pkg.events),
            "events": [
                {
                    "time": e.timestamp.isoformat(),
                    "description": e.description,
                    "location": e.location,
                }
                for e in pkg.events
            ],
        }

        if pkg.last_event:
            attrs["last_event"] = pkg.last_event.description
            attrs["last_event_time"] = pkg.last_event.timestamp.isoformat()
            attrs["last_event_location"] = pkg.last_event.location

        return attrs

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when removed."""
        _LOGGER.debug("Removing sensor for %s", self._tracking_number)


def _iso(value) -> str | None:
    return value.isoformat() if value else None


class SuiviColisQuotaSensor(CoordinatorEntity[SuiviColisCoordinator], SensorEntity):
    """Remaining 17track tracking quota (1 credit per new tracking number)."""

    _attr_has_entity_name = True
    _attr_translation_key = "quota_remain"
    _attr_icon = "mdi:counter"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "suivis"

    def __init__(self, coordinator: SuiviColisCoordinator, entry: ConfigEntry) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_quota_remain"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="17track",
            manufacturer="17TRACK",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://api.17track.net/admin/dashboard",
        )

    @property
    def available(self) -> bool:
        """Available once the quota has been fetched."""
        return super().available and self.coordinator.quota is not None

    @property
    def native_value(self) -> int | None:
        """Return the remaining quota."""
        return (self.coordinator.quota or {}).get("quota_remain")

    @property
    def extra_state_attributes(self) -> dict:
        """Return the other quota counters."""
        quota = self.coordinator.quota or {}
        return {
            key: quota.get(key)
            for key in ("quota_total", "quota_used", "today_used", "max_track_daily")
            if key in quota
        }
