#!/usr/bin/env bash
# Installs the Minecraft network from this package on a Linux server.
# Debian 12+/Ubuntu 22.04+ (apt) or Fedora/RHEL/Rocky/Alma/Oracle Linux 9+ (dnf), 64-bit (x86 or ARM),
# with internet access. Also runs on Oracle Cloud's free ARM servers (see README.md).
#
#   sudo ./install.sh [options]          without --type or --servers it asks what to install
#     --type TYPE           full       hub + CityBuild + all minigames (default)
#                           minigames  hub + the minigames, no CityBuild
#                           citybuild  CityBuild on its own (players arrive there)
#     --servers LIST        pick the servers yourself, e.g. lobby,bedwars,skywars
#     --name NAME           name of this network (default mcnet). A second network on the same machine
#                           needs its own name, e.g. --name citybuild; it gets its own ports, ranks
#                           database and command (mcctl-citybuild)
#     --owner NAME          your Minecraft name: op everywhere + the owner rank
#     --size SIZE           auto       the biggest sizes that fit this machine (default)
#                           normal     the RAM the servers have on Windows
#                           small      about half
#                           tiny       the full network in 12 GB (Oracle's free server), shorter view distance
#     --ram LIST            change RAM per server on top, e.g. bedwars=4G,lobby=1G,proxy=512M
#     --port N              port players connect to (default 25565, or the next free one)
#     --motd TEXT           server list message (default: made from the installed servers)
#     --dir PATH            install folder (default /opt/mcnet, or /opt/<name>)
#     --accept-eula         accept the Minecraft EULA without asking (https://aka.ms/MinecraftEULA)
#     --no-start            set everything up but do not start the servers
set -euo pipefail
PKG="$(cd "$(dirname "$0")" && pwd)"
NAME=mcnet DIR="" TYPE="" SERVERS="" PORT="" OWNER="" SIZE=auto RAM="" MOTD="" EULA=no START=yes
REGISTRY=/etc/mcnet/networks   # every installed network's folder, so a new one picks free ports

die() { echo "install: $*" >&2; exit 1; }
while [ $# -gt 0 ]; do
  case "$1" in
    --type) TYPE="$2"; shift 2 ;;
    --servers) SERVERS="$2"; shift 2 ;;
    --name) NAME="$2"; shift 2 ;;
    --owner) OWNER="$2"; shift 2 ;;
    --size) SIZE="$2"; shift 2 ;;
    --ram) RAM="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --motd) MOTD="$2"; shift 2 ;;
    --dir) DIR="$2"; shift 2 ;;
    --accept-eula) EULA=yes; shift ;;
    --no-start) START=no; shift ;;
    -h|--help) sed -n '2,/^set -euo/{/^set -euo/d;s/^# \{0,1\}//;p}' "$0"; exit 0 ;;
    *) die "unknown option $1 (see --help)" ;;
  esac
done
[ "$(id -u)" = 0 ] || die "run as root: sudo ./install.sh"
[ -f "$PKG/network.json" ] || die "run this from the unpacked package folder"
[ -z "$PORT" ] || [[ "$PORT" =~ ^[0-9]+$ ]] || die "--port must be a number"
unit_of() { if [ "$1" = mcnet ]; then echo mcnet; else echo "mcnet-$1"; fi; }
exists() { [ -e "/etc/systemd/system/$(unit_of "$1")@.service" ]; }

# ---- what to install: ask when nothing was given ------------------------------------------------------------
pkg_names() { grep -o '"name": "[^"]*"' "$PKG/network.json" | cut -d'"' -f4; }
if [ -z "$TYPE$SERVERS" ] && [ -t 0 ]; then
  games=$(pkg_names | grep -vxE 'lobby|citybuild' | xargs | sed 's/ /, /g' || true)
  cat <<EOF
What should this machine run?
  1) the full network: hub, CityBuild and the minigames
  2) minigames: hub + $games
  3) CityBuild on its own
  4) choose the servers yourself
EOF
  read -r -p "Choice [1]: " c
  case "${c:-1}" in
    1) TYPE=full ;; 2) TYPE=minigames ;; 3) TYPE=citybuild ;;
    4) echo "Servers in this package: $(pkg_names | xargs)"
       read -r -p "Which ones (comma separated): " SERVERS ;;
    *) die "no such choice: $c" ;;
  esac
  if [ "$NAME" = mcnet ] && exists mcnet; then
    echo "This machine already runs a network called mcnet. The new one runs next to it with its own name."
    def=$([ "$TYPE" = citybuild ] && echo citybuild || echo minigames)
    read -r -p "Name for the new network [$def]: " NAME; NAME="${NAME:-$def}"
  fi
fi
TYPE="${TYPE:-full}"
[[ "$NAME" =~ ^[a-z][a-z0-9]{0,19}$ ]] || die "--name: lower-case letters and digits, starting with a letter"
exists "$NAME" && die "a network called $NAME is already installed - give the new one another --name"
UNIT="$(unit_of "$NAME")"
if [ "$NAME" = mcnet ]; then CTL=mcctl; else CTL="mcctl-$NAME"; fi
DIR="${DIR:-/opt/$NAME}"
[ -e "$DIR/network.conf" ] && die "$DIR already has a network - manage it with: sudo $CTL"

if [ "$EULA" != yes ]; then
  echo "Minecraft servers may only run if you accept the Minecraft EULA: https://aka.ms/MinecraftEULA"
  if [ -t 0 ]; then read -r -p "Do you accept the EULA? [y/N] " answer; [[ "$answer" =~ ^[yY] ]] && EULA=yes; fi
  [ "$EULA" = yes ] || die "EULA not accepted - nothing was installed"
fi

java_major() { "$1" -version 2>&1 | sed -nE 's/.*version "([0-9]+).*/\1/p' | head -1; }
find_java() {
  local j
  for j in /usr/lib/jvm/temurin-25*/bin/java /usr/lib/jvm/*25*/bin/java "$(command -v java || true)"; do
    [ -x "$j" ] && [ "$(java_major "$j")" -ge 25 ] 2>/dev/null && { echo "$j"; return 0; }
  done
  return 1
}

# ---- packages: Java 25 (Eclipse Temurin), MariaDB, python3 ----------------------------------------------
. /etc/os-release
if command -v apt-get >/dev/null; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -q
  apt-get install -y -q ca-certificates curl gnupg python3 tar mariadb-server
  if ! find_java >/dev/null; then
    install -d -m 755 /etc/apt/keyrings
    curl -fsSL https://packages.adoptium.net/artifactory/api/gpg/key/public | gpg --dearmor --yes -o /etc/apt/keyrings/adoptium.gpg
    echo "deb [signed-by=/etc/apt/keyrings/adoptium.gpg] https://packages.adoptium.net/artifactory/deb ${VERSION_CODENAME:?} main" \
      > /etc/apt/sources.list.d/adoptium.list
    apt-get update -q
    apt-get install -y -q temurin-25-jre || apt-get install -y -q temurin-25-jdk
  fi
elif command -v dnf >/dev/null; then
  dnf install -y curl python3 tar mariadb-server
  if ! find_java >/dev/null; then
    case "$ID" in fedora) repo=fedora ;; *) repo=rhel ;; esac
    cat > /etc/yum.repos.d/adoptium.repo <<EOF
[Adoptium]
name=Adoptium
baseurl=https://packages.adoptium.net/artifactory/rpm/$repo/\$releasever/\$basearch
enabled=1
gpgcheck=1
gpgkey=https://packages.adoptium.net/artifactory/api/gpg/key/public
EOF
    dnf install -y temurin-25-jre || dnf install -y temurin-25-jdk
  fi
else
  echo "No apt or dnf here: install Java 25, MariaDB and python3 yourself, then run this again."
  command -v python3 >/dev/null && command -v mariadb >/dev/null || die "missing python3 or mariadb"
fi
JAVA="$(find_java)" || die "Java 25 could not be installed"
echo "java: $JAVA"
systemctl enable --now mariadb

# ---- the network ------------------------------------------------------------------------------------------
id minecraft >/dev/null 2>&1 || useradd --system --user-group --home-dir "$DIR" --no-create-home \
  --shell "$(command -v nologin || echo /bin/false)" minecraft
args=(--pkg "$PKG" --dest "$DIR" --java "$JAVA" --name "$NAME" --type "$TYPE" --servers "$SERVERS"
      --size "$SIZE" --ram "$RAM" --motd "$MOTD" --owner "$OWNER" --registry "$REGISTRY" --accept-eula)
[ -n "$PORT" ] && args+=(--port "$PORT")
python3 "$PKG/configure.py" "${args[@]}"
source "$DIR/network.conf"   # what configure.py chose: SERVERS, HUB, PORT, OWNER_UUID
mkdir -p "$(dirname "$REGISTRY")"; echo "$DIR" >> "$REGISTRY"
chown -R minecraft:minecraft "$DIR"
chmod 750 "$DIR"
chmod 600 "$DIR/SECRETS.txt"
sed -e "s|@DIR@|$DIR|g" -e "s|@NAME@|$NAME|g" "$PKG/mcnet@.service" > "/etc/systemd/system/$UNIT@.service"
ln -sf "$DIR/bin/mcctl" "/usr/local/bin/$CTL"

# nightly backup at 04:00 ($CTL autobackup off disables it)
cat > "/etc/systemd/system/$UNIT-backup.service" <<UNIT
[Unit]
Description=Minecraft network $NAME: backup
[Service]
Type=oneshot
ExecStart=$DIR/bin/mcctl backup
UNIT
cat > "/etc/systemd/system/$UNIT-backup.timer" <<UNIT
[Unit]
Description=Minecraft network $NAME: nightly backup
[Timer]
OnCalendar=*-*-* 04:00
RandomizedDelaySec=30min
Persistent=true
[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
"$DIR/bin/mcctl" autostart on
"$DIR/bin/mcctl" autobackup on

# ---- firewall: only the proxy port is opened; the servers listen on 127.0.0.1 only ------------------------
blocks() { "$1" -S INPUT 2>/dev/null | grep -qE '^-P INPUT DROP|-j (REJECT|DROP)'; }
if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
  ufw allow "$PORT/tcp"
elif systemctl is-active -q firewalld 2>/dev/null; then
  firewall-cmd -q --permanent --add-port="$PORT/tcp" && firewall-cmd -q --reload
elif command -v iptables >/dev/null && blocks iptables; then
  # plain iptables rules that reject everything else, like on Oracle Cloud's Ubuntu images
  for t in iptables ip6tables; do
    command -v "$t" >/dev/null && blocks "$t" || continue
    "$t" -C INPUT -p tcp --dport "$PORT" -j ACCEPT 2>/dev/null || "$t" -I INPUT 1 -p tcp --dport "$PORT" -j ACCEPT
  done
  if command -v netfilter-persistent >/dev/null; then
    netfilter-persistent save >/dev/null 2>&1
  elif [ -d /etc/iptables ]; then
    iptables-save > /etc/iptables/rules.v4
    ! command -v ip6tables-save >/dev/null || ip6tables-save > /etc/iptables/rules.v6
  else
    echo "WARNING: port $PORT is open in iptables until the next reboot - save the iptables rules to keep it"
  fi
  echo "opened TCP $PORT in iptables"
fi
if ss -ltnH 2>/dev/null | awk '{print $4}' | grep -E ':3306$' | grep -qvE '^(127\.0\.0\.1|\[::1\]):'; then
  echo "WARNING: MariaDB listens on a public address. Set bind-address=127.0.0.1 in its config and restart it."
fi

# ---- first start: the hub (or the only server), import the ranks, then everything else --------------------
if [ "$START" = yes ]; then
  since=$(date +%s)
  echo "Starting $HUB (the first start downloads the Minecraft server files and can take a few minutes)..."
  "$DIR/bin/mcctl" start "$HUB"
  "$DIR/bin/mcctl" wait "$HUB" 'Done \(' 900 "$since" || die "$HUB did not start - see: sudo $CTL log $HUB"
  since=$(date +%s)
  "$DIR/bin/mcctl" cmd "$HUB" "lp import luckperms-network.json.gz"
  "$DIR/bin/mcctl" wait "$HUB" 'COMPLETED' 180 "$since" && echo "ranks imported" \
    || echo "WARNING: rank import not confirmed - check: sudo $CTL log $HUB"
  [ -n "$OWNER_UUID" ] && "$DIR/bin/mcctl" cmd "$HUB" "lp user $OWNER_UUID parent set owner"
  "$DIR/bin/mcctl" start all
fi

ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
join="$ip"; [ "$PORT" = 25565 ] || join="$ip:$PORT"
cat <<EOF

Network $NAME installed in $DIR.  Players join: $join
  sudo $CTL status            what is running (the game servers need a minute after starting)
  sudo $CTL console $HUB     console (Ctrl+D to leave)
  sudo $CTL stop | start      whole network
  sudo $CTL backup            backup into $DIR/backups (also runs every night at 04:00)
If the machine is at a hosting provider, also allow TCP $PORT in its firewall panel.
EOF
if grep -qi oraclecloud /sys/class/dmi/id/chassis_asset_tag 2>/dev/null; then
  cat <<EOF
Oracle Cloud: add an ingress rule, or players can't get in. In the Oracle console:
  Networking > Virtual cloud networks > (your network) > Security > Default security list >
  Add ingress rules: source CIDR 0.0.0.0/0, IP protocol TCP, destination port $PORT
EOF
fi
