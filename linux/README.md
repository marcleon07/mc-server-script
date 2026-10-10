# Minecraft network for Linux

This package is a copy of the Windows network: the hub, CityBuild, BedWars, SkyWars, Hide & Seek, Duels and Parkour, each with its own lobby, behind a Velocity proxy. The ranks are shared through MariaDB. Player data, logs and secrets were left out. The installer creates new secrets.

## Install

You need a 64-bit Linux server running Debian 12+, Ubuntu 22.04+, or Fedora/RHEL/Rocky/Alma 9+, with internet access and root rights. Copy the package to the server, then:

```bash
tar xzf mcnet-*.tar.gz
cd mcnet
sudo ./install.sh --owner YourMinecraftName
```

The installer:

1. Asks you to accept the Minecraft EULA.
2. Installs Java 25 (Eclipse Temurin) and MariaDB.
3. Creates the `minecraft` user and copies the network into `/opt/mcnet`.
4. Starts the hub, imports the ranks, gives you op and the owner rank, and starts the rest.

Players connect to `<server-ip>:25565`. Only that port is opened in the firewall; every server behind the proxy listens on 127.0.0.1 only. If the machine is at a hosting provider, also allow TCP 25565 in its firewall panel.

### Options

| Option | Example | Meaning |
|---|---|---|
| `--servers` | `lobby,bedwars,skywars` | Install only some servers. The hub and the proxy are always installed. |
| `--ram` | `bedwars=4G,lobby=1G` | Change RAM per server. |
| `--port` | `25565` | Port players connect to. |
| `--dir` | `/opt/mcnet` | Install folder. |
| `--owner` | `Steve` | Op on every server, plus the owner rank. |
| `--accept-eula` | | Accept the EULA without being asked (for unattended installs). |
| `--no-start` | | Set everything up, but don't start anything. |

### RAM

| Server | RAM |
|---|---|
| lobby (hub) | 2G |
| citybuild | 4G |
| bedwars | 3G |
| skywars | 2G |
| hideseek | 2G |
| duels | 2G |
| parkour | 1.5G |
| proxy | 0.5G |

The full network needs about 17 GB plus 1–2 GB for Linux and MariaDB. For a small machine, install fewer servers; for example `--servers lobby,bedwars,skywars` needs about 8 GB. Hub gates for games you didn't install stay in the world but do nothing.

## Running it: `sudo mcctl`

| Command | What it does |
|---|---|
| `mcctl status` | Shows what is running. |
| `mcctl start` / `stop` / `restart` `[server]` | Whole network, or one server (`lobby`, `bedwars`, `proxy`, …). |
| `mcctl console lobby` | Live console. Type commands; Ctrl+D leaves and the server keeps running. |
| `mcctl cmd lobby "lp user Steve parent set vip"` | Runs one console command. |
| `mcctl log bedwars` | Follows a server's log. |
| `mcctl backup` | Saves the worlds and packs all servers and the ranks into `/opt/mcnet/backups/`. |
| `mcctl autostart on` / `off` | Start on boot. On by default. |

Each server is a systemd service called `mcnet@<name>`. A crash or `/stop` restarts it after 10 seconds, the same as the Windows restart loop. To change RAM, edit `/opt/mcnet/network.conf`, then run `sudo mcctl restart <server>`.

## Good to know

- `/opt/mcnet/SECRETS.txt` holds the MariaDB password for LuckPerms. Only root can read it.
- `SERVER-GUIDE.md` in `/opt/mcnet` describes the worlds, gates, commands and ranks. It talks about the Windows start scripts; on Linux, use `mcctl` instead.
- To move newer builds from Windows:
  1. Make a new package with `python tools/linux/export-linux.py`.
  2. Install it on a fresh machine, or into another `--dir`.
- The installer doesn't overwrite an existing install.
