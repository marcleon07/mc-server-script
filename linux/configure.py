"""Copies the network out of this package into the install folder and sets it up.
Called by install.sh (as root); it does not touch anything outside --dest except the MariaDB grants.

python3 configure.py --pkg <package dir> --dest <install dir> --java <java path>
                     [--type full|minigames|citybuild] [--servers lobby,bedwars,...] [--name mcnet]
                     [--port 25565] [--ram bedwars=4G,...] [--motd TEXT] [--owner <Minecraft name>]
                     [--accept-eula] [--skip-db] [--registry /etc/mcnet/networks]
"""
import argparse, json, os, re, secrets, shlex, shutil, socket, subprocess, sys, urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("--pkg", required=True)
ap.add_argument("--dest", required=True)
ap.add_argument("--java", required=True)
ap.add_argument("--type", default="full", help="full, minigames or citybuild")
ap.add_argument("--servers", default="", help="pick servers yourself (instead of --type)")
ap.add_argument("--name", default="mcnet", help="name of this network, for more than one on a machine")
ap.add_argument("--port", type=int, help="port players connect to (default 25565 or the next free one)")
ap.add_argument("--ram", default="")
ap.add_argument("--motd", default="", help="server list message (default: made from the servers)")
ap.add_argument("--owner", default="")
ap.add_argument("--accept-eula", action="store_true")
ap.add_argument("--skip-db", action="store_true", help="do not create the MariaDB database/user")
ap.add_argument("--registry", default="/etc/mcnet/networks", help="list of the networks on this machine")
a = ap.parse_args()
J = os.path.join
FILES = J(a.pkg, "files")


def die(msg):
    sys.exit("configure: " + msg)


def edit(path, fn):
    t = open(path, encoding="utf-8").read()
    open(path, "w", encoding="utf-8", newline="").write(fn(t))


if not re.fullmatch(r"[a-z][a-z0-9]{0,19}", a.name):
    die(f"bad --name '{a.name}' (lower-case letters and digits, starting with a letter)")
if os.path.exists(J(a.dest, "network.conf")):
    die(f"{a.dest} already has a network - manage it with mcctl")

# ---- which servers ----------------------------------------------------------------------------------------
net = json.load(open(J(a.pkg, "network.json")))
known = [s["name"] for s in net["servers"]]


def kind(s):   # hub, survival (CityBuild) or game; older packages have no "kind"
    return s.get("kind") or ("hub" if s["name"] == "lobby" else "survival" if s["name"] == "citybuild" else "game")


TYPES = {"full": lambda s: True,
         "minigames": lambda s: kind(s) in ("hub", "game"),
         "citybuild": lambda s: kind(s) == "survival"}
if a.servers and a.servers != "all":
    wanted = [n.strip() for n in a.servers.split(",") if n.strip()]
    for n in wanted:
        if n not in known:
            die(f"unknown server '{n}' (this package has: {', '.join(known)})")
elif a.type in TYPES:
    wanted = [s["name"] for s in net["servers"] if TYPES[a.type](s)]
else:
    die(f"unknown --type '{a.type}' (use {', '.join(TYPES)})")
servers = [s for s in net["servers"] if s["name"] in wanted]          # package order: the hub first
if not servers:
    die(f"this package has no servers for --type {a.type}")
names = [s["name"] for s in servers]
hub = "lobby" if "lobby" in names else names[0]       # where players arrive (and where the ranks are imported)
games = [s for s in servers if kind(s) == "game"]

ram = {s["name"]: s["ram"] for s in servers} | {"proxy": net["proxy"]["ram"]}
for item in filter(None, a.ram.split(",")):
    k, _, v = item.partition("=")
    if k not in ram or not re.fullmatch(r"\d+[MG]", v):
        die(f"bad --ram entry '{item}' (use name=SIZE like bedwars=4G or proxy=512M)")
    ram[k] = v

# ---- ports: the package's own, unless another network on this machine already has them ----------------
used = set()
try:
    dirs = [l.strip() for l in open(a.registry) if l.strip()]
except OSError:
    dirs = []
for d in dirs:
    if os.path.abspath(d) == os.path.abspath(a.dest):
        continue
    try:
        conf = open(J(d, "network.conf")).read()
    except OSError:
        continue
    used.update(int(p) for p in re.findall(r"(?m)^PORT=(\d+)", conf))
    used.update(int(p) for p in re.findall(r":(\d+)(?=[ \"])", conf))   # name:folder:RAM:port entries


def free(p):
    if p in used or not 1024 <= p <= 65535:
        return False
    with socket.socket() as s:                      # also not taken by some other program right now
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("0.0.0.0", p))
            return True
        except OSError:
            return False


if a.port:
    if not free(a.port):
        die(f"port {a.port} is already used (by another network or program) - pick another --port")
    port = a.port
elif free(net["proxy"]["port"]) and not used:
    port = net["proxy"]["port"]
else:                                               # next free block of ten, e.g. 25585 after 25565-25574
    port = (max(used | {net["proxy"]["port"]}) // 10 + 1) * 10 + 5
    while not free(port):
        port += 1
pkg_ports = [s["port"] for s in servers]
if all(free(p) and p != port for p in pkg_ports):
    ports = pkg_ports
else:
    ports, p = [], port
    for s in servers:
        p += 1
        while not free(p) or p in ports:
            p += 1
        ports.append(p)
port_of = dict(zip(names, ports))

# ---- copy ---------------------------------------------------------------------------------------------
os.makedirs(a.dest, exist_ok=True)
folders = [s["folder"] for s in servers] + ["proxy"]
for f in folders + ["tools"]:
    shutil.copytree(J(FILES, f), J(a.dest, f), dirs_exist_ok=True)
shutil.copy2(J(FILES, "SERVER-GUIDE.md"), J(a.dest, "SERVER-GUIDE.md"))
os.makedirs(J(a.dest, "shared"), exist_ok=True)
for copy, original in json.load(open(J(a.pkg, "dedupe.json"))).items():
    folder = copy.split("/")[1]
    if folder in folders or folder == "tools":
        dst = J(a.dest, *copy.split("/")[1:])
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(J(a.pkg, *original.split("/")), dst)
print(f"network {a.name}: " + ", ".join(names) + " + proxy")

# ---- secrets: new forwarding secret + database (one per network) ------------------------------------------
db = "luckperms" if a.name == "mcnet" else f"luckperms_{a.name}"     # database and user have the same name
fwd, dbpw = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
open(J(a.dest, "proxy", "forwarding.secret"), "w").write(fwd)


def luckperms(t):
    t = t.replace("__LUCKPERMS_DB_PASSWORD__", dbpw)
    return re.sub(r"(?m)^(  (?:database|username): )luckperms(?=\r?$)", lambda m: m.group(1) + db, t)


for s in servers:
    edit(J(a.dest, s["folder"], "config", "paper-global.yml"), lambda t: t.replace("__FORWARDING_SECRET__", fwd))
    edit(J(a.dest, s["folder"], "plugins", "LuckPerms", "config.yml"), luckperms)
sec = J(a.dest, "SECRETS.txt")
with open(os.open(sec, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
    f.write(f"MariaDB (127.0.0.1:3306) database {db}\nuser: {db}\npassword: {dbpw}\n")

if not a.skip_db:
    client = shutil.which("mariadb") or shutil.which("mysql") or die("no mariadb/mysql client found")
    sql = f"CREATE DATABASE IF NOT EXISTS {db} CHARACTER SET utf8mb4;\n"
    for host in ("localhost", "127.0.0.1"):
        sql += (f"CREATE USER IF NOT EXISTS '{db}'@'{host}' IDENTIFIED BY '{dbpw}';\n"
                f"ALTER USER '{db}'@'{host}' IDENTIFIED BY '{dbpw}';\n"
                f"GRANT ALL PRIVILEGES ON {db}.* TO '{db}'@'{host}';\n")
    subprocess.run([client], input=sql + "FLUSH PRIVILEGES;\n", text=True, check=True)
    print(f"database {db} ready")

# ---- EULA, ports, proxy -----------------------------------------------------------------------------------
if a.accept_eula:
    for s in servers:
        open(J(a.dest, s["folder"], "eula.txt"), "w").write(
            "# Accepted during install (https://aka.ms/MinecraftEULA)\neula=true\n")
for s in servers:
    edit(J(a.dest, s["folder"], "server.properties"),
         lambda t: re.sub(r"(?m)^server-port=\d+", f"server-port={port_of[s['name']]}", t))

LABEL = {"bedwars": "<aqua>BedWars", "skywars": "<green>SkyWars", "hideseek": "<yellow>Hide&Seek",
         "duels": "<red>Duels", "parkour": "<gold>Parkour", "citybuild": "<light_purple>CityBuild"}
if a.motd:
    motd = a.motd
elif names == known:
    motd = None                                     # the whole network: keep its own message
else:
    title = "Minigames" if games else "CityBuild" if "citybuild" in names else names[0].capitalize()
    parts = [LABEL.get(n, "<white>" + n.capitalize()) for n in names if n != "lobby"]
    if parts == ["<light_purple>CityBuild"]:
        parts = ["<light_purple>Plots, shops and survival"]
    motd = f"<gold><bold>{title}</bold></gold> <gray>| " + " <gray>- ".join(parts)


def velocity(t):
    t = re.sub(r'(?m)^bind = "[^"]*"', f'bind = "0.0.0.0:{port}"', t)
    entries = "".join(f'{n} = "127.0.0.1:{port_of[n]}"\n' for n in names)
    t, n = re.subn(r"(?ms)^\[servers\][ \t]*\r?\n.*?^try = \[.*?\]",
                   lambda m: f'[servers]\n{entries}try = [\n    "{hub}"\n]', t)
    assert n == 1, "[servers] / try not found in velocity.toml"
    if motd:
        t = re.sub(r"(?m)^motd = .*$", lambda m: "motd = " + json.dumps(motd), t)
    return t
edit(J(a.dest, "proxy", "velocity.toml"), velocity)


def prune_links(t):
    """Drops ServerLink links (/bedwars, /farm, ...) to servers that were not installed."""
    head, sep, rest = t.partition("\nlinks:\n")
    if not sep:
        return t
    m = re.search(r"(?m)^\S", rest)
    body, tail = (rest[:m.start()], rest[m.start():]) if m else (rest, "")
    blocks = re.split(r"(?m)^(?=  \S)", body)
    keep = [b for b in blocks if not (re.search(r"(?m)^    server: (\S+)", b) and
                                       re.search(r"(?m)^    server: (\S+)", b).group(1) not in names)]
    return head + sep + "".join(keep) + tail
for s in servers:
    edit(J(a.dest, s["folder"], "plugins", "ServerLink", "config.yml"), prune_links)

# ---- owner: op on every server + owner rank after the first start -------------------------------------
owner_uuid = ""
if a.owner and not re.fullmatch(r"[A-Za-z0-9_]{3,16}", a.owner):
    print(f"WARNING: '{a.owner}' is not a Minecraft name (3-16 letters, digits or _); no owner set")
elif a.owner:
    try:
        with urllib.request.urlopen(f"https://api.mojang.com/users/profiles/minecraft/{a.owner}", timeout=15) as r:
            prof = json.load(r)
        h = prof["id"]
        owner_uuid = f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"
        ops = [{"uuid": owner_uuid, "name": prof["name"], "level": 4, "bypassesPlayerLimit": True}]
        for s in servers:
            json.dump(ops, open(J(a.dest, s["folder"], "ops.json"), "w"), indent=2)
        print(f"owner {prof['name']} = {owner_uuid}")
    except Exception as e:
        print(f"WARNING: could not look up Minecraft player '{a.owner}' ({e}); set the owner later by hand")
hub_folder = next(s["folder"] for s in servers if s["name"] == hub)
shutil.copy2(J(a.pkg, "luckperms-network.json.gz"), J(a.dest, hub_folder, "plugins", "LuckPerms"))

# ---- scripts + settings ---------------------------------------------------------------------------------
os.makedirs(J(a.dest, "bin"), exist_ok=True)
for f in ("mcctl", "run"):
    shutil.copy2(J(a.pkg, f), J(a.dest, "bin", f))
    os.chmod(J(a.dest, "bin", f), 0o755)
entries = [f"{s['name']}:{s['folder']}:{ram[s['name']]}:{port_of[s['name']]}" for s in servers]
entries.append(f"proxy:proxy:{ram['proxy']}:{port}")
open(J(a.dest, "network.conf"), "w", newline="\n").write(
    "# Minecraft network settings, read by bin/run and bin/mcctl.\n"
    "# Change a server's RAM here, then: sudo mcctl restart <name>\n"
    f"NAME={a.name}\n"
    f"UNIT={'mcnet' if a.name == 'mcnet' else 'mcnet-' + a.name}\n"
    f"JAVA={shlex.quote(a.java)}\n"
    "# name:folder:RAM:port in start order (the proxy starts last, stops first; ports are set in the configs)\n"
    f'SERVERS="{" ".join(entries)}"\n'
    f"HUB={hub}\n"
    f"PORT={port}\n"
    f"DB={db}\n"
    f"OWNER_UUID={owner_uuid}\n"
    "# how many backups mcctl backup keeps (the oldest are removed)\n"
    "BACKUP_KEEP=7\n")
print(f"players join on port {port}" + ("" if port == 25565 else " (put it after the address: <ip>:" + str(port) + ")"))

gb = lambda v: int(v[:-1]) / (1024 if v.endswith("M") else 1)
need = sum(gb(v) for v in ram.values())
try:
    have = int(re.search(r"MemTotal:\s+(\d+)", open("/proc/meminfo").read()).group(1)) / 1024 / 1024
    print(f"RAM: the servers use {need:.1f} GB, this machine has {have:.1f} GB")
    if need > have - 1:
        print("WARNING: not enough memory for all servers - install fewer (--servers) or lower --ram")
except OSError:
    pass
