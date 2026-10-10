"""Generate the Minigames lobby: console build commands + an HTML top-down preview.

usage: python lobbygen.py <ground_y> <out_cmds.txt> <out_preview.html>
Coordinates are centred on (0, 0) in the lobby world. y is relative to ground (0 = grass layer).
"""
import json, math, random, sys

G = int(sys.argv[1])
OUT_CMDS, OUT_HTML = sys.argv[2], sys.argv[3]
R = 70                       # half-size of the build box
rng = random.Random(1337)
blocks = {}                  # (x, y, z) -> block state; later writes win
extra = []                   # commands placed after the blocks (signs, entities)

def put(x, y, z, b): blocks[(x, y, z)] = b
def polar(x, z): return math.hypot(x, z), (math.degrees(math.atan2(x, -z)) % 360)   # 0 = north, 90 = east
def angdiff(a, b): return abs((a - b + 180) % 360 - 180)

# ---------------------------------------------------------------- games / gates
GATES = [  # angle, key, colour, title, subtitle, sign colour, command, props
    (0,   "BEDWARS",     "red",        "red",          "Protect your bed, destroy theirs",  "dark_red",   "/bedwars",         ["end_stone", "red_wool", "obsidian"]),
    (45,  "SKYWARS",     "light_blue", "aqua",         "Loot. Bridge. Survive.",            "dark_aqua",  "/skywars",         ["grass_block", "dirt", "chest"]),
    (90,  "HIDE & SEEK", "lime",       "green",        "Blend in - or hunt them down",      "dark_green", "/hideseek",        ["hay_block", "barrel", "carved_pumpkin"]),
    (135, "DUELS",       "orange",     "gold",         "1v1 - prove you're the best",       "gold",       "/duels",           ["iron_block", "smooth_stone", "anvil"]),
    (180, "CITYBUILD",   "yellow",     "yellow",       "Claim a plot & build your city",    "gold",       "/citybuild",  ["bricks", "bookshelf", "lantern"]),
    (225, "FARMWORLD",   "brown",      "#C8874A",      "Gather resources for CityBuild",    "dark_gray",  "/farmworld",  ["oak_log", "hay_block", "composter"]),
    (270, "PARKOUR",     "purple",     "light_purple", "Climb the tower behind me!",        "dark_purple", None,              ["slime_block", "purpur_block", "end_rod"]),
    (315, "SERVER INFO", "white",      "white",        "Rules, ranks & commands",           "black",      "/rules",           ["bookshelf", "chiseled_bookshelf", "lantern"]),
]
GATE_R = 36
PARKOUR_C = (-56, 0)         # parkour tower centre (west)

def gate_local(x, z, ang):
    """world cell -> (f, s) in the gate frame: f outward from plaza, s sideways."""
    a = math.radians(ang)
    fx, fz = math.sin(a), -math.cos(a)        # outward
    sx, sz = math.cos(a), math.sin(a)         # right-hand side
    cx, cz = fx * GATE_R, fz * GATE_R
    dx, dz = x + 0.5 - cx, z + 0.5 - cz
    return dx * fx + dz * fz, dx * sx + dz * sz

def in_parkour_zone(x, z):
    r, a = polar(x, z)
    return angdiff(a, 270) < 32 and r > 42 and r < 66

# ---------------------------------------------------------------- ground + hills
def hill_h(x, z):
    r, a = polar(x, z)
    r0 = 64 if angdiff(a, 270) < 32 else 47
    if r < r0: return 0
    n = 1.6 * (math.sin(x * 0.23) + math.cos(z * 0.19)) + 1.1 * math.sin((x + z) * 0.11)
    return max(0, min(15, int((r - r0) * 0.62 + n + 1)))

H = {}
for x in range(-R, R + 1):
    for z in range(-R, R + 1):
        h = hill_h(x, z); H[(x, z)] = h
        for y in range(1, h): put(x, y, z, "dirt")
        if h: put(x, h, z, "grass_block")

# ---------------------------------------------------------------- plaza + fountain
FLOWERS = ["poppy", "allium", "cornflower", "azure_bluet", "oxeye_daisy", "dandelion", "lily_of_the_valley"]
for x in range(-16, 17):
    for z in range(-16, 17):
        r, a = polar(x + 0.5, z + 0.5)
        if r > 15.5: continue
        if r >= 14.3:   b = "polished_deepslate"
        elif r >= 6.6:
            spoke = min(angdiff(a, k * 45) for k in range(8)) * math.radians(1) * r < 1.4
            if spoke:            b = "smooth_stone"
            elif int(r) % 4 == 0: b = "polished_andesite"
            else:                b = rng.choice(["stone_bricks"] * 6 + ["mossy_stone_bricks", "cracked_stone_bricks"])
        elif r >= 5.0:
            b = "grass_block"; put(x, 1, z, FLOWERS[(x * 7 + z * 13) % len(FLOWERS)])
        elif r >= 3.6:
            b = "polished_andesite"; put(x, 1, z, "smooth_quartz")
        else:
            b = "sea_lantern" if (x + z) % 2 == 0 else "prismarine_bricks"; put(x, 1, z, "water")
        put(x, 0, z, b)
for y in range(1, 6): put(0, y, 0, "quartz_pillar")
for dx, dz in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
    put(dx, 5 if (dx, dz) != (0, 0) else 6, dz, "smooth_quartz_slab" if (dx, dz) != (0, 0) else "water")
put(0, 6, 0, "water")
for k in range(8):                                          # plaza lamp posts between the paths
    a = math.radians(22.5 + 45 * k); x, z = round(math.sin(a) * 12.5), round(-math.cos(a) * 12.5)
    for y in (1, 2, 3): put(x, y, z, "stone_brick_wall")
    put(x, 4, z, "lantern")

# ---------------------------------------------------------------- paths
def path_info(x, z):
    """returns (t, d) along the nearest radial path, or None."""
    best = None
    for k in range(8):
        a = math.radians(45 * k); fx, fz = math.sin(a), -math.cos(a)
        t = (x + 0.5) * fx + (z + 0.5) * fz; d = -(x + 0.5) * fz + (z + 0.5) * fx
        if 15 < t < GATE_R - 2.5 and abs(d) < 2.6 and (best is None or abs(d) < abs(best[1])): best = (t, d, k)
    return best

for x in range(-R, R + 1):
    for z in range(-R, R + 1):
        p = path_info(x, z)
        if not p: continue
        t, d, k = p
        put(x, 0, z, "polished_andesite" if abs(d) > 1.7 else rng.choice(["stone_bricks"] * 5 + ["mossy_stone_bricks", "andesite"]))
for k in range(8):                                          # path lamp posts
    a = math.radians(45 * k); fx, fz = math.sin(a), -math.cos(a)
    for t in (20, 27):
        for side in (-3.4, 3.4):
            x, z = math.floor(fx * t - fz * side), math.floor(fz * t + fx * side)
            put(x, 1, z, "spruce_fence"); put(x, 2, z, "spruce_fence"); put(x, 3, z, "lantern")

# ---------------------------------------------------------------- gates
def sign_rotation(dx, dz):
    return round(math.degrees(math.atan2(-dx, dz)) / 22.5) % 16

def text_display(x, y, z, title, colour, subtitle, scale=2.0):
    extra.append(
        f'summon text_display {x:.1f} {G + y:.1f} {z:.1f} {{Tags:["lobby"],billboard:"vertical",background:1073741824,'
        f'transformation:{{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],translation:[0f,0f,0f],scale:[{scale}f,{scale}f,{scale}f]}},'
        f'text:{{text:"{title}",color:"{colour}",bold:true,extra:[{{text:"\\n{subtitle}",color:"gray",bold:false}}]}}}}')

for ang, title, col, tcol, sub, scol, cmd, props in GATES:
    open_gate = cmd is None or title == "SERVER INFO"
    for x in range(-R, R + 1):
        for z in range(-R, R + 1):
            f, s = gate_local(x, z, ang)
            if -3.5 <= f <= 5.5 and abs(s) <= 5.5:          # platform
                edge = f < -2.6 or f > 4.6 or abs(s) > 4.6
                put(x, 0, z, "polished_deepslate" if edge else f"{col}_concrete")
            if abs(f - 1) <= 0.75 and abs(abs(s) - 3.6) <= 0.75:   # pillars
                for y in range(1, 7): put(x, y, z, "quartz_pillar")
                put(x, 7, z, "chiseled_quartz_block")
            if abs(f - 1) <= 0.75 and abs(s) <= 4.4:              # beam
                put(x, 8, z, f"{col}_concrete")
                put(x, 9, z, "smooth_quartz_slab")
            if not open_gate and abs(f - 1) <= 0.5 and abs(s) <= 2.85:   # coloured "portal"
                for y in range(1, 8): put(x, y, z, f"{col}_stained_glass")
            if 2.5 <= f <= 4.0 and 4.0 <= abs(s) <= 5.2:          # themed prop stacks
                for i, b in enumerate(props): put(x, 1 + i, z, b)
    a = math.radians(ang); fx, fz = math.sin(a), -math.cos(a)
    sx, sz = math.floor(fx * (GATE_R - 2.2)), math.floor(fz * (GATE_R - 2.2))
    put(sx, 1, sz, "chiseled_stone_bricks")
    rot = sign_rotation(-fx, -fz)
    click = f',click_event:{{action:"run_command",command:"{cmd}"}}' if cmd else ""
    line3 = "Click to enter!" if title not in ("SERVER INFO", "PARKOUR") else ("Click for rules" if cmd else "Walk through ->")
    if title in ("CITYBUILD", "FARMWORLD"): line3 = "Click to travel!"
    extra.append(
        f'setblock {sx} {G + 2} {sz} minecraft:oak_sign[rotation={rot}]{{is_waxed:1b,front_text:{{messages:['
        f'{{text:"-------------",color:"dark_gray"{click}}},{{text:"{title}",color:"{scol}",bold:true}},'
        f'{{text:"{line3}",color:"black"}},{{text:"-------------",color:"dark_gray"}}]}}}}')
    text_display(fx * GATE_R + 0.5, 11.2, fz * GATE_R + 0.5, title, tcol, sub)

# the parkour sign starts the BattleArena race (the gate behind it stays open for free runs)
extra.append(
    f'setblock -34 {G + 2} 0 minecraft:oak_sign[rotation=12]{{is_waxed:1b,front_text:{{messages:[{{text:"",click_event:'
    f'{{action:"run_command",command:"/parkour"}}}},{{text:"PARKOUR",color:"dark_purple",bold:true}},'
    f'"Click: race lobby","or walk through"]}}}}')

# ---------------------------------------------------------------- server info board (NW)
info = ("\\n".join([
    "1. Be respectful - no harassment",
    "2. No cheats, hacked clients or exploits",
    "3. No griefing or stealing on plots",
    "4. No spam or advertising",
    "",
    "/lobby  /citybuild  /farmworld  -  CityBuild: /plot auto /home /tpa /bal",
    "Ranks: VIP, VIP+, MVP - Staff: Helper, Mod, Admin",
]))
a = math.radians(315); fx, fz = math.sin(a), -math.cos(a)
extra.append(
    f'summon text_display {fx * (GATE_R + 3) + 0.5:.1f} {G + 4.2:.1f} {fz * (GATE_R + 3) + 0.5:.1f} {{Tags:["lobby"],billboard:"vertical",'
    f'line_width:260,background:1610612736,text:{{text:"{info}",color:"white"}}}}')

# ---------------------------------------------------------------- parkour tower (west)
cx, cz = PARKOUR_C
for x in range(cx - 3, cx + 4):
    for z in range(cz - 3, cz + 4):
        d = math.hypot(x - cx, z - cz)
        if d <= 2.2:
            for y in range(1, 19): put(x, y, z, "purpur_pillar" if d < 1 else "purpur_block")
for x in range(cx - 4, cx + 5):                              # finish platform
    for z in range(cz - 4, cz + 5):
        if math.hypot(x - cx, z - cz) <= 4.3: put(x, 19, z, "gold_block" if (x + z) % 2 else "yellow_concrete")
put(cx, 20, cz, "beacon"); put(cx, 21, cz, "air")
COLS = ["red", "orange", "yellow", "lime", "light_blue", "magenta"]
radius = 7.2
jumps, ang, y = [(math.floor(cx + radius), cz, 1)], 90.0, 1
while y < 18:
    ang += 1.0
    x, z = math.floor(cx + math.sin(math.radians(ang)) * radius), math.floor(cz - math.cos(math.radians(ang)) * radius)
    px, pz, py = jumps[-1]
    if math.hypot(x - px, z - pz) >= 2.8:
        if len(jumps) % 2 == 1: y += 1
        jumps.append((x, z, y))
jumps = [j for j in jumps if j[2] < 19]
start = (cx + 9, cz)  # start pad on the gate side
for x in range(start[0] - 1, start[0] + 2):
    for z in range(start[1] - 1, start[1] + 2): put(x, 0, z, "emerald_block")
first = jumps[0]
for i, (x, z, y) in enumerate(jumps):
    put(x, y, z, "gold_block" if i and i % 10 == 0 else f"{COLS[i % len(COLS)]}_concrete")
# path from the open west gate to the start pad
for x in range(start[0] + 2, -40):
    for z in range(-1, 2): put(x, 0, z, "stone_bricks" if z == 0 else "polished_andesite")
text_display(start[0] + 0.5, 3.5, start[1] + 0.5, "START", "green", "Jump on the coloured blocks", 1.5)
text_display(cx + 0.5, 23.5, cz + 0.5, "FINISH", "gold", "You made it!", 2.0)
extra.append(
    f'setblock {cx + 2} {G + 20} {cz} minecraft:oak_sign[rotation=12]{{is_waxed:1b,front_text:{{messages:['
    f'{{text:"-------------",color:"dark_gray",click_event:{{action:"run_command",command:"/spawn"}}}},'
    f'{{text:"Well done!",color:"dark_green",bold:true}},{{text:"Back to spawn",color:"black"}},{{text:"-------------",color:"dark_gray"}}]}}}}')

# ---------------------------------------------------------------- welcome sign over the fountain
text_display(0.5, 10.5, 0.5, "WELCOME", "gold", "Pick a game at one of the gates", 3.0)

# ---------------------------------------------------------------- vegetation
def near_gate(x, z, pad):
    return any(-3.5 - pad <= gate_local(x, z, g[0])[0] <= 5.5 + pad and abs(gate_local(x, z, g[0])[1]) <= 5.5 + pad for g in GATES)

def tree(x, z, kind):
    base = H[(x, z)] + 1
    leaves = {"oak": "oak_leaves", "birch": "birch_leaves", "spruce": "spruce_leaves", "cherry": "cherry_leaves"}[kind] + "[persistent=true]"
    log = f"{kind}_log"
    h = {"oak": rng.randint(4, 6), "birch": rng.randint(5, 7), "spruce": rng.randint(7, 9), "cherry": rng.randint(4, 5)}[kind]
    top = base + h
    if kind == "spruce":
        for yy in range(base + 2, top + 2):
            rad = max(0, (top + 1 - yy) // 2 + (1 if (top - yy) % 2 == 0 else 0)); rad = min(rad, 3)
            for dx in range(-rad, rad + 1):
                for dz in range(-rad, rad + 1):
                    if abs(dx) + abs(dz) <= rad + 1: put(x + dx, yy, z + dz, leaves)
        put(x, top + 2, z, leaves)
    else:
        rad = 3 if kind == "cherry" else 2
        for yy in range(top - 2, top + 2):
            rr = rad if yy < top else rad - 1
            for dx in range(-rr, rr + 1):
                for dz in range(-rr, rr + 1):
                    if dx * dx + dz * dz <= rr * rr + 1 and rng.random() > 0.08: put(x + dx, yy, z + dz, leaves)
    for yy in range(base, top): put(x, yy, z, log)

placed = []
attempts = 0
while len(placed) < 70 and attempts < 5000:
    attempts += 1
    x, z = rng.randint(-R + 3, R - 3), rng.randint(-R + 3, R - 3)
    r, a = polar(x, z)
    if r < 19 or near_gate(x, z, 3) or path_info(x, z) or in_parkour_zone(x, z) or math.hypot(x - cx, z - cz) < 13: continue
    if any(path_info(x + dx, z + dz) for dx in (-3, 0, 3) for dz in (-3, 0, 3)): continue
    if any(math.hypot(x - px, z - pz) < 6 for px, pz in placed): continue
    if r < 44 and rng.random() < 0.6: continue                 # keep the inner meadow airy
    tree(x, z, rng.choice(["oak", "oak", "birch", "spruce", "cherry"])); placed.append((x, z))

for x in range(-R, R + 1):                                   # grass + flowers on open ground
    for z in range(-R, R + 1):
        h = H[(x, z)]
        if (x, h + 1, z) in blocks or blocks.get((x, h, z), "grass_block") != "grass_block": continue
        if h == 0 and (polar(x, z)[0] < 16 or path_info(x, z) or near_gate(x, z, 0)): continue
        v = rng.random()
        if v < 0.10: put(x, h + 1, z, "short_grass")
        elif v < 0.115: put(x, h + 1, z, rng.choice(FLOWERS))
        elif v < 0.135: put(x, h + 1, z, "flowering_azalea_leaves[persistent=true]")

# ---------------------------------------------------------------- emit commands
cmds = ["kill @e[type=text_display,tag=lobby]"]
for y in range(30, 0, -1):                                   # clear top-down so water/plants don't drop items
    cmds.append(f"fill {-R} {G + y} {-R} {R} {G + y} {R} air")
cmds.append(f"fill {-R} {G} {-R} {R} {G} {R} grass_block")
for y in (-1, -2, -3): cmds.append(f"fill {-R} {G + y} {-R} {R} {G + y} {R} dirt")

def emit_layer(y, cells):
    # greedy rectangles: runs along x, merged along z
    rows = {}
    for (x, z), b in cells.items(): rows.setdefault(z, []).append((x, b))
    runs = {}
    for z, lst in rows.items():
        lst.sort(); i = 0
        while i < len(lst):
            x0, b = lst[i]; j = i
            while j + 1 < len(lst) and lst[j + 1] == (lst[j][0] + 1, b): j += 1
            runs.setdefault((x0, lst[j][0], b), []).append(z); i = j + 1
    out = []
    for (x0, x1, b), zs in runs.items():
        zs.sort(); k = 0
        while k < len(zs):
            z0 = zs[k]; m = k
            while m + 1 < len(zs) and zs[m + 1] == zs[m] + 1: m += 1
            out.append((x0, x1, z0, zs[m], b)); k = m + 1
    return out

layers = {}
for (x, y, z), b in blocks.items():
    if b == "grass_block" and y == 0: continue                # ground already grass
    layers.setdefault(y, {})[(x, z)] = b
WATERISH = ("water",)
FRAGILE = ("lantern", "short_grass", "poppy", "allium", "cornflower", "azure_bluet", "oxeye_daisy", "dandelion",
           "lily_of_the_valley", "end_rod", "beacon", "anvil", "chest", "carved_pumpkin", "composter", "barrel")
late = []
for y in sorted(layers):
    for x0, x1, z0, z1, b in emit_layer(y, layers[y]):
        c = f"fill {x0} {G + y} {z0} {x1} {G + y} {z1} {b}" if (x0, z0) != (x1, z1) else f"setblock {x0} {G + y} {z0} {b}"
        (late if b.split("[")[0] in FRAGILE + WATERISH else cmds).append(c)
cmds += late + extra
open(OUT_CMDS, "w", newline="\n").write("\n".join(cmds) + "\n")

# ---------------------------------------------------------------- preview
COL = {"grass_block": "#5d9e3a", "dirt": "#7a5534", "stone_bricks": "#8a8a8a", "mossy_stone_bricks": "#6f8062", "cracked_stone_bricks": "#7c7c7c",
       "polished_andesite": "#a3a6a5", "andesite": "#8d8f8e", "smooth_stone": "#b4b4b4", "polished_deepslate": "#4a4a4f", "sea_lantern": "#cfe7e3",
       "prismarine_bricks": "#5aa497", "water": "#3f76e4", "smooth_quartz": "#ece6df", "smooth_quartz_slab": "#ece6df", "quartz_pillar": "#e8e2d8",
       "chiseled_quartz_block": "#e6dfd3", "stone_brick_wall": "#8a8a8a", "lantern": "#f4b542", "spruce_fence": "#6b4f2f", "chiseled_stone_bricks": "#7f7f7f",
       "purpur_block": "#a77ba7", "purpur_pillar": "#ab81ab", "gold_block": "#f5d33b", "yellow_concrete": "#f1af15", "beacon": "#7de0e0",
       "emerald_block": "#2fc463", "short_grass": "#6aa84a", "oak_log": "#6b5233", "birch_log": "#d8d5c8", "spruce_log": "#3b2a18", "cherry_log": "#3d2028",
       "oak_leaves[persistent=true]": "#3f7d1f", "birch_leaves[persistent=true]": "#5c8a3c", "spruce_leaves[persistent=true]": "#2f5233",
       "cherry_leaves[persistent=true]": "#f2a9c9", "flowering_azalea_leaves[persistent=true]": "#7b9b3a", "end_stone": "#e0e2a8", "red_wool": "#a12722",
       "obsidian": "#1b1528", "chest": "#a2782f", "hay_block": "#c5a21c", "barrel": "#7a5a33", "carved_pumpkin": "#d07a14", "iron_block": "#d9d9d9",
       "anvil": "#4a4a4a", "bricks": "#965b49", "bookshelf": "#7a5a33", "composter": "#6b4f2f", "slime_block": "#79c05a", "end_rod": "#f0ece0",
       "chiseled_bookshelf": "#7a5a33"}
CONC = {"red": "#a02722", "light_blue": "#2389c6", "lime": "#5ea918", "orange": "#e06100", "yellow": "#f1af15", "brown": "#603b1f",
        "purple": "#64209c", "white": "#cfd5d6", "magenta": "#a9309f"}
for c, v in CONC.items(): COL[f"{c}_concrete"] = v; COL[f"{c}_stained_glass"] = v
for fl in FLOWERS: COL.setdefault(fl, "#d84a4a")
top = {}
for (x, y, z), b in blocks.items():
    if (x, z) not in top or y > top[(x, z)][0]: top[(x, z)] = (y, b)
grid = []
for z in range(-R, R + 1):
    row = []
    for x in range(-R, R + 1):
        y, b = top.get((x, z), (0, "grass_block"))
        row.append([COL.get(b, "#ff00ff"), y])
    grid.append(row)
labels = [[math.sin(math.radians(g[0])) * (GATE_R + 8), -math.cos(math.radians(g[0])) * (GATE_R + 8), g[1]] for g in GATES]
html = """<!doctype html><html><head><meta charset="utf-8"><title>Lobby Preview</title>
<style>body{margin:0;background:#1b1d22;color:#eee;font:14px system-ui;display:flex;flex-direction:column;align-items:center;padding:16px}
canvas{max-width:100%;height:auto;image-rendering:pixelated;border-radius:8px;box-shadow:0 4px 24px #0008}
p{color:#aab;max-width:720px;text-align:center}</style></head><body>
<h2>Minigames Lobby - top-down preview (north is up)</h2><canvas id="c"></canvas>
<p>Fountain plaza at the centre, 8 gates with a click-to-join sign and floating title, parkour tower in the west, hills and trees around the edge. Brighter = higher.</p>
<script>const G=__GRID__,L=__LABELS__,S=6,N=G.length,c=document.getElementById('c');c.width=c.height=N*S;const x=c.getContext('2d');
function sh(h,a){h=h.replace('#','');let r=parseInt(h.substr(0,2),16),g=parseInt(h.substr(2,2),16),b=parseInt(h.substr(4,2),16);
r=Math.max(0,Math.min(255,r*a));g=Math.max(0,Math.min(255,g*a));b=Math.max(0,Math.min(255,b*a));return`rgb(${r|0},${g|0},${b|0})`}
for(let z=0;z<N;z++)for(let i=0;i<N;i++){const[cl,y]=G[z][i];const w=i>0?G[z][i-1][1]:y;const n=z>0?G[z-1][i][1]:y;
x.fillStyle=sh(cl,0.82+Math.min(0.35,y*0.012)+(y>w||y>n?0.12:(y<w||y<n?-0.12:0)));x.fillRect(i*S,z*S,S,S)}
x.font='bold 15px system-ui';x.textAlign='center';for(const[lx,lz,t]of L){const px=(lx+70.5)*S,pz=(lz+70.5)*S;
x.lineWidth=4;x.strokeStyle='#000c';x.strokeText(t,px,pz);x.fillStyle='#fff';x.fillText(t,px,pz)}
</script></body></html>"""
open(OUT_HTML, "w", encoding="utf-8").write(html.replace("__GRID__", json.dumps(grid, separators=(",", ":"))).replace("__LABELS__", json.dumps(labels)))
import itertools
bad=[(a,b) for a,b in zip(jumps,jumps[1:]) if (b[2]-a[2]==1 and math.hypot(b[0]-a[0],b[1]-a[1])>3.2) or math.hypot(b[0]-a[0],b[1]-a[1])>4.1 or math.hypot(b[0]-a[0],b[1]-a[1])<1.9]
print("bad jumps:",bad)
print(f"blocks={len(blocks)} commands={len(cmds)} trees={len(placed)} jumps={len(jumps)} first_jump={first} start={start}")
