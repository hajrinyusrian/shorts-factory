"""Bit - the channel mascot. A floating, big-eyed little robot (faceless channel = no human face).

All animation is computed in python per frame and baked to keyframes by Tracker.
"""
import math

from mathutils import Euler

from common import (empty, sphere, cyl, capsule, make_material, hex_rgba, Tracker,
                    ease_out_back, smoothstep, pulse, clamp01)

EMOTIONS = ("happy", "surprised", "thinking", "excited", "proud")


class Mascot:
    def __init__(self, tr: Tracker, palette, loc=(1.15, -0.9, 0.55), prop_pos=(0, 0, 1.6), seed=1):
        self.tr = tr
        self.base = list(loc)
        self.prop_pos = prop_pos
        self.seed = seed
        self.rng_blinks = self._blink_times(seed)

        shell = make_material("bit_shell", (0.93, 0.95, 1.0, 1), rough=0.2, sss=0.2, coat=0.7, bevel=0.01)
        accent = make_material("bit_accent", hex_rgba(palette["accent"]), rough=0.3, coat=0.5, sss=0.1, bevel=0.01)
        visor_m = make_material("bit_visor", (0.012, 0.02, 0.05, 1), rough=0.06, coat=1.0, bevel=0)
        eye_col = hex_rgba(palette.get("eye", "#7CF3FF"))
        eye_m = make_material("bit_eye", eye_col, rough=0.5, emission=eye_col, strength=2.6, bevel=0)
        blush_m = make_material("bit_blush", (1.0, 0.45, 0.55, 1), rough=0.6, emission=(1.0, 0.35, 0.5, 1),
                                strength=1.4, bevel=0)
        bulb_m = make_material("bit_bulb", hex_rgba(palette["accent"]), rough=0.2,
                               emission=hex_rgba(palette["accent"]), strength=4.0, bevel=0)
        self.bulb_socket = bulb_m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
        tr.track_socket(self.bulb_socket)

        self.root = empty("bit_root", loc)
        tr.track(self.root)
        body = sphere("bit_body", 0.3, (0, 0, 0), shell, self.root, scale=(1.0, 0.9, 1.25))
        # belly accent ring
        cyl("bit_belt", 0.285, 0.05, (0, 0, 0.04), accent, self.root, bevel=0.015)

        self.head = empty("bit_head", (0, 0, 0.42), self.root)
        tr.track(self.head)
        sphere("bit_head_shell", 0.48, (0, 0, 0.36), shell, self.head, scale=(1.12, 1.0, 0.92))
        sphere("bit_visor", 0.42, (0, -0.30, 0.37), visor_m, self.head, scale=(1.0, 0.57, 0.8))
        # ear discs
        for s in (-1, 1):
            cyl(f"bit_ear{s}", 0.13, 0.11, (s * 0.555, 0.0, 0.36), accent, self.head, rot=(0, math.radians(90), 0),
                bevel=0.03)
        # antenna
        cyl("bit_ant", 0.016, 0.2, (0, 0.0, 0.84), shell, self.head, bevel=0.0, verts=12)
        sphere("bit_bulb", 0.06, (0, 0.0, 0.96), bulb_m, self.head, seg=24, rings=12)

        # eyes + blush
        self.eyes = []
        for s in (-1, 1):
            e = sphere(f"bit_eye{s}", 0.09, (s * 0.17, -0.505, 0.395), eye_m, self.head,
                       scale=(0.8, 0.34, 1.05), seg=32, rings=16)
            tr.track(e, "location", "scale")
            self.eyes.append((e, s))
            b = sphere(f"bit_blush{s}", 0.06, (s * 0.30, -0.465, 0.30), blush_m, self.head,
                       scale=(1.25, 0.2, 0.7), seg=20, rings=10)

        # arms (pivot at shoulder)
        self.arms = {}
        for s, name in ((-1, "L"), (1, "R")):
            piv = empty(f"bit_arm{name}", (s * 0.31, 0.0, 0.14), self.root)
            tr.track(piv, "rotation_euler")
            capsule(f"bit_arm_seg{name}", 0.065, 0.2, (0, 0, -0.17), shell, piv)
            sphere(f"bit_hand{name}", 0.085, (0, 0, -0.35), accent, piv, seg=24, rings=12)
            self.arms[name] = piv

    @staticmethod
    def _blink_times(seed):
        import random
        r = random.Random(seed * 17 + 3)
        t, out = 0.9, []
        while t < 40:
            out.append(t)
            t += r.uniform(2.0, 3.6)
        return out

    # ------------------------------------------------------------------
    def update(self, t, emotion="happy"):
        bx, by, bz = self.base
        # entrance: pop-in after small delay
        pop = ease_out_back((t - 0.25) / 0.55)
        s = max(0.001, pop)
        self.root.scale = (s, s, s)

        # float idle + breathing
        bob = 0.07 * math.sin(2 * math.pi * t / 2.6)
        hop = 0.0
        if emotion == "excited":
            hop = 0.16 * abs(math.sin(2 * math.pi * t / 0.9))
        if emotion == "surprised":
            hop = 0.35 * pulse(t, 0.55, 0.5)
        self.root.location = (bx, by, bz + bob + hop)

        # face the prop
        # prop sits beside/behind the mascot: turn ~25 degrees toward it, keep facing the camera
        yaw = 0.0 if abs(bx - self.prop_pos[0]) < 0.2 else -0.42 * (1 if bx > self.prop_pos[0] else -1)
        sway = 0.05 * math.sin(2 * math.pi * t / 3.1)
        self.root.rotation_euler = Euler((0.03 * math.sin(2 * math.pi * t / 2.6 + 1), 0, yaw + sway), "XYZ")

        # head: nod / tilt per emotion
        nod = 0.06 * math.sin(2 * math.pi * t / 2.6 + 0.8)
        tilt = 0.0
        pitch_extra = 0.0
        if emotion == "thinking":
            tilt = 0.22 + 0.04 * math.sin(2 * math.pi * t / 2.0)
            pitch_extra = -0.05
        elif emotion == "proud":
            pitch_extra = -0.12 * smoothstep((t - 0.5) / 0.6)
        elif emotion == "excited":
            nod += 0.10 * math.sin(2 * math.pi * t / 0.45)
        self.head.rotation_euler = Euler((nod + pitch_extra, tilt, 0.05 * math.sin(2 * math.pi * t / 3.7)), "XYZ")

        # eyes
        sx, sz = {"happy": (1.12, 0.78), "surprised": (1.35, 1.5), "thinking": (1.0, 1.0),
                  "excited": (1.2, 1.15), "proud": (1.1, 0.7)}.get(emotion, (1.0, 1.0))
        blink = 0.0
        for bt in self.rng_blinks:
            blink = max(blink, pulse(t, bt, 0.16))
        look_x = 0.025 * math.sin(2 * math.pi * t / 5.0) - 0.012 * (1 if self.base[0] > 0 else -1)
        for e, side in self.eyes:
            k = 0.78 if (emotion == "thinking" and side == -1) else 1.0
            e.scale = (0.8 * sx * k, 0.34, max(0.05, 1.05 * sz * k * (1 - 0.92 * blink)))
            e.location = (side * 0.17 + look_x, -0.505, 0.395 + (0.012 if emotion == "thinking" else 0.0))

        # arms
        w = lambda f, ph=0.0: math.sin(2 * math.pi * f * t + ph)
        rest = math.radians(14)
        angR = Euler((0, -rest, 0))
        angL = Euler((0, rest, 0))
        if emotion in ("happy", "proud"):
            up = smoothstep((t - 0.6) / 0.35) * (1.0 if emotion == "happy" else 0.0)
            angR = Euler((0, -(rest + up * (math.radians(125) + math.radians(18) * w(2.4))), 0))
        elif emotion == "excited":
            up = smoothstep((t - 0.4) / 0.3)
            a = rest + up * math.radians(135)
            angR = Euler((0, -(a + math.radians(14) * w(2.2)), 0))
            angL = Euler((0, (a + math.radians(14) * w(2.2, 1.2)), 0))
        elif emotion == "surprised":
            up = smoothstep((t - 0.5) / 0.25) * (1 - smoothstep((t - 1.4) / 0.5))
            a = rest + up * math.radians(70)
            angR = Euler((0, -a, 0))
            angL = Euler((0, a, 0))
        elif emotion == "thinking":
            up = smoothstep((t - 0.4) / 0.5)
            angR = Euler((-math.radians(100) * up, math.radians(28) * up - rest * (1 - up), 0))
        self.arms["R"].rotation_euler = angR
        self.arms["L"].rotation_euler = angL

        # antenna glow
        self.bulb_socket.default_value = 3.0 + 4.0 * (0.5 + 0.5 * math.sin(2 * math.pi * t / 1.4))
