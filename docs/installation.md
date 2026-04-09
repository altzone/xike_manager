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
        proxy_buffering off;
        proxy_read_timeout 86400s;
    }
}
```

### Backup

All data is in the `data/` folder. To backup:

```bash
cp -r data/ data-backup-$(date +%Y%m%d)/
```

### Update

```bash
git pull
docker compose down
docker compose build --no-cache
docker compose up -d
```

Your data in `data/` is preserved across updates.

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
Delete the database and restart:
```bash
rm data/switchpilot.db
docker compose restart
```
You'll go through the setup wizard again. Switch configurations are on the switches themselves, not in SwitchPilot.

### Port changes don't persist
Make sure to click "Apply & Save" on the VLAN page, or wait for the changes to auto-save on the Ports page.
