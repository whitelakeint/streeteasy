"""Database operations for the StreetEasy scraper."""

from datetime import date
import mysql.connector
from config import get_db_config
from parsers import parse_rent, parse_beds, parse_baths


class DBManager:
    def __init__(self):
        self.config = get_db_config()

    def _connect(self):
        return mysql.connector.connect(**self.config)

    # --- URL Management ---

    def add_url(self, name, url):
        """Add a URL to scrape. Returns the inserted ID."""
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO scrape_urls (name, url) VALUES (%s, %s) "
            "ON DUPLICATE KEY UPDATE name = VALUES(name), is_active = 1",
            (name, url),
        )
        conn.commit()
        row_id = cursor.lastrowid
        cursor.close()
        conn.close()
        return row_id

    def get_active_urls(self):
        """Get all active URLs (eligible for scraping)."""
        conn = self._connect()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM scrape_urls WHERE is_active = 1 ORDER BY id")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows

    def get_all_urls(self):
        """Get all URLs."""
        conn = self._connect()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM scrape_urls ORDER BY created_at DESC")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows

    def update_url_status(self, url_id, status):
        """Update last_status and last_scraped_at of a URL."""
        conn = self._connect()
        cursor = conn.cursor()
        if status == "completed":
            cursor.execute(
                "UPDATE scrape_urls SET last_status = %s, last_scraped_at = NOW() WHERE id = %s",
                (status, url_id),
            )
        else:
            cursor.execute(
                "UPDATE scrape_urls SET last_status = %s WHERE id = %s",
                (status, url_id),
            )
        conn.commit()
        cursor.close()
        conn.close()

    def deactivate_url(self, url_id):
        """Mark a URL as inactive (won't be scraped)."""
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute("UPDATE scrape_urls SET is_active = 0 WHERE id = %s", (url_id,))
        conn.commit()
        cursor.close()
        conn.close()

    def activate_url(self, url_id):
        """Mark a URL as active (will be scraped)."""
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute("UPDATE scrape_urls SET is_active = 1 WHERE id = %s", (url_id,))
        conn.commit()
        cursor.close()
        conn.close()

    # --- Property Data ---

    def save_properties(self, url_id, properties, scrape_date=None):
        """
        Save extracted properties for a URL.
        For each property: if a row with same url_id + scrape_date + property_name
        exists, update it. Otherwise insert a new row.
        Previous days' data is untouched.
        """
        if not properties:
            return

        if scrape_date is None:
            scrape_date = date.today()

        conn = self._connect()
        cursor = conn.cursor()

        for p in properties:
            prop_name = p.get("property_name", "")

            # Check if this property already exists for today
            cursor.execute(
                "SELECT id FROM properties "
                "WHERE url_id = %s AND scrape_date = %s AND property_name = %s",
                (url_id, scrape_date, prop_name),
            )
            existing = cursor.fetchone()

            rent_int = parse_rent(p.get("rent"))
            beds_no = parse_beds(p.get("beds"))
            baths_no = parse_baths(p.get("baths"))

            if existing:
                cursor.execute(
                    """UPDATE properties
                       SET rent = %s, beds = %s, beds_no = %s,
                           baths = %s, baths_no = %s, area = %s,
                           listing_url = %s, listed_by = %s, availability = %s,
                           specials = %s, original = 1, scraped_at = NOW()
                       WHERE id = %s""",
                    (
                        rent_int,
                        p.get("beds"),
                        beds_no,
                        p.get("baths"),
                        baths_no,
                        p.get("area"),
                        p.get("listing_url"),
                        p.get("listed_by"),
                        p.get("availability"),
                        p.get("specials"),
                        existing[0],
                    ),
                )
            else:
                cursor.execute(
                    """INSERT INTO properties
                           (url_id, scrape_date, property_name, rent, beds, beds_no,
                            baths, baths_no, area, listing_url, listed_by,
                            availability, specials, original)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1)""",
                    (
                        url_id,
                        scrape_date,
                        prop_name,
                        rent_int,
                        p.get("beds"),
                        beds_no,
                        p.get("baths"),
                        baths_no,
                        p.get("area"),
                        p.get("listing_url"),
                        p.get("listed_by"),
                        p.get("availability"),
                        p.get("specials"),
                    ),
                )

        conn.commit()
        cursor.close()
        conn.close()

    def get_properties_by_url(self, url_id, scrape_date=None):
        """Get properties for a URL. If date given, filter by that date."""
        conn = self._connect()
        cursor = conn.cursor(dictionary=True)
        if scrape_date:
            cursor.execute(
                "SELECT * FROM properties WHERE url_id = %s AND scrape_date = %s",
                (url_id, scrape_date),
            )
        else:
            cursor.execute("SELECT * FROM properties WHERE url_id = %s", (url_id,))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows

    def get_properties_by_date(self, scrape_date=None):
        """Get all properties for a given date (defaults to today)."""
        if scrape_date is None:
            scrape_date = date.today()
        conn = self._connect()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT p.*, s.name as building_name, s.url as source_url "
            "FROM properties p JOIN scrape_urls s ON p.url_id = s.id "
            "WHERE p.scrape_date = %s ORDER BY s.name, p.property_name",
            (scrape_date,),
        )
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows
