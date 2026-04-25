"""
CLI entry point for the StreetEasy scraper.

Usage:
    python main.py setup                        - Create database and tables
    python main.py serve                        - Start the server (runs forever)

    --- These talk to the running server ---
    python main.py scrape                       - Trigger scraping now
    python main.py status                       - Check server/extension/scraper state

    --- Local DB commands (Laravel UI is preferred for these) ---
    python main.py add "Name" "URL"             - Add a URL to scrape
    python main.py list                         - List all URLs
    python main.py results [--date YYYY-MM-DD]  - Show scraped results
"""

import sys
import os
import asyncio
import urllib.request
import urllib.error
import json
from datetime import date, datetime
from dotenv import load_dotenv
from db_setup import create_database
from db_manager import DBManager

load_dotenv()

_host = os.getenv("SERVER_HOST", "127.0.0.1")
_port = os.getenv("HTTP_PORT", "8766")
_cli_host = "127.0.0.1" if _host == "0.0.0.0" else _host
SERVER_URL = f"http://{_cli_host}:{_port}"


def print_usage():
    print(__doc__)


def server_request(method, path, expect_json=True):
    """Send a request to the running server's HTTP control API."""
    url = f"{SERVER_URL}{path}"
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode()
            return json.loads(body) if expect_json else body
    except urllib.error.URLError:
        print("Error: Server is not running. Start it with: python main.py serve")
        sys.exit(1)


# --- Local commands (don't need server running) ---

def cmd_setup():
    create_database()


def cmd_add(args):
    if len(args) < 2:
        print('Usage: python main.py add "Name" "URL"')
        return
    db = DBManager()
    name, url = args[0], args[1]
    row_id = db.add_url(name, url)
    print(f"Added: {name} -> {url} (id: {row_id})")


def cmd_list():
    db = DBManager()
    urls = db.get_all_urls()
    if not urls:
        print("No URLs in database.")
        return
    print(f"\n{'ID':<5} {'Active':<8} {'Last Status':<14} {'Last Scraped':<22} {'Name':<30} {'URL'}")
    print("-" * 130)
    for u in urls:
        active = "Yes" if u["is_active"] else "No"
        status = u["last_status"] or "never"
        scraped = str(u["last_scraped_at"] or "-")
        print(f"{u['id']:<5} {active:<8} {status:<14} {scraped:<22} {u['name']:<30} {u['url']}")
    print()


def cmd_results(args):
    db = DBManager()
    scrape_date = date.today()
    url_id = None

    i = 0
    while i < len(args):
        if args[i] == "--date" and i + 1 < len(args):
            scrape_date = datetime.strptime(args[i + 1], "%Y-%m-%d").date()
            i += 2
        elif args[i] == "--url_id" and i + 1 < len(args):
            url_id = int(args[i + 1])
            i += 2
        else:
            i += 1

    if url_id:
        props = db.get_properties_by_url(url_id, scrape_date)
    else:
        props = db.get_properties_by_date(scrape_date)

    if not props:
        print(f"No results found for {scrape_date}.")
        return

    print(f"\nResults for: {scrape_date}")
    print(f"{'Name':<12} {'Rent':<12} {'Beds':<10} {'Baths':<10} {'Area':<12} {'Listed By'}")
    print("-" * 80)
    for p in props:
        print(
            f"{p['property_name']:<12} "
            f"{p['rent']:<12} "
            f"{p['beds']:<10} "
            f"{p['baths']:<10} "
            f"{p['area']:<12} "
            f"{p['listed_by']}"
        )
    print(f"\nTotal: {len(props)} properties")


def cmd_serve():
    from server import main as server_main
    asyncio.run(server_main())


# --- Remote commands (talk to running server) ---

def cmd_scrape():
    resp = server_request("POST", "/scrape")
    print(resp.get("message", resp))


def cmd_status():
    resp = server_request("GET", "/status")
    print(f"  Extension : {resp['extension']}")
    print(f"  Scraper   : {resp['scraper']}")


def main():
    if len(sys.argv) < 2:
        print_usage()
        return

    command = sys.argv[1]
    args = sys.argv[2:]

    commands = {
        # Local (direct DB)
        "setup": lambda: cmd_setup(),
        "add": lambda: cmd_add(args),
        "list": lambda: cmd_list(),
        "results": lambda: cmd_results(args),
        "serve": lambda: cmd_serve(),
        # Remote (talk to running server)
        "scrape": lambda: cmd_scrape(),
        "status": lambda: cmd_status(),
    }

    if command in commands:
        commands[command]()
    else:
        print(f"Unknown command: {command}")
        print_usage()


if __name__ == "__main__":
    main()
