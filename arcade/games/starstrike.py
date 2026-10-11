"""STAR STRIKE - a vertical shoot-'em-up for the retro arcade.

Arrows / WASD move, hold Space (or Z) to fire. Collect power-ups:
P = stronger weapon, S = shield, L = extra life.
Every 5th wave ends with a boss. P pauses, Esc = menu.
"""
import math
import random

import pygame

import scores
from engine import Scene, W, H, clamp, sprite_from_rows, text
from toolkit import Particles, Starfield, draw_hint


def mirror_even(rows):
    return [r + r[::-1] for r in rows]


def mirror_odd(rows):
    return [r + r[-2::-1] for r in rows]


SHIP = mirror_odd([
    "......W", ".....WW", ".....WW", "....WWW", "..B.WCW", "..BBWCW",
    ".BBBWWW", "BBBBWWW", "BB.BBWW", "B..EEWW", "...E.E."])
SHIP_COL = {"W": (225, 235, 255), "B": (70, 120, 235), "C": (90, 225, 255),
            "E": (255, 150, 40)}

GRUNT = mirror_even(["...XXX", "..XXXX", ".XXXXX", "XXX.XX", "XXXXXX", ".X.XXX",
                     "X.X...", "X.....", "......"])
WEAVER = mirror_even(["X....X", "XX..XX", "XXXXXX", ".XX.XX", "..XXXX", "..XXXX",
                      ".X..XX", "X....X", "......"])
GUNNER = mirror_even(["..XXXX", ".XXXXX", "XXXXXX", "XX.XXX", "XXXXXX", ".XXXXX",
                      "..X.XX", "..X..X", "..X..."])
TANK = mirror_even(["..XXXXXX", ".XXXXXXX", "XXXXXXXX", "XXX.XXXX", "XXXXXXXX", "XXXXXXXX",
                    "XX.XXX.X", "X..XXX..", "...XXX..", "..X..X.."])
BOSS = mirror_even([
    ".......XXXXXXXXX", "....XXXXXXXXXXXX", "..XXXXXXXXXXXXXX", ".XXXXXXXXXXXXXXX",
    "XXXXX..XXXXXXXXX", "XXXX.XX.XXXXXXXX", "XXXXXXXXXXXXXXXX", "XXXXXXXXXX..XXXX",
    ".XXXXXXXXXXXXXXX", "..XX.XXXXXXX.XXX", "..X...XXXX....XX", ".X.....XX......X"])

ETYPES = {
    "grunt": dict(hp=1, score=100, shoot=0.0, rows=GRUNT, col=(255, 90, 90)),
    "weaver": dict(hp=2, score=200, shoot=0.0, rows=WEAVER, col=(255, 170, 60)),
    "gunner": dict(hp=3, score=300, shoot=1.6, rows=GUNNER, col=(190, 100, 255)),
    "tank": dict(hp=7, score=600, shoot=2.0, rows=TANK, col=(110, 200, 120)),
}
POWER_COL = {"P": (255, 170, 40), "S": (70, 160, 255), "L": (255, 90, 120)}


class StarStrikeScene(Scene):
    def __init__(self):
        self.ship = sprite_from_rows(SHIP, SHIP_COL)
        self.flash = {}
        self.spr = {k: sprite_from_rows(v["rows"], v["col"]) for k, v in ETYPES.items()}
        self.boss_spr = sprite_from_rows(BOSS, (230, 70, 110))
        self.boss_hit = sprite_from_rows(BOSS, (255, 255, 255))
        self.stars = Starfield(W, H)
        self.parts = Particles()
        self.t = 0.0
        self.paused = False
        self.new_game()

    # ------------------------------------------------------------------
    def new_game(self):
        self.score = 0
        self.lives = 3
        self.wave = 1
        self.weapon = 1
        self.hi = scores.top("starstrike")[0]["score"]
        self.px, self.py = W / 2.0, H - 30.0
        self.dead_t = 0.0
        self.invuln = 2.0
        self.shield = 0.0
        self.cool = 0.0
        self.state = "play"          # play | gameover
        self.timer = 0.0
        self.banner = 1.8
        self.start_wave()

    def start_wave(self):
        self.enemies, self.ebullets, self.pbullets, self.items = [], [], [], []
        self.boss = None
        self.queue = []
        self.clear_t = 0.0
        self.wave_t = 0.0
        n = self.wave
        if n % 5 == 0:
            hp = 40 + n * 6
            self.boss = dict(x=W / 2.0, y=-30.0, hp=hp, max=hp, t=0.0, state="enter",
                             cool=1.5, pat=0, pat_t=0.0, burst=0, hit=0.0)
            return
        pool = ["grunt"] + (["weaver"] if n >= 2 else []) + (["gunner"] if n >= 3 else []) \
            + (["tank"] if n >= 5 else [])
        t = 0.5
        for _ in range(2 + min(3, n // 2)):
            et = random.choice(pool)
            kind = "hover" if et == "tank" else random.choice(["dive", "sweep", "hover"])
            count = random.randint(4, 7) if et in ("grunt", "weaver") else random.randint(2, 4)
            x0 = random.uniform(50, W - 50)
            side = random.choice((-1, 1))
            amp = random.uniform(15, 45)
            for i in range(count):
                self.queue.append([t + i * 0.5, et, kind, x0, side, amp, i])
            t += count * 0.5 + 2.0
        self.queue.sort(key=lambda q: q[0])

    def snd(self, n):
        self.app.sound.play(n)

    def spawn(self, et, kind, x0, side, amp, i):
        spec = ETYPES[et]
        sw, sh = self.spr[et].get_size()
        e = dict(type=et, kind=kind, hp=spec["hp"] + self.wave // 6, t=0.0,
                 shoot=random.uniform(0.6, 1.6), x=x0, y=-12.0, x0=x0, amp=amp,
                 side=side, state=0, hold=0.0, w=sw, h=sh, hit=0.0)
        if kind == "sweep":
            e["x"] = -12.0 if side > 0 else W + 12.0
            e["y"] = random.uniform(20, 70)
        elif kind == "hover":
            e["x"] = e["tx"] = clamp(x0 + (i - 2) * 22, 20, W - 20)
            e["ty"] = 26 + 14 * (i % 3)
        self.enemies.append(e)

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
        self.stars.update(dt, 1.0 + (0.5 if self.boss else 0.0))
        self.parts.update(dt)
        self.banner = max(0.0, self.banner - dt)

        if self.state == "gameover":
            self.timer -= dt
            if self.timer <= 0 or (self.timer < 2.4 and ({"start", "fire"} & p)):
                self.app.finish_game("starstrike", self.score)
            return

        self.update_player(dt, inp)
        self.update_waves(dt)
        self.update_enemies(dt)
        self.update_boss(dt)
        self.update_bullets(dt)
        self.update_items(dt)

        if (not self.queue and not self.enemies and not self.boss
                and self.state == "play"):
            self.clear_t += dt
            if self.clear_t > 2.0:
                self.wave += 1
                self.banner = 1.8
                self.snd("jingle")
                self.start_wave()

    def update_player(self, dt, inp):
        if self.dead_t > 0:
            self.dead_t -= dt
            if self.dead_t <= 0:
                if self.lives <= 0:
                    self.state = "gameover"
                    self.timer = 3.5
                    self.snd("gameover")
                else:
                    self.px, self.py = W / 2.0, H - 30.0
                    self.invuln = 2.5
            return
        self.invuln = max(0.0, self.invuln - dt)
        self.shield = max(0.0, self.shield - dt)
        dx = int(inp.held("right")) - int(inp.held("left"))
        dy = int(inp.held("down")) - int(inp.held("up"))
        norm = 0.707 if dx and dy else 1.0
        self.px = clamp(self.px + dx * 115 * dt * norm, 8, W - 8)
        self.py = clamp(self.py + dy * 100 * dt * norm, 78, H - 12)
        self.cool -= dt
        if inp.held("fire") and self.cool <= 0:
            self.fire()

    def fire(self):
        lv = self.weapon
        self.cool = max(0.09, 0.22 - 0.025 * lv)
        x, y = self.px, self.py - 7
        shots = [(0, 0, -250)]
        if lv == 2:
            shots = [(-3, 0, -250), (3, 0, -250)]
        elif lv == 3:
            shots = [(0, 0, -260), (-4, -30, -245), (4, 30, -245)]
        elif lv >= 4:
            shots = [(0, 0, -270), (-3, -22, -260), (3, 22, -260),
                     (-6, -50, -235), (6, 50, -235)]
        for ox, vx, vy in shots:
            self.pbullets.append([x + ox, y, vx, vy])
        self.snd("shoot")

    def update_waves(self, dt):
        if self.boss:
            return
        self.wave_t += dt
        while self.queue and self.queue[0][0] <= self.wave_t:
            q = self.queue.pop(0)
            self.spawn(*q[1:])

    def update_enemies(self, dt):
        for e in self.enemies[:]:
            e["t"] += dt
            e["hit"] = max(0.0, e["hit"] - dt)
            k = e["kind"]
            if k == "dive":
                e["y"] += (42 + self.wave * 3) * dt
                e["x"] = e["x0"] + e["amp"] * math.sin(e["t"] * 2.2)
            elif k == "sweep":
                e["x"] += e["side"] * (65 + self.wave * 2) * dt
                e["y"] += (14 + math.sin(e["t"] * 3) * 20) * dt
            else:
                if e["state"] == 0:
                    e["y"] += 70 * dt
                    if e["y"] >= e["ty"]:
                        e["state"] = 1
                        e["hold"] = random.uniform(5, 8)
                elif e["state"] == 1:
                    e["hold"] -= dt
                    e["x"] = e["tx"] + 22 * math.sin(e["t"] * 1.1)
                    if e["hold"] <= 0:
                        e["state"] = 2
                else:
                    e["y"] += 90 * dt
            spec = ETYPES[e["type"]]
            if spec["shoot"] > 0 and 8 < e["y"] < H - 50 and self.dead_t <= 0:
                e["shoot"] -= dt
                if e["shoot"] <= 0:
                    e["shoot"] = spec["shoot"] * random.uniform(0.7, 1.3) / (1 + 0.04 * self.wave)
                    self.enemy_fire(e)
            if e["y"] > H + 16 or e["x"] < -26 or e["x"] > W + 26:
                self.enemies.remove(e)

    def enemy_fire(self, e):
        a = math.atan2(self.py - e["y"], self.px - e["x"])
        angles = [a] if e["type"] != "tank" else [a - 0.3, a, a + 0.3]
        sp = 68 + self.wave * 2
        for ang in angles:
            self.ebullets.append([e["x"], e["y"] + 4, sp * math.cos(ang), sp * math.sin(ang)])
        self.snd("enemy_shoot")

    def update_boss(self, dt):
        b = self.boss
        if not b:
            return
        b["t"] += dt
        b["hit"] = max(0.0, b["hit"] - dt)
        if b["state"] == "enter":
            b["y"] += 40 * dt
            if b["y"] >= 34:
                b["state"] = "fight"
            return
        rage = 1.0 + (1.0 - b["hp"] / float(b["max"])) * 0.8
        b["x"] = W / 2.0 + 105 * math.sin(b["t"] * 0.7 * rage)
        b["pat_t"] += dt
        if b["pat_t"] > 4.0:
            b["pat_t"] = 0.0
            b["pat"] = (b["pat"] + 1) % 3
        b["cool"] -= dt
        if self.dead_t > 0 or b["cool"] > 0:
            return
        sp = 80 + self.wave * 2
        if b["pat"] == 0:                       # fan
            b["cool"] = 1.1 / rage
            for i in range(-3, 4):
                ang = math.pi / 2 + i * 0.22
                self.ebullets.append([b["x"], b["y"] + 10, sp * math.cos(ang), sp * math.sin(ang)])
        elif b["pat"] == 1:                     # aimed bursts
            b["cool"] = 0.18 / rage if b["burst"] < 3 else 1.3 / rage
            b["burst"] = (b["burst"] + 1) % 4
            a = math.atan2(self.py - b["y"], self.px - b["x"])
            self.ebullets.append([b["x"], b["y"] + 10, sp * 1.3 * math.cos(a), sp * 1.3 * math.sin(a)])
        else:                                   # rain
            b["cool"] = 0.22 / rage
            self.ebullets.append([b["x"] + random.uniform(-40, 40), b["y"] + 10,
                                  random.uniform(-10, 10), sp * 0.9])
        self.snd("enemy_shoot")

    def kill_player(self):
        self.lives -= 1
        self.dead_t = 1.4
        self.weapon = max(1, self.weapon - 1)
        self.parts.burst(self.px, self.py, (255, 255, 255), 22, 80)
        self.parts.burst(self.px, self.py, (255, 150, 40), 16, 55)
        self.ebullets = []
        self.snd("explode")

    def drop(self, x, y, chance):
        if random.random() < chance:
            kind = random.choices(["P", "S", "L"], weights=[60, 32, 8])[0]
            self.items.append([x, y, kind])

    def update_bullets(self, dt):
        for b in self.pbullets[:]:
            b[0] += b[2] * dt
            b[1] += b[3] * dt
            if b[1] < -6 or b[0] < -6 or b[0] > W + 6:
                self.pbullets.remove(b)
                continue
            br = pygame.Rect(int(b[0]) - 1, int(b[1]) - 3, 3, 6)
            hit = False
            for e in self.enemies[:]:
                if br.colliderect(pygame.Rect(int(e["x"] - e["w"] / 2), int(e["y"] - e["h"] / 2),
                                              e["w"], e["h"])):
                    e["hp"] -= 1
                    e["hit"] = 0.08
                    hit = True
                    if e["hp"] <= 0:
                        spec = ETYPES[e["type"]]
                        self.enemies.remove(e)
                        self.score += spec["score"]
                        self.parts.burst(e["x"], e["y"], spec["col"], 12, 55)
                        self.parts.burst(e["x"], e["y"], (255, 240, 200), 5, 35)
                        self.snd("boom")
                        self.drop(e["x"], e["y"], 0.08 + 0.05 * (e["type"] in ("gunner", "tank")))
                    break
            if not hit and self.boss and br.colliderect(
                    pygame.Rect(int(self.boss["x"]) - 16, int(self.boss["y"]) - 6, 32, 12)):
                self.boss["hp"] -= 1
                self.boss["hit"] = 0.06
                hit = True
                self.parts.add(b[0], b[1], random.uniform(-30, 30), random.uniform(-30, 0),
                               (255, 220, 120), 0.25, 1)
                if self.boss["hp"] <= 0:
                    self.kill_boss()
            if hit and b in self.pbullets:
                self.pbullets.remove(b)

        prect = pygame.Rect(int(self.px) - 2, int(self.py) - 2, 5, 5)
        body = pygame.Rect(int(self.px) - 5, int(self.py) - 5, 10, 10)
        can_hurt = self.dead_t <= 0 and self.invuln <= 0
        for b in self.ebullets[:]:
            b[0] += b[2] * dt
            b[1] += b[3] * dt
            if b[1] > H + 6 or b[1] < -8 or b[0] < -8 or b[0] > W + 8:
                self.ebullets.remove(b)
                continue
            if can_hurt and pygame.Rect(int(b[0]) - 1, int(b[1]) - 1, 3, 3).colliderect(prect):
                self.ebullets.remove(b)
                if self.shield > 0:
                    self.shield = 0.0
                    self.invuln = 0.6
                    self.snd("hurt")
                else:
                    self.kill_player()
                    can_hurt = False
        if can_hurt:
            for e in self.enemies[:]:
                if body.colliderect(pygame.Rect(int(e["x"] - e["w"] / 2), int(e["y"] - e["h"] / 2),
                                                e["w"], e["h"])):
                    self.enemies.remove(e)
                    self.parts.burst(e["x"], e["y"], ETYPES[e["type"]]["col"], 10, 50)
                    if self.shield > 0:
                        self.shield = 0.0
                        self.invuln = 0.6
                        self.snd("hurt")
                    else:
                        self.kill_player()
                    break

    def kill_boss(self):
        b = self.boss
        self.boss = None
        self.score += 3000 + self.wave * 400
        for _ in range(4):
            self.parts.burst(b["x"] + random.uniform(-14, 14), b["y"] + random.uniform(-6, 6),
                             random.choice([(255, 240, 200), (255, 150, 40), (230, 70, 110)]),
                             16, 90, (0.4, 1.0))
        self.ebullets = []
        self.snd("explode")
        self.items.append([b["x"] - 12, b["y"], "P"])
        self.items.append([b["x"] + 12, b["y"], "S"])

    def update_items(self, dt):
        body = pygame.Rect(int(self.px) - 7, int(self.py) - 7, 14, 14)
        for it in self.items[:]:
            it[1] += 32 * dt
            if it[1] > H + 8:
                self.items.remove(it)
            elif self.dead_t <= 0 and body.colliderect(pygame.Rect(int(it[0]) - 5, int(it[1]) - 5, 10, 10)):
                self.items.remove(it)
                self.snd("pickup")
                if it[2] == "P":
                    if self.weapon >= 4:
                        self.score += 500
                    self.weapon = min(4, self.weapon + 1)
                elif it[2] == "S":
                    self.shield = 8.0
                else:
                    self.lives = min(6, self.lives + 1)

    # ------------------------------------------------------------------
    def draw(self, low):
        f = self.app.fonts
        low.fill((4, 3, 16))
        self.stars.draw(low)

        for x, y, kind in self.items:
            low.fill(POWER_COL[kind], (int(x) - 5, int(y) - 5, 10, 10))
            low.fill((255, 255, 255), (int(x) - 5, int(y) - 5, 10, 1))
            text(low, kind, (int(x), int(y) - 5), f.small, (20, 10, 40), "midtop", shadow=None)

        for e in self.enemies:
            img = self.spr[e["type"]]
            if e["hit"] > 0:
                img = self.hit_version(e["type"], img)
            low.blit(img, (int(e["x"] - e["w"] / 2), int(e["y"] - e["h"] / 2)))
        if self.boss:
            b = self.boss
            img = self.boss_hit if b["hit"] > 0 else self.boss_spr
            low.blit(img, (int(b["x"] - img.get_width() / 2), int(b["y"] - img.get_height() / 2)))
            frac = b["hp"] / float(b["max"])
            low.fill((70, 20, 40), (60, 16, 200, 4))
            low.fill((255, 70, 110), (60, 16, int(200 * frac), 4))

        for x, y, vx, vy in self.pbullets:
            low.fill((255, 250, 180), (int(x) - 1, int(y) - 3, 2, 6))
        for x, y, vx, vy in self.ebullets:
            low.fill((255, 90, 120), (int(x) - 1, int(y) - 1, 3, 3))
            low.fill((255, 220, 230), (int(x), int(y), 1, 1))

        if self.dead_t <= 0 and (self.invuln <= 0 or int(self.t * 16) % 2 == 0):
            low.blit(self.ship, (int(self.px - self.ship.get_width() / 2),
                                 int(self.py - self.ship.get_height() / 2)))
            if int(self.t * 20) % 2:
                low.fill((255, 200, 80), (int(self.px) - 1, int(self.py) + 6, 2, 3))
            if self.shield > 0 and (self.shield > 2 or int(self.t * 10) % 2):
                pygame.draw.circle(low, (110, 190, 255), (int(self.px), int(self.py)), 11, 1)
        self.parts.draw(low)

        text(low, "SCORE %06d" % self.score, (6, 2), f.small)
        text(low, "HI %06d" % max(self.hi, self.score), (W // 2, 2), f.small,
             (255, 220, 80), "midtop")
        text(low, "WAVE %d" % self.wave, (W - 6, 2), f.small, (130, 255, 150), "topright")
        for i in range(max(0, self.lives)):
            low.blit(self.ship, (6 + i * 15, H - 14))
        text(low, "WEAPON %d" % self.weapon, (W - 6, H - 12), f.small, (255, 190, 90), "topright")

        draw_hint(low, f, ["ARROWS: MOVE    HOLD SPACE: FIRE", "COLLECT P S L POWER-UPS"],
                  self.t, y=108)
        if self.banner > 0 and self.state == "play":
            label = "BOSS WAVE" if self.wave % 5 == 0 else "WAVE %d" % self.wave
            text(low, label, (W // 2, 70), f.med, (255, 255, 255), "midtop")
        if self.state == "gameover":
            text(low, "GAME OVER", (W // 2, 70), f.big, (255, 70, 70), "midtop")
        if self.paused:
            text(low, "PAUSED", (W // 2, 70), f.big, (255, 255, 255), "midtop")

    def hit_version(self, key, img):
        v = self.flash.get(key)
        if v is None:
            v = img.copy()
            v.fill((120, 120, 120), special_flags=pygame.BLEND_RGB_ADD)
            self.flash[key] = v
        return v
