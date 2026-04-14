"""
HTTP client for the Laravel scraper API.
Replaces direct DB access from the Python scraper.
"""

import os
import requests
from datetime import date
from dotenv import load_dotenv

# Load .env BEFORE reading any env vars. Safe to call multiple times.
load_dotenv()


def _base() -> str:
    return os.getenv("LARAVEL_API_BASE", "http://localhost:8000/api/scraper")


def _headers() -> dict:
    """Build headers lazily so every request picks up the current env value.
    Prevents the 'token was empty at import time' bug."""
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Api-Token": os.getenv("SCRAPER_API_TOKEN", ""),
    }


class ApiClient:
    """Thin wrapper over the Laravel endpoints used by the scraper."""

    def get_active_urls(self):
        r = requests.get(f"{_base()}/urls", headers=_headers(), timeout=15)
        r.raise_for_status()
        return r.json().get("urls", [])

    def update_url_status(self, url_id, status):
        r = requests.post(
            f"{_base()}/urls/{url_id}/status",
            json={"status": status},
            headers=_headers(),
            timeout=15,
        )
        r.raise_for_status()

    def log(self, level, event, message, url_id=None, property_name=None, context=None):
        """Send a log entry to Laravel. Never raises — scraper must not fail on log errors."""
        try:
            requests.post(
                f"{_base()}/logs",
                json={
                    "url_id": url_id,
                    "property_name": property_name,
                    "level": level,
                    "event": event,
                    "message": str(message)[:1000],
                    "context": context,
                },
                headers=_headers(),
                timeout=5,
            )
        except Exception:
            pass  # logging must never break the scrape

    def save_properties(self, url_id, properties, scrape_date=None):
        if not properties:
            return
        payload = {
            "url_id": url_id,
            "scrape_date": str(scrape_date or date.today()),
            "properties": properties,
        }
        r = requests.post(
            f"{_base()}/properties",
            json=payload,
            headers=_headers(),
            timeout=60,
        )
        r.raise_for_status()
        return r.json()
