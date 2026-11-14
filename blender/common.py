"""Shared helpers for the procedural "Pixar-ish" Blender scenes.

Runs INSIDE Blender (blender -b -P render_scene.py). Target: Blender 4.0+.
Look recipe: soft bevelled geometry, glossy clear-coat plastic, a little
subsurface, large soft area lights, depth of field and bokeh in the back.
"""
import math
import random

import bpy
import bmesh
from mathutils import Vector, Euler


# --------------------------------------------------------------------------
# colour helpers
# --------------------------------------------------------------------------
def hex_rgba(h, a=1.0):
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    # sRGB -> linear
    f = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return (f(r), f(g), f(b), a)


# --------------------------------------------------------------------------
# easing
# --------------------------------------------------------------------------
def clamp01(x):
    return max(0.0, min(1.0, x))


def smoothstep(x):
    x = clamp01(x)
    return x * x * (3 - 2 * x)


def ease_out_back(x, s=1.70158):
    x = clamp01(x)
    x1 = x - 1
    return 1 + (s + 1) * x1 ** 3 + s * x1 ** 2


def ease_out_cubic(x):
    x = clamp01(x)
    return 1 - (1 - x) ** 3


def pulse(t, start, dur):
    """0..1..0 bump between start and start+dur."""
    if dur <= 0:
        return 0.0
    x = (t - start) / dur
    if x < 0 or x > 1:
        return 0.0
    return math.sin(x * math.pi)


# --------------------------------------------------------------------------
# materials
# --------------------------------------------------------------------------
def make_material(name, color, rough=0.35, metal=0.0, sss=0.0, coat=0.0,
                  emission=None, strength=0.0, bevel=0.015, alpha=1.0,
                  sss_radius=(1.0, 0.4, 0.25)):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    bsdf = nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if "Subsurface Weight" in bsdf.inputs:
        bsdf.inputs["Subsurface Weight"].default_value = 0.0   # SSS is slow; fake softness with colour instead
        bsdf.inputs["Subsurface Radius"].default_value = sss_radius
        bsdf.inputs["Subsurface Scale"].default_value = 0.08
        bsdf.inputs["Coat Weight"].default_value = coat
        bsdf.inputs["Coat Roughness"].default_value = 0.08
    if emission is not None and strength > 0:
        bsdf.inputs["Emission Color"].default_value = emission
        bsdf.inputs["Emission Strength"].default_value = strength
    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
    if bevel and bevel > 0:
        bev = nodes.new("ShaderNodeBevel")
        bev.inputs["Radius"].default_value = bevel
        bev.samples = 2
        links.new(bev.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def make_procedural_material(name, kind, c1, c2, scale=3.0, rough=0.4, bevel=0.0,
                             coat=0.1, sss=0.05):
    """Noise/wave driven two-colour material (planet bands, globe land/sea)."""
    mat = make_material(name, c1, rough=rough, sss=sss, coat=coat, bevel=bevel)
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    bsdf = nodes.get("Principled BSDF")
    coord = nodes.new("ShaderNodeTexCoord")
    ramp = nodes.new("ShaderNodeValToRGB")
    if kind == "bands":
        tex = nodes.new("ShaderNodeTexWave")
        tex.wave_type = "BANDS"
        tex.bands_direction = "Z"
        tex.inputs["Scale"].default_value = scale
        tex.inputs["Distortion"].default_value = 3.0
        tex.inputs["Detail"].default_value = 3.0
        links.new(coord.outputs["Object"], tex.inputs["Vector"])
        links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
        ramp.color_ramp.interpolation = "EASE"
    else:  # "land": hard threshold noise
        tex = nodes.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = scale
        tex.inputs["Detail"].default_value = 4.0
        tex.inputs["Roughness"].default_value = 0.55
        links.new(coord.outputs["Object"], tex.inputs["Vector"])
        links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
        ramp.color_ramp.interpolation = "CONSTANT"
        ramp.color_ramp.elements[0].position = 0.0
        ramp.color_ramp.elements[1].position = 0.56
    ramp.color_ramp.elements[0].color = c1
    ramp.color_ramp.elements[1].color = c2
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


# --------------------------------------------------------------------------
# primitives (all shaded smooth, optional bevel modifier for "toy" edges)
# --------------------------------------------------------------------------
def _finish(obj, mat, parent, smooth=True):
    if mat is not None:
        obj.data.materials.append(mat)
    if smooth:
        for p in obj.data.polygons:
            p.use_smooth = True
    if parent is not None:
        obj.parent = parent
    return obj


def add_bevel(obj, width, segments=5, limit_angle=True):
    m = obj.modifiers.new("Bevel", "BEVEL")
    m.width = width
    m.segments = segments
    if limit_angle:
        m.limit_method = "ANGLE"
        m.angle_limit = math.radians(35)
    m.harden_normals = False
    return m


def empty(name, loc=(0, 0, 0), parent=None):
    e = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(e)
    e.location = loc
    if parent is not None:
        e.parent = parent
    return e


def sphere(name, r, loc, mat, parent=None, scale=(1, 1, 1), seg=48, rings=24):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=loc, segments=seg, ring_count=rings)
    o = bpy.context.active_object
    o.name = name
    o.scale = scale
    return _finish(o, mat, parent)


def rbox(name, size, loc, mat, parent=None, radius=0.05, segs=5):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.active_object
    o.name = name
    o.scale = size
    bpy.ops.object.transform_apply(scale=True)
    add_bevel(o, min(radius, min(size) * 0.49), segs, limit_angle=False)
    return _finish(o, mat, parent)


def cyl(name, r, h, loc, mat, parent=None, rot=(0, 0, 0), bevel=0.03, verts=48):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=h, location=loc, rotation=rot, vertices=verts)
    o = bpy.context.active_object
    o.name = name
    if bevel:
        add_bevel(o, min(bevel, r * 0.95, h * 0.49), 4)
    return _finish(o, mat, parent)


def cone(name, r1, r2, h, loc, mat, parent=None, rot=(0, 0, 0), bevel=0.02, verts=48):
    bpy.ops.mesh.primitive_cone_add(radius1=r1, radius2=r2, depth=h, location=loc, rotation=rot, vertices=verts)
    o = bpy.context.active_object
    o.name = name
    if bevel:
        add_bevel(o, bevel, 4)
    return _finish(o, mat, parent)


def torus(name, major, minor, loc, mat, parent=None, rot=(0, 0, 0), seg=64, minor_seg=16):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, location=loc, rotation=rot,
                                     major_segments=seg, minor_segments=minor_seg)
    o = bpy.context.active_object
    o.name = name
    return _finish(o, mat, parent)


def capsule(name, r, length, loc, mat, parent=None, rot=(0, 0, 0)):
    """Rounded cylinder (axis = local Z)."""
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=length + 2 * r, location=loc, rotation=rot, vertices=32)
    o = bpy.context.active_object
    o.name = name
    add_bevel(o, r * 0.98, 8, limit_angle=False)
    return _finish(o, mat, parent)


def polygon_prism(name, pts, depth, mat, parent=None, loc=(0, 0, 0), bevel=0.03):
    """Extrude a 2D polygon (XZ plane, thickness along Y)."""
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    verts = [bm.verts.new((x, 0, z)) for x, z in pts]
    face = bm.faces.new(verts)
    res = bmesh.ops.extrude_face_region(bm, geom=[face])
    ext_verts = [v for v in res["geom"] if isinstance(v, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, depth, 0), verts=ext_verts)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    o = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(o)
    o.location = loc
    # centre geometry on Y
    for v in mesh.vertices:
        v.co.y -= depth / 2
    add_bevel(o, bevel, 4, limit_angle=False)
    return _finish(o, mat, parent)


def link_between(name, a, b, radius, mat, parent=None):
    """Thin cylinder from point a to b (world/parent-local coordinates)."""
    a, b = Vector(a), Vector(b)
    d = b - a
    mid = (a + b) / 2
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=d.length, location=mid, vertices=16)
    o = bpy.context.active_object
    o.name = name
    o.rotation_mode = "QUATERNION"
    o.rotation_quaternion = d.to_track_quat("Z", "Y")
    return _finish(o, mat, parent)


# --------------------------------------------------------------------------
# keyframe tracking: evaluate python animation per frame, bake as keys
# --------------------------------------------------------------------------
class Tracker:
    def __init__(self):
        self.objs = []      # (obj, props)
        self.sockets = []   # socket objects (emission strength etc.)

    def track(self, obj, *props):
        props = props or ("location", "rotation_euler", "scale")
        self.objs.append((obj, props))
        return obj

    def track_socket(self, socket):
        self.sockets.append(socket)

    def key(self, frame):
        for obj, props in self.objs:
            for p in props:
                obj.keyframe_insert(data_path=p, frame=frame)
        for s in self.sockets:
            s.keyframe_insert(data_path="default_value", frame=frame)


def look_at(obj, target, up_axis="Y"):
    d = Vector(target) - obj.location
    obj.rotation_euler = d.to_track_quat("-Z", up_axis).to_euler()


def seeded(seed):
    return random.Random(seed)
