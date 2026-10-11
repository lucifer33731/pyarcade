"""BREAKOUT for the retro arcade.

Left/Right (A/D) move the paddle, Space launches the ball. Catch the falling
capsules: W = wide paddle, M = multi-ball, S = slow ball, L = extra life.
P pauses, Esc = menu.
"""
import math
import random

import pygame

import scores
from engine import Scene, W, H, clamp, text
from toolkit import Particles, draw_hint

COLS, ROWS = 12, 6
BW, BH = 24, 8
BX0, BY0 = 16, 30
PADDLE_Y = 164
ROW_COLORS = [(230, 60, 60), (240, 150, 50), (240, 220, 60),
              (80, 210, 90), (60, 170, 240), (160, 90, 230)]
POWER_COLORS = {"W": (80, 220, 100), "M": (80, 160, 255), "S": (255, 160, 50),
                "L": (255, 80, 110)}


def layout(level):
    """Return a list of (col, row, hp) for the given level number."""
    pat = level % 5
    out = []
    for r in range(ROWS):
        for c in range(COLS):
            if pat == 1:
                keep = (r <= c < COLS - r) if r < 3 else True
            elif pat == 2:
                keep = c % 2 == 0 or r % 2 == 0
            elif pat == 3:
                keep = (c + r) % 2 == 0
            elif pat == 4:
                keep = not (4 <= c <= 7 and 1 <= r <= 3)
            else:
                keep = True
            if not keep:
                continue
            hp = 1
            if level >= 2 and r == 0:
                hp = 2
            if level >= 5 and r <= 1:
                hp = 2
            out.append((c, r, hp))
    return out


class BreakoutScene(Scene):
    def __init__(self):
        self.parts = Particles()
        self.t = 0.0
        self.paused = False
        self.new_game()

    def new_game(self):
        self.score = 0
        self.lives = 3
        self.level = 0
        self.hi = scores.top("breakout")[0]["score"]
        self.state = "play"
        self.timer = 0.0
        self.start_level()

    def start_level(self):
        self.bricks = []
        for c, r, hp in layout(self.level):
            self.bricks.append({"rect": pygame.Rect(BX0 + c * BW, BY0 + r * BH, BW - 1, BH - 1),
                                "row": r, "hp": hp})
        self.items = []
        self.wide_t = 0.0
        self.slow_t = 0.0
        self.px = W / 2.0
        self.balls = []
        self.stuck = True
        self.hits = 0
        self.banner = 1.4

    def paddle_w(self):
        return 56 if self.wide_t > 0 else 36

    def base_speed(self):
        s = 125 + self.level * 8 + min(self.hits, 40) * 1.5
        return min(s, 235) * (0.7 if self.slow_t > 0 else 1.0)

    def snd(self, n):
        self.app.sound.play(n)

    # ------------------------------------------------------------------
    def update(self, dt, inp):
        self.t += dt
        p = inp.pressed
        if "back" in p:
            self.app.go_menu()
            return
        if "pause" in p and self.state == "play":
            self.paused = not self.paused
        if self.paused:
            return
        self.parts.update(dt)
        self.banner = max(0.0, self.banner - dt)

        if self.state == "over":
            self.timer -= dt
            if self.timer <= 0 or (self.timer < 2.2 and ({"start", "fire"} & p)):
                self.app.finish_game("breakout", self.score)
            return

        mv = int(inp.held("right")) - int(inp.held("left"))
        pw = self.paddle_w()
        self.px = clamp(self.px + mv * 210 * dt, pw / 2.0 + 2, W - pw / 2.0 - 2)
        self.wide_t = max(0.0, self.wide_t - dt)
        self.slow_t = max(0.0, self.slow_t - dt)

        if self.stuck:
            if not self.balls:
                self.balls = [[self.px, PADDLE_Y - 4.0, 0.0, 0.0]]
            self.balls[0][0] = self.px
            self.balls[0][1] = PADDLE_Y - 4.0
            if "fire" in p or "start" in p:
                ang = math.radians(random.uniform(-25, 25))
                s = self.base_speed()
                self.balls[0][2] = s * math.sin(ang)
                self.balls[0][3] = -s * math.cos(ang)
                self.stuck = False
                self.snd("blip")
        else:
            self.update_balls(dt)

        self.update_items(dt)
        if not self.bricks and self.state == "play":
            self.level += 1
            self.score += 500
            self.snd("jingle")
            self.start_level()

    def update_balls(self, dt):
        pw = self.paddle_w()
        prect = pygame.Rect(int(self.px - pw / 2), PADDLE_Y, pw, 5)
        speed = self.base_speed()
        for b in self.balls[:]:
            # keep the ball at the intended speed (power-ups can change it)
            mag = math.hypot(b[2], b[3]) or 1.0
            b[2] *= speed / mag
            b[3] *= speed / mag
            b[0] += b[2] * dt
            b[1] += b[3] * dt
            if b[0] < 2:
                b[0], b[2] = 2, abs(b[2])
                self.snd("blip2")
            elif b[0] > W - 2:
                b[0], b[2] = W - 2, -abs(b[2])
                self.snd("blip2")
            if b[1] < 18:
                b[1], b[3] = 18, abs(b[3])
                self.snd("blip2")
            brect = pygame.Rect(int(b[0] - 2), int(b[1] - 2), 4, 4)
            if b[3] > 0 and brect.colliderect(prect):
                off = clamp((b[0] - self.px) / (pw / 2.0), -1.0, 1.0)
                ang = off * math.radians(60)
                b[2] = speed * math.sin(ang)
                b[3] = -speed * math.cos(ang)
                b[1] = PADDLE_Y - 3
                self.hits += 1
                self.snd("blip")
                continue
            for br in self.bricks:
                if brect.colliderect(br["rect"]):
                    r = br["rect"]
                    ox = min(brect.right, r.right) - max(brect.left, r.left)
                    oy = min(brect.bottom, r.bottom) - max(brect.top, r.top)
                    if ox < oy:
                        b[2] = -b[2]
                    else:
                        b[3] = -b[3]
                    self.hit_brick(br)
                    break
            if b[1] > H + 4:
                self.balls.remove(b)
        if not self.balls and self.state == "play":
            self.lives -= 1
            self.snd("hurt")
            if self.lives <= 0:
                self.state = "over"
                self.timer = 3.5
                self.snd("gameover")
            else:
                self.stuck = True
                self.items = []

    def hit_brick(self, br):
        br["hp"] -= 1
        r = br["rect"]
        if br["hp"] > 0:
            self.snd("blip2")
            return
        self.bricks.remove(br)
        self.score += (ROWS - br["row"]) * 10
        self.snd("boom")
        self.parts.burst(r.centerx, r.centery, ROW_COLORS[br["row"]], 6, 40)
        if random.random() < 0.18:
            self.items.append([r.centerx, r.centery, random.choice("WWMSL")])

    def update_items(self, dt):
        pw = self.paddle_w()
        prect = pygame.Rect(int(self.px - pw / 2), PADDLE_Y, pw, 5)
        for it in self.items[:]:
            it[1] += 55 * dt
            if pygame.Rect(int(it[0]) - 5, int(it[1]) - 3, 10, 6).colliderect(prect):
                self.items.remove(it)
                self.snd("pickup")
                kind = it[2]
                if kind == "W":
                    self.wide_t = 12.0
                elif kind == "S":
                    self.slow_t = 10.0
                elif kind == "L":
                    self.lives = min(5, self.lives + 1)
                elif kind == "M" and self.balls:
                    b = self.balls[0]
                    for a in (-0.5, 0.5):
                        mag = math.hypot(b[2], b[3]) or 120.0
                        ang = math.atan2(b[3], b[2]) + a
                        self.balls.append([b[0], b[1], mag * math.cos(ang), mag * math.sin(ang)])
                    self.stuck = False
            elif it[1] > H + 6:
                self.items.remove(it)

    # ------------------------------------------------------------------
    def draw(self, low):
        f = self.app.fonts
        low.fill((8, 6, 26))
        low.fill((60, 56, 120), (0, 16, W, 1))
        for br in self.bricks:
            r = br["rect"]
            col = ROW_COLORS[br["row"]]
            if br["hp"] > 1:
                col = (190, 195, 210)
            low.fill(col, r)
            low.fill(tuple(min(255, c + 60) for c in col), (r.x, r.y, r.w, 1))
            low.fill(tuple(c // 2 for c in col), (r.x, r.bottom - 1, r.w, 1))

        pw = self.paddle_w()
        low.fill((200, 210, 240), (int(self.px - pw / 2), PADDLE_Y, pw, 5))
        low.fill((90, 140, 255), (int(self.px - pw / 2), PADDLE_Y + 3, pw, 2))
        for b in self.balls:
            low.fill((255, 255, 255), (int(b[0] - 2), int(b[1] - 2), 4, 4))
        for x, y, kind in self.items:
            low.fill(POWER_COLORS[kind], (int(x) - 5, int(y) - 3, 10, 6))
            text(low, kind, (int(x), int(y) - 5), f.small, (255, 255, 255), "midtop", shadow=None)
        self.parts.draw(low)

        text(low, "SCORE %06d" % self.score, (6, 2), f.small)
        text(low, "HI %06d" % max(self.hi, self.score), (W // 2, 2), f.small,
             (255, 220, 80), "midtop")
        text(low, "LV %d   LIVES %d" % (self.level + 1, self.lives), (W - 6, 2), f.small,
             (130, 255, 150), "topright")
        if self.stuck and self.state == "play":
            draw_hint(low, f, ["SPACE: LAUNCH BALL", "CATCH CAPSULES: W M S L"],
                      self.t, y=118, show=8.0)
        if self.banner > 0 and self.state == "play":
            text(low, "LEVEL %d" % (self.level + 1), (W // 2, 100), f.med, (255, 255, 255), "midtop")
        if self.state == "over":
            text(low, "GAME OVER", (W // 2, 80), f.big, (255, 70, 70), "midtop")
        if self.paused:
            text(low, "PAUSED", (W // 2, 80), f.big, (255, 255, 255), "midtop")
