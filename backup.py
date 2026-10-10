"""Backs up the Windows network: every server folder, the proxy and the ranks database.

usage:  backup.bat [--live] [--keep N]        (or: python tools/backup.py ...)
    --live      also back up while servers are running (a world that is saving at that moment can be
                slightly behind; stop the network for a perfect copy)
    --keep N    how many backups to keep in backups/auto (default 7, the oldest are removed)

Leaves out what the servers download again (libraries, versions, cache) and the logs.
The ranks: with MariaDB running they are dumped to luckperms.sql, otherwise its data folder is copied.
The backup holds the configs and the database passwords - keep it private.
"""
import argparse, datetime, glob, hashlib, os, re, subprocess, sys, tarfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
J = os.path.join
SKIP_DIRS = {"libraries", "versions", "cache", "logs", "crash-reports", "debug", "__pycache__"}
SKIP_FILES = {".console_in", ".console_out", "session.lock"}

ap = argparse.ArgumentParser(description="Backs up the Minecraft network.")
ap.add_argument("--live", action="store_true", help="back up even while servers are running")
ap.add_argument("--keep", type=int, default=7, help="backups to keep (default 7)")
a = ap.parse_args()


def running(exe):
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {exe}"], capture_output=True, text=True).stdout
    return exe.lower() in out.lower()


if running("java.exe") and not a.live:
    sys.exit("Servers are running. Stop the network for a clean backup, or run: backup.bat --live")

toml = open(J(ROOT, "proxy", "velocity.toml"), encoding="utf-8").read()
block = re.search(r"(?ms)^\[servers\]\s*$(.*?)^\[", toml).group(1)
folders = [f"{n}-server" for n in re.findall(r'(?m)^(\w+) = "127\.0\.0\.1:\d+"', block)] + ["proxy", "tools"]
folders = [f for f in folders if os.path.isdir(J(ROOT, f))]

out_dir = J(ROOT, "backups", "auto")
os.makedirs(out_dir, exist_ok=True)
out = J(out_dir, f"network-{datetime.datetime.now():%Y-%m-%d_%H-%M}.tar.gz")
skipped = []

seen = {}   # sha256 -> name in the archive: the same paper.jar or plugin in 7 servers is stored once

with tarfile.open(out, "w:gz", compresslevel=6) as tar:
    def add(path):
        arc = os.path.relpath(path, ROOT).replace("\\", "/")
        try:
            if os.path.getsize(path) >= 1024 * 1024:
                h = hashlib.sha256()
                with open(path, "rb") as f:
                    for block in iter(lambda: f.read(1 << 20), b""):
                        h.update(block)
                h = h.hexdigest()
                if h in seen:         # a hard link to the first copy (tar and 7-Zip restore it as a file)
                    info = tar.gettarinfo(path, arc)
                    info.type, info.linkname, info.size = tarfile.LNKTYPE, seen[h], 0
                    tar.addfile(info)
                    return
                seen[h] = arc
            tar.add(path, arcname=arc, recursive=False)
        except OSError as e:          # a file the running server keeps locked
            skipped.append(f"{arc} ({e.strerror})")

    for folder in folders:
        for dirpath, dirnames, filenames in os.walk(J(ROOT, folder)):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            for f in sorted(filenames):
                if f not in SKIP_FILES and not f.endswith(".log"):
                    add(J(dirpath, f))
        print("packed", folder)
    for f in ("start-all.bat", "backup.bat", "SERVER-GUIDE.md"):
        if os.path.exists(J(ROOT, f)):
            add(J(ROOT, f))

    db = J(ROOT, "mariadb")
    if running("mariadbd.exe"):
        pw = re.search(r"(?m)^root password: *(\S+)", open(J(db, "PASSWORDS.txt"), encoding="utf-8").read()).group(1)
        sql = J(out_dir, "luckperms.sql")
        try:
            with open(sql, "wb") as f:
                subprocess.run([J(db, "bin", "mariadb-dump.exe"), "-h127.0.0.1", "-uroot", "--single-transaction",
                                "luckperms"], stdout=f, check=True, env={**os.environ, "MYSQL_PWD": pw})
            tar.add(sql, arcname="luckperms.sql")
        finally:
            os.remove(sql)
        print("packed the ranks (luckperms.sql)")
    else:
        tar.add(J(db, "data"), arcname="mariadb/data", filter=lambda i: None if i.name.endswith((".err", ".pid")) else i)
        print("packed mariadb (it is stopped, so its data folder is copied)")

print(f"backup: {out} ({os.path.getsize(out) / 1e6:.0f} MB)")
if skipped:
    print(f"{len(skipped)} file(s) could not be read (in use):", *skipped[:10], sep="\n  ")

old = sorted(glob.glob(J(out_dir, "network-*.tar.gz")), key=os.path.getmtime, reverse=True)[max(a.keep, 1):]
for f in old:
    os.remove(f)
    print("removed old backup", os.path.basename(f))
