"""Procedural, toy-like 3D props. Each builder returns a Prop (root empty + inner animation fn).

Prop keys (Gemini picks one per scene, see pipeline/script_writer.py):
chip planet rocket battery neural globe bulb shield atom gear money gold house courthouse document car
"""
import math

from mathutils import Euler

from common import (empty, sphere, rbox, cyl, cone, torus, capsule, polygon_prism, link_between,
                    make_material, make_procedural_material, hex_rgba, Tracker, ease_out_back,
                    smoothstep, pulse)

PROP_KEYS = ["chip", "planet", "rocket", "battery", "neural", "globe", "bulb", "shield", "atom", "gear"]


class Prop:
    def __init__(self, root, inner, hover=0.06, tilt=(0, 0, 0)):
        self.root = root
        self.inner = inner
        self.hover = hover
        self.base_loc = tuple(root.location)

    def update(self, t):
        pop = ease_out_back(t / 0.7)
        s = max(0.001, pop)
        self.root.scale = (s, s, s)
        bx, by, bz = self.base_loc
        self.root.location = (bx, by, bz + self.hover * math.sin(2 * math.pi * t / 3.2))
        self.inner(t)


# ---------------------------------------------------------------------------
def _m(name, col, **kw):
    return make_material(name, col, **kw)


def build_chip(tr, pal, pos):
    root = empty("prop_root", pos)
    tr.track(root)
    tilt = empty("chip_tilt", (0, 0, 0), root)
    tilt.rotation_euler = Euler((math.radians(58), 0, 0))
    tr.track(tilt, "rotation_euler")
    body = _m("chip_body", hex_rgba("#1A2342"), rough=0.3, metal=0.25, coat=0.7, bevel=0.02)
    die = _m("chip_die", hex_rgba(pal["accent"]), rough=0.22, coat=0.8, bevel=0.01,
             emission=hex_rgba(pal["accent"]), strength=0.5)
    core = _m("chip_core", hex_rgba(pal["accent2"]), rough=0.3, emission=hex_rgba(pal["accent2"]), strength=3.0, bevel=0)
    gold = _m("chip_pin", (1.0, 0.76, 0.28, 1), rough=0.22, metal=1.0, bevel=0.01)
    trace = _m("chip_trace", hex_rgba("#7CF3FF"), rough=0.5, emission=hex_rgba("#7CF3FF"), strength=2.5, bevel=0)
    rbox("chip_base", (1.7, 1.7, 0.22), (0, 0, 0), body, tilt, radius=0.12)
    rbox("chip_die", (0.95, 0.95, 0.09), (0, 0, 0.15), die, tilt, radius=0.05)
    rbox("chip_core", (0.5, 0.5, 0.06), (0, 0, 0.21), core, tilt, radius=0.04)
    for i in range(7):
        p = -0.66 + i * 0.22
        rbox(f"pin_t{i}", (0.1, 0.24, 0.06), (p, 0.95, 0.0), gold, tilt, radius=0.02, segs=3)
        rbox(f"pin_b{i}", (0.1, 0.24, 0.06), (p, -0.95, 0.0), gold, tilt, radius=0.02, segs=3)
        rbox(f"pin_l{i}", (0.24, 0.1, 0.06), (-0.95, p, 0.0), gold, tilt, radius=0.02, segs=3)
        rbox(f"pin_r{i}", (0.24, 0.1, 0.06), (0.95, p, 0.0), gold, tilt, radius=0.02, segs=3)
    for i, off in enumerate((-0.3, 0.0, 0.3)):
        rbox(f"tr_h{i}", (0.28, 0.025, 0.02), (-0.7, off, 0.2), trace, tilt, radius=0.008, segs=2)
        rbox(f"tr_v{i}", (0.025, 0.28, 0.02), (off, 0.7, 0.2), trace, tilt, radius=0.008, segs=2)
    sock = core.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
    tr.track_socket(sock)

    def inner(t):
        root.rotation_euler = Euler((0, 0, 0.45 * math.sin(2 * math.pi * t / 6.0)))
        tilt.rotation_euler = Euler((math.radians(58) + 0.07 * math.sin(2 * math.pi * t / 4.0), 0, 0))
        sock.default_value = 2.0 + 3.0 * (0.5 + 0.5 * math.sin(2 * math.pi * t / 1.1))
    return Prop(root, inner)


def build_planet(tr, pal, pos):
    root = empty("prop_root", pos)
    tr.track(root)
    tilt = empty("planet_tilt", (0, 0, 0), root)
    tilt.rotation_euler = Euler((math.radians(-18), math.radians(14), 0))
    surf = make_procedural_material("planet_surf", "bands", hex_rgba(pal["accent2"]), hex_rgba("#FFE8C2"),
                                    scale=3.2, rough=0.5, coat=0.2, sss=0.2)
    ringm = _m("planet_ring", hex_rgba(pal["accent"]), rough=0.4, coat=0.5, sss=0.1, bevel=0)
    ringm2 = _m("planet_ring2", hex_rgba("#FFF3D6"), rough=0.4, coat=0.4, bevel=0)
    moonm = _m("planet_moon", hex_rgba("#E5E7EB"), rough=0.55, coat=0.3, bevel=0)
    planet = sphere("planet", 0.78, (0, 0, 0), surf, tilt, seg=64, rings=32)
    tr.track(planet, "rotation_euler")
    r1 = torus("ring1", 1.2, 0.08, (0, 0, 0), ringm, tilt, rot=(0, 0, 0))
    r1.scale = (1, 1, 0.3)
    r2 = torus("ring2", 1.48, 0.045, (0, 0, 0), ringm2, tilt, rot=(0, 0, 0))
    r2.scale = (1, 1, 0.3)
    orbit = empty("moon_orbit", (0, 0, 0), root)
    orbit.rotation_euler = Euler((math.radians(70), 0, math.radians(20)))
    moon = sphere("moon", 0.17, (1.5, 0, 0), moonm, orbit, seg=32, rings=16)
    tr.track(moon, "location")

    def inner(t):
        planet.rotation_euler = Euler((0, 0, 0.5 * t))
        a = 2 * math.pi * t / 6.5 + 0.6
        moon.location = (1.55 * math.cos(a), 1.55 * math.sin(a), 0)
        root.rotation_euler = Euler((0, 0, 0.25 * math.sin(2 * math.pi * t / 7.0)))
    return Prop(root, inner)


def build_rocket(tr, pal, pos):
    root = empty("prop_root", pos)
    tr.track(root)
    lean = empty("rocket_lean", (0, 0, 0), root)
    lean.rotation_euler = Euler((0, math.radians(-32), 0))
    white = _m("rk_body", (0.96, 0.97, 1.0, 1), rough=0.25, coat=0.7, sss=0.1, bevel=0.012)
    red = _m("rk_red", hex_rgba(pal["accent2"]), rough=0.3, coat=0.6, bevel=0.012)
    acc = _m("rk_acc", hex_rgba(pal["accent"]), rough=0.3, coat=0.5, bevel=0.012)
    glass = _m("rk_glass", hex_rgba("#5BC8FF"), rough=0.05, coat=1.0, emission=hex_rgba("#5BC8FF"), strength=0.7, bevel=0)
    flame_m = _m("rk_flame", hex_rgba("#FF9A1F"), rough=0.5, emission=hex_rgba("#FFB02E"), strength=8.0, bevel=0)
    flame_m2 = _m("rk_flame2", hex_rgba("#FFF1A8"), rough=0.5, emission=hex_rgba("#FFF1A8"), strength=10.0, bevel=0)
    capsule("rk_cap", 0.38, 0.75, (0, 0, 0), white, lean)
    cone("rk_nose", 0.37, 0.0, 0.85, (0, 0, 0.98), red, lean, bevel=0.05)
    torus("rk_stripe", 0.385, 0.045, (0, 0, -0.25), acc, lean)
    glass_ring = torus("rk_win_ring", 0.2, 0.045, (0, -0.35, 0.25), acc, lean, rot=(math.radians(90), 0, 0))
    sphere("rk_win", 0.17, (0, -0.36, 0.25), glass, lean, scale=(1, 0.55, 1), seg=32, rings=16)
    for k in range(3):
        a = k * 2 * math.pi / 3 + math.pi / 2
        holder = empty(f"fin_h{k}", (0, 0, -0.5), lean)
        holder.rotation_euler = Euler((0, 0, a - math.pi / 2))
        f = rbox(f"fin{k}", (0.1, 0.55, 0.62), (0, 0.5, -0.1), red, holder, radius=0.04)
        f.rotation_euler = Euler((math.radians(-18), 0, 0))
    cyl("rk_nozzle", 0.2, 0.2, (0, 0, -0.78), acc, lean, bevel=0.03)
    fl1 = cone("rk_flame", 0.2, 0.0, 0.9, (0, 0, -1.3), flame_m, lean, rot=(math.radians(180), 0, 0), bevel=0)
    fl2 = cone("rk_flame_in", 0.11, 0.0, 0.6, (0, 0, -1.16), flame_m2, lean, rot=(math.radians(180), 0, 0), bevel=0)
    tr.track(fl1, "scale")
    tr.track(fl2, "scale")

    def inner(t):
        k = 1.0 + 0.18 * math.sin(2 * math.pi * t * 7.0) + 0.1 * math.sin(2 * math.pi * t * 11.3)
        fl1.scale = (1.0, 1.0, k)
        fl2.scale = (1.0, 1.0, 1.0 + 0.2 * math.sin(2 * math.pi * t * 9.0 + 1))
        root.rotation_euler = Euler((0.04 * math.sin(2 * math.pi * t * 1.6), 0.06 * math.sin(2 * math.pi * t * 2.1),
                                     0.25 * math.sin(2 * math.pi * t / 5.0)))
    return Prop(root, inner, hover=0.14)


def build_battery(tr, pal, pos):
    root = empty("prop_root", pos)
    tr.track(root)
    roll = empty("bat_roll", (0, 0, 0), root)
    roll.rotation_euler = Euler((0, math.radians(18), 0))
    body = _m("bat_body", hex_rgba("#2B3358"), rough=0.3, coat=0.7, sss=0.05, bevel=0.015)
    green = _m("bat_green", hex_rgba(pal["accent2"]), rough=0.28, coat=0.7, sss=0.1, bevel=0.012)
    metal = _m("bat_metal", (0.85, 0.87, 0.92, 1), rough=0.2, metal=1.0, bevel=0.01)
    bolt_m = _m("bat_bolt", hex_rgba("#FFE14D"), rough=0.4, emission=hex_rgba("#FFD21F"), strength=4.0, bevel=0)
    cyl("bat_body", 0.58, 1.65, (0, 0, 0), body, roll, bevel=0.1)
    cyl("bat_label", 0.595, 1.0, (0, 0, -0.18), green, roll, bevel=0.04)
    cyl("bat_term", 0.22, 0.2, (0, 0, 0.9), metal, roll, bevel=0.04)
    bolt_pts = [(0.14, 0.62), (-0.30, -0.06), (-0.02, -0.06), (-0.16, -0.62), (0.32, 0.10), (0.04, 0.10)]
    polygon_prism("bat_bolt", bolt_pts, 0.1, bolt_m, roll, loc=(0, -0.62, -0.15), bevel=0.025)
    sock = bolt_m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
    tr.track_socket(sock)

    def inner(t):
        root.rotation_euler = Euler((0, 0, 0.5 * math.sin(2 * math.pi * t / 5.5)))
        roll.rotation_euler = Euler((0.05 * math.sin(2 * math.pi * t / 3.0), math.radians(18), 0))
        sock.default_value = 2.5 + 3.5 * (0.5 + 0.5 * math.sin(2 * math.pi * t / 1.3))
    tr.track(roll, "rotation_euler")
    return Prop(root, inner)


def build_neural(tr, pal, pos):
    import random
    rng = random.Random(7)
    root = empty("prop_root", pos)
    tr.track(root)
    layers = [3, 4, 4, 2]
    xs = [-1.35, -0.45, 0.45, 1.35]
    mats, nodes_by_layer = [], []
    colors = [pal["accent"], "#FFFFFF", pal["accent2"], pal["accent"]]
    for li, c in enumerate(colors):
        mm = _m(f"nn_node{li}", hex_rgba(c), rough=0.25, coat=0.8, sss=0.1, bevel=0,
                emission=hex_rgba(c), strength=0.8)
        mats.append(mm)
        tr.track_socket(mm.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"])
    edge = _m("nn_edge", hex_rgba("#FFFFFF"), rough=0.5, emission=hex_rgba("#FFFFFF"), strength=1.6, bevel=0)
    pts = []
    for li, n in enumerate(layers):
        col = []
        for i in range(n):
            z = (i - (n - 1) / 2) * 0.62
            y = rng.uniform(-0.35, 0.35)
            col.append((xs[li], y, z))
            sphere(f"nn_{li}_{i}", 0.22, (xs[li], y, z), mats[li], root, seg=32, rings=16)
        pts.append(col)
    for li in range(len(layers) - 1):
        for a in pts[li]:
            for b in pts[li + 1]:
                link_between("nn_edge", a, b, 0.03, edge, root)

    def inner(t):
        loop = 2.6
        for li, mm in enumerate(mats):
            sock = mm.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
            sock.default_value = 0.8 + 9.0 * pulse((t % loop), li * 0.42, 0.55)
        root.rotation_euler = Euler((0.05 * math.sin(2 * math.pi * t / 4.0), 0, 0.55 * math.sin(2 * math.pi * t / 6.0)))
    return Prop(root, inner, hover=0.1)


def build_globe(tr, pal, pos):
    root = empty("prop_root", pos)
    tr.track(root)
    axial = empty("globe_axial", (0, 0, 0), root)
    axial.rotation_euler = Euler((0, math.radians(-23), 0))
    earth = make_procedural_material("globe_surf", "land", hex_rgba("#1F7BFF"), hex_rgba("#59D36B"),
                                     scale=2.6, rough=0.45, coat=0.5, sss=0.1)
    metal = _m("globe_metal", (0.9, 0.9, 0.95, 1), rough=0.22, metal=1.0, bevel=0)
    mark = _m("globe_mark", hex_rgba(pal["accent"]), rough=0.3, emission=hex_rgba(pal["accent"]), strength=6.0, bevel=0)
    spin = empty("globe_spin", (0, 0, 0), axial)
    tr.track(spin, "rotation_euler")
    sphere("globe", 0.88, (0, 0, 0), earth, spin, seg=72, rings=36)
    for i, (lat, lon) in enumerate([(25, 20), (-10, 100), (45, 200), (5, 280), (-35, 330), (60, 70)]):
        la, lo = math.radians(lat), math.radians(lon)
        r = 0.91
        sphere(f"mark{i}", 0.045, (r * math.cos(la) * math.cos(lo), r * math.cos(la) * math.sin(lo), r * math.sin(la)),
               mark, spin, seg=16, rings=8)
    torus("globe_ring", 1.08, 0.028, (0, 0, 0), metal, axial, rot=(math.radians(90), 0, 0))
    torus("globe_ring2", 1.16, 0.02, (0, 0, 0), metal, axial, rot=(math.radians(90), 0, math.radians(90)))

    def inner(t):
        spin.rotation_euler = Euler((0, 0, 0.7 * t))
    return Prop(root, inner)


def build_bulb(tr, pal, pos):
    root = empty("prop_root", pos)
    tr.track(root)
    glow_col = hex_rgba("#FFD166")
    glass = _m("bulb_glass", glow_col, rough=0.1, coat=1.0, emission=glow_col, strength=2.6, bevel=0)
    metal = _m("bulb_metal", (0.78, 0.8, 0.86, 1), rough=0.28, metal=1.0, bevel=0.01)
    dark = _m("bulb_dark", hex_rgba("#2B3358"), rough=0.4, coat=0.4, bevel=0.01)
    ray = _m("bulb_ray", hex_rgba(pal["accent"]), rough=0.4, emission=hex_rgba(pal["accent"]), strength=3.0, bevel=0)
    tr.track_socket(glass.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"])
    sphere("bulb_glass", 0.78, (0, 0, 0.35), glass, root, scale=(1, 1, 1.05), seg=64, rings=32)
    cone("bulb_neck", 0.5, 0.3, 0.45, (0, 0, -0.45), glass, root, bevel=0)
    for i in range(4):
        torus(f"bulb_thread{i}", 0.31 - i * 0.012, 0.055, (0, 0, -0.78 - i * 0.12), metal, root)
    sphere("bulb_tip", 0.13, (0, 0, -1.28), dark, root, seg=24, rings=12)
    rays = []
    for i in range(8):
        a = i * math.pi / 4
        h = empty(f"ray_h{i}", (0, 0, 0.35), root)
        h.rotation_euler = Euler((0, 0, 0))
        r = capsule(f"ray{i}", 0.045, 0.2, (1.25 * math.cos(a), 0, 1.25 * math.sin(a)), ray, h,
                    rot=(0, math.pi / 2 - a + math.pi / 2 * 0, 0))
        r.rotation_euler = Euler((0, -(a) + math.pi / 2, 0))
        tr.track(r, "scale")
        rays.append((r, i))
    sock = glass.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]

    def inner(t):
        sock.default_value = 2.6 + 1.4 * (0.5 + 0.5 * math.sin(2 * math.pi * t / 1.6))
        for r, i in rays:
            k = 0.75 + 0.45 * (0.5 + 0.5 * math.sin(2 * math.pi * t / 1.6 + i * 0.4))
            r.scale = (k, k, k)
        root.rotation_euler = Euler((0, 0.06 * math.sin(2 * math.pi * t / 3.0), 0.4 * math.sin(2 * math.pi * t / 6.0)))
    return Prop(root, inner)


def build_shield(tr, pal, pos):
    root = empty("prop_root", pos)
    tr.track(root)
    outer = _m("sh_outer", hex_rgba(pal["accent2"]), rough=0.25, coat=0.8, sss=0.1, bevel=0.012)
    inner_m = _m("sh_inner", hex_rgba("#2B6BFF"), rough=0.25, coat=0.8, sss=0.1, bevel=0.012)
    check = _m("sh_check", (1, 1, 1, 1), rough=0.3, emission=(1, 1, 1, 1), strength=2.0, bevel=0)
    pts = [(-0.85, 0.95), (0.85, 0.95), (0.85, 0.15), (0.62, -0.42), (0.0, -1.05), (-0.62, -0.42), (-0.85, 0.15)]
    pts_in = [(x * 0.82, z * 0.82 + 0.02) for x, z in pts]
    polygon_prism("sh_outer", pts, 0.3, outer, root, bevel=0.07)
    polygon_prism("sh_inner", pts_in, 0.1, inner_m, root, loc=(0, -0.18, 0), bevel=0.04)
    a = rbox("chk_long", (0.74, 0.13, 0.2), (0.15, -0.3, 0.12), check, root, radius=0.06)
    a.rotation_euler = Euler((0, math.radians(-52), 0))
    b = rbox("chk_short", (0.42, 0.13, 0.2), (-0.28, -0.3, 0.0), check, root, radius=0.06)
    b.rotation_euler = Euler((0, math.radians(42), 0))

    def inner(t):
        root.rotation_euler = Euler((0, 0.05 * math.sin(2 * math.pi * t / 3.3), 0.5 * math.sin(2 * math.pi * t / 5.0)))
    return Prop(root, inner)


def build_atom(tr, pal, pos):
    root = empty("prop_root", pos)
    tr.track(root)
    nuc_a = _m("atom_a", hex_rgba(pal["accent"]), rough=0.25, coat=0.8, sss=0.1, bevel=0)
    nuc_b = _m("atom_b", hex_rgba(pal["accent2"]), rough=0.25, coat=0.8, sss=0.1, bevel=0)
    ringm = _m("atom_ring", hex_rgba("#BFD8FF"), rough=0.3, emission=hex_rgba("#BFD8FF"), strength=0.8, bevel=0)
    elec = _m("atom_e", hex_rgba("#7CF3FF"), rough=0.2, emission=hex_rgba("#7CF3FF"), strength=7.0, bevel=0)
    for i, p in enumerate([(0.1, 0.05, 0.1), (-0.12, -0.05, 0.06), (0.0, 0.12, -0.12), (0.02, -0.12, -0.04), (-0.1, 0.1, -0.1)]):
        sphere(f"nuc{i}", 0.27, p, nuc_a if i % 2 == 0 else nuc_b, root, seg=32, rings=16)
    electrons = []
    for k in range(3):
        h = empty(f"ring_h{k}", (0, 0, 0), root)
        h.rotation_euler = Euler((math.radians(72), 0, k * math.pi / 3))
        torus(f"ring{k}", 1.22, 0.045, (0, 0, 0), ringm, h)
        e = sphere(f"elec{k}", 0.15, (1.22, 0, 0), elec, h, seg=24, rings=12)
        tr.track(e, "location")
        electrons.append((e, k))

    def inner(t):
        for e, k in electrons:
            a = 2 * math.pi * t / (2.6 + 0.5 * k) + k * 2.1
            e.location = (1.22 * math.cos(a), 1.22 * math.sin(a), 0)
        root.rotation_euler = Euler((0.12 * math.sin(2 * math.pi * t / 5.0), 0, 0.4 * t))
    return Prop(root, inner, hover=0.08)


def _gear(name, teeth, r_root, tooth_h, thick, mat_body, mat_cap, parent):
    g = empty(name, (0, 0, 0), parent)
    cyl(name + "_body", r_root, thick, (0, 0, 0), mat_body, g, rot=(math.radians(90), 0, 0), bevel=0.04)
    for i in range(teeth):
        a = i * 2 * math.pi / teeth
        holder = empty(f"{name}_t{i}", (0, 0, 0), g)
        holder.rotation_euler = Euler((0, -a, 0))
        rbox(f"{name}_tooth{i}", (r_root * 0.5, thick, tooth_h * 1.1 * 0 + r_root * 0.34),
             (0, 0, r_root + tooth_h * 0.25), mat_body, holder, radius=0.045, segs=3)
    cyl(name + "_cap", r_root * 0.42, thick * 1.2, (0, 0, 0), mat_cap, g, rot=(math.radians(90), 0, 0), bevel=0.03)
    cyl(name + "_hub", r_root * 0.2, thick * 1.5, (0, 0, 0), mat_body, g, rot=(math.radians(90), 0, 0), bevel=0.02)
    return g


def build_gear(tr, pal, pos):
    root = empty("prop_root", pos)
    tr.track(root)
    a_m = _m("gear_a", hex_rgba(pal["accent"]), rough=0.28, coat=0.7, sss=0.1, bevel=0.012)
    b_m = _m("gear_b", hex_rgba(pal["accent2"]), rough=0.28, coat=0.7, sss=0.1, bevel=0.012)
    cap = _m("gear_cap", hex_rgba("#2B3358"), rough=0.3, coat=0.6, bevel=0.01)
    ga = _gear("gearA", 12, 0.78, 0.2, 0.34, a_m, cap, root)
    gb = _gear("gearB", 8, 0.5, 0.2, 0.34, b_m, cap, root)
    ga.location = (-0.45, 0, 0.35)
    ang = math.radians(32)
    d = 0.78 + 0.5 + 0.2 + 0.02
    gb.location = (-0.45 + d * math.cos(ang), 0, 0.35 - d * math.sin(ang))
    tr.track(ga, "rotation_euler")
    tr.track(gb, "rotation_euler")

    def inner(t):
        w = 0.55 * t
        ga.rotation_euler = Euler((0, w, 0))
        gb.rotation_euler = Euler((0, -w * 12 / 8 + math.pi / 8, 0))
        root.rotation_euler = Euler((math.radians(-8), 0.35 * math.sin(2 * math.pi * t / 6.0), 0))
    return Prop(root, inner)



# ---------------------------------------------------------------------------
# Documentary / investigative props (reusable across non-technology stories)
def _case_prop(tr, pos, name):
    root = empty(f"{name}_root", pos)
    tr.track(root)
    return root


def build_money(tr, pal, pos):
    root = _case_prop(tr, pos, "money")
    paper = _m("cash_paper", hex_rgba("#6F9B78"), rough=0.85, bevel=0.008)
    band = _m("cash_band", hex_rgba("#F4E7C5"), rough=0.8, bevel=0.004)
    ink = _m("cash_ink", hex_rgba("#254A38"), rough=0.8, bevel=0)
    for i in range(3):
        x = (i - 1) * 0.62
        rbox(f"cash_stack_{i}", (0.82, 0.48, 0.22), (x, 0, 0), paper, root, radius=0.025)
        rbox(f"cash_band_{i}", (0.14, 0.50, 0.235), (x, 0, 0.01), band, root, radius=0.008)
        rbox(f"cash_mark_{i}", (0.20, 0.025, 0.24), (x, -0.245, 0), ink, root, radius=0.003)
    return Prop(root, lambda t: setattr(root, "rotation_euler", Euler((0, 0, 0.08 * math.sin(t * 0.8)))))


def build_gold(tr, pal, pos):
    root = _case_prop(tr, pos, "gold")
    gold = _m("gold_bar", hex_rgba("#D9A62E"), rough=0.24, metal=0.82, coat=0.35, bevel=0.02)
    highlight = _m("gold_stamp", hex_rgba("#FFE7A0"), rough=0.35, metal=0.6, emission=hex_rgba("#FFE7A0"), strength=0.15, bevel=0)
    for i, (x, y, z) in enumerate([(-0.48, 0, 0), (0.48, 0, 0), (0, 0.02, 0.24)]):
        bar = rbox(f"gold_ingot_{i}", (0.95, 0.52, 0.22), (x, y, z), gold, root, radius=0.07)
        bar.rotation_euler[1] = math.radians(-8 if i == 0 else 8 if i == 1 else 0)
        rbox(f"gold_stamp_{i}", (0.34, 0.025, 0.018), (x, -0.265, z + 0.025), highlight, root, radius=0.006)
    return Prop(root, lambda t: setattr(root, "rotation_euler", Euler((0, 0, 0.07 * math.sin(t * 0.7)))))


def build_house(tr, pal, pos):
    root = _case_prop(tr, pos, "house")
    wall = _m("house_wall", hex_rgba("#B8C6D5"), rough=0.82, bevel=0.01)
    roof = _m("house_roof", hex_rgba(pal["accent"]), rough=0.7, bevel=0.01)
    dark = _m("house_window", hex_rgba("#19344D"), rough=0.3, emission=hex_rgba("#19344D"), strength=0.2, bevel=0)
    rbox("house_body", (1.75, 1.25, 1.05), (0, 0, 0.48), wall, root, radius=0.025)
    left = rbox("house_roof_left", (1.0, 1.48, 0.16), (-0.40, 0, 1.08), roof, root, radius=0.02)
    right = rbox("house_roof_right", (1.0, 1.48, 0.16), (0.40, 0, 1.08), roof, root, radius=0.02)
    left.rotation_euler[1] = math.radians(-32)
    right.rotation_euler[1] = math.radians(32)
    rbox("house_door", (0.28, 0.04, 0.58), (0, -0.64, 0.25), dark, root, radius=0.01)
    for x in (-0.52, 0.52):
        rbox("house_window", (0.30, 0.04, 0.28), (x, -0.64, 0.62), dark, root, radius=0.01)
    return Prop(root, lambda t: setattr(root, "rotation_euler", Euler((0, 0, 0.04 * math.sin(t * 0.6)))))


def build_courthouse(tr, pal, pos):
    root = _case_prop(tr, pos, "courthouse")
    stone = _m("court_stone", hex_rgba("#CBD5E1"), rough=0.75, bevel=0.01)
    gold = _m("court_accent", hex_rgba(pal["accent"]), rough=0.45, metal=0.35, bevel=0.01)
    rbox("court_base", (2.1, 1.15, 0.18), (0, 0, -0.12), stone, root, radius=0.025)
    rbox("court_roof", (2.05, 1.0, 0.20), (0, 0, 1.05), stone, root, radius=0.025)
    for x in (-0.72, -0.24, 0.24, 0.72):
        cyl("court_column", 0.095, 1.05, (x, -0.25, 0.42), stone, root, bevel=0.012)
    cone("court_pediment", 1.12, 0.0, 0.58, (0, -0.02, 1.35), gold, root, rot=(math.radians(90), 0, 0), bevel=0.015)
    return Prop(root, lambda t: setattr(root, "rotation_euler", Euler((0, 0, 0.035 * math.sin(t * 0.55)))))


def build_document(tr, pal, pos):
    root = _case_prop(tr, pos, "document")
    paper = _m("doc_paper", hex_rgba("#E8EDF2"), rough=0.9, bevel=0.006)
    line = _m("doc_line", hex_rgba("#61758A"), rough=0.9, bevel=0)
    stamp = _m("doc_stamp", hex_rgba("#C84B45"), rough=0.6, emission=hex_rgba("#C84B45"), strength=0.15, bevel=0)
    for i in range(3):
        sheet = rbox(f"document_sheet_{i}", (1.15, 0.82, 0.035), (0.08 * i, 0.04 * i, 0.035 * i), paper, root, radius=0.008)
        sheet.rotation_euler[2] = math.radians((i - 1) * 5)
    for i in range(4):
        rbox(f"document_text_{i}", (0.68, 0.018, 0.008), (-0.02, -0.25 + i * 0.13, 0.13), line, root, radius=0.002)
    cyl("document_seal", 0.19, 0.025, (0.42, -0.19, 0.15), stamp, root, rot=(math.radians(90), 0, 0), bevel=0.004)
    return Prop(root, lambda t: setattr(root, "rotation_euler", Euler((0, 0, 0.05 * math.sin(t * 0.65)))))


def build_car(tr, pal, pos):
    root = _case_prop(tr, pos, "car")
    body = _m("car_body", hex_rgba("#315A78"), rough=0.3, metal=0.25, coat=0.5, bevel=0.025)
    glass = _m("car_glass", hex_rgba("#A9D7E8"), rough=0.16, metal=0.1, bevel=0.01)
    tyre = _m("car_tyre", hex_rgba("#17212B"), rough=0.8, bevel=0.01)
    rbox("car_chassis", (1.8, 0.86, 0.36), (0, 0, 0.25), body, root, radius=0.10)
    rbox("car_cabin", (0.92, 0.72, 0.42), (0.08, 0, 0.60), glass, root, radius=0.10)
    for x in (-0.58, 0.58):
        for y in (-0.43, 0.43):
            cyl("car_wheel", 0.22, 0.13, (x, y, 0.12), tyre, root, rot=(math.radians(90), 0, 0), bevel=0.02)
    return Prop(root, lambda t: setattr(root, "rotation_euler", Euler((0, 0, 0.035 * math.sin(t * 0.5)))))



BUILDERS = {
    "chip": build_chip, "planet": build_planet, "rocket": build_rocket, "battery": build_battery,
    "neural": build_neural, "globe": build_globe, "bulb": build_bulb, "shield": build_shield,
    "atom": build_atom, "gear": build_gear,
    "money": build_money, "gold": build_gold, "house": build_house,
    "courthouse": build_courthouse, "document": build_document, "car": build_car,
}


def build_none(tr, pal, pos):
    root = empty("prop_root", pos)
    return Prop(root, lambda t: None)


BUILDERS["none"] = build_none


def build_prop(key, tr, pal, pos=(0, 0, 1.55)):
    return BUILDERS.get(key, build_chip)(tr, pal, pos)
