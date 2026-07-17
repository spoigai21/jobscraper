# Running the monitor free on an Oracle Cloud "Always Free" VM

The monitor is a lightweight outbound-only poller. An Oracle Always-Free VM
gives it a real dedicated public IP (so ntfy.sh won't block it) at $0/month.

## 1. Create the VM (one time, in the Oracle Cloud console)

1. Sign up at <https://www.oracle.com/cloud/free/> (needs a card for identity
   verification; **Always Free** resources are never charged).
2. **Compute → Instances → Create Instance.**
   - **Image:** Canonical **Ubuntu** (22.04 or 24.04).
   - **Shape:** pick an **Always Free-eligible** shape:
     - `VM.Standard.E2.1.Micro` (AMD, 1 GB RAM) — always available, plenty for this, **or**
     - `VM.Standard.A1.Flex` (ARM, e.g. 1 OCPU / 6 GB) — also free, more headroom.
   - **SSH keys:** upload your public key (or let it generate one and download it).
3. Create it, and note the **public IP** it gets assigned.

> No inbound ports are needed — the monitor only makes outbound connections.
> You do **not** need to touch security lists / firewall rules.

## 2. Install the monitor (one command)

SSH in (`ssh ubuntu@<public-ip>`), then run:

```bash
curl -fsSL https://raw.githubusercontent.com/spoigai21/jobscraper/main/deploy/setup.sh | bash
```

This installs Python, clones the repo to `/opt/jobscraper`, builds the venv,
installs a `systemd` service, and enables it on boot.

## 3. Add your secret and start it

```bash
nano /opt/jobscraper/.env        # set NTFY_TOPIC (your existing topic)
sudo systemctl start jobscraper
journalctl -u jobscraper -f      # watch it scrape + deliver a heartbeat
```

Your phone/laptops keep the **same ntfy subscription** — nothing changes on
their side, because you're reusing the same `NTFY_TOPIC`.

## 4. Verify, then retire Railway

- Confirm alerts + heartbeat arrive on your phone from the VM.
- Only then, on Railway, disable the paid static IP and stop/delete the service:
  ```
  railway outbound-network static-ip disable --service jobscraper
  ```
  (or delete the service in the dashboard) so you stop paying.

## Ops cheat-sheet

| Action | Command |
|---|---|
| Status | `systemctl status jobscraper` |
| Logs (live) | `journalctl -u jobscraper -f` |
| Restart | `sudo systemctl restart jobscraper` |
| Update to latest code | `cd /opt/jobscraper && git pull && sudo systemctl restart jobscraper` |
