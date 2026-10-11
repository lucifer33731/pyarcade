"""RALLY RUSH - top-down rally racing for the retro arcade.

Up = gas, Down = brake / reverse, Left/Right = steer,
Space or Shift = handbrake (drift round corners!).
3 laps against 5 rivals. Grass slows you down. P pauses, R restarts, Esc = menu.
"""
import math
import random

import pygame

from engine import Scene, W, H, clamp, text
from toolkit import Particles

WORLD_W, WORLD_H = 960, 720
ROAD_R = 17
LAPS = 3
SPACING = 2.0
ACC, DRAG, DRAG_OFF = 100.0, 0.72, 2.3
BRAKE = 170.0
TURN = 2.5
NUM_AI = 5

TRACKS = [
    dict(name="SUNNY CIRCUIT", kind="grass",
         grass=((46, 140, 70), (40, 128, 62)), road=(96, 96, 104),
         curb=((220, 50, 50), (240, 240, 240)),
         pts=[(180, 140), (420, 100), (700, 120), (850, 220), (830, 380), (700, 470),
              (540, 430), (430, 520), (520, 610), (300, 650), (140, 560), (110, 380),
              (200, 270)]),
    dict(name="DESERT RUN", kind="desert",
         grass=((214, 178, 110), (204, 168, 100)), road=(108, 98, 94),
         curb=((240, 140, 40), (240, 240, 240)),
         pts=[(120, 360), (180, 200), (340, 120), (520, 180), (640, 100), (820, 160),
              (880, 320), (780, 420), (860, 540), (700, 650), (520, 590), (360, 660),
              (200, 600), (150, 480)]),
    dict(name="SNOW PASS", kind="snow",
         grass=((225, 232, 240), (210, 220, 232)), road=(86, 90, 104),
         curb=((60, 120, 230), (240, 240, 240)),
         pts=[(150, 200), (380, 140), (560, 260), (760, 150), (880, 300), (760, 430),
              (580, 380), (480, 500), (660, 620), (420, 680), (230, 600), (300, 460),
              (120, 400)]),
]
CAR_COLORS = [(255, 210, 40), (230, 50, 50), (60, 130, 240), (70, 210, 100),
              (200, 80, 240), (235, 235, 245)]
NAMES = ["YOU", "VIPER", "COMET", "NOVA", "BLAZE", "GHOST"]


def wrap_angle(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def catmull_closed(pts, per_seg=40):
    n = len(pts)
    out = []
    for i in range(n):
        p0, p1, p2, p3 = pts[(i - 1) % n], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        for s in range(per_seg):
            t = s / float(per_seg)
            t2, t3 = t * t, t * t * t
            x = 0.5 * (2 * p1[0] + (-p0[0] + p2[0]) * t
                       + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                       + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * (2 * p1[1] + (-p0[1] + p2[1]) * t
                       + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                       + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append((x, y))
    return out


def resample(pts, spacing):
    out = [pts[0]]
    carry = 0.0
    n = len(pts)
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        if d == 0:
            continue
        pos = spacing - carry
        while pos <= d:
            t = pos / d
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
            pos += spacing
        carry = d - (pos - spacing)
    return out


class Track:
    def __init__(self, spec):
        self.spec = spec
        self.name = spec["name"]
        self.pts = resample(catmull_closed(spec["pts"]), SPACING)
        self.n = len(self.pts)
        self.tang = []
        for i in range(self.n):
            a, b = self.pts[(i + 2) % self.n], self.pts[(i - 2) % self.n]
            self.tang.append(math.atan2(a[1] - b[1], a[0] - b[0]))
        self.world = None
        self.mini = None
        self.preview = None

    def nearest(self, x, y, hint, window=30):
        pts, n = self.pts, self.n
        best, bi = None, hint
        for off in range(-window, window + 1):
            i = (hint + off) % n
            px, py = pts[i]
            d = (px - x) ** 2 + (py - y) ** 2
            if best is None or d < best:
                best, bi = d, i
        if best > (3 * ROAD_R) ** 2:          # lost the track: full scan
            for i in range(0, n):
                px, py = pts[i]
                d = (px - x) ** 2 + (py - y) ** 2
                if d < best:
                    best, bi = d, i
        return bi, math.sqrt(best)

    def get_preview(self):
        if self.preview is None:
            s = pygame.Surface((120, 90), pygame.SRCALPHA)
            pts = [(x / 8.0, y / 8.0) for x, y in self.pts[::6]]
            pygame.draw.lines(s, self.spec["curb"][1], True, pts, 5)
            pygame.draw.lines(s, self.spec["road"], True, pts, 3)
            self.preview = s
        return self.preview

    def build(self):
        sp = self.spec
        rng = random.Random(self.name)
        w = pygame.Surface((WORLD_W, WORLD_H))
        w.fill(sp["grass"][0])
        for _ in range(2600):
            w.fill(sp["grass"][1], (rng.randrange(WORLD_W), rng.randrange(WORLD_H),
                                    rng.choice((1, 2)), 1))
        for i, (x, y) in enumerate(self.pts):
            pygame.draw.circle(w, sp["curb"][(i // 6) % 2], (int(x), int(y)), ROAD_R + 3)
        for x, y in self.pts:
            pygame.draw.circle(w, sp["road"], (int(x), int(y)), ROAD_R)
        dark = tuple(max(0, c - 10) for c in sp["road"])
        light = tuple(min(255, c + 10) for c in sp["road"])
        for i in range(0, self.n, 2):
            x, y = self.pts[i]
            ox, oy = rng.randint(-ROAD_R + 2, ROAD_R - 2), rng.randint(-ROAD_R + 2, ROAD_R - 2)
            if math.hypot(ox, oy) < ROAD_R - 1:
                w.fill(rng.choice((dark, light)), (int(x + ox), int(y + oy), 1, 1))
        for i, (x, y) in enumerate(self.pts):
            if (i // 6) % 2 == 0:
                w.fill((225, 225, 210), (int(x), int(y), 2, 2))
        # start / finish line
        a = self.tang[0]
        sx, sy = self.pts[0]
        nx, ny = -math.sin(a), math.cos(a)
        tx, ty = math.cos(a), math.sin(a)
        for row in range(2):
            for k in range(-ROAD_R, ROAD_R, 3):
                col = (250, 250, 250) if ((k // 3) + row) % 2 == 0 else (20, 20, 20)
                w.fill(col, (int(sx + nx * k + tx * row * 3), int(sy + ny * k + ty * row * 3), 3, 3))
        self.scatter(w, rng)
        self.world = w

        mini = pygame.Surface((64, 48), pygame.SRCALPHA)
        mini.fill((10, 5, 30, 170))
        pygame.draw.lines(mini, (210, 210, 235), True,
                          [(x / 15.0, y / 15.0) for x, y in self.pts[::8]], 2)
        self.mini = mini

    def scatter(self, w, rng):
        sample = self.pts[::8]
        lim = (ROAD_R + 14) ** 2
        placed = tries = 0
        kind = self.spec["kind"]
        while placed < 140 and tries < 1600:
            tries += 1
            x, y = rng.randrange(8, WORLD_W - 8), rng.randrange(8, WORLD_H - 8)
            if any((x - px) ** 2 + (y - py) ** 2 < lim for px, py in sample):
                continue
            placed += 1
            if kind == "grass":
                pygame.draw.circle(w, (24, 90, 50), (x, y), 6)
                pygame.draw.circle(w, (40, 130, 70), (x - 1, y - 1), 4)
                pygame.draw.circle(w, (70, 170, 90), (x - 2, y - 2), 2)
            elif kind == "desert":
                if rng.random() < 0.5:
                    w.fill((40, 120, 60), (x, y - 5, 2, 9))
                    w.fill((40, 120, 60), (x - 3, y - 3, 3, 2))
                    w.fill((40, 120, 60), (x + 2, y - 1, 3, 2))
                else:
                    pygame.draw.circle(w, (130, 110, 90), (x, y), 4)
                    pygame.draw.circle(w, (170, 150, 120), (x - 1, y - 1), 2)
            else:
                pygame.draw.polygon(w, (30, 90, 80), [(x, y - 8), (x - 5, y + 3), (x + 5, y + 3)])
                pygame.draw.polygon(w, (240, 245, 250), [(x, y - 8), (x - 2, y - 3), (x + 2, y - 3)])


_car_cache = {}


def car_frames(color):
    fr = _car_cache.get(color)
    if fr is None:
        base = pygame.Surface((11, 7), pygame.SRCALPHA)
        dark = tuple(c // 2 for c in color)
        base.fill((15, 15, 20), (2, 0, 2, 1))
        base.fill((15, 15, 20), (7, 0, 2, 1))
        base.fill((15, 15, 20), (2, 6, 2, 1))
        base.fill((15, 15, 20), (7, 6, 2, 1))
        base.fill(color, (0, 1, 11, 5))
        base.fill(dark, (0, 1, 11, 1))
        base.fill(dark, (0, 5, 11, 1))
        base.fill((30, 40, 70), (6, 2, 2, 3))
        base.fill((255, 240, 160), (10, 2, 1, 1))
        base.fill((255, 240, 160), (10, 4, 1, 1))
        base.fill((255, 255, 255), (3, 3, 2, 1))
        fr = [pygame.transform.rotate(base, -k * 10) for k in range(36)]
        _car_cache[color] = fr
    return fr


class RCar:
    def __init__(self, x, y, h, color, name, vcap=130.0, lane=0.0):
        self.x, self.y, self.h = x, y, h
        self.vx = self.vy = 0.0
        self.color, self.name = color, name
        self.vcap, self.lane = vcap, lane
        self.idx = 0
        self.lap = 0
        self.dist = 0.0
        self.off = False
        self.drift = False
        self.finish = None
        self.speed = 0.0

    def total(self, n):
        return self.lap * n + self.idx


class RallyScene(Scene):
    def __init__(self):
        self.tracks = [Track(s) for s in TRACKS]
        self.sel = 0
        self.mode = "select"        # select | countdown | race | done
        self.t = 0.0
        self.parts = Particles()
        self.paused = False
        self.cam = [0.0, 0.0]
        self.bump_cd = 0.0

    # ------------------------------------------------------------------
    def start_race(self):
        self.track = self.tracks[self.sel]
        if self.track.world is None:
            self.track.build()
        tr = self.track
        self.cars = []
        for k in range(NUM_AI + 1):
            idx = (tr.n - 14 - 12 * k) % tr.n
            a = tr.tang[idx]
            lane = 7 if k % 2 == 0 else -7
            x = tr.pts[idx][0] - math.sin(a) * lane
            y = tr.pts[idx][1] + math.cos(a) * lane
            player = k == NUM_AI
            ci = 0 if player else k + 1
            car = RCar(x, y, a, CAR_COLORS[ci], NAMES[ci],
                       vcap=[132, 128, 124, 120, 116][k % 5] * random.uniform(0.98, 1.02),
                       lane=random.uniform(-7, 7))
            car.idx = idx
            self.cars.append(car)
        self.player = self.cars[-1]
        self.mode = "countdown"
        self.countdown = 3.0
        self.race_time = 0.0
        self.final_pos = None
        self.parts.items = []
        self.cam = [self.player.x - W / 2.0, self.player.y - H / 2.0]
        self.go_t = 0.0

    def snd(self, n):
        self.app.sound.play(n)

    def standings(self):
        n = self.track.n
        fin = sorted([c for c in self.cars if c.finish is not None], key=lambda c: c.finish)
        rest = sorted([c for c in self.cars if c.finish is None], key=lambda c: -c.total(n))
        return fin + rest

    # ------------------------------------------------------------------
    def update(self, dt, inp):
        p = inp.pressed
        self.t += dt
        if "back" in p:
            self.app.go_menu()
            return
        if self.mode == "select":
            if "left" in p or "right" in p:
                self.sel = (self.sel + (1 if "right" in p else -1)) % len(self.tracks)
                self.snd("select")
            if "start" in p or "fire" in p:
                self.snd("start")
                self.start_race()
            return
        if "pause" in p and self.mode == "race":
            self.paused = not self.paused
        if self.paused:
            return
        self.parts.update(dt)
        self.bump_cd = max(0.0, self.bump_cd - dt)

        if self.mode == "done":
            self.race_time += dt
            self.coast(dt)
            if "start" in p or "fire" in p:
                n = len(self.cars)
                score = (n + 1 - self.final_pos) * 1000 + int(max(0.0, 150.0 - self.player.finish) * 10)
                self.app.finish_game("rally", score)
            return

        if self.mode == "countdown":
            self.countdown -= dt
            if int(self.countdown + dt) != int(self.countdown) and self.countdown > 0:
                self.snd("select")
            if self.countdown <= 0:
                self.mode = "race"
                self.go_t = 0.9
                self.snd("start")
            self.camera(dt)
            return

        self.race_time += dt
        self.go_t = max(0.0, self.go_t - dt)
        self.drive_all(dt, inp)
        self.collide()
        self.camera(dt)

    def coast(self, dt):
        # after finishing everyone keeps driving
        self.drive_all(dt, None)
        self.collide()
        self.camera(dt)

    def drive_all(self, dt, inp):
        tr = self.track
        ptotal = self.player.total(tr.n)
        for c in self.cars:
            if c is self.player and inp is not None and c.finish is None:
                k = inp.keys
                throttle = 1.0 if inp.held("up") else 0.0
                brake = 1.0 if inp.held("down") else 0.0
                steer = int(inp.held("right")) - int(inp.held("left"))
                hb = bool(k[pygame.K_SPACE] or k[pygame.K_LSHIFT] or k[pygame.K_RSHIFT])
            elif c is self.player:
                throttle, brake, steer, hb = 0.0, 0.4, 0.0, False
            else:
                throttle, brake, steer, hb = self.ai_control(c, ptotal)
            self.physics(c, dt, throttle, brake, steer, hb)
            self.progress(c)

    def ai_control(self, car, ptotal):
        tr = self.track
        n = tr.n
        look = int(14 + car.speed * 0.22)
        ti = (car.idx + look) % n
        a = tr.tang[ti]
        tx = tr.pts[ti][0] - math.sin(a) * car.lane
        ty = tr.pts[ti][1] + math.cos(a) * car.lane
        diff = wrap_angle(math.atan2(ty - car.y, tx - car.x) - car.h)
        steer = clamp(diff * 2.0, -1.0, 1.0)
        a1, a2 = tr.tang[(car.idx + 10) % n], tr.tang[(car.idx + 60) % n]
        dth = abs(wrap_angle(a2 - a1))
        vcap = car.vcap
        gap = car.total(n) - ptotal
        if gap > 350:
            vcap *= 0.94
        elif gap < -350:
            vcap *= 1.06
        vt = vcap * (1.0 - clamp(dth * 0.75, 0.0, 0.5))
        if car.off:
            vt = min(vt, 70.0)
        if car.speed < vt:
            return 1.0, 0.0, steer, False
        if car.speed > vt + 10:
            return 0.0, 0.5, steer, False
        return 0.35, 0.0, steer, False

    def physics(self, car, dt, throttle, brake, steer, hb):
        h = car.h
        fx, fy = math.cos(h), math.sin(h)
        vf = car.vx * fx + car.vy * fy
        a = ACC * throttle
        if brake > 0:
            a -= (BRAKE if vf > 2 else 70.0) * brake
        car.vx += fx * a * dt
        car.vy += fy * a * dt
        k = max(0.0, 1.0 - (DRAG_OFF if car.off else DRAG) * dt)
        car.vx *= k
        car.vy *= k
        vf = car.vx * fx + car.vy * fy
        sf = clamp(vf / 35.0, -1.0, 1.0)
        rate = TURN * (1.0 - 0.35 * clamp(vf / 140.0, 0.0, 1.0)) * (1.25 if hb else 1.0)
        car.h = h = h + steer * rate * sf * dt
        fx, fy = math.cos(h), math.sin(h)
        lx, ly = -fy, fx
        vf = car.vx * fx + car.vy * fy
        vl = car.vx * lx + car.vy * ly
        vl *= math.exp(-(1.8 if hb else 7.5) * dt)
        if hb:
            vf *= 1.0 - 0.5 * dt
        vf = max(vf, -45.0)
        car.vx = fx * vf + lx * vl
        car.vy = fy * vf + ly * vl
        car.x += car.vx * dt
        car.y += car.vy * dt
        if car.x < 6 or car.x > WORLD_W - 6:
            car.x = clamp(car.x, 6, WORLD_W - 6)
            car.vx = 0.0
        if car.y < 6 or car.y > WORLD_H - 6:
            car.y = clamp(car.y, 6, WORLD_H - 6)
            car.vy = 0.0
        car.speed = math.hypot(car.vx, car.vy)
        car.drift = abs(vl) > 22 and car.speed > 40
        if car.drift and not car.off:
            rx, ry = car.x - fx * 4, car.y - fy * 4
            for s in (-3, 3):
                self.track.world.fill((52, 52, 58), (int(rx + lx * s), int(ry + ly * s), 1, 1))
        if car.drift and random.random() < 0.5:
            self.parts.add(car.x - fx * 4, car.y - fy * 4, random.uniform(-6, 6),
                           random.uniform(-6, 6), (225, 225, 230), 0.4, 2)
        elif car.off and car.speed > 30 and random.random() < 0.5:
            dust = (170, 140, 90) if self.track.spec["kind"] != "snow" else (240, 245, 250)
            self.parts.add(car.x - fx * 4, car.y - fy * 4, random.uniform(-8, 8),
                           random.uniform(-8, 8), dust, 0.35, 2)

    def progress(self, car):
        tr = self.track
        prev = car.idx
        car.idx, car.dist = tr.nearest(car.x, car.y, prev)
        car.off = car.dist > ROAD_R - 1
        n = tr.n
        if prev > n * 0.75 and car.idx < n * 0.25:
            car.lap += 1
        elif prev < n * 0.25 and car.idx > n * 0.75:
            car.lap -= 1
        if car.lap > LAPS and car.finish is None:
            car.finish = self.race_time
            if car is self.player:
                self.final_pos = [c.name for c in self.standings()].index("YOU") + 1
                self.mode = "done"
                self.snd("jingle")

    def collide(self):
        cars = self.cars
        for i in range(len(cars)):
            for j in range(i + 1, len(cars)):
                a, b = cars[i], cars[j]
                dx, dy = b.x - a.x, b.y - a.y
                if abs(dx) > 10 or abs(dy) > 10:
                    continue
                d = math.hypot(dx, dy) or 0.01
                if d >= 9:
                    continue
                nx, ny = dx / d, dy / d
                push = (9 - d) / 2.0
                a.x -= nx * push
                a.y -= ny * push
                b.x += nx * push
                b.y += ny * push
                rel = (b.vx - a.vx) * nx + (b.vy - a.vy) * ny
                if rel < 0:
                    imp = -rel * 0.6
                    a.vx -= nx * imp
                    a.vy -= ny * imp
                    b.vx += nx * imp
                    b.vy += ny * imp
                    if (a is self.player or b is self.player) and self.bump_cd <= 0 and -rel > 15:
                        self.bump_cd = 0.3
                        self.snd("boom")

    def camera(self, dt):
        p = self.player
        tx = clamp(p.x + p.vx * 0.3 - W / 2.0, 0, WORLD_W - W)
        ty = clamp(p.y + p.vy * 0.3 - H / 2.0, 0, WORLD_H - H)
        k = min(1.0, 6 * dt)
        self.cam[0] += (tx - self.cam[0]) * k
        self.cam[1] += (ty - self.cam[1]) * k

    # ------------------------------------------------------------------
    def draw(self, low):
        f = self.app.fonts
        if self.mode == "select":
            low.fill((10, 8, 30))
            text(low, "RALLY RUSH", (W // 2, 6), f.big, (255, 220, 80), "midtop")
            tr = self.tracks[self.sel]
            text(low, "< %s >" % tr.name, (W // 2, 46), f.med, (255, 255, 255), "midtop")
            low.fill(tr.spec["grass"][0], (W // 2 - 64, 68, 128, 94))
            low.blit(tr.get_preview(), (W // 2 - 60, 70))
            text(low, "LEFT/RIGHT: TRACK    ENTER: RACE", (W // 2, 166), f.small,
                 (230, 220, 255), "midtop")
            return

        cx, cy = int(self.cam[0]), int(self.cam[1])
        cx = int(clamp(cx, 0, WORLD_W - W))
        cy = int(clamp(cy, 0, WORLD_H - H))
        low.blit(self.track.world, (0, 0), pygame.Rect(cx, cy, W, H))
        self.parts.draw(low, cx, cy)
        for c in sorted(self.cars, key=lambda c: c.y):
            frames = car_frames(c.color)
            img = frames[int(round(math.degrees(c.h) / 10.0)) % 36]
            low.blit(img, (int(c.x - cx - img.get_width() / 2), int(c.y - cy - img.get_height() / 2)))
        # player arrow
        pl = self.player
        low.fill((255, 255, 255), (int(pl.x - cx) - 1, int(pl.y - cy) - 9, 3, 1))

        n = self.track.n
        lap = int(clamp(pl.lap, 1, LAPS))
        text(low, "LAP %d/%d" % (lap, LAPS), (6, 2), f.small, (255, 220, 80))
        shown = pl.finish if pl.finish is not None else self.race_time
        text(low, "%d:%05.2f" % (int(shown // 60), shown % 60), (6, 13), f.small)
        order = self.standings()
        pos = [c.name for c in order].index("YOU") + 1
        text(low, "POS %d/%d" % (pos, len(order)), (W - 6, 2), f.small, (255, 220, 80), "topright")
        text(low, "%d" % int(pl.speed * 1.9), (6, H - 22), f.med, (255, 255, 255))
        text(low, "KM/H", (38 if pl.speed * 1.9 >= 100 else 30, H - 14), f.small, (200, 190, 240))
        low.blit(self.track.mini, (W - 68, H - 52))
        for c in self.cars:
            col = (255, 255, 255) if c is pl else c.color
            low.fill(col, (W - 68 + int(c.x / 15.0) - 1, H - 52 + int(c.y / 15.0) - 1, 3, 3))

        if self.mode == "countdown":
            text(low, str(max(1, int(math.ceil(self.countdown)))), (W // 2, 50), f.big,
                 (255, 220, 80), "midtop")
            text(low, "UP: GAS   SPACE: DRIFT   LEFT/RIGHT: STEER", (W // 2, 120), f.small,
                 (255, 240, 170), "midtop")
        elif self.go_t > 0:
            text(low, "GO!", (W // 2, 50), f.big, (120, 255, 140), "midtop")
        if self.mode == "done":
            veil = pygame.Surface((W, H), pygame.SRCALPHA)
            veil.fill((10, 5, 30, 170))
            low.blit(veil, (0, 0))
            text(low, "FINISH!", (W // 2, 8), f.big, (255, 220, 80), "midtop")
            text(low, "YOU FINISHED %d OF %d" % (self.final_pos, len(self.cars)),
                 (W // 2, 48), f.med, (255, 255, 255), "midtop")
            for i, c in enumerate(order):
                t = "%d:%05.2f" % (int(c.finish // 60), c.finish % 60) if c.finish is not None else "racing..."
                text(low, "%d. %-6s %s" % (i + 1, c.name, t), (W // 2 - 60, 74 + i * 11), f.small,
                     (255, 220, 80) if c.name == "YOU" else (255, 255, 255))
            text(low, "PRESS ENTER", (W // 2, 160), f.small, (230, 220, 255), "midtop")
        if self.paused:
            text(low, "PAUSED", (W // 2, 60), f.big, (255, 255, 255), "midtop")

    def handle_event(self, e):
        if e.type == pygame.KEYDOWN and e.key == pygame.K_r and self.mode in ("race", "done", "countdown"):
            self.paused = False
            self.start_race()
