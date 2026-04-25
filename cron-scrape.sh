#!/usr/bin/env bash
# Daily scrape trigger — called by cron.
# Logs output to /var/log/streeteasy-cron.log
#
# Install:
#   sudo cp /opt/streeteasy/cron-scrape.sh /opt/streeteasy/
#   sudo chmod +x /opt/streeteasy/cron-scrape.sh
#   sudo crontab -u streeteasy -e
#   # Add:  0 6 * * * /opt/streeteasy/cron-scrape.sh >> /var/log/streeteasy-cron.log 2>&1

set -euo pipefail

INSTALL_DIR="/opt/streeteasy"
VENV="$INSTALL_DIR/venv/bin/python"
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"

cd "$INSTALL_DIR"

# Check the server is running before triggering
STATUS=$("$VENV" main.py status 2>&1) || {
    echo "$LOG_PREFIX ERROR: Server not running. Skipping scrape."
    exit 1
}

echo "$LOG_PREFIX Server status: $STATUS"
echo "$LOG_PREFIX Triggering daily scrape..."

"$VENV" main.py scrape 2>&1
echo "$LOG_PREFIX Scrape triggered."
