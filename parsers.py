"""Helpers to convert scraped string values to numeric form."""

import re


def parse_rent(rent_str):
    """'$5,125' -> 5125, '$1,200/mo' -> 1200. Returns None if unparseable."""
    if rent_str is None:
        return None
    digits = re.sub(r"[^\d]", "", str(rent_str))
    return int(digits) if digits else None


def parse_beds(beds_str):
    """'Studio' -> 0, '1 bed' -> 1, '2 beds' -> 2. Returns None if unparseable."""
    if beds_str is None:
        return None
    s = str(beds_str).strip().lower()
    if "studio" in s:
        return 0
    m = re.search(r"(\d+)", s)
    return int(m.group(1)) if m else None


def parse_baths(baths_str):
    """'1 bath' -> 1.0, '2.5 baths' -> 2.5. Returns None if unparseable."""
    if baths_str is None:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)", str(baths_str))
    return float(m.group(1)) if m else None
