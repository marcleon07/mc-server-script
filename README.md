# Minecraft network tools

These are the tools behind a small Minecraft network: one hub, CityBuild and one server per game mode (BedWars, SkyWars, Hide & Seek, Duels, Parkour), all behind a Velocity proxy. The ranks are shared through LuckPerms on MariaDB.

| Folder / file | What it is |
|---|---|
| [`serverlink/`](serverlink/) | A Paper plugin that adds travel commands (`/bedwars`, `/lobby`, …) to send players between servers. It can also teleport them, or run a command for them, when they arrive. |
| [`linux/`](linux/) | Packs a network from Windows and installs it on a Linux server with systemd, plus `mcctl` to control it. |
| [`lobbygen.py`](lobbygen.py) | Builds the hub: a plaza with gates to every game mode, as console commands, plus a top-down preview. |
| [`gamelobby.py`](gamelobby.py) | Builds the small themed lobby of one game server, with join signs. |
| [`png.py`](png.py) | Turns the hub preview into a PNG image. |
| [`backup.py`](backup.py) | Backs up the network on Windows: server folders, proxy and the LuckPerms database, keeping the newest 7. |

This repository holds only the tools. It does not include the servers, plugins, maps or Minecraft itself. Get those from their own sources and follow their licences.

Requirements:

- Paper 26.2 and Velocity 3.x / 4.x
- Java 25 to run the servers; Java 21+ to build ServerLink
- Python 3.9+

## ServerLink

ServerLink sends a player to another server behind Velocity, using the proxy's `BungeeCord` plugin channel. On the way, it can:

- teleport them to a world or a location when they arrive, or
- run a command as them when they arrive, for example `/bedwars join cave` from the hub joins that arena on the BedWars server.

It works from commands, command signs and NPCs. Signs run their commands on the backend server, so a sign can't use the proxy's `/server`.

### Setting up the proxy and servers

- **Velocity:** set `bungee-plugin-message-channel = true`.
- **Every server:** set `shared-folder` to the same folder, relative to the server's own folder (for example `../shared`). ServerLink uses it to pass "what to do on arrival" from one server to the next.

### Config (`plugins/ServerLink/config.yml`)

```yaml
shared-folder: ../shared
links:
  lobby:                       # the command: /lobby
    server: lobby              # Velocity server name
    aliases: [hub, l]
  bedwars:
    server: bedwars
    command: bw {args}         # "/bedwars join cave" runs "/bw join cave" there; "/bedwars" alone just travels
  farmworld:
    server: citybuild
    world: farmworld           # arrive at that world's spawn (Multiverse)
  arena:
    server: duels
    location: arenas 0.5 65 0.5 90 0   # world x y z [yaw pitch]
send-home:                     # optional: players standing near <location> are sent to <server>
  enabled: false
  server: lobby
  location: lobby 0.5 -4 9.5
  radius: 6
  grace-seconds: 5
```

Each link can also have `default-args`, which is used for `{args}` when the player typed nothing.

### Building

```bash
cd serverlink
mvn package              # -> target/ServerLink.jar
```

Without Maven, `./build.sh <a Paper server's libraries folder>` produces `ServerLink.jar`.

## Linux deployment

`linux/export-linux.py` must sit in `tools/linux/` inside the network folder. That folder has to contain `proxy/` and one `<name>-server/` folder for each server listed in `proxy/velocity.toml`.

The export:

- packs the worlds, plugins and configs into one `.tar.gz`;
- leaves out player data and every secret;
- leaves out the EssentialsX first-join kit outside CityBuild.

On the Linux server, `install.sh` does the rest:

- installs Java 25 and MariaDB;
- asks you to accept the Minecraft EULA;
- creates new secrets;
- installs the whole network, only the minigames or only CityBuild (`--type`), or your own pick of servers;
- can run several networks side by side on one machine (`--name`), each with its own ports and ranks;
- sets up one systemd service per server;
- opens only the proxy port.

[`linux/README.md`](linux/README.md) has all options and the `mcctl` commands.

Don't publish the generated `.tar.gz`. It contains third-party plugins and maps.

## Lobby builders

```bash
python lobbygen.py -5 hub_cmds.txt hub_preview.html        # ground at y=-5 (flat world)
python png.py hub_preview.html hub_preview.png
python gamelobby.py bedwars bedwars_cmds.txt               # bedwars | skywars | hideseek | duels | parkour
```

Paste the generated commands into that server's console, or send them through RCON. The scripts force-load the area themselves. The sign commands and theme colours are at the top of each script.

## License

MIT, see [LICENSE](LICENSE).
