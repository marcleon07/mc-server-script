"""Builds the small lobby of one game server (its overworld, called "lobby").
usage: python gamelobby.py <bedwars|skywars|hideseek|duels|parkour> <out_cmds.txt>
Paste the output into that server's console (it force-loads the area itself).
The round plaza (radius 14) sits on the flat grass at y=-5. Players spawn at 0.5 -4 9.5 facing north,
towards the centre statue and the wall of join signs at z=-10.
"""
import math, sys

G = -5
R = 13
THEMES = {
    "bedwars": dict(title="BEDWARS", color="red", sub="Protect your bed, break theirs!",
                    floor=("smooth_stone", "polished_andesite"), ring="red_concrete", centre="red_wool",
                    wall="red_terracotta", pillar="stone_bricks", light="glowstone", glass="red_stained_glass",
                    pedestal="white_wool", signbase="red_terracotta",
                    signs=[("QUICK JOIN", "dark_red", "Any arena", "/bw autojoin"),
                           ("CAVE", "gold", "4 teams of 4", "/bw join cave"),
                           ("DESERT", "gold", "2 teams of 2", "/bw join desert"),
                           ("LEAVE", "dark_gray", "Leave queue", "/bw leave"),
                           ("HUB", "dark_green", "Back to hub", "/lobby")],
                    pads=[(-9, 0, "orange_carpet", "Cave - waiting area"), (10, 0, "yellow_carpet", "Desert - waiting area")]),
    "skywars": dict(title="SKYWARS", color="aqua", sub="Loot, bridge, survive!",
                    floor=("smooth_quartz", "quartz_bricks"), ring="light_blue_concrete", centre="cyan_glazed_terracotta",
                    wall="cyan_terracotta", pillar="quartz_pillar", light="sea_lantern", glass="light_blue_stained_glass",
                    pedestal="grass_block", signbase="cyan_terracotta",
                    signs=[("SOLO", "dark_aqua", "Join a game", "/rsw play solo"),
                           ("KITS", "dark_purple", "Pick a kit", "/rsw kits"),
                           ("SHOP", "gold", "Spend coins", "/rsw shop"),
                           ("LEAVE", "dark_gray", "Leave game", "/rsw leave"),
                           ("HUB", "dark_green", "Back to hub", "/lobby")], pads=[]),
    "hideseek": dict(title="HIDE & SEEK", color="yellow", sub="Hide well... or seek them all!",
                     floor=("moss_block", "mossy_stone_bricks"), ring="lime_concrete", centre="jack_o_lantern",
                     wall="oak_leaves[persistent=true]", pillar="spruce_log", light="ochre_froglight", glass="lime_stained_glass",
                     pedestal="mossy_cobblestone", signbase="spruce_planks",
                     signs=[("JOIN", "dark_green", "Join the queue", "/hs join"),
                            ("LEAVE", "dark_gray", "Leave queue", "/hs leave"),
                            ("HUB", "dark_green", "Back to hub", "/lobby")], pads=[]),
    "duels": dict(title="DUELS", color="gold", sub="1v1 - pick a kit and fight",
                  floor=("polished_blackstone_bricks", "blackstone"), ring="orange_concrete", centre="gilded_blackstone",
                  wall="polished_blackstone", pillar="chiseled_polished_blackstone", light="shroomlight", glass="orange_stained_glass",
                  pedestal="gold_block", signbase="polished_blackstone",
                  signs=[("QUEUES", "dark_red", "Pick a kit", "/queue"),
                         ("LEAVE", "dark_gray", "Leave queue", "/queue leave"),
                         ("HUB", "dark_green", "Back to hub", "/lobby")], pads=[]),
    "parkour": dict(title="PARKOUR", color="light_purple", sub="Race to the top of the tower",
                    floor=("purpur_block", "end_stone_bricks"), ring="magenta_concrete", centre="purpur_pillar",
                    wall="purpur_block", pillar="purpur_pillar", light="end_rod", glass="magenta_stained_glass",
                    pedestal="end_stone_bricks", signbase="purpur_block",
                    signs=[("RACE", "dark_purple", "Tower (2+)", "/parkour join tower"),
                           ("LEAVE", "dark_gray", "Leave race", "/parkour leave"),
                           ("HUB", "dark_green", "Back to hub", "/lobby")], pads=[]),
}

game, out = sys.argv[1], sys.argv[2]
T = THEMES[game]
cmds = ["forceload add -24 -24 23 23",
        "minecraft:kill @e[type=text_display,tag=gamelobby]",
        f"fill -18 {G + 1} -18 18 {G + 8} 18 air",
        f"fill -18 {G} -18 18 {G} 18 grass_block"]
blocks = {}
def put(x, y, z, b): blocks[(x, y, z)] = b

for x in range(-R - 2, R + 3):
    for z in range(-R - 2, R + 3):
        r = math.hypot(x, z)
        if r < 2.5: put(x, G, z, T["centre"])
        elif r <= R - 0.5: put(x, G, z, T["ring"] if 6.5 <= r < 7.5 else T["floor"][(x + z) % 2])
        elif r <= R + 0.5: put(x, G, z, T["ring"])
        elif r <= R + 1.5:                                   # low wall + invisible barrier
            put(x, G, z, T["ring"]); put(x, G + 1, z, T["wall"])
            for y in (G + 2, G + 3): put(x, y, z, "barrier")
for k in range(8):                                           # pillars with lights around the wall
    a = math.radians(22.5 + k * 45)
    x, z = round(math.sin(a) * (R + 1)), round(-math.cos(a) * (R + 1))
    for y in range(G + 1, G + 5): put(x, y, z, T["pillar"])
    put(x, G + 5, z, T["light"])
for dx in (-1, 0, 1):                                        # centre pedestal
    for dz in (-1, 0, 1):
        put(dx, G + 1, dz, T["pedestal"])
put(0, G + 2, 0, T["centre"])
put(0, G + 3, 0, T["light"])

# sign wall (north): coloured glass backdrop, one sign per entry on a base block, facing south
n = len(T["signs"]); xs = [round((i - (n - 1) / 2) * 3) for i in range(n)]
for x in range(xs[0] - 2, xs[-1] + 3):
    for y in range(G + 1, G + 4): put(x, y, -11, T["glass"])
for x in xs: put(x, G + 1, -10, T["signbase"])

for (x, y, z), b in sorted(blocks.items(), key=lambda kv: kv[0][1]):
    cmds.append(f"setblock {x} {y} {z} {b}")

for x, (title, col, desc, cmd) in zip(xs, T["signs"]):
    cmds.append(f'setblock {x} {G + 2} -10 minecraft:oak_sign[rotation=0]{{is_waxed:1b,front_text:{{messages:['
                f'{{text:"-------------",color:"dark_gray",click_event:{{action:"run_command",command:"{cmd}"}}}},'
                f'{{text:"{title}",color:"{col}",bold:true}},{{text:"{desc}",color:"black"}},{{text:"-------------",color:"dark_gray"}}]}}}}')

def text_display(x, y, z, text, scale=1.0, extra=""):
    cmds.append(f'summon text_display {x} {y} {z} {{Tags:["gamelobby"],billboard:"vertical",background:1610612736,'
                f'transformation:{{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],translation:[0f,0f,0f],scale:[{scale}f,{scale}f,{scale}f]}},'
                f'text:{text}{extra}}}')
text_display(0.5, G + 5.2, 0.5, f'{{text:"{T["title"]}",color:"{T["color"]}",bold:true,extra:[{{text:"\\n{T["sub"]}",color:"gray",bold:false}}]}}', 2.0)
text_display(0.5, G + 4.6, -10.4, '{text:"Click a sign",color:"white"}')
for x, z, carpet, label in T["pads"]:
    for dx in (-1, 0, 1):
        for dz in (-1, 0, 1): cmds.append(f"setblock {x + dx} {G + 1} {z + dz} {carpet}")
    text_display(x + 0.5, G + 3.2, z + 0.5, f'{{text:"{label}",color:"yellow"}}')

cmds += [f"setworldspawn 0 {G + 1} 9 180 0", "forceload remove -24 -24 23 23"]
open(out, "w", newline="\n").write("\n".join(cmds) + "\n")
print(game, len(cmds), "commands")
