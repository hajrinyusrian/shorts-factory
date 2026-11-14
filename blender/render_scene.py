"""Render animated 3D scenes headlessly.

    blender -b -P blender/render_scene.py -- manifest.json

manifest.json = {"scenes": [ {out_dir, frames, fps, width, height, samples, prop, emotion,
                              palette, seed, mascot_side, camera, preview_frame?} , ... ]}
"""
import json
import math
import os
import random
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from common import (empty, sphere, make_material, hex_rgba, Tracker, smoothstep, ease_out_cubic)  # noqa: E402
from mascot import Mascot  # noqa: E402
from props import build_prop  # noqa: E402

PALETTES = {
    "ocean":  dict(wall_a="#0B3C8C", wall_b="#35A2FF", accent="#FFC53D", accent2="#FF6B8B", eye="#7CF3FF"),
    "sunset": dict(wall_a="#4A1D96", wall_b="#FF8A5B", accent="#FFD23F", accent2="#2BD9D0", eye="#8CFBFF"),
    "mint":   dict(wall_a="#0F5E57", wall_b="#5EEAD4", accent="#FF9F1C", accent2="#FF4D6D", eye="#B8FFF2"),
    "candy":  dict(wall_a="#6D28D9", wall_b="#F472B6", accent="#FDE047", accent2="#22D3EE", eye="#9BF6FF"),
    "sky":    dict(wall_a="#173FBF", wall_b="#5FA8FF", accent="#FB923C", accent2="#84E04C", eye="#7CF3FF"),
    "dusk":   dict(wall_a="#1B1850", wall_b="#6C6CF5", accent="#FFB020", accent2="#34D399", eye="#9BE7FF"),
}

PROP_POS = (0.0, 0.0, 1.55)


def args_after_dashes():
    argv = sys.argv
    return argv[argv.index("--") + 1:] if "--" in argv else []


# ---------------------------------------------------------------------------
def enable_denoiser(c) -> bool:
    """Turn on OpenImageDenoise if this Blender build supports it. Returns True when enabled."""
    try:
        c.denoiser = "OPENIMAGEDENOISE"
    except (TypeError, ValueError):
        return False
    c.use_denoising = True
    c.denoising_prefilter = "ACCURATE"
    return True


def setup_render(scene, w, h, fps, samples, motion_blur):
    scene.render.engine = "CYCLES"
    c = scene.cycles
    c.device = "CPU"
    c.samples = samples
    c.use_adaptive_sampling = True
    c.adaptive_threshold = 0.06
    c.adaptive_min_samples = 4
    # bpy.app.build_options has NO "openimagedenoise" flag (checked on Blender 4.0), so the old check was always
    # False. The reliable test is whether Cycles accepts OPENIMAGEDENOISE as a denoiser value: builds without
    # OIDN (e.g. Debian/Ubuntu apt) expose an empty enum and raise TypeError.
    if enable_denoiser(c):
        print("[blender] denoiser: OpenImageDenoise enabled", flush=True)
    else:
        c.use_denoising = False
        print("[blender] WARNING: this Blender build has no OpenImageDenoise -> raw (noisy) samples", flush=True)
    c.max_bounces = 3
    c.diffuse_bounces = 2
    c.glossy_bounces = 2
    c.transmission_bounces = 1
    c.volume_bounces = 0
    c.caustics_reflective = False
    c.caustics_refractive = False
    c.sample_clamp_indirect = 6.0
    c.sample_clamp_direct = 20.0
    scene.render.resolution_x = w
    scene.render.resolution_y = h
    scene.render.resolution_percentage = 100
    scene.render.fps = fps
    scene.render.use_motion_blur = bool(motion_blur)
    scene.render.motion_blur_shutter = 0.6
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.compression = 12
    scene.render.film_transparent = False
    scene.render.filter_size = 1.3
    # colour: punchy but not blown out
    vs = scene.view_settings
    for vt in ("Filmic", "AgX", "Standard"):
        try:
            vs.view_transform = vt
            break
        except TypeError:
            continue
    for look in ("High Contrast", "Medium High Contrast", "AgX - Medium High Contrast", "Punchy"):
        try:
            vs.look = look
            break
        except TypeError:
            continue
    vs.exposure = 0.15


def build_world(scene, pal):
    w = bpy.data.worlds.new("world")
    scene.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = hex_rgba(pal["wall_b"])
    bg.inputs["Strength"].default_value = 0.35


def build_cyclorama(pal):
    """Seamless floor-to-wall backdrop with a vertical colour gradient and glossy floor."""
    prof = [(-40.0, 0.0), (5.0, 0.0)]
    R = 4.5
    for i in range(1, 19):
        a = (math.pi / 2) * i / 18
        prof.append((5.0 + R * math.sin(a), R - R * math.cos(a)))
    prof.append((5.0 + R, 40.0))
    xs = (-40.0, 40.0)
    verts, faces = [], []
    for (y, z) in prof:
        verts.append((xs[0], y, z))
        verts.append((xs[1], y, z))
    for i in range(len(prof) - 1):
        a, b, c, d = 2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2
        faces.append((a, b, c, d))
    mesh = bpy.data.meshes.new("cyc")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    for p in mesh.polygons:
        p.use_smooth = True
    obj = bpy.data.objects.new("cyc", mesh)
    bpy.context.collection.objects.link(obj)
    # flip normals to face the camera (-Y side / +Z up)
    mesh.flip_normals()
    mat = make_material("cyc_mat", (1, 1, 1, 1), rough=0.7, coat=0.0, bevel=0.0)
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    mapr = nt.nodes.new("ShaderNodeMapRange")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    nt.links.new(coord.outputs["Object"], sep.inputs["Vector"])
    nt.links.new(sep.outputs["Z"], mapr.inputs["Value"])
    mapr.inputs["From Min"].default_value = 0.0
    mapr.inputs["From Max"].default_value = 14.0
    mapr.clamp = True
    nt.links.new(mapr.outputs["Result"], ramp.inputs["Fac"])
    ramp.color_ramp.elements[0].color = hex_rgba(pal["wall_b"])
    ramp.color_ramp.elements[1].color = hex_rgba(pal["wall_a"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    obj.data.materials.append(mat)
    return obj


def build_bokeh(tr, pal, rng, count=24):
    items = []
    cols = [pal["accent"], pal["accent2"], "#FFFFFF", pal["wall_b"], "#FFFFFF"]
    for i in range(count):
        c = hex_rgba(rng.choice(cols))
        m = make_material(f"bk{i}", c, rough=0.5, emission=c, strength=rng.uniform(2.0, 5.0), bevel=0)
        r = rng.uniform(0.07, 0.28)
        loc = (rng.uniform(-3.6, 3.6), rng.uniform(3.0, 7.0), rng.uniform(0.3, 8.0))
        o = sphere(f"bk{i}", r, loc, m, None, seg=16, rings=8)
        tr.track(o, "location")
        items.append((o, loc, rng.uniform(0.04, 0.16), rng.uniform(0, 6.28)))
    return items


def build_lights(pal, key_rot_seed=0):
    def area(name, loc, size, energy, color, target=(0, 0, 1.4)):
        ld = bpy.data.lights.new(name, "AREA")
        ld.shape = "RECTANGLE"
        ld.size, ld.size_y = size, size * 0.7
        ld.energy = energy
        ld.color = color
        o = bpy.data.objects.new(name, ld)
        bpy.context.collection.objects.link(o)
        o.location = loc
        d = Vector(target) - Vector(loc)
        o.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        return o
    area("key", (-3.2, -4.6, 5.2), 4.0, 900, (1.0, 0.93, 0.84))
    area("fill", (4.2, -4.2, 2.2), 5.0, 330, (0.80, 0.90, 1.0))
    area("rim", (0.0, 3.8, 4.8), 4.0, 700, hex_rgba(pal["accent"])[:3], target=(0, 0, 1.6))


def build_camera(scene, w, h, shift_y):
    cd = bpy.data.cameras.new("cam")
    cd.lens = 58
    cd.sensor_width = 36
    cd.sensor_fit = "HORIZONTAL"
    cd.shift_y = shift_y
    cd.dof.use_dof = True
    cd.dof.aperture_fstop = 3.2
    cd.dof.focus_distance = 7.6
    cam = bpy.data.objects.new("cam", cd)
    bpy.context.collection.objects.link(cam)
    tgt = empty("cam_target", (0, 0, 1.35))
    con = cam.constraints.new("TRACK_TO")
    con.target = tgt
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    scene.camera = cam
    return cam


# ---------------------------------------------------------------------------
def render_scene(cfg):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"
    scene = bpy.context.scene
    pal = PALETTES.get(cfg.get("palette", "ocean"), PALETTES["ocean"])
    seed = int(cfg.get("seed", 1))
    rng = random.Random(seed)
    fps = int(cfg["fps"])
    frames = int(cfg["frames"])
    W, H = int(cfg["width"]), int(cfg["height"])

    setup_render(scene, W, H, fps, int(cfg.get("samples", 24)), cfg.get("motion_blur", True))
    build_world(scene, pal)
    build_cyclorama(pal)
    build_lights(pal)
    cam = build_camera(scene, W, H, float(cfg.get("shift_y", -0.1)))

    tr = Tracker()
    tr.track(cam, "location")
    bokeh = build_bokeh(tr, pal, rng)
    ms = int(cfg.get("mascot_side", 1))
    side = 1 if ms >= 0 else -1
    prop_pos = (-0.38 * side, 0.0, PROP_POS[2])
    prop = build_prop(cfg.get("prop", "chip"), tr, pal, prop_pos)
    if ms == 0:   # outro: mascot centred, no prop
        mascot = Mascot(tr, pal, loc=(0.0, -0.6, 1.1), prop_pos=(0, 0, 1.1), seed=seed)
    else:
        mascot = Mascot(tr, pal, loc=(1.12 * side, -0.85, 0.5), prop_pos=prop_pos, seed=seed)

    move = cfg.get("camera", "push")
    T = frames / fps
    scene.frame_start, scene.frame_end = 1, frames
    for f in range(1, frames + 1):
        t = (f - 1) / fps
        k = t / max(T, 0.001)
        if move == "orbit":
            cx = 0.8 * math.sin(math.pi * (k - 0.5)) * 1.0
            cam.location = (cx, -7.6 + 0.2 * k, 1.9)
        elif move == "pull":
            cam.location = (0.0, -7.1 - 0.5 * ease_out_cubic(k), 1.9)
        else:  # push in
            cam.location = (0.25 * math.sin(math.pi * k), -7.9 + 0.8 * smoothstep(k), 1.9)
        for o, loc, spd, ph in bokeh:
            o.location = (loc[0] + 0.15 * math.sin(t * 0.6 + ph), loc[1], 0.3 + (loc[2] - 0.3 + spd * t * 1.2) % 8.0)
        prop.update(t)
        mascot.update(t, cfg.get("emotion", "happy"))
        tr.key(f)

    pf = cfg.get("preview_frame")
    out_dir = cfg["out_dir"]
    os.makedirs(out_dir, exist_ok=True)
    if pf:
        scene.frame_set(int(pf))
        scene.render.filepath = os.path.join(out_dir, "preview.png")
        bpy.ops.render.render(write_still=True)
    else:
        scene.render.filepath = os.path.join(out_dir, "f_")
        bpy.ops.render.render(animation=True)


def main():
    a = args_after_dashes()
    with open(a[0]) as fh:
        manifest = json.load(fh)
    for i, cfg in enumerate(manifest["scenes"]):
        print(f"[blender] scene {i + 1}/{len(manifest['scenes'])}: {cfg.get('prop')} / {cfg.get('emotion')}", flush=True)
        render_scene(cfg)


main()
