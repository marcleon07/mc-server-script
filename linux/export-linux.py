"""Packs this network (hub, CityBuild, the game servers and the Velocity proxy) into one .tar.gz
that installs on a Linux server with install.sh.

usage (on this PC, with the network stopped):
    python tools/linux/export-linux.py [output folder]          default: linux-package/

What goes in: every <name>-server folder listed in proxy/velocity.toml, with its worlds, plugins and
configs, plus the proxy, tools/ and the guide. Ranks come from the newest LuckPerms export in
lobby-server/plugins/LuckPerms (refresh it in the hub console: lp export network-template --without-users).

What stays out: player data (inventories, stats, homes, balances), logs, caches, the Windows start
scripts, backups/, the local MariaDB, ops/bans and every secret. The installer makes new secrets and
asks for the EULA itself. The export stops if a secret from this PC would end up in the package.
"""
import datetime, glob, gzip, hashlib, io, json, os, re, sys, tarfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "linux-package")
J = os.path.join

# left out of every server folder (paths relative to that folder; {world} = level-name)
SKIP = ["logs", "cache", "libraries", "versions", "crash-reports", "debug", "start.bat", "usercache.json",
        ".console_in", ".console_out", "{world}/players", "{world}/session.lock",
        "plugins/Essentials/userdata", "plugins/Essentials/userdata-npc-backup",
        "plugins/Essentials/usermap.bin", "plugins/Essentials/uuids.bin",
        "plugins/BedWars/database", "plugins/Duels/users", "plugins/Duels/logs", "plugins/BattleArena/backups",
        "plugins/KenshinsHideAndSeek/khs.db", "plugins/RealSkywars/RealSkywars.db",
        "plugins/QuickShop-Hikari/shops.mv.db", "plugins/QuickShop-Hikari/shops.trace.db",
        "plugins/bStats", "plugins/faststats", "plugins/spark",
        # proxy
        "forwarding.secret", "plugins/bstats"]
SKIP_NAMES = {"session.lock", "__pycache__"}
SKIP_SUFFIX = (".log", ".log.gz", ".json.gz", ".mv.db", ".lck")
EMPTY_JSON = {"ops.json", "banned-players.json", "banned-ips.json", "whitelist.json"}
NEWBIE_KIT_SERVERS = {"citybuild-server"}   # only survival keeps EssentialsX's starter kit
FWD, DBPW ="__FORWARDING_SECRET__", "__LUCKPERMS_DB_PASSWORD__"


def read(p):
    return open(p, encoding="utf-8", errors="replace").read()


# ---- what the network looks like now ---------------------------------------------------------------
toml = read(J(ROOT, "proxy", "velocity.toml"))
servers_block = re.search(r"(?ms)^\[servers\]\s*$(.*?)^\[", toml).group(1)
ram_of = lambda folder: re.search(r"-Xmx(\S+)", read(J(ROOT, folder, "start.bat"))).group(1)
network = {"proxy": {"folder": "proxy", "ram": ram_of("proxy"),
                     "port": int(re.search(r'(?m)^bind = "[^"]*:(\d+)"', toml).group(1))},
           "servers": []}
for name, port in re.findall(r'(?m)^(\w+) = "127\.0\.0\.1:(\d+)"', servers_block):
    folder = f"{name}-server"
    assert os.path.isdir(J(ROOT, folder)), f"velocity.toml lists {name}, but there is no {folder} folder"
    network["servers"].append({"name": name, "folder": folder, "port": int(port), "ram": ram_of(folder)})
assert network["servers"] and network["servers"][0]["name"] == "lobby", "the first server must be lobby"

# secrets that must not leave this PC
secrets = {read(J(ROOT, "proxy", "forwarding.secret")).strip()}
for s in network["servers"]:
    lp = read(J(ROOT, s["folder"], "plugins/LuckPerms/config.yml"))
    secrets.add(re.search(r"(?m)^  username: luckperms\n  password: '([^']*)'", lp).group(1))
    secrets.update(re.findall(r"(?m)^management-server-secret=(\S+)", read(J(ROOT, s["folder"], "server.properties"))))
pw_file = J(ROOT, "mariadb", "PASSWORDS.txt")
if os.path.exists(pw_file):
    secrets.update(re.findall(r"(?m)password: *(\S+)", read(pw_file)))
secrets = {s.encode() for s in secrets if len(s) >= 8}
fwd_secret = read(J(ROOT, "proxy", "forwarding.secret")).strip()


def rewrite(folder, rel, data):
    """Returns the bytes to pack for one file (secrets swapped for placeholders, lists emptied)."""
    if folder != "proxy" and rel in EMPTY_JSON:
        return b"[]\n"
    if rel == "eula.txt":
        return b"# The installer asks you to accept the Minecraft EULA (https://aka.ms/MinecraftEULA)\neula=false\n"
    text = None
    if rel == "server.properties":
        text = re.sub(r"(?m)^management-server-secret=[^\r\n]*", "management-server-secret=", data.decode())
    elif rel == "config/paper-global.yml":
        text = data.decode().replace(fwd_secret, FWD)
        assert FWD in text, f"{folder}: forwarding secret not found in paper-global.yml"
    elif rel == "plugins/LuckPerms/config.yml":
        text, n = re.subn(r"(?m)^(  username: luckperms\r?\n  password: )'[^']*'", rf"\1'{DBPW}'", data.decode())
        assert n == 1, f"{folder}: LuckPerms password line not found"
    elif rel == "plugins/Essentials/config.yml" and folder not in NEWBIE_KIT_SERVERS:
        # no first-join kit (stone tools) in the hub and the game modes: each server would hand it out again
        text = re.sub(r"(?m)^(  kit: )(?!'')\S+", r"\1''", data.decode())
    return data if text is None else text.encode()


# ---- pack --------------------------------------------------------------------------------------------
lp_dir = J(ROOT, "lobby-server", "plugins", "LuckPerms")
exports = sorted(glob.glob(J(lp_dir, "*.json.gz")), key=os.path.getmtime)
assert exports, "no LuckPerms export found - in the hub console run: lp export network-template --without-users"
ranks = json.load(gzip.open(exports[-1]))
ranks.pop("users", None)                        # only groups and tracks travel
print("ranks from", os.path.basename(exports[-1]), "-", ", ".join(ranks["groups"]))

os.makedirs(OUT, exist_ok=True)
out_file = J(OUT, f"mcnet-{datetime.date.today():%Y-%m-%d}.tar.gz")
tar = tarfile.open(out_file, "w:gz", compresslevel=6)
seen, dedupe, total = {}, {}, [0, 0]


def add_bytes(arc, data, mode=0o644):
    info = tarfile.TarInfo("mcnet/" + arc)
    info.size, info.mode, info.mtime = len(data), mode, int(datetime.datetime.now().timestamp())
    tar.addfile(info, io.BytesIO(data))
    total[0] += 1; total[1] += len(data)


def add_tree(folder, skip):
    base = J(ROOT, folder)
    for dirpath, dirnames, filenames in os.walk(base):
        rel_dir = os.path.relpath(dirpath, base).replace("\\", "/")
        rel_dir = "" if rel_dir == "." else rel_dir + "/"
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_NAMES and rel_dir + d not in skip)
        for f in sorted(filenames):
            rel = rel_dir + f
            if f in SKIP_NAMES or rel in skip or f.endswith(SKIP_SUFFIX):
                continue
            data = rewrite(folder, rel, open(J(dirpath, f), "rb").read())
            for s in secrets:
                assert s not in data, f"a secret from this PC is in {folder}/{rel} - nothing exported"
            arc = f"files/{folder}/{rel}"
            if len(data) >= 256 * 1024:          # big identical files (jars, libs) are packed once
                h = hashlib.sha256(data).hexdigest()
                if h in seen:
                    dedupe[arc] = seen[h]
                    continue
                seen[h] = arc
            add_bytes(arc, data, 0o755 if f.endswith(".sh") else 0o644)


for s in network["servers"]:
    world = re.search(r"(?m)^level-name=(\S+)", read(J(ROOT, s["folder"], "server.properties"))).group(1)
    add_tree(s["folder"], {p.replace("{world}", world) for p in SKIP})
    print("packed", s["folder"])
add_tree("proxy", set(SKIP))
add_tree("tools", {"linux"})
add_bytes("files/SERVER-GUIDE.md", open(J(ROOT, "SERVER-GUIDE.md"), "rb").read())

for f in ["install.sh", "configure.py", "mcctl", "run", "mcnet@.service", "README.md"]:
    data = open(J(HERE, f), "rb").read().replace(b"\r\n", b"\n")
    add_bytes(f, data, 0o755 if f in ("install.sh", "mcctl", "run") else 0o644)
add_bytes("network.json", json.dumps(network, indent=2).encode())
add_bytes("dedupe.json", json.dumps(dedupe, indent=1).encode())
buf = io.BytesIO()
with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as g:
    g.write(json.dumps(ranks).encode())
add_bytes("luckperms-network.json.gz", buf.getvalue())
tar.close()

print(f"{total[0]} files ({total[1] / 1e6:.0f} MB, {len(dedupe)} duplicates restored on install)")
print(f"-> {out_file} ({os.path.getsize(out_file) / 1e6:.0f} MB)")
