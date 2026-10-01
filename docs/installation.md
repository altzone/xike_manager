# Installation Guide

## Requirements

- **Docker** and **Docker Compose** (included with Docker Desktop)
- Network access to your Xikestor switch(es)
- A modern web browser (Chrome, Firefox, Safari, Edge)

## Install on Linux

```bash
# Install Docker (if not already installed)
curl -fsSL https://get.docker.com | sh

# Clone and start
git clone https://github.com/altzone/xike_manager.git
cd xike_manager
docker compose up -d
```

Open **http://YOUR_SERVER_IP:8880**

## Install on Windows

1. Download and install [Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/)
2. Open PowerShell or Command Prompt:

```powershell
git clone https://github.com/altzone/xike_manager.git
cd xike_manager
docker compose up -d
```

Open **http://localhost:8880**

> **Note:** If you don't have git, download the ZIP from GitHub and extract it.

## Install on macOS

1. Download and install [Docker Desktop for Mac](https://docs.docker.com/desktop/install/mac-install/)
2. Open Terminal:

```bash
git clone https://github.com/altzone/xike_manager.git
cd xike_manager
docker compose up -d
```

Open **http://localhost:8880**

## Install on Synology NAS

1. Open **Container Manager** (formerly Docker)
2. Go to **Project** > **Create**
3. Upload the `docker-compose.yml` file
4. Set the path to a folder on your NAS
5. Click **Build & Start**

Access at **http://YOUR_NAS_IP:8880**

## Install on Raspberry Pi

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Clone and start
git clone https://github.com/altzone/xike_manager.git
cd xike_manager
docker compose up -d
```

> Works on Raspberry Pi 4/5 with 64-bit OS.

## First Run Setup

1. Open SwitchPilot in your browser
2. You'll be redirected to the **Setup** page
3. Create your **admin account** (username + password)
4. Click **Add Switch**:
   - **Name**: A friendly name (e.g. "Office Switch")
   - **IP Address**: Your switch's IP (e.g. 10.1.10.40)
   - **Username**: Usually `admin`
   - **Password**: Usually `admin` (default Xikestor password)
5. SwitchPilot will test the connection. If successful, you're ready to go!

## Configuration

### Change the Port

Edit `docker-compose.yml`:

```yaml
ports:
  - "3000:80"  # Change 8880 to your preferred port
```

Then restart:
```bash
docker compose down && docker compose up -d
```

### Add SSL/HTTPS

SwitchPilot runs on HTTP by default. For HTTPS, use a reverse proxy:

**With Caddy (easiest):**
```
switch.yourdomain.com {
    reverse_proxy localhost:8880
}
```

**With nginx:**
```nginx
server {
    listen 443 ssl;
    server_name switch.yourdomain.com;
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    location / {
        proxy_pass http://127.0.0.1:8880;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_buffering off;
        proxy_read_timeout 86400s;
    }
}
```

Then tell SwitchPilot which address the proxy connects from, so that login throttling (10 wrong
passwords per account and client address) counts browsers, not the proxy:

```yaml
# docker-compose.yml
      - TRUSTED_PROXIES=172.17.0.1        # the proxy's address or network, comma-separated
```

Without it every browser behind the proxy shares one address, which is fine for one household
but means ten wrong passwords on one account lock that account for everyone for 10 minutes.
Caddy forwards `X-Forwarded-For` on its own; only `TRUSTED_PROXIES` is needed with it.
SwitchPilot sends `X-Frame-Options: DENY`: it opens in its own tab, not inside another
dashboard's iframe.

### Backup

All data is in the `data/` folder. To backup:

```bash
cp -r data/ data-backup-$(date +%Y%m%d)/
```

### Update

```bash
docker compose down
cp -r data/ data-backup-$(date +%Y%m%d)/
git pull
docker compose build --no-cache
docker compose up -d
```

Your data in `data/` is preserved across updates. Read the [Upgrade Guide](upgrade.md) first:
it lists what changed and what to check afterwards (for example the SFP+ port numbering setting).

## Troubleshooting

### Can't connect to switch
- Verify the switch IP is reachable: `ping 10.1.10.40`
- Verify credentials: try logging into the switch's native web UI
- Check that port 80 on the switch is not blocked by a firewall

### Container won't start
```bash
docker compose logs
```

### Lost admin password
If another admin account exists, ask them: **Users → Reset password**.

Otherwise the only way is to start the database over. That loses everything SwitchPilot stores
(switch entries, port descriptions, VLAN and LAG names, snapshots, the change log); the switches
themselves keep their configuration. Take a backup first, then:
```bash
docker compose down
mv data/switchpilot.db data/switchpilot.db.old
docker compose up -d
```
You'll go through the setup wizard again and will have to re-add your switches. Export any
snapshot you care about before doing this (System → Configuration Snapshots).

### Port changes don't persist
Make sure to click "Apply & Save" on the VLAN page, or wait for the changes to auto-save on the Ports page.
