# Minecraft network for Linux

This package is a copy of the Windows network: the hub, CityBuild, BedWars, SkyWars, Hide & Seek, Duels and Parkour, each with its own lobby, behind a Velocity proxy. The ranks are shared through MariaDB. Player data, logs and secrets were left out. The installer creates new secrets.

## Install

You need a 64-bit Linux server (x86 or ARM) running Debian 12+, Ubuntu 22.04+, or Fedora/RHEL/Rocky/Alma/Oracle Linux 9+, with internet access and root rights. Copy the package to the server, then:

```bash
tar xzf mcnet-*.tar.gz
cd mcnet
sudo ./install.sh --owner YourMinecraftName
```

Without `--type` or `--servers`, the installer first asks what this machine should run:

```
What should this machine run?
  1) the full network: hub, CityBuild and the minigames
  2) minigames: hub + bedwars, skywars, hideseek, duels, parkour
  3) CityBuild on its own
  4) choose the servers yourself
```

Then it:

1. Asks you to accept the Minecraft EULA.
2. Installs Java 25 (Eclipse Temurin) and MariaDB.
3. Creates the `minecraft` user and copies the servers into `/opt/mcnet`.
4. Starts the hub, imports the ranks, gives you op and the owner rank, and starts the rest.

Players connect to `<server-ip>:25565`. Only that port is opened in the firewall; every server behind the proxy listens on 127.0.0.1 only. If the machine is at a hosting provider, also allow TCP 25565 in its firewall panel.

### Kinds of setup

| Setup | Command | Players arrive in |
|---|---|---|
| Everything in one network (default) | `sudo ./install.sh --type full` | the hub |
| Minigames only | `sudo ./install.sh --type minigames` | the hub |
| CityBuild only | `sudo ./install.sh --type citybuild` | CityBuild |
| Your own pick | `sudo ./install.sh --servers lobby,bedwars,skywars` | the hub, or the first server if there is no hub |

The server list message (MOTD) is made to match what you installed. `--motd` sets your own.

### Minigames and CityBuild as separate networks

Two networks can run on one machine side by side. Give the second one a `--name`:

```bash
sudo ./install.sh --type minigames --owner Steve
sudo ./install.sh --type citybuild --name citybuild --owner Steve
```

Each network gets:

- its own folder (`/opt/citybuild`)
- its own port: the next free one, here 25585, so players join with `<server-ip>:25585`. `--port` picks one yourself.
- its own ranks database
- its own command: `sudo mcctl-citybuild status`

To put them on two different machines instead, run the first command on one machine and the second, without `--name`, on the other. Then both use port 25565.

In a CityBuild-only network, the travel commands to the hub and the games (`/lobby`, `/bedwars`, …) are left out. Signs or NPCs in CityBuild that use them do nothing.

### Options

| Option | Example | Meaning |
|---|---|---|
| `--type` | `minigames` | `full`, `minigames` or `citybuild` (see above). |
| `--servers` | `lobby,bedwars,skywars` | Pick the servers yourself instead. The proxy is always installed. |
| `--name` | `citybuild` | Name of the network, for a second one on the same machine. Folder, command and services follow it. |
| `--motd` | `'<gold>My server'` | Server list message (MiniMessage colours). |
| `--size` | `tiny` | `auto` (default): the biggest sizes that fit the machine. `normal`: the Windows values. `small`: about half. `tiny`: the full network in 12 GB. |
| `--ram` | `bedwars=4G,lobby=1G` | Change RAM per server, on top of `--size`. |
| `--port` | `25565` | Port players connect to. Default 25565, or the next free one. |
| `--dir` | `/opt/mcnet` | Install folder. Default `/opt/mcnet`, or `/opt/<name>`. |
| `--owner` | `Steve` | Op on every server, plus the owner rank. |
| `--accept-eula` | | Accept the EULA without being asked (for unattended installs). |
| `--no-start` | | Set everything up, but don't start anything. |

### RAM

| Server | normal | small | tiny |
|---|---|---|---|
| lobby (hub) | 2G | 1G | 1G |
| citybuild | 4G | 2G | 1.5G |
| bedwars | 3G | 1.5G | 1G |
| skywars | 2G | 1G | 768M |
| hideseek | 2G | 1G | 768M |
| duels | 2G | 1G | 1G |
| parkour | 1.5G | 1G | 768M |
| proxy | 0.5G | 0.5G | 256M |

Java needs about 360 MB next to each Paper server's RAM (measured with these plugins), and Linux and MariaDB need about 0.75 GB. All together, the machine needs:

| Setup | normal | small | tiny |
|---|---|---|---|
| full network | about 20 GB | about 12.5 GB | about 10.5 GB |
| minigames | about 16 GB | about 10 GB | about 8.5 GB |
| CityBuild only | about 6 GB | about 4 GB | about 3 GB |

The installer checks the machine's memory and picks the biggest sizes that fit.

`tiny` also shortens the view distance to 6 chunks (CityBuild 8), so each player costs less memory. With no players, each server holds 270–450 MB of live data; tiny leaves 300 MB to 1 GB on top of that for players. That's fine for a small community of about 10–20 players at once. With more players, use a bigger machine. For a small machine, install fewer servers; for example `--servers lobby,bedwars,skywars` needs about 8 GB. Hub gates for games you didn't install stay in the world but do nothing.

## Free hosting: Oracle Cloud

Oracle's "Always Free" ARM server has 2 cores and 12 GB of RAM (Oracle cut it from 24 GB in June 2026). With the `tiny` sizes, the full network fits: it needs about 10.5 GB.

1. Create an Oracle Cloud account. It needs a credit card to verify you, but the free server costs nothing.
2. Create an instance: shape **VM.Standard.A1.Flex** with 2 OCPUs and 12 GB, image **Ubuntu 24.04** or **Oracle Linux 9**. If it says "out of capacity", try another availability domain or try again later.
3. Open the port in Oracle's own firewall. Go to **Networking > Virtual cloud networks >** (your network) **> Security > Default security list > Add ingress rules**. Use source `0.0.0.0/0`, protocol TCP, destination port `25565`.
4. Log in with SSH, copy the package over, and install:
   ```bash
   sudo ./install.sh --owner YourMinecraftName
   ```
   The installer picks the `tiny` sizes for the full network (or `small` for minigames only) and opens the port inside the machine too. On Ubuntu, that means Oracle's iptables rules. At the end, it reminds you of step 3.

The 2 cores are the other limit: eight servers share them. With few players that is fine, but the first start, when every server prepares its files at once, takes several minutes. Oracle can reclaim free servers it thinks are idle, so keep backups somewhere else.

## Running it: `sudo mcctl`

| Command | What it does |
|---|---|
| `mcctl status` | Shows what is running and how much memory each server uses. |
| `mcctl start` / `stop` / `restart` `[server]` | Whole network, or one server (`lobby`, `bedwars`, `proxy`, …). |
| `mcctl console lobby` | Live console. Type commands; Ctrl+D leaves and the server keeps running. |
| `mcctl cmd lobby "lp user Steve parent set vip"` | Runs one console command. |
| `mcctl log bedwars` | Follows a server's log. |
| `mcctl backup` | Saves the worlds and packs all servers and the ranks into `/opt/mcnet/backups/`. Keeps the newest 7 (`BACKUP_KEEP` in `network.conf`). |
| `mcctl autostart on` / `off` | Start on boot. On by default. |
| `mcctl autobackup on` / `off` | Run the backup every night at 04:00. On by default. |

For a network installed with `--name citybuild`, the command is `mcctl-citybuild` instead of `mcctl`.

Each server is a systemd service called `mcnet@<server>` (`mcnet-<name>@<server>` for a named network). A crash or `/stop` restarts it after 10 seconds, the same as the Windows restart loop. To change RAM, edit `/opt/mcnet/network.conf`, then run `sudo mcctl restart <server>`.

## Good to know

- `/opt/mcnet/SECRETS.txt` holds the MariaDB password for LuckPerms. Only root can read it, and the same goes for the backups, which contain it too.
- The servers run as the `minecraft` user and can only write inside `/opt/mcnet`, so a bad plugin can't change the rest of the system.
- Copy the backups to another machine now and then. A backup on the same disk doesn't help if the disk dies.
- `SERVER-GUIDE.md` in `/opt/mcnet` describes the worlds, gates, commands and ranks. It talks about the Windows start scripts; on Linux, use `mcctl` instead.
- To move newer builds from Windows:
  1. Make a new package with `python tools/linux/export-linux.py`.
  2. Install it on a fresh machine, or into another `--dir`.
- The installer doesn't overwrite an existing install.
