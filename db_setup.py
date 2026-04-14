"""
Database setup script for StreetEasy scraper.
Creates the MySQL database and tables.
"""

import mysql.connector
from config import get_db_config


def create_database():
    """Create the database if it doesn't exist."""
    cfg = get_db_config()
    db_name = cfg.pop("database")

    conn = mysql.connector.connect(**cfg)
    cursor = conn.cursor()

    cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}`")
    cursor.execute(f"USE `{db_name}`")

    # Table: scrape_urls - URLs we want to scrape
    # url_hash is SHA-256 of the URL for uniqueness (avoids key length limit on long URLs)
    # last_status reflects outcome of the most recent scrape (not a gate)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scrape_urls (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            url VARCHAR(2048) NOT NULL,
            url_hash CHAR(64) GENERATED ALWAYS AS (SHA2(url, 256)) STORED UNIQUE,
            is_active TINYINT(1) DEFAULT 1,
            last_status ENUM('never', 'in_progress', 'completed', 'failed') DEFAULT 'never',
            last_scraped_at TIMESTAMP NULL DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    # Table: properties - Extracted property data
    # scrape_date tracks which day's data this is — same-day re-scrape overwrites,
    # previous days' data is preserved
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS properties (
            id INT AUTO_INCREMENT PRIMARY KEY,
            url_id INT NOT NULL,
            scrape_date DATE NOT NULL,
            property_name VARCHAR(255),
            rent INT NULL,
            beds VARCHAR(50),
            beds_no INT NULL,
            baths VARCHAR(50),
            baths_no DECIMAL(4,1) NULL,
            area VARCHAR(50),
            listing_url VARCHAR(2048),
            listed_by VARCHAR(255),
            availability VARCHAR(100),
            specials TEXT,
            original TINYINT(1) NOT NULL DEFAULT 1,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (url_id) REFERENCES scrape_urls(id) ON DELETE CASCADE,
            INDEX idx_url_date (url_id, scrape_date),
            INDEX idx_scrape_date (scrape_date),
            INDEX idx_property_name (property_name)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    conn.commit()
    cursor.close()
    conn.close()
    print(f"Database '{db_name}' and tables created successfully.")


if __name__ == "__main__":
    create_database()
