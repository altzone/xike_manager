# Installation Guide

For a new installation. **Already running SwitchPilot?** Follow the [upgrade guide](upgrade.md)
instead: it keeps your data.

## What you need

- **Docker** with **Docker Compose**: included in Docker Desktop (Windows, macOS) and installed by
  Docker's own script on Linux.
- A machine that can reach your Xikestor switch(es) over the network. A factory-new switch answers
  on `192.168.10.12`.
- A web browser (Chrome, Firefox, Safari, Edge).

SwitchPilot runs as one container (web page + API) and keeps its data in a `data/` folder next to
`docker-compose.yml`. The first start builds the image, which takes a few minutes.

## 1. Install

### Linux

```bash
curl -fsSL https://get.docker.com | sh       # install Docker, if it is not installed yet

git clone https://github.com/altzone/xike_manager.git
cd xike_manager
docker compose up -d
```

Open **http://YOUR_SERVER_IP:8880**.

### Raspberry Pi

A Raspberry Pi 4 or 5 with a **64-bit** OS:

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER                # then log out and in again, to use docker without sudo

git clone https://github.com/altzone/xike_manager.git
cd xike_manager
docker compose up -d
```

Open **http://YOUR_PI_IP:8880**.

### Windows

1. Download and install [Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/).
2. **Start Docker Desktop** from the Start menu and wait until it shows **"Engine running"**.
   The first start asks to install or update **WSL 2**: run `wsl --update` (or `wsl --install`)
   in an administrator PowerShell, then reboot.
3. Open PowerShell and check that the engine answers: `docker version` must show a **`Server:`**
   section.
4. Install and start SwitchPilot:

   ```powershell
   git clone https://github.com/altzone/xike_manager.git
   cd xike_manager
   docker compose up -d --build
   docker compose ps        # wait for "healthy" (the first build takes a few minutes)
   ```

Open **http://localhost:8880**. No git? Download the ZIP from GitHub (**Code → Download ZIP**),
extract it, and run the `docker compose` lines from the extracted folder.

| Message | Fix |
|---|---|
| `failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine` | Docker Desktop is not running: start it and wait for "Engine running", then run the command again. |
| Docker Desktop does not start | Enable virtualization: Task Manager → Performance → CPU must show "Virtualization: Enabled" (otherwise turn on Intel VT-x / AMD SVM in the BIOS), and update WSL (`wsl --update`). |
| `docker version` shows `OS/Arch: windows/amd64` under `Server:` | Right-click the Docker icon in the taskbar → **Switch to Linux containers**. |
| The switch cannot be reached | A factory-new Xikestor switch is at `192.168.10.12`. Give the PC an extra address in that network on the Ethernet adapter connected to it (for example `192.168.10.100` / `255.255.255.0`); the container uses the PC's network. |

### macOS

1. Download and install [Docker Desktop for Mac](https://docs.docker.com/desktop/install/mac-install/)
   and start it.
2. In Terminal:

   ```bash
   git clone https://github.com/altzone/xike_manager.git
   cd xike_manager
   docker compose up -d
   ```

Open **http://localhost:8880**.

### Synology NAS

Container Manager builds the image from the source files, so it needs the whole folder, not only
`docker-compose.yml`:

1. Download the ZIP from GitHub (**Code → Download ZIP**) and, with **File Station**, extract it
   into a folder on the NAS, for example `docker/switchpilot`.
2. Open **Container Manager → Project → Create**. Give it a name, choose that folder as the path
   and keep the `docker-compose.yml` it contains.
3. Confirm and let it build, then start the project.

Open **http://YOUR_NAS_IP:8880**. If port 8880 is taken on the NAS, change it first (see
[Change the port](#change-the-port)).

## 2. First start

1. Open SwitchPilot in your browser: it shows the **Setup** page.
2. Create the **admin account**: the username and password you will use for SwitchPilot (not the
   switch's).
3. Click **Add Switch**:
   - **Name**: a name you choose, for example "Office switch".
   - **IP address**: the switch's address (`192.168.10.12` on a factory-new switch).
   - **Username / Password**: the switch's own login (`admin` / `admin` on a factory-new switch).
   - **SFP+ ports 9 and 10**: leave **Automatic**; SwitchPilot picks the numbering from the
     switch's firmware.
4. SwitchPilot checks the connection and reads the switch. The dashboard, ports, VLANs, LAG,
   monitoring and system settings are then available.

Add more users (admins or read-only viewers) under **Users**.

## 3. Options

### Change the port

In `docker-compose.yml`:

```yaml
    ports:
      - "3000:80"  # 3000 instead of 8880
```

Then `docker compose up -d` again.

### HTTPS behind a reverse proxy

SwitchPilot speaks HTTP. For HTTPS, put a reverse proxy in front of it.

**Caddy** (gets a certificate on its own):
```
switch.yourdomain.com {
    reverse_proxy localhost:8880
}
```

**nginx:**
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
# docker-compose.yml, under environment:
      - TRUSTED_PROXIES=172.17.0.1        # the proxy's address or network, comma-separated
```

Without it every browser behind the proxy shares one address, which is fine for one household
but means ten wrong passwords on one account lock that account for everyone for 10 minutes.
Caddy forwards `X-Forwarded-For` on its own; only `TRUSTED_PROXIES` is needed with it.
SwitchPilot sends `X-Frame-Options: DENY`: it opens in its own tab, not inside another
dashboard's iframe.

### Stopping

`docker compose down` stops SwitchPilot. If a change is still being sent to a switch, it is
finished first (150 seconds at most; usually a second or two). With `docker run` or another tool,
give the container the same time, for example `docker stop -t 150 switchpilot`.

## 4. Keep it up to date

See the [upgrade guide](upgrade.md). In short, from the `xike_manager` folder:

```bash
docker compose down
cp -r data/ data-backup-$(date +%Y%m%d)/
git pull
docker compose build --no-cache
docker compose up -d
```

The version you run is shown at the bottom of the side menu, and the [change log](../CHANGELOG.md)
lists what each version brings. SwitchPilot is not updated automatically: a Watchtower container
that updates everything else leaves it alone.

## 5. Backup and restore

Everything SwitchPilot stores is in the `data/` folder: the database (users, switches, VLAN and
LAG names, port descriptions, snapshots, change log) and the session key. The switches keep their
own configuration.

**Backup**, with SwitchPilot stopped or running:

```bash
cp -r data/ data-backup-$(date +%Y%m%d)/
```

SwitchPilot also copies its database to `data/backups/` by itself before an update changes it
(`switchpilot-<previous>-to-<new>-<date>.db`, the 5 newest kept). These files hold the switches'
passwords: keep any copy you take somewhere private.

**Restore** a copy:

```bash
docker compose down
ls data/backups/                                          # the copies, newest last
cp data/backups/<the copy you want> data/switchpilot.db
docker compose up -d
```

A copy is the database as it was before the update named in its file name: restore it with the
version you ran then (see [rolling back](upgrade.md#4-rolling-back)).

## Troubleshooting

### Can't connect to the switch
- Check that the switch answers: `ping 192.168.10.12` (or its address).
- Check its login on the switch's own web page.
- Check that nothing blocks port 80 between the machine running SwitchPilot and the switch.

### The container does not start
```bash
docker compose logs
```

### Lost admin password
If another admin account exists, ask them: **Users → Reset password**.

Otherwise the only way is to start the database over. That loses everything SwitchPilot stores
(switch entries, port descriptions, VLAN and LAG names, snapshots, the change log); the switches
themselves keep their configuration. Export any snapshot you care about first (System →
Configuration Snapshots), take a backup, then:
```bash
docker compose down
mv data/switchpilot.db data/switchpilot.db.old
docker compose up -d
```
You go through the setup page again and add your switches again.

### Port changes don't persist
Click **Apply & Save** on the VLAN page; on the Ports page changes are saved to the switch when
applied.
