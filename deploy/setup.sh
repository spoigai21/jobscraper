#!/usr/bin/env bash
# One-shot setup for the internship monitor on a fresh Ubuntu VM
# (Oracle Cloud Always Free, or any Linux box). Idempotent: re-run to update.
#
#   curl -fsSL https://raw.githubusercontent.com/spoigai21/jobscraper/main/deploy/setup.sh | bash
#   # ...or clone the repo and run: bash deploy/setup.sh
#
# The monitor is outbound-only (scrapes career pages, publishes to ntfy).
# It needs NO inbound ports, so no firewall / Oracle security-list changes.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/jobscraper}"
REPO="${REPO:-https://github.com/spoigai21/jobscraper.git}"
RUN_USER="${RUN_USER:-$(id -un)}"

echo ">> Installing system packages (python3, venv, git)..."
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip git

echo ">> Setting up $APP_DIR (owner: $RUN_USER)..."
sudo mkdir -p "$APP_DIR"
sudo chown "$RUN_USER":"$RUN_USER" "$APP_DIR"

if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" pull --ff-only
else
  git clone "$REPO" "$APP_DIR"
fi

cd "$APP_DIR"
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt

if [ ! -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  # On a VM the DB is just a local file, not a Railway volume.
  sed -i 's|^MONITOR_DB_PATH=.*|MONITOR_DB_PATH='"$APP_DIR"'/monitor.db|' "$APP_DIR/.env" || true
  echo "!! Created $APP_DIR/.env from the example."
  echo "!! EDIT IT and set NTFY_TOPIC (same topic your phone/laptops subscribe to) before starting."
fi

echo ">> Installing systemd service..."
sudo cp "$APP_DIR/deploy/jobscraper.service" /etc/systemd/system/jobscraper.service
sudo sed -i "s|__APP_DIR__|$APP_DIR|g; s|__RUN_USER__|$RUN_USER|g" \
  /etc/systemd/system/jobscraper.service
sudo systemctl daemon-reload
sudo systemctl enable jobscraper

cat <<EOF

>> Setup complete. Final steps:
   1) Edit secrets:        nano $APP_DIR/.env      (set NTFY_TOPIC)
   2) Start the monitor:   sudo systemctl start jobscraper
   3) Watch it run:        journalctl -u jobscraper -f
   You should see companies scraped and a heartbeat delivered to your phone.
EOF
