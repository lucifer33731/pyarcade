"""PONG for the retro arcade.

Player 1: W / S (and the arrow keys in 1-player mode).
Player 2: Up / Down arrows. First to 7 wins. P pauses, Esc = menu.
"""
import math
import random

import pygame

from engine import Scene, W, H, clamp, text
from toolkit import draw_hint

COURT_T, COURT_B = 22, H - 6
MID_Y = (COURT_T + COURT_B) / 2.0
PW, PH = 4, 28
WIN = 7


class PongScene(Scene):
    def __init__(self):
        self.t = 0.0
        self.mode = "menu"          # menu | serve | play | over
        self.sel = 0
        self.two = False
        self.paused = False
        self.reset_match()

    def reset_match(self):
        self.s1 = self.s2 = 0
        self.p1y = self.p2y = MID_Y
        self.ai_off = 0.0
        self.serve_dir = random.choice((-1, 1))
        self.over_t = 0.0
        self.ball_reset()

    def ball_reset(self):
        self.bx, self.by = W / 2.0, MID_Y
        self.speed = 125.0
        self.bvx = self.bvy = 0.0
        self.timer = 1.0
        self.trail = []

    def snd(self, name):
        self.app.sound.play(name)

    # ------------------------------------------------------------------
    def update(self, dt, inp):
        self.t += dt
        p, k = inp.pressed, inp.keys
        if "back" in p:
            self.app.go_menu()
            return

        if self.mode == "menu":
            if "up" in p or "down" in p:
                self.sel ^= 1
                self.snd("select")
            if "start" in p or "fire" in p:
                self.two = self.sel == 1
                self.reset_match()
                self.mode = "serve"
                self.t = 0.0
                self.snd("start")
            return

        if "pause" in p and self.mode == "play":
            self.paused = not self.paused
        if self.paused:
            return

        if self.mode == "over":
            self.over_t += dt
            if self.over_t > 0.6 and ("start" in p or "fire" in p):
                if self.two:
                    self.app.go_menu()
                else:
                    won = self.s1 > self.s2
                    score = max(0, self.s1 * 100 - self.s2 * 30) + (500 if won else 0)
                    self.app.finish_game("pong", score)
            return

        # paddles
        up1 = k[pygame.K_w] or (not self.two and k[pygame.K_UP])
        dn1 = k[pygame.K_s] or (not self.two and k[pygame.K_DOWN])
        self.p1y += (int(bool(dn1)) - int(bool(up1))) * 150 * dt
        if self.two:
            self.p2y += (int(bool(k[pygame.K_DOWN])) - int(bool(k[pygame.K_UP]))) * 150 * dt
        else:
            target = self.by + self.ai_off if self.bvx > 0 else MID_Y
            diff = target - self.p2y
            step = (100 + 4 * self.s1) * dt
            if abs(diff) > 3:
                self.p2y += clamp(diff, -step, step)
        lo, hi = COURT_T + PH / 2.0, COURT_B - PH / 2.0
        self.p1y = clamp(self.p1y, lo, hi)
        self.p2y = clamp(self.p2y, lo, hi)

        if self.mode == "serve":
            self.timer -= dt
            if self.timer <= 0:
                ang = random.uniform(-0.45, 0.45)
                self.bvx = self.serve_dir * self.speed * math.cos(ang)
                self.bvy = self.speed * math.sin(ang)
                self.mode = "play"
            return

        # ball
        self.trail.append((self.bx, self.by))
        self.trail = self.trail[-5:]
        self.bx += self.bvx * dt
        self.by += self.bvy * dt
        if self.by < COURT_T:
            self.by = COURT_T
            self.bvy = abs(self.bvy)
            self.snd("blip2")
        elif self.by > COURT_B - 4:
            self.by = COURT_B - 4
            self.bvy = -abs(self.bvy)
            self.snd("blip2")

        brect = pygame.Rect(int(self.bx), int(self.by), 4, 4)
        r1 = pygame.Rect(10, int(self.p1y - PH / 2), PW, PH)
        r2 = pygame.Rect(W - 14, int(self.p2y - PH / 2), PW, PH)
        if self.bvx < 0 and brect.colliderect(r1):
            self.paddle_hit(self.p1y, 1)
            self.bx = 10 + PW
        elif self.bvx > 0 and brect.colliderect(r2):
            self.paddle_hit(self.p2y, -1)
            self.bx = W - 14 - 4

        if self.bx < -6:
            self.point(2)
        elif self.bx > W + 2:
            self.point(1)

    def paddle_hit(self, py, direction):
        off = clamp((self.by + 2 - py) / (PH / 2.0), -1.0, 1.0)
        self.speed = min(self.speed * 1.07, 270.0)
        ang = off * math.radians(55)
        self.bvx = direction * self.speed * math.cos(ang)
        self.bvy = self.speed * math.sin(ang)
        self.ai_off = random.uniform(-9, 9)
        self.snd("blip")

    def point(self, who):
        if who == 1:
            self.s1 += 1
        else:
            self.s2 += 1
        if max(self.s1, self.s2) >= WIN:
            self.mode = "over"
            self.over_t = 0.0
            self.snd("jingle" if (self.two or self.s1 > self.s2) else "gameover")
            return
        self.snd("boom")
        self.serve_dir = 1 if who == 2 else -1
        self.ball_reset()
        self.mode = "serve"

    # ------------------------------------------------------------------
    def draw(self, low):
        f = self.app.fonts
        low.fill((8, 6, 26))
        if self.mode == "menu":
            text(low, "PONG", (W // 2, 24), f.big, (255, 255, 255), "midtop")
            for i, label in enumerate(("1 PLAYER", "2 PLAYERS")):
                col = (255, 220, 80) if i == self.sel else (150, 140, 190)
                text(low, ("> " if i == self.sel else "  ") + label, (W // 2 - 36, 84 + i * 18),
                     f.med, col)
            text(low, "P1: W / S      P2: UP / DOWN", (W // 2, 140), f.small,
                 (200, 190, 240), "midtop")
            text(low, "FIRST TO %d WINS" % WIN, (W // 2, 152), f.small, (200, 190, 240), "midtop")
            return

        low.fill((40, 36, 90), (0, COURT_T - 3, W, 2))
        low.fill((40, 36, 90), (0, COURT_B + 2, W, 2))
        for y in range(COURT_T, COURT_B, 10):
            low.fill((60, 56, 120), (W // 2 - 1, y, 2, 5))

        text(low, str(self.s1), (W // 2 - 40, 2), f.big, (120, 220, 255), "midtop")
        text(low, str(self.s2), (W // 2 + 40, 2), f.big, (255, 130, 200), "midtop")
        text(low, "P1", (8, 4), f.small, (120, 220, 255))
        text(low, "P2" if self.two else "CPU", (W - 8, 4), f.small, (255, 130, 200), "topright")

        low.fill((120, 220, 255), (10, int(self.p1y - PH / 2), PW, PH))
        low.fill((255, 130, 200), (W - 14, int(self.p2y - PH / 2), PW, PH))
        for i, (x, y) in enumerate(self.trail):
            b = 40 + i * 30
            low.fill((b, b, b), (int(x), int(y), 4, 4))
        if self.mode != "over":
            low.fill((255, 255, 255), (int(self.bx), int(self.by), 4, 4))

        if self.mode == "serve":
            draw_hint(low, f, ["GET READY"] if self.t > 3 else
                      ["MOVE: W / S   (P1)      UP / DOWN   (P2)"], self.t, y=120, show=3.0)
        if self.mode == "over":
            if self.two:
                msg = "PLAYER %d WINS!" % (1 if self.s1 > self.s2 else 2)
            else:
                msg = "YOU WIN!" if self.s1 > self.s2 else "CPU WINS"
            text(low, msg, (W // 2, 70), f.big, (255, 220, 80), "midtop")
            text(low, "PRESS ENTER", (W // 2, 112), f.small, (255, 255, 255), "midtop")
        if self.paused:
            text(low, "PAUSED", (W // 2, 70), f.big, (255, 255, 255), "midtop")
