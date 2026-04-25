# StreetEasy Scraper — Ubuntu Installation

## 1. System dependencies

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
```

## 2. Create a service user

```bash
sudo useradd -r -s /usr/sbin/nologin -m -d /opt/streeteasy streeteasy
```

## 3. Deploy the code

```bash
sudo mkdir -p /opt/streeteasy
sudo cp -r . /opt/streeteasy/
sudo chown -R streeteasy:streeteasy /opt/streeteasy
```

## 4. Set up the Python virtual environment

```bash
sudo -u streeteasy bash -c '
  cd /opt/streeteasy
  python3 -m venv venv
  source venv/bin/activate
  pip install -r requirements.txt
'
```

## 5. Configure environment

```bash
sudo cp /opt/streeteasy/.env.example /opt/streeteasy/.env
sudo nano /opt/streeteasy/.env
```

Set all values — especially `LARAVEL_API_BASE`, `SCRAPER_API_TOKEN`, MySQL credentials, and `SERVER_HOST` (use `0.0.0.0` if the extension connects from another machine).

## 6. Install the systemd service

```bash
sudo cp /opt/streeteasy/streeteasy-scraper.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable streeteasy-scraper
sudo systemctl start streeteasy-scraper
```

## 7. Verify

```bash
sudo systemctl status streeteasy-scraper
journalctl -u streeteasy-scraper -f
```

## Common commands

| Action | Command |
|---|---|
| Start | `sudo systemctl start streeteasy-scraper` |
| Stop | `sudo systemctl stop streeteasy-scraper` |
| Restart | `sudo systemctl restart streeteasy-scraper` |
| Logs (live) | `journalctl -u streeteasy-scraper -f` |
| Logs (last 100) | `journalctl -u streeteasy-scraper -n 100` |
| Status | `sudo systemctl status streeteasy-scraper` |

## 8. Set up daily cron job

```bash
sudo chmod +x /opt/streeteasy/cron-scrape.sh
sudo touch /var/log/streeteasy-cron.log
sudo chown streeteasy:streeteasy /var/log/streeteasy-cron.log
sudo crontab -u streeteasy -e
```

Add this line to run the scrape every day at 6:00 AM (adjust time as needed):

```
0 6 * * * /opt/streeteasy/cron-scrape.sh >> /var/log/streeteasy-cron.log 2>&1
```

Verify the cron is registered:

```bash
sudo crontab -u streeteasy -l
```

Check cron logs:

```bash
tail -f /var/log/streeteasy-cron.log
```

## Updating

```bash
cd /opt/streeteasy
sudo -u streeteasy git pull
sudo -u streeteasy bash -c 'source venv/bin/activate && pip install -r requirements.txt'
sudo systemctl restart streeteasy-scraper
```

## Firewall

If the Chrome extension connects from another machine, open the WS and HTTP ports:

```bash
sudo ufw allow 8765/tcp   # WebSocket
sudo ufw allow 8766/tcp   # HTTP Control API
```
