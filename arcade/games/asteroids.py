"""ROCK BLASTER - vector-style Asteroids for the retro arcade.

Left/Right rotate, Up thrusts, Space (or Z) fires, Down = hyperspace
(risky!). Watch out for UFOs. P pauses, Esc = menu.
"""
import math
import random

import pygame

import scores
from engine import Scene, W, H, clamp, text
from toolkit import Particles, draw_hint

SIZES = {2: dict(r=13, pts=20, name="large"),
         1: dict(r=7, pts=50, name="medium"),
         0: dict(r=4, pts=100, name="small")}
ROCK_COL = (205, 215, 240)
SHIP_COL = (255, 255, 255)
EXTRA_LIFE = 10000


def rot(x, y, a):
    c, s = math.cos(a), math.sin(a)
    return x * c - y * s, x * s + y * c


def wdist(ax, ay, bx, by):
    dx, dy = abs(ax - bx), abs(ay - by)
    return math.hypot(min(dx, W - dx), min(dy, H - dy))


def offsets(x, y, r):
    xs, ys = [0], [0]
    if x < r:
        xs.append(W)
    elif x > W - r:
        xs.append(-W)
    if y < r:
        ys.append(H)
    elif y > H - r:
        ys.append(-H)
    return [(ox, oy) for ox in xs for oy in ys]


def draw_poly(low, color, pts, x, y, r, closed=True):
    for ox, oy in offsets(x, y, r):
        shifted = [(px + ox, py + oy) for px, py in pts]
        if closed:
            pygame.draw.polygon(low, color, shifted, 1)
        else:
            pygame.draw.lines(low, color, False, shifted)


class AsteroidsScene(Scene):
    def __init__(self):
        self.parts = Particles()
        self.t = 0.0
        self.paused = False
        self.new_game()

    def new_game(self):
        self.score = 0
        self.lives = 3
        self.wave = 0
        self.next_life = EXTRA_LIFE
        self.hi = scores.top("asteroids")[0]["score"]
        self.state = "play"
        self.timer = 0.0
        self.respawn()
        self.bullets, self.ubullets, self.rocks = [], [], []
        self.ufo = None
        self.ufo_t = random.uniform(15, 25)
        self.next_wave()

    def respawn(self):
        self.x, self.y = W / 2.0, H / 2.0
        self.vx = self.vy = 0.0
        self.ang = 0.0
        self.dead_t = 0.0
        self.invuln = 2.5
        self.cool = 0.0
        self.hyper_cd = 0.0
        self.thrusting = False

    def next_wave(self):
        self.wave += 1
        self.banner = 1.8
        n = min(10, 3 + self.wave)
        self.rocks = []
        for _ in range(n):
            while True:
                x, y = random.uniform(0, W), random.uniform(0, H)
                if wdist(x, y, self.x, self.y) > 70:
                    break
            self.add_rock(x, y, 2)
        self.ubullets = []

    def add_rock(self, x, y, size):
        sp = random.uniform(14, 34) + self.wave * 2
        a = random.uniform(0, 6.283)
        pts = [(2 * math.pi * i / 10, random.uniform(0.72, 1.15)) for i in range(10)]
        self.rocks.append(dict(x=x, y=y, vx=sp * math.cos(a), vy=sp * math.sin(a), size=size,
                               ang=random.uniform(0, 6.283),
                               spin=random.uniform(-1.2, 1.2), shape=pts))

    def snd(self, n):
        self.app.sound.play(n)

    # ------------------------------------------------------------------
    def update(self, dt, inp):
        p = inp.pressed
        if "back" in p:
            self.app.go_menu()
            return
        if "pause" in p and self.state == "play":
            self.paused = not self.paused
        if self.paused:
            return
        self.t += dt
        self.parts.update(dt)
        self.banner = max(0.0, self.banner - dt)

        if self.state == "over":
            self.timer -= dt
            if self.timer <= 0 or (self.timer < 2.4 and ({"start", "fire"} & p)):
                self.app.finish_game("asteroids", self.score)
            return

        self.update_ship(dt, inp)
        self.update_rocks(dt)
        self.update_bullets(dt)
        self.update_ufo(dt)
        self.collisions()

        if not self.rocks and not self.ufo and self.state == "play":
            self.next_wave()
            self.snd("jingle")

    def update_ship(self, dt, inp):
        if self.dead_t > 0:
            self.dead_t -= dt
            if self.dead_t <= 0 and self.lives > 0:
                # wait for a safe spot
                if all(wdist(r["x"], r["y"], W / 2.0, H / 2.0) > SIZES[r["size"]]["r"] + 30
                       for r in self.rocks):
                    self.respawn()
                else:
                    self.dead_t = 0.2
            elif self.dead_t <= 0:
                self.state = "over"
                self.timer = 3.5
                self.snd("gameover")
            return
        self.invuln = max(0.0, self.invuln - dt)
        self.hyper_cd = max(0.0, self.hyper_cd - dt)
        turn = int(inp.held("right")) - int(inp.held("left"))
        self.ang += turn * 3.6 * dt
        self.thrusting = inp.held("up")
        if self.thrusting:
            self.vx += math.sin(self.ang) * 120 * dt
            self.vy -= math.cos(self.ang) * 120 * dt
            if random.random() < 0.5:
                fx, fy = rot(0, 6, self.ang)
                self.parts.add(self.x + fx, self.y + fy, -math.sin(self.ang) * 40 + random.uniform(-8, 8),
                               math.cos(self.ang) * 40 + random.uniform(-8, 8),
                               (255, 170, 60), 0.3, 1)
            if int(self.t * 12) % 3 == 0:
                self.snd("thrust")
        drag = 1.0 - 0.35 * dt
        self.vx *= drag
        self.vy *= drag
        sp = math.hypot(self.vx, self.vy)
        if sp > 170:
            self.vx *= 170 / sp
            self.vy *= 170 / sp
        self.x = (self.x + self.vx * dt) % W
        self.y = (self.y + self.vy * dt) % H

        self.cool -= dt
        if inp.held("fire") and self.cool <= 0 and len(self.bullets) < 4:
            self.cool = 0.2
            nx, ny = rot(0, -7, self.ang)
            self.bullets.append(dict(x=self.x + nx, y=self.y + ny,
                                     vx=self.vx + math.sin(self.ang) * 220,
                                     vy=self.vy - math.cos(self.ang) * 220, life=1.1))
            self.snd("laser")
        if "down" in inp.pressed and self.hyper_cd <= 0:
            self.hyper_cd = 2.0
            self.x, self.y = random.uniform(10, W - 10), random.uniform(20, H - 10)
            self.vx = self.vy = 0.0
            self.snd("powerup")
            if random.random() < 0.12:
                self.kill_ship()

    def update_rocks(self, dt):
        for r in self.rocks:
            r["x"] = (r["x"] + r["vx"] * dt) % W
            r["y"] = (r["y"] + r["vy"] * dt) % H
            r["ang"] += r["spin"] * dt

    def update_bullets(self, dt):
        for group in (self.bullets, self.ubullets):
            for b in group[:]:
                b["x"] = (b["x"] + b["vx"] * dt) % W
                b["y"] = (b["y"] + b["vy"] * dt) % H
                b["life"] -= dt
                if b["life"] <= 0:
                    group.remove(b)

    def update_ufo(self, dt):
        if self.ufo is None:
            self.ufo_t -= dt
            if self.ufo_t <= 0 and self.rocks and self.state == "play":
                small = self.wave >= 3 and random.random() < 0.45
                d = random.choice((-1, 1))
                self.ufo = dict(x=-8.0 if d > 0 else W + 8.0, y=random.uniform(24, H - 24),
                                dir=d, small=small, shoot=1.0, turn=1.0, vy=0.0)
                self.ufo_t = random.uniform(18, 30)
            return
        u = self.ufo
        u["x"] += u["dir"] * (45 if not u["small"] else 62) * dt
        u["turn"] -= dt
        if u["turn"] <= 0:
            u["turn"] = random.uniform(0.7, 1.6)
            u["vy"] = random.choice((-30, 0, 30))
        u["y"] = clamp(u["y"] + u["vy"] * dt, 14, H - 8)
        u["shoot"] -= dt
        if u["shoot"] <= 0 and self.dead_t <= 0:
            u["shoot"] = 1.3 if not u["small"] else 0.9
            if u["small"]:
                a = math.atan2(self.y - u["y"], self.x - u["x"]) + random.uniform(-0.25, 0.25)
            else:
                a = random.uniform(0, 6.283)
            self.ubullets.append(dict(x=u["x"], y=u["y"], vx=95 * math.cos(a),
                                      vy=95 * math.sin(a), life=2.2))
            self.snd("enemy_shoot")
        if u["x"] < -14 or u["x"] > W + 14:
            self.ufo = None

    # ------------------------------------------------------------------
    def add_score(self, pts):
        self.score += pts
        if self.score >= self.next_life:
            self.next_life += EXTRA_LIFE
            self.lives += 1
            self.snd("pickup")

    def split(self, r):
        self.rocks.remove(r)
        spec = SIZES[r["size"]]
        self.add_score(spec["pts"])
        self.parts.burst(r["x"], r["y"], ROCK_COL, 6 + r["size"] * 3, 40 + r["size"] * 10)
        self.snd("explode" if r["size"] == 2 else "boom")
        if r["size"] > 0:
            for _ in range(2):
                self.add_rock(r["x"], r["y"], r["size"] - 1)

    def kill_ship(self):
        if self.dead_t > 0:
            return
        self.lives -= 1
        self.dead_t = 1.5
        self.parts.burst(self.x, self.y, (255, 255, 255), 20, 70)
        self.parts.burst(self.x, self.y, (255, 160, 60), 12, 50)
        self.snd("explode")

    def collisions(self):
        for b in self.bullets[:]:
            hit = False
            for r in self.rocks[:]:
                if wdist(b["x"], b["y"], r["x"], r["y"]) < SIZES[r["size"]]["r"]:
                    self.split(r)
                    hit = True
                    break
            if not hit and self.ufo:
                u = self.ufo
                if wdist(b["x"], b["y"], u["x"], u["y"]) < (4 if u["small"] else 7):
                    self.add_score(1000 if u["small"] else 200)
                    self.parts.burst(u["x"], u["y"], (255, 120, 220), 16, 60)
                    self.snd("explode")
                    self.ufo = None
                    hit = True
            if hit:
                self.bullets.remove(b)

        if self.dead_t > 0 or self.invuln > 0:
            return
        for r in self.rocks[:]:
            if wdist(self.x, self.y, r["x"], r["y"]) < SIZES[r["size"]]["r"] + 3:
                self.split(r)
                self.kill_ship()
                return
        for b in self.ubullets[:]:
            if wdist(self.x, self.y, b["x"], b["y"]) < 4:
                self.ubullets.remove(b)
                self.kill_ship()
                return
        if self.ufo and wdist(self.x, self.y, self.ufo["x"], self.ufo["y"]) < 9:
            self.parts.burst(self.ufo["x"], self.ufo["y"], (255, 120, 220), 14, 60)
            self.ufo = None
            self.kill_ship()

    # ------------------------------------------------------------------
    def ship_points(self):
        pts = []
        for px, py in ((0, -7), (-5, 6), (0, 3), (5, 6)):
            rx, ry = rot(px, py, self.ang)
            pts.append((self.x + rx, self.y + ry))
        return pts

    def draw(self, low):
        f = self.app.fonts
        low.fill((3, 4, 12))

        for r in self.rocks:
            rad = SIZES[r["size"]]["r"]
            pts = [(r["x"] + math.cos(a + r["ang"]) * rad * m,
                    r["y"] + math.sin(a + r["ang"]) * rad * m) for a, m in r["shape"]]
            draw_poly(low, ROCK_COL, pts, r["x"], r["y"], rad + 2)

        if self.ufo:
            u = self.ufo
            s = 0.6 if u["small"] else 1.0
            x, y = u["x"], u["y"]
            hull = [(x - 8 * s, y), (x - 4 * s, y - 3 * s), (x + 4 * s, y - 3 * s),
                    (x + 8 * s, y), (x + 4 * s, y + 3 * s), (x - 4 * s, y + 3 * s)]
            draw_poly(low, (255, 120, 220), hull, x, y, 10)
            dome = [(x - 3 * s, y - 3 * s), (x - 2 * s, y - 6 * s), (x + 2 * s, y - 6 * s),
                    (x + 3 * s, y - 3 * s)]
            draw_poly(low, (255, 120, 220), dome, x, y, 10, closed=False)

        for b in self.bullets:
            low.fill((255, 250, 170), (int(b["x"]) - 1, int(b["y"]) - 1, 2, 2))
        for b in self.ubullets:
            low.fill((255, 120, 220), (int(b["x"]) - 1, int(b["y"]) - 1, 2, 2))

        if self.dead_t <= 0 and (self.invuln <= 0 or int(self.t * 14) % 2 == 0):
            draw_poly(low, SHIP_COL, self.ship_points(), self.x, self.y, 9)
            if self.thrusting and int(self.t * 30) % 2:
                fl = []
                for px, py in ((-2, 5), (0, 10), (2, 5)):
                    rx, ry = rot(px, py, self.ang)
                    fl.append((self.x + rx, self.y + ry))
                draw_poly(low, (255, 170, 60), fl, self.x, self.y, 12, closed=False)
        self.parts.draw(low)

        text(low, "%06d" % self.score, (6, 2), f.small)
        text(low, "HI %06d" % max(self.hi, self.score), (W // 2, 2), f.small,
             (255, 220, 80), "midtop")
        text(low, "WAVE %d" % self.wave, (W - 6, 2), f.small, (130, 255, 150), "topright")
        for i in range(max(0, self.lives)):
            x = 10 + i * 12
            pygame.draw.polygon(low, SHIP_COL, [(x, 16), (x - 3, 23), (x, 21), (x + 3, 23)], 1)
        draw_hint(low, f, ["LEFT/RIGHT: ROTATE   UP: THRUST   SPACE: FIRE",
                           "DOWN: HYPERSPACE (RISKY)"], self.t, y=150)
        if self.banner > 0 and self.state == "play":
            text(low, "WAVE %d" % self.wave, (W // 2, 70), f.med, (255, 255, 255), "midtop")
        if self.state == "over":
            text(low, "GAME OVER", (W // 2, 70), f.big, (255, 70, 70), "midtop")
        if self.paused:
            text(low, "PAUSED", (W // 2, 70), f.big, (255, 255, 255), "midtop")
