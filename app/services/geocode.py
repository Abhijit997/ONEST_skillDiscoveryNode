"""
Offline geocoding service — maps PIN / ZIP codes to latitude & longitude.

Uses **pgeocode** which ships with an offline GeoNames dataset (~2 MB, cached
locally after the first import).  No internet required after initial download.

Supported countries: India ("IN"), US ("US"), UK ("GB"), and 80+ others.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import pgeocode

# Singleton instances keyed by country code — avoids reloading the dataset.
_nominatim_cache: dict[str, pgeocode.Nominatim] = {}

# Default country for PIN code lookups.
DEFAULT_COUNTRY = "IN"


# ── ISO 3166-2:IN  State / UT mapping ────────────────────────────────────────

# Canonical dict:  ISO code → official name
INDIA_STATES: dict[str, str] = {
    "AN": "Andaman & Nicobar Islands",
    "AP": "Andhra Pradesh",
    "AR": "Arunachal Pradesh",
    "AS": "Assam",
    "BR": "Bihar",
    "CH": "Chandigarh",
    "CG": "Chhattisgarh",
    "DN": "Dadra & Nagar Haveli and Daman & Diu",
    "DL": "Delhi",
    "GA": "Goa",
    "GJ": "Gujarat",
    "HR": "Haryana",
    "HP": "Himachal Pradesh",
    "JK": "Jammu & Kashmir",
    "JH": "Jharkhand",
    "KA": "Karnataka",
    "KL": "Kerala",
    "LA": "Ladakh",
    "LD": "Lakshadweep",
    "MP": "Madhya Pradesh",
    "MH": "Maharashtra",
    "MN": "Manipur",
    "ML": "Meghalaya",
    "MZ": "Mizoram",
    "NL": "Nagaland",
    "OD": "Odisha",
    "PY": "Puducherry",
    "PB": "Punjab",
    "RJ": "Rajasthan",
    "SK": "Sikkim",
    "TN": "Tamil Nadu",
    "TS": "Telangana",
    "TR": "Tripura",
    "UP": "Uttar Pradesh",
    "UK": "Uttarakhand",
    "WB": "West Bengal",
}

# Reverse: name (lower) → ISO code  (includes common spelling variants)
_NAME_TO_ISO: dict[str, str] = {v.lower(): k for k, v in INDIA_STATES.items()}
# Add common variants & pgeocode spellings
_NAME_TO_ISO.update({
    "andaman and nicobar islands": "AN",
    "andaman & nicobar": "AN",
    "chattisgarh": "CG",          # pgeocode typo
    "dadra and nagar haveli and daman and diu": "DN",
    "dadra and nagar haveli": "DN",
    "daman and diu": "DN",
    "daman & diu": "DN",
    "pondicherry": "PY",          # old name used by pgeocode
    "orissa": "OD",               # old name
    "uttaranchal": "UK",          # old name
    "nct of delhi": "DL",
})

# pgeocode numeric state_code → ISO code  (India postal region numbers)
_PGEOCODE_NUM_TO_ISO: dict[str, str] = {
    "1":  "AN",
    "2":  "AP",
    "30": "AR",
    "3":  "AS",
    "34": "BR",
    "5":  "CH",
    "37": "CG",
    "52": "DN",
    "7":  "DL",
    "33": "GA",
    "9":  "GJ",
    "10": "HR",
    "11": "HP",
    "12": "JK",
    "38": "JH",
    "19": "KA",
    "13": "KL",
    "14": "LD",
    "35": "MP",
    "16": "MH",
    "17": "MN",
    "18": "ML",
    "31": "MZ",
    "20": "NL",
    "21": "OD",
    "22": "PY",
    "23": "PB",
    "24": "RJ",
    "29": "SK",
    "25": "TN",
    "40": "TS",
    "26": "TR",
    "36": "UP",
    "39": "UK",
    "28": "WB",
}


def state_name_to_iso(name: str) -> Optional[str]:
    """Convert a state name (any common variant) to its ISO 3166-2:IN code."""
    if not name:
        return None
    return _NAME_TO_ISO.get(name.strip().lower())


def iso_to_state_name(code: str) -> Optional[str]:
    """Convert an ISO 3166-2:IN code to the official state name."""
    if not code:
        return None
    return INDIA_STATES.get(code.strip().upper())


def _pgeocode_to_iso(pgeocode_state_code, pgeocode_state_name) -> Optional[str]:
    """
    Convert pgeocode's numeric state_code (or state_name) to ISO code.
    Tries numeric first, falls back to name-based lookup.
    """
    # Try numeric code
    if pgeocode_state_code is not None and not _is_nan(pgeocode_state_code):
        num = str(int(float(pgeocode_state_code)))
        iso = _PGEOCODE_NUM_TO_ISO.get(num)
        if iso:
            return iso

    # Fallback: try name
    if pgeocode_state_name and not _is_nan(pgeocode_state_name):
        return state_name_to_iso(str(pgeocode_state_name))

    return None


@dataclass(frozen=True)
class GeoResult:
    """Result of a postal‑code geocode lookup."""
    latitude: float
    longitude: float
    place_name: Optional[str] = None
    state_name: Optional[str] = None
    state_code: Optional[str] = None
    county_name: Optional[str] = None   # district in India


def _get_nominatim(country: str = DEFAULT_COUNTRY) -> pgeocode.Nominatim:
    """Return (and cache) a Nominatim instance for *country*."""
    country = country.upper()
    if country not in _nominatim_cache:
        _nominatim_cache[country] = pgeocode.Nominatim(country)
    return _nominatim_cache[country]


def geocode_pincode(
    pincode: str,
    country: str = DEFAULT_COUNTRY,
) -> Optional[GeoResult]:
    """
    Look up a postal / PIN code and return lat/lon + metadata.

    Returns ``None`` when the code is unknown or the dataset has no
    coordinates for it.

    >>> geocode_pincode("560038")
    GeoResult(latitude=13.2257, longitude=77.575, ...)
    """
    nomi = _get_nominatim(country)
    row = nomi.query_postal_code(pincode.strip())

    # pgeocode returns a pandas Series; NaN means not found.
    if row is None or (hasattr(row, "latitude") and _is_nan(row.latitude)):
        return None

    # Resolve ISO state code from pgeocode's numeric code + name
    iso_code = _pgeocode_to_iso(row.state_code, row.state_name)
    iso_name = INDIA_STATES.get(iso_code) if iso_code else _str_or_none(row.state_name)

    return GeoResult(
        latitude=round(float(row.latitude), 6),
        longitude=round(float(row.longitude), 6),
        place_name=_str_or_none(row.place_name),
        state_name=iso_name,
        state_code=iso_code,
        county_name=_str_or_none(row.county_name),
    )


# ── helpers ────────────────────────────────────


def _is_nan(value) -> bool:
    """Return True for NaN / None / empty."""
    if value is None:
        return True
    try:
        return math.isnan(value)
    except (TypeError, ValueError):
        return False


def _str_or_none(value) -> Optional[str]:
    """Convert pandas scalar to Python str, or None when missing."""
    if value is None or (_is_nan(value) if isinstance(value, float) else False):
        return None
    s = str(value).strip()
    return s if s else None
