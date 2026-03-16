# make_dac_m2_pins.py
# Metal2 EN/ENB/ON/ONB input pin boxes + labels for dac4x32module top level.
#
# Layout geometry (dbu=0.001, all coords in nm):
#   4 × dac2u32out4in instances at x = 22050, 97650, 173250, 248850 (pitch 75600)
#   Each instance has 36 pins per row × 2 rows = 72 pins × 4 = 288 total
#
# Pin sequence per instance (physical left→right):
#   Bottom: EN[4k], ENB[4k],  ON[32k..32k+15], ONB[32k..32k+15],  EN[4k+1], ENB[4k+1]
#   Top:  ENB[4k+3], EN[4k+3], ONB[32k+31..32k+16], ON[32k+31..32k+16], ENB[4k+2], EN[4k+2]
#
# ON/ONB wrap: bottom left→right = indices 0..15, top right→left = indices 16..31
# EN/ENB: 4 per instance (2 bottom + 2 top), numbered 0..15 across all 4 instances

try:
    from klayout import db as pya
except ImportError:
    import pya

layout = pya.Layout()
layout.dbu = 0.001
top = layout.create_cell("DAC4X32_M2_PINS")

l_pin   = layout.layer(pya.LayerInfo(10, 2,  "Metal2_pin"))
l_label = layout.layer(pya.LayerInfo(10, 25, "Metal2_label"))

HALF = 100   # 200nm wide pins → ±100nm

# ── geometry constants (local coords within one dac2u32out4in, nm) ──────────
Y_BOT  =   145
Y_TOP  = 26045
X_EN0  =  1625   # EN  bottom-left
X_ENB0 =  2175   # ENB bottom-left
X_ON0  =  3625   # first ON  bottom (ON[0]), pitch 2000 between pairs
X_ONB0 =  4175   # first ONB bottom
ON_PITCH = 2000  # x pitch between ON[i] and ON[i+1]
X_EN1  = 35625   # EN  bottom-right
X_ENB1 = 36175   # ENB bottom-right

# instance x origins in top-level (nm)
INST_X = [22050, 97650, 173250, 248850]

def place(name, lx, y, inst_ox):
    """Place one pin box + label. lx = local x (within instance), inst_ox = instance origin x."""
    x = lx + inst_ox
    top.shapes(l_pin).insert(pya.Box(x - HALF, y - HALF, x + HALF, y + HALF))
    t = pya.Text(name, pya.Trans(pya.Vector(x, y)))
    t.halign = pya.HAlign.HAlignCenter
    t.valign = pya.VAlign.VAlignCenter
    top.shapes(l_label).insert(t)

for k, ox in enumerate(INST_X):
    on_base = k * 32   # ON indices: 0..31, 32..63, 64..95, 96..127
    en_base = k * 4    # EN indices: 0..3,  4..7,   8..11,  12..15

    # ── bottom row, left → right ─────────────────────────────────────────
    place(f"EN[{en_base}]",   X_EN0,  Y_BOT, ox)
    place(f"ENB[{en_base}]",  X_ENB0, Y_BOT, ox)
    for i in range(16):
        place(f"ON[{on_base+i}]",  X_ON0  + i*ON_PITCH, Y_BOT, ox)
        place(f"ONB[{on_base+i}]", X_ONB0 + i*ON_PITCH, Y_BOT, ox)
    place(f"EN[{en_base+1}]",  X_EN1,  Y_BOT, ox)
    place(f"ENB[{en_base+1}]", X_ENB1, Y_BOT, ox)

    # ── top row, left → right (ON indices run 31→16 left→right) ─────────
    place(f"ENB[{en_base+3}]", X_EN0,  Y_TOP, ox)   # ENB left of EN on top
    place(f"EN[{en_base+3}]",  X_ENB0, Y_TOP, ox)
    for i in range(16):
        # physically: ONB[31],ON[31], ONB[30],ON[30], ... ONB[16],ON[16]
        j = 31 - i
        place(f"ONB[{on_base+j}]", X_ON0  + i*ON_PITCH, Y_TOP, ox)
        place(f"ON[{on_base+j}]",  X_ONB0 + i*ON_PITCH, Y_TOP, ox)
    place(f"ENB[{en_base+2}]", X_EN1,  Y_TOP, ox)
    place(f"EN[{en_base+2}]",  X_ENB1, Y_TOP, ox)

n = 4 * (2 + 32 + 2 + 2 + 32 + 2)   # = 288
layout.write("dac4x32_m2_pins.gds")
print(f"Wrote dac4x32_m2_pins.gds  ({n} pins)")
