"""
One-shot migration:
  1. Add beds_no, baths_no columns (if missing).
  2. Convert rent from VARCHAR to INT (if not already INT).
  3. Backfill rent / beds_no / baths_no from existing string values.

Run once:  python migrate_numeric_fields.py
"""

import mysql.connector
from config import get_db_config
from parsers import parse_rent, parse_beds, parse_baths


def column_exists(cursor, table, column):
    cursor.execute(
        """SELECT COUNT(*) FROM information_schema.columns
           WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s""",
        (table, column),
    )
    return cursor.fetchone()[0] > 0


def column_type(cursor, table, column):
    cursor.execute(
        """SELECT DATA_TYPE FROM information_schema.columns
           WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s""",
        (table, column),
    )
    row = cursor.fetchone()
    return row[0].lower() if row else None


def main():
    conn = mysql.connector.connect(**get_db_config())
    cursor = conn.cursor()

    # 1. Add beds_no / baths_no if missing
    if not column_exists(cursor, "properties", "beds_no"):
        print("Adding column beds_no...")
        cursor.execute("ALTER TABLE properties ADD COLUMN beds_no INT NULL AFTER beds")
    if not column_exists(cursor, "properties", "baths_no"):
        print("Adding column baths_no...")
        cursor.execute("ALTER TABLE properties ADD COLUMN baths_no DECIMAL(4,1) NULL AFTER baths")
    else:
        # If it already exists as INT from a prior run, widen it to DECIMAL
        bt = column_type(cursor, "properties", "baths_no")
        if bt == "int":
            print("Widening baths_no INT -> DECIMAL(4,1)...")
            cursor.execute("ALTER TABLE properties MODIFY COLUMN baths_no DECIMAL(4,1) NULL")

    # 2. Backfill numerics from existing string values BEFORE changing rent type
    print("Backfilling numeric fields from existing records...")
    cursor.execute("SELECT id, rent, beds, baths FROM properties")
    rows = cursor.fetchall()
    print(f"  Found {len(rows)} record(s) to process.")

    updates = []
    for row_id, rent_val, beds_val, baths_val in rows:
        updates.append((
            parse_rent(rent_val),
            parse_beds(beds_val),
            parse_baths(baths_val),
            row_id,
        ))

    # Add a temporary rent_int column to hold parsed rent, then swap
    rent_col_type = column_type(cursor, "properties", "rent")
    if rent_col_type != "int":
        print(f"Converting rent column from {rent_col_type} to INT...")
        if not column_exists(cursor, "properties", "rent_int_tmp"):
            cursor.execute("ALTER TABLE properties ADD COLUMN rent_int_tmp INT NULL AFTER rent")

        # Fill rent_int_tmp + beds_no + baths_no in one pass
        cursor.executemany(
            """UPDATE properties
               SET rent_int_tmp = %s, beds_no = %s, baths_no = %s
               WHERE id = %s""",
            updates,
        )
        conn.commit()

        # Drop old rent, rename rent_int_tmp -> rent
        cursor.execute("ALTER TABLE properties DROP COLUMN rent")
        cursor.execute("ALTER TABLE properties CHANGE COLUMN rent_int_tmp rent INT NULL")
        print("  rent column is now INT.")
    else:
        print("rent column is already INT — updating values in place.")
        cursor.executemany(
            """UPDATE properties
               SET rent = %s, beds_no = %s, baths_no = %s
               WHERE id = %s""",
            updates,
        )

    conn.commit()
    cursor.close()
    conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    main()
