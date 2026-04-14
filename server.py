"""
WebSocket server that orchestrates the Chrome extension.
Also runs an HTTP control API on port 8766 so CLI commands
(scrape, activate, deactivate, status) can talk to the running server.
"""

import asyncio
import json
import logging
import random
import uuid
from http import HTTPStatus
from aiohttp import web
from websockets.asyncio.server import serve
from api_client import ApiClient
from parsers import parse_rent, parse_beds, parse_baths


# Wraps a blocking ApiClient method so it runs in a thread — prevents it from
# blocking the aiohttp event loop (which would make HTTP /scrape endpoint hang).
async def run_blocking(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("server")

# Global state
extension_ws = None
pending_commands = {}  # cmd_id -> asyncio.Future
scrape_running = False
api = ApiClient()

# ─── WebSocket handler (extension connection) ───

async def ws_handler(websocket):
    """Handle the WebSocket connection from the Chrome extension."""
    global extension_ws
    extension_ws = websocket
    log.info("Extension connected")

    try:
        async for raw in websocket:
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "ping":
                await websocket.send(json.dumps({"type": "pong"}))
            elif msg_type == "extension_ready":
                log.info("Extension is ready and standing by.")
            else:
                # Route response to the matching pending command
                cmd_id = msg.get("cmd_id")
                if cmd_id and cmd_id in pending_commands:
                    pending_commands[cmd_id].set_result(msg)
                else:
                    log.warning(f"Received unmatched response: {msg_type} (cmd_id={cmd_id})")
    except Exception as e:
        log.error(f"Connection error: {e}")
    finally:
        extension_ws = None
        log.info("Extension disconnected")


async def send_command(cmd):
    """Send a command to the extension and wait for the matching response.
    Each command is tagged with a unique cmd_id. The extension echoes it back."""
    if not extension_ws:
        log.info(f"  Extension disconnected before {cmd['type']} — waiting for reconnect...")
        if not await wait_for_extension(60):
            raise RuntimeError(f"Extension not available for {cmd['type']}")

    cmd_id = str(uuid.uuid4())
    cmd["cmd_id"] = cmd_id

    # Create a future for this specific command
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    pending_commands[cmd_id] = future

    try:
        await extension_ws.send(json.dumps(cmd))
        log.info(f"Sent command: {cmd['type']} ({cmd_id[:8]})")

        response = await asyncio.wait_for(future, timeout=120)
    except asyncio.TimeoutError:
        raise RuntimeError(f"Timeout waiting for response to {cmd['type']}")
    finally:
        pending_commands.pop(cmd_id, None)

    if response.get("type") == "error":
        raise RuntimeError(f"Extension error: {response.get('message')}")

    return response


# ─── Captcha handling ───

async def check_and_solve_captcha(context=""):
    """Check for captcha and solve if present. Returns True if clear."""
    resp = await send_command({"type": "check_captcha"})
    if not resp.get("has_captcha"):
        return True

    log.info(f"  Captcha detected{' after ' + context if context else ''} — solving...")
    resp = await send_command({"type": "solve_captcha"})

    if not resp.get("success"):
        log.warning(f"  Captcha solve failed: {resp.get('reason')}")
        return False

    log.info(f"  Captcha solved in {resp.get('elapsed')}ms")
    await asyncio.sleep(3)

    resp = await send_command({"type": "check_captcha"})
    if resp.get("has_captcha"):
        log.info("  Second captcha appeared — solving again...")
        resp = await send_command({"type": "solve_captcha"})
        if not resp.get("success"):
            log.warning("  Second captcha solve failed")
            return False
        await asyncio.sleep(3)

    return True


# ─── Scrape pipeline ───

async def wait_for_extension(timeout=60):
    """Wait until the extension is connected, or timeout."""
    elapsed = 0
    while not extension_ws and elapsed < timeout:
        log.info("  Waiting for extension to connect...")
        await asyncio.sleep(3)
        elapsed += 3
    return extension_ws is not None


async def trigger_scrape():
    """Safe wrapper — prevents overlapping runs."""
    global scrape_running
    if scrape_running:
        log.warning("Scrape already in progress — ignoring.")
        return

    scrape_running = True
    log.info("Scrape triggered.")

    try:
        if not extension_ws:
            log.info("Extension not connected — waiting up to 60s...")
            if not await wait_for_extension(60):
                log.error("Extension did not connect within timeout. Aborting scrape.")
                return

        await run_scrape_pipeline()
        log.info("Scrape finished successfully.")
    except Exception as e:
        log.error(f"Scrape failed: {e}")
    finally:
        scrape_running = False


async def run_scrape_pipeline():
    """Main scraping pipeline. Scrapes all active URLs."""
    urls = await run_blocking(api.get_active_urls)

    if not urls:
        log.info("No active URLs to scrape.")
        return

    # Randomize order to avoid predictable scraping patterns
    urls = list(urls)
    random.shuffle(urls)
    log.info(f"Found {len(urls)} active URL(s) to scrape (randomized order)")
    await run_blocking(api.log,"info", "pipeline_start", f"Scrape run started for {len(urls)} URL(s)")

    for row in urls:
        url_id = row["id"]
        url = row["url"]
        name = row["name"]

        log.info(f"[{url_id}] Scraping: {name} -> {url}")
        await run_blocking(api.update_url_status,url_id, "in_progress")
        await run_blocking(api.log,"info", "url_start", f"Scraping: {name}", url_id=url_id, context={"url": url})

        try:
            # Step 1: Navigate directly to the URL
            resp = await send_command({"type": "navigate", "url": url})
            log.info(f"  Navigation complete")
            await run_blocking(api.log,"info", "navigate_done", "Page loaded", url_id=url_id)

            # Captcha check — after navigation
            if not await check_and_solve_captcha("navigation"):
                await run_blocking(api.update_url_status,url_id, "failed")
                await run_blocking(api.log,"error", "captcha_fail", "Captcha solve failed after navigation", url_id=url_id)
                continue

            # Step 2: Click all "Show more" buttons (with captcha handling mid-loop)
            total_show_more_clicks = 0
            while True:
                resp = await send_command({"type": "click_show_more"})
                total_show_more_clicks += resp.get("clicked", 0)

                if resp.get("captcha_detected"):
                    log.info(f"  Captcha appeared after {total_show_more_clicks} click(s) — solving...")
                    await run_blocking(api.log,"warn", "captcha_mid_loop", f"Captcha appeared after {total_show_more_clicks} click(s)", url_id=url_id)
                    if not await check_and_solve_captcha("click_show_more"):
                        break
                    continue
                else:
                    break

            log.info(f"  Clicked 'Show more' buttons {total_show_more_clicks} time(s) total")
            await run_blocking(api.log,"info", "show_more_done", f"Clicked 'Show more' {total_show_more_clicks} time(s)", url_id=url_id, context={"clicks": total_show_more_clicks})

            if not await check_and_solve_captcha("post_click_show_more"):
                await run_blocking(api.update_url_status,url_id, "failed")
                await run_blocking(api.log,"error", "captcha_fail", "Captcha solve failed after show-more loop", url_id=url_id)
                continue

            # Step 3: Extract property data
            resp = await send_command({"type": "extract_data"})
            properties = resp.get("properties", [])
            log.info(f"  Extracted {len(properties)} properties")
            await run_blocking(api.log,"info", "extract_done", f"Extracted {len(properties)} properties", url_id=url_id, context={"count": len(properties)})

            if not properties:
                await run_blocking(api.log,"warn", "no_properties", "Zero properties extracted — page may have changed structure", url_id=url_id)

            # Step 4: Enrich with numeric fields, then send to Laravel API
            for p in properties:
                p["rent"] = parse_rent(p.get("rent"))
                p["beds_no"] = parse_beds(p.get("beds"))
                p["baths_no"] = parse_baths(p.get("baths"))
            await run_blocking(api.save_properties, url_id, properties)
            await run_blocking(api.update_url_status,url_id, "completed")
            log.info(f"  Saved to database. Done.")
            await run_blocking(api.log,"info", "url_done", f"Saved {len(properties)} properties", url_id=url_id, context={"count": len(properties)})

            # Step 5: Cooldown — wait 30-60 seconds before next page
            cooldown = random.randint(30, 60)
            log.info(f"  Cooling down for {cooldown}s...\n")
            await asyncio.sleep(cooldown)

        except Exception as e:
            log.error(f"  FAILED: {e}\n")
            await run_blocking(api.update_url_status,url_id, "failed")
            await run_blocking(api.log,"error", "url_fail", str(e), url_id=url_id, context={"name": name, "url": url})

    log.info("All URLs processed.")
    await run_blocking(api.log,"info", "pipeline_done", "All URLs processed")


# ─── HTTP Control API (port 8766) ───

async def handle_scrape(request):
    """POST /scrape — trigger a scrape run."""
    if scrape_running:
        return web.json_response({"ok": False, "message": "Scrape already in progress"})
    asyncio.create_task(trigger_scrape())
    return web.json_response({"ok": True, "message": "Scrape started"})


async def handle_status(request):
    """GET /status — reports LOCAL state only (no external calls).
    Laravel is the source of truth for URL counts."""
    return web.json_response({
        "extension": "connected" if extension_ws else "disconnected",
        "scraper": "running" if scrape_running else "idle",
    })


def create_http_app():
    app = web.Application()
    app.router.add_post("/scrape", handle_scrape)
    app.router.add_get("/status", handle_status)
    return app


# ─── Main ───

async def main():
    # Bind to 0.0.0.0 to listen on all network interfaces —
    # accessible via localhost, 127.0.0.1, or the machine's LAN IP.
    log.info("Starting WebSocket server on ws://0.0.0.0:8765")
    ws_server = await serve(ws_handler, "0.0.0.0", 8765)

    log.info("Starting HTTP control API on http://0.0.0.0:8766")
    http_app = create_http_app()
    runner = web.AppRunner(http_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8766)
    await site.start()

    log.info("Server is running. Use CLI commands from another terminal.")
    log.info("  python main.py scrape       — start scraping")
    log.info("  python main.py status       — check status")
    log.info("  python main.py activate 3   — activate a URL")
    log.info("  python main.py deactivate 3 — deactivate a URL")

    # Run forever
    await asyncio.get_running_loop().create_future()


if __name__ == "__main__":
    asyncio.run(main())
