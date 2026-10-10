#!/usr/bin/env bash
# Installs the Minecraft network from this package on a Linux server.
# Debian 12+/Ubuntu 22.04+ (apt) or Fedora/RHEL/Rocky/Alma 9+ (dnf), 64-bit, with internet access.
#
#   sudo ./install.sh [options]
#     --owner NAME          your Minecraft name: op everywhere + the owner rank
#     --servers LIST        which servers to install, e.g. lobby,bedwars,skywars (default: all)
#     --ram LIST            change RAM, e.g. bedwars=4G,lobby=1G,proxy=512M
#     --port N              port players connect to (default 25565)
#     --dir PATH            install folder (default /opt/mcnet)
#     --accept-eula         accept the Minecraft EULA without asking (https://aka.ms/MinecraftEULA)
#     --no-start            set everything up but do not start the servers
set -euo pipefail
PKG="$(cd "$(dirname "$0")" && pwd)"
DIR=/opt/mcnet SERVERS=all PORT=25565 OWNER="" RAM="" EULA=no START=yes

die() { echo "install: $*" >&2; exit 1; }
while [ $# -gt 0 ]; do
  case "$1" in
    --owner) OWNER="$2"; shift 2 ;;
    --servers) SERVERS="$2"; shift 2 ;;
    --ram) RAM="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --dir) DIR="$2"; shift 2 ;;
    --accept-eula) EULA=yes; shift ;;
    --no-start) START=no; shift ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) die "unknown option $1 (see --help)" ;;
  esac
done
[ "$(id -u)" = 0 ] || die "run as root: sudo ./install.sh"
[ -f "$PKG/network.json" ] || die "run this from the unpacked package folder"
[ -e "$DIR/network.conf" ] && die "$DIR already has a network - manage it with: sudo mcctl"
[[ "$PORT" =~ ^[0-9]+$ ]] || die "--port must be a number"

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
python3 "$PKG/configure.py" --pkg "$PKG" --dest "$DIR" --java "$JAVA" --servers "$SERVERS" --port "$PORT" \
  --ram "$RAM" --owner "$OWNER" --accept-eula
chown -R minecraft:minecraft "$DIR"
chmod 750 "$DIR"
chmod 600 "$DIR/SECRETS.txt"
sed "s|@DIR@|$DIR|g" "$PKG/mcnet@.service" > /etc/systemd/system/mcnet@.service
ln -sf "$DIR/bin/mcctl" /usr/local/bin/mcctl
systemctl daemon-reload
mcctl autostart on

# ---- firewall: only the proxy port is opened; the servers listen on 127.0.0.1 only ------------------------
if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
  ufw allow "$PORT/tcp"
elif systemctl is-active -q firewalld 2>/dev/null; then
  firewall-cmd -q --permanent --add-port="$PORT/tcp" && firewall-cmd -q --reload
fi
if ss -ltnH 2>/dev/null | awk '{print $4}' | grep -E ':3306$' | grep -qvE '^(127\.0\.0\.1|\[::1\]):'; then
  echo "WARNING: MariaDB listens on a public address. Set bind-address=127.0.0.1 in its config and restart it."
fi

# ---- first start: hub, import the ranks, then everything else ---------------------------------------------
if [ "$START" = yes ]; then
  source "$DIR/network.conf"
  since=$(date +%s)
  echo "Starting the hub (the first start downloads the Minecraft server files and can take a few minutes)..."
  mcctl start lobby
  mcctl wait lobby 'Done \(' 900 "$since" || die "the hub did not start - see: sudo mcctl log lobby"
  since=$(date +%s)
  mcctl cmd lobby "lp import luckperms-network.json.gz"
  mcctl wait lobby 'COMPLETED' 180 "$since" && echo "ranks imported" || echo "WARNING: rank import not confirmed - check: sudo mcctl log lobby"
  [ -n "$OWNER_UUID" ] && mcctl cmd lobby "lp user $OWNER_UUID parent set owner"
  mcctl start all
fi

ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
cat <<EOF

Installed in $DIR.  Players join: $ip:$PORT
  sudo mcctl status            what is running (the game servers need a minute after starting)
  sudo mcctl console lobby     hub console (Ctrl+D to leave)
  sudo mcctl stop | start      whole network
  sudo mcctl backup            backup into $DIR/backups
If the machine is at a hosting provider, also allow TCP $PORT in its firewall panel.
EOF
