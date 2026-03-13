import pya

layout = pya.Layout()
layout.dbu = 0.001  # database unit: 1 nm (so coordinates below are in microns / dbu = nm integers)

cell = layout.create_cell("analog_wires")

# Helper: insert a box from micron coordinates (left, bottom, right, top)
def box(layer, datatype, l, b, r, t):
    idx = layout.layer(layer, datatype)
    cell.shapes(idx).insert(pya.DBox(l, b, r, t))

# Helper: insert a path from micron coordinates
def path(layer, datatype, pts_um, width_um):
    idx = layout.layer(layer, datatype)
    pts = [pya.Point.from_dpoint(pya.DPoint(x, y)) for x, y in pts_um]
    w = pya.DPoint(width_um, 0)
    cell.shapes(idx).insert(pya.Path(pts, round(width_um / layout.dbu)))

# Helper: insert a text label
def label(layer, texttype, text, x_um, y_um, mag=0.4):
    idx = layout.layer(layer, texttype)
    t = pya.Text(text, pya.Trans(pya.Point.from_dpoint(pya.DPoint(x_um, y_um))))
    t.size = round(mag / layout.dbu)
    cell.shapes(idx).insert(t)


# ── Boxes ───────────────────────────────────────────────────────────────────

# layer 189/4  – bounding box
box(189, 4,   0.0,   0.0,  99.6, 188.0)

# layer 30/2  – pin rectangles
box(30, 2,  99.2, 103.93,  99.6, 104.63)
box(30, 2,  99.2,  95.745, 99.6,  96.445)

box(30, 2,   0.0, 167.83,   0.4, 168.53)
box(30, 2,   0.0, 151.46,   0.4, 152.16)
box(30, 2,   0.0, 159.645,  0.4, 160.345)
box(30, 2,   0.0, 152.56,   0.4, 154.29)
box(30, 2,   0.0, 165.7,    0.4, 167.43)
box(30, 2,   0.0, 158.345,  0.4, 159.045)
box(30, 2,   0.0, 160.945,  0.4, 161.645)

box(30, 2,   0.0,  35.77,   0.4,  36.47)
box(30, 2,   0.0,  19.4,    0.4,  20.1)
box(30, 2,   0.0,  27.585,  0.4,  28.285)
box(30, 2,   0.0,  20.5,    0.4,  22.23)
box(30, 2,   0.0,  33.64,   0.4,  35.37)
box(30, 2,   0.0,  26.285,  0.4,  26.985)
box(30, 2,   0.0,  28.885,  0.4,  29.585)


# ── Paths (layer 30/0) ───────────────────────────────────────────────────────

# bottom group (y ~ 19–36 µm)
path(30, 0, [( 0.0,  36.12),  (10.91,  36.12)],  0.7)
path(30, 0, [( 0.0,  19.75),  (10.91,  19.75)],  0.7)
path(30, 0, [( 0.0,  27.935), (21.91,  27.935)],  0.7)
path(30, 0, [( 0.0,  21.365), (20.7,   21.365)],  1.73)
path(30, 0, [( 0.0,  34.505), (20.7,   34.505)],  1.73)
path(30, 0, [( 0.0,  29.235), (21.91,  29.235)],  0.7)
path(30, 0, [( 0.0,  26.635), (21.91,  26.635)],  0.7)

# top group (y ~ 151–168 µm)
path(30, 0, [( 0.0, 153.425), (20.7,  153.425)],  1.73)
path(30, 0, [( 0.0, 166.565), (20.7,  166.565)],  1.73)
path(30, 0, [( 0.0, 161.295), (21.91, 161.295)],  0.7)
path(30, 0, [( 0.0, 158.695), (21.91, 158.695)],  0.7)
path(30, 0, [( 0.0, 159.995), (21.91, 159.995)],  0.7)
path(30, 0, [( 0.0, 168.18),  (10.91, 168.18)],   0.7)
path(30, 0, [( 0.0, 151.81),  (10.91, 151.81)],   0.7)

# horizontal bus wires spanning full width
path(30, 0, [( 0.0,  96.095), (99.6,  96.095)],  0.7)
path(30, 0, [( 0.0, 104.28),  (99.6, 104.28)],   0.7)


# ── Labels (layer 30/25) ────────────────────────────────────────────────────

# bottom group
label(30, 25, "VcascP[0]", 0.2,  19.75)
label(30, 25, "VcascP[1]", 0.2,  36.12)
label(30, 25, "Iout[0]",   0.2,  27.935)
label(30, 25, "VDDA[0]",   0.2,  21.365)
label(30, 25, "VDDA[1]",   0.2,  34.505)
label(30, 25, "VbiasP[1]", 0.2,  29.235)
label(30, 25, "VbiasP[0]", 0.2,  26.635)

# top group
label(30, 25, "VcascP[2]", 0.2, 151.81)
label(30, 25, "VcascP[3]", 0.2, 168.18)
label(30, 25, "Iout[1]",   0.2, 159.995)
label(30, 25, "VDDA[2]",   0.2, 153.425)
label(30, 25, "VDDA[3]",   0.2, 166.565)
label(30, 25, "VbiasP[3]", 0.2, 161.295)
label(30, 25, "VbiasP[2]", 0.2, 158.695)

# right-side pins
label(30, 25, "i_in",  99.4, 104.28)
label(30, 25, "i_out", 99.4,  96.095)


# ── Write output ─────────────────────────────────────────────────────────────

layout.write("analog_wires_rebuilt.gds")
print("Written: analog_wires_rebuilt.gds")
