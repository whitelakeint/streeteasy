"""
Demo data generator.

1. Adds `original` BOOLEAN column to `properties` (TRUE for real scrapes).
2. For each existing property, walks BACKWARDS from its oldest scrape_date
   to 2026-03-15, creating synthetic daily records with realistic rent variance.

Variance model per day:
  - 60% chance: rent stays the same as the previous day (prices don't change daily)
  - 20% chance: rent moves up 1-3%
  - 20% chance: rent moves down 1-3%

Run once:  python generate_demo_history.py
"""

import random
from datetime import date, timedelta
import mysql.connector
from config import get_db_config


START_DATE = date(2026, 3, 15)

# Probability weights — tuned for realistic "sometimes stable" behavior
P_STABLE = 0.60
P_UP = 0.20
P_DOWN = 0.20
VARIANCE_MIN = 0.01   # 1%
VARIANCE_MAX = 0.03   # 3%


def column_exists(cursor, table, column):
    cursor.execute(
        """SELECT COUNT(*) AS c FROM information_schema.columns
           WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s""",
        (table, column),
    )
    row = cursor.fetchone()
    # Cursor may be dict-mode or tuple-mode depending on caller
    if isinstance(row, dict):
        return row.get("c", 0) > 0
    return row[0] > 0


def next_rent(current):
    """Apply one day of variance to the current rent and return the new rent."""
    if current is None:
        return None
    roll = random.random()
    if roll < P_STABLE:
        return current
    pct = random.uniform(VARIANCE_MIN, VARIANCE_MAX)
    if roll < P_STABLE + P_UP:
        return int(round(current * (1 + pct)))
    return int(round(current * (1 - pct)))


def main():
    random.seed()  # fresh randomness every run
    conn = mysql.connector.connect(**get_db_config())
    cursor = conn.cursor(dictionary=True)
    write = conn.cursor()

    # 1. Ensure `original` column exists; mark all existing rows as originals
    if not column_exists(cursor, "properties", "original"):
        print("Adding column `original`...")
        write.execute(
            "ALTER TABLE properties ADD COLUMN original TINYINT(1) NOT NULL DEFAULT 0 AFTER specials"
        )
        write.execute("UPDATE properties SET original = 1")
        conn.commit()
        print("  Marked all existing rows as original = 1.")

    # 2. For every distinct (url_id, property_name) pair, find its earliest and
    #    latest real record. We fill BOTH directions:
    #      - backward from earliest-1 down to START_DATE
    #      - forward from latest+1 up to yesterday (today is left alone for live scrapes)
    cursor.execute(
        """SELECT url_id, property_name,
                  MIN(scrape_date) AS earliest,
                  MAX(scrape_date) AS latest
           FROM properties
           WHERE original = 1
           GROUP BY url_id, property_name"""
    )
    groups = cursor.fetchall()
    print(f"Found {len(groups)} unique (url, unit) pair(s).")

    today = date.today()
    yesterday = today - timedelta(days=1)
    total_inserted = 0

    def row_exists(url_id, prop_name, day):
        cursor.execute(
            """SELECT id FROM properties
               WHERE url_id = %s AND property_name = %s AND scrape_date = %s""",
            (url_id, prop_name, day),
        )
        return cursor.fetchone() is not None

    def load_template(url_id, prop_name, day):
        cursor.execute(
            """SELECT * FROM properties
               WHERE url_id = %s AND property_name = %s AND scrape_date = %s
               LIMIT 1""",
            (url_id, prop_name, day),
        )
        return cursor.fetchone()

    for g in groups:
        url_id = g["url_id"]
        prop_name = g["property_name"]
        earliest = g["earliest"]
        latest = g["latest"]
        if earliest is None:
            continue

        batch = []

        # ---- Backward fill: earliest-1 → START_DATE ----
        if earliest > START_DATE:
            template = load_template(url_id, prop_name, earliest)
            if template and template.get("rent") is not None:
                current_rent = template["rent"]
                day = earliest - timedelta(days=1)
                while day >= START_DATE:
                    if row_exists(url_id, prop_name, day):
                        day -= timedelta(days=1)
                        continue
                    current_rent = next_rent(current_rent)
                    batch.append((
                        url_id, day, prop_name, current_rent,
                        template.get("beds"), template.get("beds_no"),
                        template.get("baths"), template.get("baths_no"),
                        template.get("area"), template.get("listing_url"),
                        template.get("listed_by"), template.get("availability"),
                        template.get("specials"),
                    ))
                    day -= timedelta(days=1)

        # ---- Forward fill: latest+1 → yesterday ----
        if latest is not None and latest < yesterday:
            template = load_template(url_id, prop_name, latest)
            if template and template.get("rent") is not None:
                current_rent = template["rent"]
                day = latest + timedelta(days=1)
                while day <= yesterday:
                    if row_exists(url_id, prop_name, day):
                        day += timedelta(days=1)
                        continue
                    current_rent = next_rent(current_rent)
                    batch.append((
                        url_id, day, prop_name, current_rent,
                        template.get("beds"), template.get("beds_no"),
                        template.get("baths"), template.get("baths_no"),
                        template.get("area"), template.get("listing_url"),
                        template.get("listed_by"), template.get("availability"),
                        template.get("specials"),
                    ))
                    day += timedelta(days=1)

        if batch:
            write.executemany(
                """INSERT INTO properties
                       (url_id, scrape_date, property_name, rent, beds, beds_no,
                        baths, baths_no, area, listing_url, listed_by,
                        availability, specials, original)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0)""",
                batch,
            )
            conn.commit()
            total_inserted += len(batch)
            print(f"  {prop_name} @ url_id={url_id}: inserted {len(batch)} synthetic day(s)")

    cursor.close()
    write.close()
    conn.close()
    print(f"\nDone. Total synthetic rows inserted: {total_inserted}")


if __name__ == "__main__":
    main()
