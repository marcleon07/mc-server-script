"""Copies the network out of this package into the install folder and sets it up.
Called by install.sh (as root); it does not touch anything outside --dest except the MariaDB grants.

python3 configure.py --pkg <package dir> --dest <install dir> --java <java path>
                     [--servers lobby,bedwars,...|all] [--port 25565] [--ram bedwars=4G,...]
                     [--owner <Minecraft name>] [--accept-eula] [--skip-db]
"""
import argparse, json, os, re, secrets, shutil, subprocess, sys, urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("--pkg", required=True)
ap.add_argument("--dest", required=True)
ap.add_argument("--java", required=True)
ap.add_argument("--servers", default="all")
ap.add_argument("--port", type=int, default=25565)
ap.add_argument("--ram", default="")
ap.add_argument("--owner", default="")
ap.add_argument("--accept-eula", action="store_true")
ap.add_argument("--skip-db", action="store_true", help="do not create the MariaDB database/user")
a = ap.parse_args()
J = os.path.join
FILES = J(a.pkg, "files")


def die(msg):
    sys.exit("configure: " + msg)


def edit(path, fn):
    t = open(path, encoding="utf-8").read()
    open(path, "w", encoding="utf-8", newline="").write(fn(t))


net = json.load(open(J(a.pkg, "network.json")))
known = [s["name"] for s in net["servers"]]
wanted = known if a.servers == "all" else [n.strip() for n in a.servers.split(",") if n.strip()]
for n in wanted:
    if n not in known:
        die(f"unknown server '{n}' (this package has: {', '.join(known)})")
servers = [s for s in net["servers"] if s["name"] in wanted or s["name"] == "lobby"]
names = [s["name"] for s in servers]
ram = {s["name"]: s["ram"] for s in servers} | {"proxy": net["proxy"]["ram"]}
for item in filter(None, a.ram.split(",")):
    k, _, v = item.partition("=")
    if k not in ram or not re.fullmatch(r"\d+[MG]", v):
        die(f"bad --ram entry '{item}' (use name=SIZE like bedwars=4G or proxy=512M)")
    ram[k] = v
if os.path.exists(J(a.dest, "network.conf")):
    die(f"{a.dest} already has a network - manage it with mcctl")

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
print("copied:", ", ".join(folders))

# ---- secrets: new forwarding secret + database password ------------------------------------------------
fwd, dbpw = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
open(J(a.dest, "proxy", "forwarding.secret"), "w").write(fwd)
for s in servers:
    edit(J(a.dest, s["folder"], "config", "paper-global.yml"), lambda t: t.replace("__FORWARDING_SECRET__", fwd))
    edit(J(a.dest, s["folder"], "plugins", "LuckPerms", "config.yml"), lambda t: t.replace("__LUCKPERMS_DB_PASSWORD__", dbpw))
sec = J(a.dest, "SECRETS.txt")
with open(os.open(sec, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
    f.write("MariaDB (127.0.0.1:3306) database luckperms\nuser: luckperms\npassword: " + dbpw + "\n")

if not a.skip_db:
    client = shutil.which("mariadb") or shutil.which("mysql") or die("no mariadb/mysql client found")
    sql = "CREATE DATABASE IF NOT EXISTS luckperms CHARACTER SET utf8mb4;\n"
    for host in ("localhost", "127.0.0.1"):
        sql += (f"CREATE USER IF NOT EXISTS 'luckperms'@'{host}' IDENTIFIED BY '{dbpw}';\n"
                f"ALTER USER 'luckperms'@'{host}' IDENTIFIED BY '{dbpw}';\n"
                f"GRANT ALL PRIVILEGES ON luckperms.* TO 'luckperms'@'{host}';\n")
    subprocess.run([client], input=sql + "FLUSH PRIVILEGES;\n", text=True, check=True)
    print("database luckperms ready")

# ---- EULA, port, which servers exist -------------------------------------------------------------------
if a.accept_eula:
    for s in servers:
        open(J(a.dest, s["folder"], "eula.txt"), "w").write(
            "# Accepted during install (https://aka.ms/MinecraftEULA)\neula=true\n")


def prune_velocity(t):
    t = re.sub(r'(?m)^bind = "[^"]*"', f'bind = "0.0.0.0:{a.port}"', t)
    return re.sub(r'(?m)^(\w+) = "127\.0\.0\.1:\d+"[ \t]*\r?\n',
                  lambda m: m.group(0) if m.group(1) in names else "", t)
edit(J(a.dest, "proxy", "velocity.toml"), prune_velocity)


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
if a.owner:
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
shutil.copy2(J(a.pkg, "luckperms-network.json.gz"), J(a.dest, "lobby-server", "plugins", "LuckPerms"))

# ---- scripts + settings ---------------------------------------------------------------------------------
os.makedirs(J(a.dest, "bin"), exist_ok=True)
for f in ("mcctl", "run"):
    shutil.copy2(J(a.pkg, f), J(a.dest, "bin", f))
    os.chmod(J(a.dest, "bin", f), 0o755)
entries = [f"{s['name']}:{s['folder']}:{ram[s['name']]}" for s in servers] + [f"proxy:proxy:{ram['proxy']}"]
open(J(a.dest, "network.conf"), "w", newline="\n").write(
    "# Minecraft network settings, read by bin/run and bin/mcctl.\n"
    "# Change a server's RAM here, then: sudo mcctl restart <name>\n"
    f"JAVA={a.java}\n"
    "# name:folder:RAM in start order (the proxy starts last, stops first)\n"
    f'SERVERS="{" ".join(entries)}"\n'
    f"PORT={a.port}\n"
    f"OWNER_UUID={owner_uuid}\n")

gb = lambda v: int(v[:-1]) / (1024 if v.endswith("M") else 1)
need = sum(gb(v) for v in ram.values())
try:
    have = int(re.search(r"MemTotal:\s+(\d+)", open("/proc/meminfo").read()).group(1)) / 1024 / 1024
    print(f"RAM: the servers use {need:.1f} GB, this machine has {have:.1f} GB")
    if need > have - 1:
        print("WARNING: not enough memory for all servers - install fewer (--servers) or lower --ram")
except OSError:
    pass
