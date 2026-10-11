"""TURBO DRIFT - pseudo-3D racer, ported into the retro arcade.

Up/W gas, Down/S brake, Left/Right steer, Space/Shift drift,
P pause, R restart, Esc back to menu.
"""
import math
import random
from types import SimpleNamespace

import pygame

from engine import Scene, W, H, SCALE

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
HORIZON = 70               # screen row of the horizon
FPS = 60

SEG = 500                  # world units per track segment
STRIPE = 160               # world units per road stripe
ZNEAR = 1000.0             # camera distance seen by the bottom row
ZCAR = ZNEAR / 0.85        # camera distance of the player's car
DRAW_DIST = 15000.0
CURVE_FAR = 14000.0
CURVE_C = 1.0e-7           # how strongly curves bend the road
ROAD_HW = 125.0            # road half-width in pixels at the bottom row
LANES = (-0.62, 0.0, 0.62)

MAX_SPEED = 1800.0
ACCEL = 900.0
BRAKE = 2400.0
DRAG = 450.0
TURN = 1.7
CENTRIFUGAL = 0.55
LAPS = 3

SECTIONS = [(25, 0), (20, 1.6), (15, 0), (20, -2.2), (10, 0), (25, 2.6),
            (15, -1.4), (10, 0), (20, -2.8), (20, 1.8), (15, 0), (25, -1.0)]


def build_track():
    raw = []
    for n, c in SECTIONS:
        raw += [float(c)] * n
    n = len(raw)
    for _ in range(3):  # smooth the corners so they ease in and out
        k = 8
        raw = [sum(raw[(i + j) % n] for j in range(-k, k + 1)) / (2 * k + 1)
               for i in range(n)]
    return raw


CURVES = build_track()
N_SEG = len(CURVES)
LAP_LEN = N_SEG * SEG


def curve_at(z):
    return CURVES[int(z // SEG) % N_SEG]


def wrapdiff(a, b=0.0):
    """Signed distance a-b on the looping track."""
    return (a - b + LAP_LEN / 2) % LAP_LEN - LAP_LEN / 2


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def mix(a, b, t):
    return (int(a[0] + (b[0] - a[0]) * t),
            int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))


def fmt_time(t):
    if t is None:
        return "-:--.--"
    m = int(t // 60)
    return "%d:%05.2f" % (m, t - 60 * m)


# --------------------------------------------------------------------------
# Procedural pixel-art sprites
# --------------------------------------------------------------------------
def make_car(body, trim=None):
    s = pygame.Surface((18, 12), pygame.SRCALPHA)
    dark = mix(body, (0, 0, 0), 0.45)
    light = mix(body, (255, 255, 255), 0.35)
    f = s.fill
    f((20, 20, 28), (0, 8, 3, 4))
    f((20, 20, 28), (15, 8, 3, 4))
    f(dark, (1, 0, 16, 2))                 # spoiler
    f(light, (1, 0, 16, 1))
    f(light, (4, 2, 10, 4))                # cabin
    f(body, (1, 5, 16, 6))                 # body
    f((25, 35, 60), (5, 3, 8, 3))          # rear window
    f((80, 100, 150), (5, 3, 8, 1))
    if trim:
        f(trim, (1, 7, 16, 1))
    f((255, 50, 50), (2, 6, 4, 2))         # tail lights
    f((255, 50, 50), (12, 6, 4, 2))
    f((255, 170, 150), (2, 6, 4, 1))
    f((255, 170, 150), (12, 6, 4, 1))
    f((235, 235, 235), (7, 8, 4, 2))       # plate
    f(dark, (2, 10, 14, 1))                # bumper
    f((0, 0, 0, 110), (1, 11, 16, 1))      # shadow
    return s


def shear(spr, tilt):
    """Lean a sprite left/right by shifting its upper rows."""
    w, h = spr.get_size()
    pad = 4
    out = pygame.Surface((w + pad * 2, h), pygame.SRCALPHA)
    for y in range(h):
        off = int(round(tilt * (h - 1 - y) / (h - 1) * 1.5))
        out.blit(spr, (pad + off, y), (0, y, w, 1))
    return out


def make_van(body):
    s = pygame.Surface((20, 17), pygame.SRCALPHA)
    dark = mix(body, (0, 0, 0), 0.4)
    light = mix(body, (255, 255, 255), 0.35)
    f = s.fill
    f((20, 20, 28), (0, 12, 3, 5))
    f((20, 20, 28), (17, 12, 3, 5))
    f(body, (1, 0, 18, 13))
    f(light, (1, 0, 18, 1))
    f(dark, (9, 1, 1, 11))                 # door seam
    f((30, 40, 60), (3, 2, 5, 3))
    f((30, 40, 60), (12, 2, 5, 3))
    f((255, 50, 50), (2, 9, 3, 2))
    f((255, 50, 50), (15, 9, 3, 2))
    f(dark, (1, 12, 18, 1))
    f((0, 0, 0, 110), (1, 16, 18, 1))
    return s


def make_pickup(kind):
    s = pygame.Surface((12, 12), pygame.SRCALPHA)
    col = {"nitro": (255, 150, 0), "shield": (50, 140, 255),
           "emp": (170, 60, 230)}[kind]
    s.fill((255, 255, 255), (1, 0, 10, 12))
    s.fill((255, 255, 255), (0, 1, 12, 10))
    s.fill(col, (2, 2, 8, 8))
    white = (255, 255, 255)
    if kind == "nitro":
        pygame.draw.lines(s, white, False, [(7, 2), (4, 6), (7, 6), (5, 9)])
    elif kind == "shield":
        pygame.draw.polygon(s, white, [(3, 3), (9, 3), (9, 7), (6, 10), (3, 7)])
    else:
        pygame.draw.circle(s, white, (6, 6), 3, 1)
        s.fill(white, (6, 6, 1, 1))
    return s


def make_tree(base):
    s = pygame.Surface((14, 24), pygame.SRCALPHA)
    s.fill((90, 55, 30), (6, 19, 2, 5))
    light = mix(base, (255, 200, 150), 0.25)
    for tier in ([(7, 0), (12, 8), (2, 8)],
                 [(7, 5), (13, 14), (1, 14)],
                 [(7, 10), (14, 20), (0, 20)]):
        pygame.draw.polygon(s, base, tier)
        pygame.draw.polygon(s, light, [tier[0], (7, tier[1][1]), tier[2]])
    return s


def sky_color(y):
    stops = [(0.0, (24, 16, 64)), (0.5, (110, 36, 110)),
             (0.85, (240, 110, 100)), (1.0, (255, 190, 120))]
    t = y / float(HORIZON)
    for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
        if t <= t1:
            return mix(c0, c1, (t - t0) / (t1 - t0))
    return stops[-1][1]


HAZE = sky_color(HORIZON)


def make_sky():
    s = pygame.Surface((W, HORIZON + 1))
    for y in range(HORIZON + 1):
        pygame.draw.line(s, sky_color(y), (0, y), (W, y))
    rng = random.Random(7)
    for _ in range(45):
        x, y = rng.randint(0, W - 1), rng.randint(0, HORIZON // 2)
        s.set_at((x, y), (255, 240, 220))
    cx, cy = W // 2 + 55, HORIZON - 16
    pygame.draw.circle(s, (255, 150, 110), (cx, cy), 27)
    pygame.draw.circle(s, (255, 232, 140), (cx, cy), 22)
    for k in range(5):                      # retro sun stripes
        y = cy + 3 + k * 4
        for yy in range(y, y + 1 + k // 2):
            pygame.draw.line(s, sky_color(yy), (cx - 24, yy), (cx + 24, yy))
    return s


def make_mountains(color, base, amps, freqs, phases):
    s = pygame.Surface((W, HORIZON + 1), pygame.SRCALPHA)
    for x in range(W):
        h = base
        for a, f, p in zip(amps, freqs, phases):
            h += a * (1 - abs(math.sin(2 * math.pi * f * x / W + p)))
        pygame.draw.line(s, color, (x, HORIZON - int(h)), (x, HORIZON))
    return s


_sprite_cache = {}


def blit_sprite(surf, spr, ref_w, cx, ybot, w_px):
    f = w_px / float(ref_w)
    nw = max(1, int(spr.get_width() * f))
    nh = max(1, int(spr.get_height() * f))
    if nw > 500:
        return nw, nh
    key = (id(spr), nw, nh)
    img = _sprite_cache.get(key)
    if img is None:
        if len(_sprite_cache) > 700:
            _sprite_cache.clear()
        img = pygame.transform.scale(spr, (nw, nh))
        _sprite_cache[key] = img
    surf.blit(img, (int(cx - nw / 2), int(ybot - nh)))
    return nw, nh


# --------------------------------------------------------------------------
# Game objects
# --------------------------------------------------------------------------
class Car:
    """Traffic car or AI opponent."""

    def __init__(self, z, x, speed, sprite, ref_w, ww, name=None):
        self.z = z % LAP_LEN
        self.total = z
        self.x = x
        self.speed = speed
        self.base = speed
        self.sprite = sprite
        self.ref_w = ref_w
        self.ww = ww
        self.name = name
        self.finish = None
        self.pref = random.uniform(-0.5, 0.5)
        self.kind = None


class Prop:
    def __init__(self, z, x, sprite, ref_w, ww, kind=None):
        self.z, self.x = z, x
        self.sprite, self.ref_w, self.ww = sprite, ref_w, ww
        self.kind = kind
        self.cool = 0.0
        self.lift = 0.0


# --------------------------------------------------------------------------
# The game
# --------------------------------------------------------------------------
class Game:
    def __init__(self):
        self.low = pygame.Surface((W, H))
        self.big = pygame.Surface((W * SCALE, H * SCALE))
        self.sky = make_sky()
        self.mtn_far = make_mountains((78, 36, 104), 14, (16, 9, 5),
                                      (2, 5, 9), (0.4, 1.7, 2.9))
        self.mtn_near = make_mountains((48, 22, 76), 8, (13, 8, 4),
                                       (3, 7, 12), (1.1, 0.3, 2.2))
        self.f_big = pygame.font.Font(None, 110)
        self.f_mid = pygame.font.Font(None, 46)
        self.f_small = pygame.font.Font(None, 28)

        body = (255, 200, 30)
        self.player_sprites = {t: shear(make_car(body, (30, 30, 40)), t)
                               for t in range(-2, 3)}
        self.rival_defs = [("VIPER", (230, 50, 50)), ("COMET", (60, 130, 240)),
                           ("NOVA", (70, 210, 100)), ("BLAZE", (200, 80, 240)),
                           ("GHOST", (225, 225, 235))]
        self.rival_sprites = [make_car(c, (255, 255, 255)) for _, c in self.rival_defs]
        palette = [(220, 90, 40), (60, 170, 200), (200, 200, 80), (130, 130, 150),
                   (180, 60, 120), (90, 160, 90)]
        self.traffic_sprites = [make_car(c) for c in palette]
        self.van_sprites = [make_van(c) for c in palette[:4]]
        self.pickup_sprites = {k: make_pickup(k) for k in ("nitro", "shield", "emp")}
        self.tree_sprites = [make_tree((18, 105, 70)), make_tree((40, 125, 60)),
                             make_tree((120, 90, 40))]

        self.best_lap = None
        self.t = 0.0
        self.paused = False
        self.reset("MENU")

    # ------------------------------------------------------------------
    def reset(self, state="COUNTDOWN"):
        self.state = state
        self.total = -900.0
        self.z = self.total % LAP_LEN
        self.px = 0.0
        self.vx = 0.0
        self.speed = 0.0
        self.drifting = False
        self.drift_dir = 0
        self.charge = 0.0
        self.boost = 0.0
        self.shield = False
        self.emp = 0.0
        self.invuln = 0.0
        self.shake = 0.0
        self.race_time = 0.0
        self.timing = False
        self.lap_start = 0.0
        self.last_lap = None
        self.finish_time = None
        self.final_pos = None
        self.countdown = 3.0
        self.go_t = 0.0
        self.bg = 0.0
        self.msg, self.msg_t = "", 0.0
        self.particles = []
        self.shift = [0.0] * H
        self.cam_x = 0.0
        self.pscr = (W / 2, H - 20, 40)
        self.build_world()

    def build_world(self):
        rnd = random
        # AI opponents on the starting grid
        grid = [(-650, -0.62), (-650, 0.62), (-400, -0.62), (-400, 0.62), (-150, 0.0)]
        speeds = [1790, 1750, 1710, 1670, 1630]
        self.ais = []
        for i, (z, x) in enumerate(grid):
            name, _ = self.rival_defs[i]
            c = Car(z, x, 0.0, self.rival_sprites[i], 18, 0.42, name)
            c.base = speeds[i] * rnd.uniform(0.97, 1.03)
            self.ais.append(c)
        # traffic
        self.traffic = []
        n = 26
        for i in range(n):
            z = 4000 + i * (LAP_LEN - 6000) / n + rnd.uniform(-1500, 1500)
            x = rnd.choice(LANES)
            sp = rnd.uniform(450, 950)
            if rnd.random() < 0.3:
                c = Car(z, x, sp, rnd.choice(self.van_sprites), 20, 0.52)
            else:
                c = Car(z, x, sp, rnd.choice(self.traffic_sprites), 18, 0.42)
            self.traffic.append(c)
        # power-ups
        self.pickups = []
        n = 16
        for i in range(n):
            z = 6000 + i * (LAP_LEN - 8000) / n + rnd.uniform(-1000, 1000)
            kind = rnd.choice(["nitro", "nitro", "shield", "emp"])
            self.pickups.append(Prop(z % LAP_LEN, rnd.choice(LANES),
                                     self.pickup_sprites[kind], 12, 0.34, kind))
        # roadside trees
        self.trees = []
        z = 300.0
        while z < LAP_LEN:
            side = rnd.choice((-1, 1))
            self.trees.append(Prop(z, side * rnd.uniform(1.35, 3.2),
                                   rnd.choice(self.tree_sprites), 14, 0.7))
            z += rnd.uniform(450, 1100)

    def say(self, text, secs=1.6):
        self.msg, self.msg_t = text, secs

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------
    def update(self, dt, inp):
        self.t += dt
        self.shake = max(0.0, self.shake - dt)
        self.msg_t = max(0.0, self.msg_t - dt)
        if self.paused:
            return
        if self.state == "MENU":
            self.speed = 1100.0
            self.total += self.speed * dt
            self.z = self.total % LAP_LEN
            self.px = math.sin(self.t * 0.6) * 0.5
            self.bg += curve_at(self.z) * 0.6 * dt * 55
            self.update_traffic(dt)
            self.update_particles(dt)
            return
        if self.state == "COUNTDOWN":
            self.countdown -= dt
            self.update_traffic(dt)
            if self.countdown <= 0:
                self.state = "RACE"
                self.go_t = 0.9
                self.race_time = 0.0
            return

        self.race_time += dt
        self.go_t = max(0.0, self.go_t - dt)
        self.invuln = max(0.0, self.invuln - dt)
        self.emp = max(0.0, self.emp - dt)
        self.update_player(dt, inp)
        self.update_traffic(dt)
        self.update_ai(dt)
        self.update_pickups(dt)
        self.update_collisions()
        self.update_particles(dt)

    def update_player(self, dt, inp):
        finished = self.state == "FINISHED"
        throttle = inp.throttle and not finished
        brake = inp.brake or finished
        steer = 0 if finished else inp.steer
        drift_key = inp.drift and not finished

        sr = self.speed / MAX_SPEED
        offroad = abs(self.px) > 1.08
        max_sp = MAX_SPEED * (1.3 if self.boost > 0 else 1.0)
        if offroad:
            max_sp = min(max_sp, MAX_SPEED * 0.4)

        if self.boost > 0:
            self.boost -= dt
            self.speed = min(self.speed + 2400 * dt, max_sp)
        else:
            if throttle:
                self.speed += ACCEL * (1.2 - sr) * dt
            else:
                self.speed -= DRAG * dt
            if self.speed > max_sp:
                self.speed = max(max_sp, self.speed - (2400 if offroad else 700) * dt)
        if brake:
            self.speed -= (700 if finished else BRAKE) * dt
        self.speed = max(0.0, self.speed)
        sr = self.speed / MAX_SPEED

        # drift state machine
        if self.drifting and (not drift_key or sr < 0.3):
            if sr >= 0.3 and self.charge >= 1.0:
                self.boost = max(self.boost, 0.7 + 0.45 * min(self.charge, 3.0))
                self.say("DRIFT BOOST!")
            self.drifting = False
            self.charge = 0.0
        elif not self.drifting and drift_key and sr >= 0.4 and steer != 0:
            self.drifting = True
            self.drift_dir = 1 if steer > 0 else -1

        # steering
        cap = TURN * min(1.0, self.speed / 350.0)
        if self.drifting:
            target = steer * cap * 1.2 + self.drift_dir * cap * 0.55
            grip = 2.2
            self.speed = max(0.0, self.speed - 40 * dt)
            if abs(self.vx) > 0.6 and steer * self.drift_dir >= 0:
                self.charge += dt * 0.9
        else:
            target = steer * cap
            grip = 9.0
        self.vx += (target - self.vx) * min(1.0, grip * dt)
        cent = curve_at(self.z) * sr * sr * CENTRIFUGAL
        self.px += (self.vx - cent) * dt

        if abs(self.px) > 1.08 and self.speed > 400:
            self.shake = max(self.shake, 0.06)
        if abs(self.px) > 2.8:
            self.px = math.copysign(2.8, self.px)
            self.vx = 0.0
            self.speed *= 0.97
        self.bg += curve_at(self.z) * sr * dt * 55

        # lap logic
        prev = self.total
        self.total += self.speed * dt
        self.z = self.total % LAP_LEN
        if prev < 0 <= self.total:
            self.timing = True
            self.lap_start = self.race_time
        old_k, new_k = int(prev // LAP_LEN), int(self.total // LAP_LEN)
        if new_k > old_k and new_k >= 1 and self.state == "RACE":
            lt = self.race_time - self.lap_start
            self.lap_start = self.race_time
            self.last_lap = lt
            if self.best_lap is None or lt < self.best_lap:
                self.best_lap = lt
                self.say("NEW BEST LAP  " + fmt_time(lt), 2.2)
            if new_k >= LAPS:
                self.state = "FINISHED"
                self.finish_time = self.race_time
                self.final_pos = [r[0] for r in self.standings()].index("YOU") + 1

        # particles from tyres / boost
        sx, yb, wpx = self.pscr
        if self.drifting and self.speed > 400:
            for side in (-1, 1):
                self.particles.append([sx + side * wpx * 0.38, yb - 1,
                                       random.uniform(-14, 14) - side * 6,
                                       random.uniform(-22, -6), 0.5, 0.5,
                                       (215, 215, 225)])
        elif offroad and self.speed > 300:
            self.particles.append([sx + random.uniform(-wpx / 2, wpx / 2), yb - 1,
                                   random.uniform(-20, 20), random.uniform(-26, -8),
                                   0.45, 0.45, (150, 110, 70)])
        if self.boost > 0:
            for side in (-1, 1):
                self.particles.append([sx + side * wpx * 0.3, yb - wpx * 0.3,
                                       random.uniform(-8, 8), random.uniform(-4, 14),
                                       0.25, 0.25, random.choice(
                                           [(255, 200, 60), (255, 120, 30)])])

    def update_traffic(self, dt):
        for t in self.traffic:
            t.z = (t.z + t.speed * dt) % LAP_LEN

    def update_ai(self, dt):
        go = self.state in ("RACE", "FINISHED")
        for a in self.ais:
            if not go:
                continue
            ahead_c = curve_at(a.z + 1200)
            target = a.base * (1.0 - 0.09 * min(1.0, abs(ahead_c) / 2.5))
            dist = a.total - self.total
            if dist > 7000:
                target *= 0.92
            elif dist < -7000:
                target *= 1.07
            if self.emp > 0:
                target *= 0.55

            want = clamp(a.pref * 0.7 + math.copysign(
                min(1.0, abs(ahead_c) / 2.0) * 0.4, curve_at(a.z + 1500)), -0.8, 0.8)

            def blocked(x):
                for t in self.traffic:
                    d = wrapdiff(t.z, a.z)
                    if 0 < d < 2600 and abs(t.x - x) < 0.45:
                        return True
                return False

            if blocked(want):
                for off in (0.6, -0.6, 1.2, -1.2):
                    c = clamp(want + off, -0.8, 0.8)
                    if not blocked(c):
                        want = c
                        break
            for t in self.traffic:          # brake behind traffic
                d = wrapdiff(t.z, a.z)
                if 0 < d < 900 and abs(t.x - a.x) < 0.4:
                    target = min(target, t.speed * 0.9)
            a.x += clamp(want - a.x, -0.9 * dt, 0.9 * dt)
            a.speed += clamp(target - a.speed, -1500 * dt, 700 * dt)
            a.total += a.speed * dt
            a.z = a.total % LAP_LEN
            if a.finish is None and a.total >= LAPS * LAP_LEN:
                a.finish = self.race_time

    def update_pickups(self, dt):
        for p in self.pickups:
            if p.cool > 0:
                p.cool -= dt
                continue
            if abs(wrapdiff(p.z, self.z)) < 200 and abs(p.x - self.px) < 0.4:
                p.cool = 8.0
                if p.kind == "nitro":
                    self.boost = max(self.boost, 2.0)
                    self.say("NITRO!")
                elif p.kind == "shield":
                    self.shield = True
                    self.say("SHIELD READY")
                else:
                    self.emp = 3.5
                    self.say("EMP! RIVALS SLOWED")

    def update_collisions(self):
        if self.invuln <= 0:
            for o in self.traffic + self.ais:
                dz = wrapdiff(o.z, self.z)
                if abs(dz) < 170 and abs(o.x - self.px) < 0.36:
                    push = 1 if self.px >= o.x else -1
                    self.invuln = 1.0
                    self.vx = push * 1.4
                    self.drifting = False
                    self.charge = 0.0
                    if self.shield:
                        self.shield = False
                        self.shake = 0.2
                        self.say("SHIELD BROKEN")
                    else:
                        if dz > 0:
                            self.speed = min(self.speed, o.speed * 0.6)
                        self.boost = 0.0
                        self.px += push * 0.12
                        self.shake = 0.4
                        if o.name:
                            o.speed *= 0.85
                    break
        if self.invuln <= 0 and abs(self.px) > 1.2:
            for tr in self.trees:
                if abs(wrapdiff(tr.z, self.z)) < 150 and abs(tr.x - self.px) < 0.3:
                    self.speed *= 0.25
                    self.boost = 0.0
                    self.drifting = False
                    self.shake = 0.5
                    self.invuln = 0.8
                    self.px -= math.copysign(0.4, self.px)
                    self.vx = 0.0
                    self.say("CRASH!", 1.0)
                    break

    def update_particles(self, dt):
        alive = []
        for p in self.particles:
            p[4] -= dt
            if p[4] > 0:
                p[0] += p[2] * dt
                p[1] += p[3] * dt
                alive.append(p)
        self.particles = alive[-250:]

    def standings(self):
        racers = [("YOU", self.total, self.finish_time)] + \
                 [(a.name, a.total, a.finish) for a in self.ais]
        fin = sorted([r for r in racers if r[2] is not None], key=lambda r: r[2])
        rest = sorted([r for r in racers if r[2] is None], key=lambda r: -r[1])
        return fin + rest

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def draw_road(self, surf):
        shift = self.shift
        dx = sh = 0.0
        prev = None
        pz = self.z
        cam = self.cam_x
        span = H - HORIZON
        for y in range(H - 1, HORIZON, -1):
            s = (y - HORIZON) / float(span)
            z_rel = ZNEAR / s
            dz = 0.0 if prev is None else z_rel - prev
            prev = z_rel
            z_abs = pz + z_rel - ZCAR
            if z_rel < CURVE_FAR:
                dx += curve_at(z_abs) * CURVE_C * dz
                sh += dx * dz
            shift[y] = sh
            hw = ROAD_HW * s
            xc = W / 2 + (sh - cam) * hw
            stripe = int(z_abs // STRIPE) & 1
            haze = min(0.85, (1 - s) ** 2.2)
            grass = mix((34, 150, 80) if stripe else (28, 130, 70), HAZE, haze)
            rumble = mix((220, 40, 50) if stripe else (240, 240, 240), HAZE, haze)
            road = mix((112, 112, 124) if stripe else (104, 104, 116), HAZE, haze)
            fill = surf.fill
            fill(grass, (0, y, W, 1))
            fill(rumble, (int(xc - hw * 1.14), y, int(hw * 2.28) + 1, 1))
            fill(road, (int(xc - hw), y, int(hw * 2) + 1, 1))
            if stripe:
                line = mix((240, 240, 240), HAZE, haze)
                lw = max(1, int(hw * 0.035))
                for u in (-0.31, 0.31):
                    fill(line, (int(xc + u * hw) - lw // 2, y, lw, 1))
            if z_abs % LAP_LEN < STRIPE:      # start / finish line
                cw = max(1, int(hw * 0.2))
                for k in range(10):
                    on = (k + int(z_abs // (STRIPE / 2))) & 1
                    col = mix((250, 250, 250) if on else (20, 20, 20), HAZE, haze)
                    fill(col, (int(xc - hw + k * hw * 0.2), y, cw, 1))
        shift[HORIZON] = shift[HORIZON + 1]

    def render_world(self, low):
        low.blit(self.sky, (0, 0))
        for layer, mult in ((self.mtn_far, 0.25), (self.mtn_near, 0.55)):
            off = int(self.bg * mult) % W
            low.blit(layer, (-off, 0))
            low.blit(layer, (W - off, 0))
        self.cam_x = self.px * 0.8
        self.draw_road(low)

        pz = self.z
        items = []
        for group in (self.traffic, self.ais, self.trees, self.pickups):
            for o in group:
                if group is self.pickups and o.cool > 0:
                    continue
                zc = wrapdiff(o.z, pz) + ZCAR
                if 700 < zc < DRAW_DIST:
                    items.append((zc, o))
        items.append((ZCAR, None))               # the player
        items.sort(key=lambda it: -it[0])

        for zc, o in items:
            s = ZNEAR / zc
            ybot = HORIZON + s * (H - HORIZON)
            row = min(H - 1, max(HORIZON + 1, int(ybot)))
            hw = ROAD_HW * s
            if o is None:
                self.draw_player(low, s, hw)
                continue
            sx = W / 2 + (self.shift[row] + o.x - self.cam_x) * hw
            w_px = o.ww * hw
            if sx < -80 or sx > W + 80 or w_px < 0.8:
                continue
            if o.kind:                           # floating pickup box
                ybot -= w_px * (0.3 + 0.15 * math.sin(self.t * 4 + o.z))
            blit_sprite(low, o.sprite, o.ref_w, sx, ybot, w_px)

        for x, y, vx, vy, life, mx, col in self.particles:
            r = max(1, int(3 * life / mx)) if col[0] > 200 and col[2] > 200 else 1
            pygame.draw.circle(low, col, (int(x), int(y)), r)

        if self.boost > 0 and self.state != "MENU":
            for _ in range(14):                  # speed lines
                x = random.randint(0, W)
                y = random.randint(HORIZON + 4, H)
                pygame.draw.line(low, (255, 235, 200), (x, y),
                                 (x + (x - W / 2) * 0.1, y + (y - HORIZON) * 0.1))

    def draw_player(self, low, s, hw):
        if self.state == "MENU" or (self.invuln > 0 and int(self.t * 14) % 2):
            if self.state != "MENU":
                return
        bump = 0
        if self.speed > 100:
            bump = int(self.t * 30) & 1
            if abs(self.px) > 1.08:
                bump += random.randint(0, 2)
        ybot = HORIZON + s * (H - HORIZON) + bump
        row = min(H - 1, int(ybot))
        sx = W / 2 + (self.shift[row] + self.px - self.cam_x) * hw
        lean = int(clamp(round(self.vx / TURN * 2.4), -2, 2))
        w_px = 0.42 * hw
        nw, nh = blit_sprite(low, self.player_sprites[lean], 18, sx, ybot, w_px)
        self.pscr = (sx, ybot, w_px)
        if self.shield:
            pygame.draw.circle(low, (120, 200, 255), (int(sx), int(ybot - nh / 2)),
                               int(nw * 0.5), 1)

    # ------------------------------------------------------------------
    def text(self, surf, msg, pos, font, color=(255, 255, 255), anchor="topleft"):
        img = font.render(msg, False, color)
        sh = font.render(msg, False, (25, 10, 45))
        r = img.get_rect(**{anchor: pos})
        surf.blit(sh, r.move(3, 3))
        surf.blit(img, r)

    def draw(self, screen):
        self.render_world(self.low)
        pygame.transform.scale(self.low, (W * SCALE, H * SCALE), self.big)
        ox = oy = 0
        if self.shake > 0:
            k = int(1 + self.shake * 6) * 1
            ox, oy = random.randint(-k, k), random.randint(-k, k)
        screen.fill((0, 0, 0))
        screen.blit(self.big, (ox, oy))
        self.draw_hud(screen)

    def draw_hud(self, screen):
        SW, SH = W * SCALE, H * SCALE
        yellow, white = (255, 215, 60), (255, 255, 255)
        if self.state == "MENU":
            self.text(screen, "TURBO DRIFT", (SW // 2, 110), self.f_big, yellow, "midtop")
            self.text(screen, "PRESS ENTER TO RACE", (SW // 2, 240), self.f_mid, white, "midtop")
            lines = ["ARROWS / WASD  drive", "SPACE / SHIFT  drift (hold while turning)",
                     "Release a charged drift for a turbo!",
                     "Grab boxes: nitro / shield / EMP"]
            for i, ln in enumerate(lines):
                self.text(screen, ln, (SW // 2, 330 + i * 28), self.f_small,
                          (255, 200, 170), "midtop")
            return

        # lap / times (top-left)
        lap = int(clamp(self.total // LAP_LEN + 1, 1, LAPS))
        self.text(screen, "LAP %d/%d" % (lap, LAPS), (16, 10), self.f_mid, yellow)
        shown = self.finish_time if self.finish_time is not None else self.race_time
        self.text(screen, "TIME  " + fmt_time(shown), (16, 50), self.f_small)
        cur = (self.race_time - self.lap_start) if self.timing and self.state == "RACE" else None
        self.text(screen, "LAP   " + fmt_time(cur), (16, 74), self.f_small)
        self.text(screen, "LAST  " + fmt_time(self.last_lap), (16, 98), self.f_small)
        self.text(screen, "BEST  " + fmt_time(self.best_lap), (16, 122), self.f_small,
                  (120, 255, 160))

        # standings (top-right)
        order = self.standings()
        pos = [r[0] for r in order].index("YOU") + 1
        self.text(screen, "POS %d/%d" % (pos, len(order)), (SW - 16, 10), self.f_mid,
                  yellow, "topright")
        for i, r in enumerate(order):
            me = r[0] == "YOU"
            self.text(screen, "%d %s" % (i + 1, r[0]), (SW - 16, 52 + i * 22),
                      self.f_small, yellow if me else (230, 220, 240), "topright")

        # speed (bottom-left)
        kmh = int(self.speed / MAX_SPEED * 280)
        self.text(screen, str(kmh), (16, SH - 30), self.f_big, white, "bottomleft")
        self.text(screen, "KM/H", (150 if kmh > 99 else 120, SH - 36), self.f_small,
                  (255, 200, 170), "bottomleft")

        # drift bar (bottom-center)
        bx, by, bw, bh = SW // 2 - 150, SH - 38, 300, 16
        pygame.draw.rect(screen, (25, 10, 45), (bx - 3, by - 3, bw + 6, bh + 6))
        frac = clamp(self.charge / 2.0, 0.0, 1.0)
        col = (120, 140, 200) if self.charge < 1 else (255, 150, 0) if self.charge < 2 else (80, 240, 255)
        pygame.draw.rect(screen, col, (bx, by, int(bw * frac), bh))
        pygame.draw.line(screen, white, (bx + bw // 2, by - 3), (bx + bw // 2, by + bh + 2), 2)
        self.text(screen, "DRIFT", (SW // 2, by - 24), self.f_small, white, "midtop")

        # status (bottom-right)
        y = SH - 20
        if self.boost > 0:
            self.text(screen, "NITRO %.1f" % self.boost, (SW - 16, y), self.f_small,
                      (255, 160, 40), "bottomright")
            y -= 26
        if self.shield:
            self.text(screen, "SHIELD", (SW - 16, y), self.f_small, (110, 190, 255),
                      "bottomright")
            y -= 26
        if self.emp > 0:
            self.text(screen, "EMP %.1f" % self.emp, (SW - 16, y), self.f_small,
                      (200, 120, 255), "bottomright")

        if self.msg_t > 0:
            self.text(screen, self.msg, (SW // 2, 150), self.f_mid, yellow, "midtop")

        if self.state == "COUNTDOWN":
            n = int(math.ceil(self.countdown))
            self.text(screen, str(max(1, n)), (SW // 2, 160), self.f_big, yellow, "midtop")
        elif self.go_t > 0:
            self.text(screen, "GO!", (SW // 2, 160), self.f_big, (120, 255, 140), "midtop")

        if self.state == "FINISHED":
            veil = pygame.Surface((SW, SH), pygame.SRCALPHA)
            veil.fill((10, 5, 30, 170))
            screen.blit(veil, (0, 0))
            self.text(screen, "RACE COMPLETE", (SW // 2, 50), self.f_big, yellow, "midtop")
            self.text(screen, "You finished %d of %d" % (self.final_pos, len(order)),
                      (SW // 2, 150), self.f_mid, white, "midtop")
            self.text(screen, "Time %s    Best lap %s" % (fmt_time(self.finish_time),
                                                        fmt_time(self.best_lap)),
                      (SW // 2, 190), self.f_small, (120, 255, 160), "midtop")
            for i, r in enumerate(order):
                label = "%d. %-6s %s" % (i + 1, r[0],
                                         fmt_time(r[2]) if r[2] is not None else "racing...")
                self.text(screen, label, (SW // 2 - 110, 235 + i * 30), self.f_small,
                          yellow if r[0] == "YOU" else white)
            self.text(screen, "ENTER: race again", (SW // 2, SH - 50), self.f_mid, white,
                      "midtop")
        if self.paused:
            self.text(screen, "PAUSED", (SW // 2, SH // 2 - 40), self.f_big, white, "midtop")


# --------------------------------------------------------------------------
# Arcade integration
# --------------------------------------------------------------------------
class DriftScene(Scene):
    """Wraps the racing Game so it plugs into the arcade menu."""

    def __init__(self):
        self.game = Game()
        self.game.reset("COUNTDOWN")
        self.prev_state = "COUNTDOWN"
        self.prev_boost = 0.0
        self.prev_shake = 0.0
        self.last_n = 99

    def handle_event(self, e):
        if e.type != pygame.KEYDOWN:
            return
        g = self.game
        if e.key == pygame.K_p and g.state in ("RACE", "FINISHED"):
            g.paused = not g.paused
        elif e.key == pygame.K_r:
            g.paused = False
            g.reset("COUNTDOWN")
            self.last_n = 99
        elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and g.state == "FINISHED":
            n = len(g.standings())
            score = (n + 1 - g.final_pos) * 1000 + int(max(0.0, 300.0 - g.finish_time) * 10)
            self.app.finish_game("drift", score)
        elif e.key == pygame.K_ESCAPE:
            self.app.go_menu()

    def update(self, dt, inp):
        g, snd = self.game, self.app.sound
        k = inp.keys
        steer = int(inp.held("right")) - int(inp.held("left"))
        drive = SimpleNamespace(
            steer=steer, throttle=inp.held("up"), brake=inp.held("down"),
            drift=bool(k[pygame.K_SPACE] or k[pygame.K_LSHIFT] or k[pygame.K_RSHIFT]))
        g.update(dt, drive)

        # sound cues
        if g.state == "COUNTDOWN":
            n = int(g.countdown) + 1
            if n != self.last_n:
                self.last_n = n
                snd.play("select")
        if self.prev_state == "COUNTDOWN" and g.state == "RACE":
            snd.play("start")
        if g.boost > 0 and self.prev_boost <= 0:
            snd.play("powerup")
        if g.shake > 0.3 and self.prev_shake <= 0.3:
            snd.play("explode")
        if g.state == "FINISHED" and self.prev_state != "FINISHED":
            snd.play("jingle")
        self.prev_state, self.prev_boost, self.prev_shake = g.state, g.boost, g.shake

        if g.shake > 0:
            kk = int(1 + g.shake * 6)
            self.offset = (random.randint(-kk, kk), random.randint(-kk, kk))
        else:
            self.offset = (0, 0)

    def draw(self, low):
        self.game.render_world(low)

    def draw_overlay(self, screen):
        self.game.draw_hud(screen)
