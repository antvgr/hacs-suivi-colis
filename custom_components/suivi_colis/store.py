"""Persistent storage for Suivi de Colis packages."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_VERSION
from .models import Package

# Removed numbers are remembered longer than the longest email search window
# (90 days) so an old email cannot bring a removed package back
REMOVED_RETENTION = timedelta(days=120)

_LOGGER = logging.getLogger(__name__)


class SuiviColisStore:
    """Manage package persistence via HA .storage."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize."""
        self._store = Store[dict[str, Any]](hass, STORAGE_VERSION, STORAGE_KEY)
        self._packages: dict[str, Package] = {}
        # Tracking number -> removal date of the packages removed by the user
        # or auto-removed after delivery: never re-imported from emails
        self._removed: dict[str, datetime] = {}

    @property
    def packages(self) -> dict[str, Package]:
        """Return all packages keyed by tracking number."""
        return self._packages

    @property
    def active_packages(self) -> dict[str, Package]:
        """Return non-archived packages."""
        return {k: v for k, v in self._packages.items() if not v.archived}

    async def async_load(self) -> None:
        """Load packages from storage."""
        data = await self._store.async_load()
        if data and "packages" in data:
            for pkg_data in data["packages"]:
                try:
                    pkg = Package.from_dict(pkg_data)
                    self._packages[pkg.tracking_number] = pkg
                except (KeyError, ValueError) as err:
                    _LOGGER.warning("Skipping invalid package data: %s", err)
        for number, removed_at in ((data or {}).get("removed") or {}).items():
            try:
                self._removed[number] = datetime.fromisoformat(removed_at)
            except (TypeError, ValueError):
                continue
        self._prune_removed()
        _LOGGER.debug("Loaded %d packages from storage", len(self._packages))

    async def async_save(self) -> None:
        """Save packages to storage."""
        self._prune_removed()
        data = {
            "packages": [pkg.to_dict() for pkg in self._packages.values()],
            "removed": {n: d.isoformat() for n, d in self._removed.items()},
        }
        await self._store.async_save(data)

    def add_package(self, package: Package) -> None:
        """Add a package (does not persist, call async_save after)."""
        self._packages[package.tracking_number] = package

    def remove_package(self, tracking_number: str) -> Package | None:
        """Remove a package (does not persist, call async_save after)."""
        return self._packages.pop(tracking_number, None)

    @property
    def removed_numbers(self) -> set[str]:
        """Tracking numbers removed recently, not to be imported again."""
        return set(self._removed)

    def mark_removed(self, tracking_number: str) -> None:
        """Remember a removed package (does not persist, call async_save after)."""
        self._removed[tracking_number] = datetime.now()

    def forget_removed(self, tracking_number: str) -> None:
        """Allow a removed number again (e.g. added back by hand)."""
        self._removed.pop(tracking_number, None)

    def _prune_removed(self) -> None:
        cutoff = datetime.now() - REMOVED_RETENTION
        self._removed = {n: d for n, d in self._removed.items() if d >= cutoff}

    def get_package(self, tracking_number: str) -> Package | None:
        """Get a package by tracking number."""
        return self._packages.get(tracking_number)

    def has_package(self, tracking_number: str) -> bool:
        """Check if a tracking number is already tracked."""
        return tracking_number in self._packages
