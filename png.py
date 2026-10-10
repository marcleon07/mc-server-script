"""Turns the HTML preview from lobbygen.py into a PNG image.
usage: python png.py <preview.html> <out.png>
"""
import json, re, sys, zlib, struct
html = open(sys.argv[1], encoding="utf-8").read()
grid = json.loads(re.search(r"const G=(\[\[.*?\]\]\]),L=", html).group(1))
S = 5; N = len(grid)
def rgb(h, a):
    h = h.lstrip("#"); return [max(0, min(255, int(int(h[i:i+2], 16) * a))) for i in (0, 2, 4)]
rows = []
for z in range(N):
    line = []
    for i in range(N):
        c, y = grid[z][i]; w = grid[z][i-1][1] if i else y; n = grid[z-1][i][1] if z else y
        a = 0.82 + min(0.35, y * 0.012) + (0.12 if (y > w or y > n) else (-0.12 if (y < w or y < n) else 0))
        line += rgb(c, a) * S
    for _ in range(S): rows.append(bytes([0]) + bytes(line))
raw = zlib.compress(b"".join(rows), 9)
def chunk(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
open(sys.argv[2], "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", N*S, N*S, 8, 2, 0, 0, 0)) + chunk(b"IDAT", raw) + chunk(b"IEND", b""))
