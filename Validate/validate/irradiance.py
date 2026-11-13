"""Sunlight data for a rooftop.

Two sources:

    nasa_power_monthly()   real monthly values for any latitude and longitude
                           from NASA POWER (free, no key, needs internet)
    climatology_monthly()  built-in typical values for coastal Odisha, used for
                           demos and when the network is not available

Values are kWh per square metre per day on a horizontal surface (GHI). For the
low tilts used on Odisha rooftops (10 to 20 degrees) this is within a few per
cent of the panel-plane value across a year.
"""
from __future__ import annotations

import calendar
import json
import urllib.request

# Approximate long-term monthly averages for Bhubaneswar, kWh/m2/day.
# Replace with NASA POWER or ORSAC/MOSDAC data for production use.
ODISHA_COAST_GHI = {1: 4.6, 2: 5.4, 3: 6.0, 4: 6.4, 5: 6.2, 6: 4.5, 7: 3.8, 8: 3.9, 9: 4.2, 10: 4.6, 11: 4.5, 12: 4.3}

NASA_URL = (
    "https://power.larc.nasa.gov/api/temporal/monthly/point"
    "?parameters=ALLSKY_SFC_SW_DWN&community=RE&format=JSON"
    "&latitude={lat}&longitude={lon}&start={start}&end={end}"
)


def climatology_monthly(year: int, month: int) -> float:
    """Typical total sunlight for one month, kWh/m2."""
    return ODISHA_COAST_GHI[month] * calendar.monthrange(year, month)[1]


def nasa_power_monthly(lat: float, lon: float, start_year: int, end_year: int, timeout: int = 30) -> dict:
    """Monthly sunlight totals from NASA POWER.

    Returns {"YYYY-MM": kWh/m2 for that month}. Raises on network failure, so
    callers can fall back to climatology_monthly().
    """
    url = NASA_URL.format(lat=lat, lon=lon, start=start_year, end=end_year)
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        data = json.load(resp)
    daily = data["properties"]["parameter"]["ALLSKY_SFC_SW_DWN"]
    out = {}
    for key, value in daily.items():
        year, month = int(key[:4]), int(key[4:6])
        if 1 <= month <= 12 and value is not None and value >= 0:
            out[f"{year}-{month:02d}"] = value * calendar.monthrange(year, month)[1]
    return out


def monthly_series(months: list, lat: float = None, lon: float = None, online: bool = False) -> list:
    """Sunlight totals for a list of "YYYY-MM" strings, with automatic fallback."""
    live = {}
    if online and lat is not None and lon is not None:
        years = [int(m[:4]) for m in months]
        try:
            live = nasa_power_monthly(lat, lon, min(years), max(years))
        except Exception:
            live = {}
    return [live.get(m, climatology_monthly(int(m[:4]), int(m[5:7]))) for m in months]
