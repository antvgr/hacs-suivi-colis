"""Tests of tracking number extraction from emails."""

from custom_components.suivi_colis.email_parser import (
    extract_tracking_numbers,
    html_to_text,
)

UPS_UPDATE_HTML = """
<html><head><style>
  .trackingNumberRow { text-decoration: none; }
  a.tracking { text-decoration: underline; }
</style></head>
<body>
  <table><tr class="trackingNumberRow"><td style="text-decoration:none">
    Numéro de suivi : <a href="https://www.ups.com/track?tracknum=1ZWV49986892191508">
    1ZWV49986892191508</a>
  </td></tr></table>
  <p>Suivre votre colis &amp; gérer la livraison</p>
</body></html>
"""


def test_html_markup_is_not_a_tracking_number():
    """Class names and CSS from a UPS update email are ignored (regression)."""
    found = extract_tracking_numbers(
        "Mise à jour UPS : le colis est programmé en livraison demain", "", UPS_UPDATE_HTML
    )
    assert found == {"1ZWV49986892191508"}


def test_words_without_digits_are_rejected():
    """Plain words after 'tracking'/'suivi' are not tracking numbers."""
    text = "Tracking information available. Suivi DECORATION. Track your INFORMATIONS"
    assert extract_tracking_numbers("", text, "") == set()


def test_generic_patterns_still_work():
    """Numbers announced by a keyword are still found."""
    assert extract_tracking_numbers("", "N° de colis : XY1234567890", "") == {
        "XY1234567890"
    }
    assert extract_tracking_numbers("", "Tracking: 123456789012", "") == {
        "123456789012"
    }


def test_html_to_text():
    """Tags, styles and entities are removed."""
    assert html_to_text("<style>a{x:y}</style><b>A &amp; B</b>").split() == ["A", "&", "B"]


# ------------------------------------------------------------ coordinator

from unittest.mock import AsyncMock, MagicMock  # noqa: E402

from custom_components.suivi_colis.models import Package  # noqa: E402

from .test_push_and_carrier import _coordinator, _store  # noqa: E402


async def test_invalid_email_packages_are_removed(hass):
    """Packages created from email markup by older versions are cleaned up."""
    junk = Package("DECORATION", carrier="ups", source="email")
    manual = Package("MANUALNAME", carrier="ups", source="manual")
    real = Package("1ZWV49986892191508", carrier="ups", source="email")
    store = _store(junk, manual, real)
    store.remove_package = MagicMock()
    api = MagicMock()
    api.stop_tracking = AsyncMock()
    coord = _coordinator(hass, store, api)

    assert await coord.async_remove_invalid_email_packages() == 1

    store.remove_package.assert_called_once_with("DECORATION")
    api.stop_tracking.assert_awaited_once_with("DECORATION")
    store.async_save.assert_awaited_once()


async def test_add_package_skips_implausible_email_number(hass):
    """No 17track registration (and no quota spent) for a word from an email."""
    store = _store()
    store.has_package = MagicMock(return_value=False)
    api = MagicMock()
    api.register_package = AsyncMock(return_value=True)
    coord = _coordinator(hass, store, api)

    assert not await coord.add_package("INGNUMBERROW", "ups", source="email")
    api.register_package.assert_not_awaited()
