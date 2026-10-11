"""SNAKE for the retro arcade.

Arrow keys / WASD steer. Eat apples to grow, grab the flashing star for a
bonus. Walls, rocks and your own tail are deadly. P pauses, Esc = menu.
"""
import random

import scores
from engine import Scene, W, H, text
from toolkit import Particles, draw_hint
import pygame

CELL = 8
GW, GH = 40, 20
OY = 18                       # field top (HUD above)
DIRS = {"left": (-1, 0), "right": (1, 0), "up": (0, -1), "down": (0, 1)}


class SnakeScene(Scene):
    def __init__(self):
        self.bg = pygame.Surface((W, H))
        self.bg.fill((8, 10, 22))
        for y in range(GH):
            for x in range(GW):
                c = (14, 24, 38) if (x + y) % 2 else (11, 19, 32)
                self.bg.fill(c, (x * CELL, OY + y * CELL, CELL, CELL))
        self.bg.fill((100, 100, 170), (0, OY - 2, W, 2))
        self.bg.fill((100, 100, 170), (0, OY + GH * CELL, W, 2))
        self.parts = Particles()
        self.paused = False
        self.t = 0.0
        self.new_game()

    def new_game(self):
        self.score = 0
        self.hi = scores.top("snake")[0]["score"]
        self.body = [(GW // 2, GH // 2), (GW // 2 - 1, GH // 2), (GW // 2 - 2, GH // 2)]
        self.dir = (1, 0)
        self.queue = []
        self.acc = 0.0
        self.interval = 0.13
        self.foods = 0
        self.rocks = set()
        self.bonus = None            # [x, y, time_left]
        self.state = "play"          # play | dead
        self.timer = 0.0
        self.food = self.free_cell()

    def free_cell(self):
        taken = set(self.body) | self.rocks
        if self.bonus:
            taken.add((self.bonus[0], self.bonus[1]))
        while True:
            c = (random.randrange(GW), random.randrange(GH))
            if c not in taken:
                return c

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

        if self.state == "dead":
            self.timer -= dt
            if self.timer <= 0 or (self.timer < 1.6 and ({"start", "fire"} & p)):
                self.app.finish_game("snake", self.score)
            return

        for name, d in DIRS.items():
            if name in p and len(self.queue) < 2:
                last = self.queue[-1] if self.queue else self.dir
                if (d[0] != -last[0] or d[1] != -last[1]) and d != last:
                    self.queue.append(d)

        if self.bonus:
            self.bonus[2] -= dt
            if self.bonus[2] <= 0:
                self.bonus = None

        self.acc += dt
        while self.acc >= self.interval and self.state == "play":
            self.acc -= self.interval
            self.step()

    def step(self):
        if self.queue:
            self.dir = self.queue.pop(0)
        hx, hy = self.body[0]
        nx, ny = hx + self.dir[0], hy + self.dir[1]
        new = (nx, ny)
        eating = new == self.food
        tail_free = self.body[:-1] if not eating else self.body
        if not (0 <= nx < GW and 0 <= ny < GH) or new in self.rocks or new in tail_free:
            self.die()
            return
        self.body.insert(0, new)
        if eating:
            self.score += 10
            self.foods += 1
            self.interval = max(0.06, self.interval - 0.003)
            self.snd("eat")
            if self.foods % 6 == 0:
                self.rocks.add(self.free_cell())
            if self.foods % 5 == 0 and not self.bonus:
                c = self.free_cell()
                self.bonus = [c[0], c[1], 8.0]
            self.food = self.free_cell()
        else:
            self.body.pop()
        if self.bonus and new == (self.bonus[0], self.bonus[1]):
            self.score += 50
            self.snd("pickup")
            self.parts.burst(nx * CELL + 4, OY + ny * CELL + 4, (255, 230, 90), 14, 50)
            self.bonus = None

    def die(self):
        self.state = "dead"
        self.timer = 2.6
        hx, hy = self.body[0]
        self.parts.burst(hx * CELL + 4, OY + hy * CELL + 4, (255, 255, 255), 24, 70)
        self.parts.burst(hx * CELL + 4, OY + hy * CELL + 4, (255, 120, 40), 16, 50)
        self.snd("explode")

    # ------------------------------------------------------------------
    def draw(self, low):
        f = self.app.fonts
        low.blit(self.bg, (0, 0))

        for rx, ry in self.rocks:
            low.fill((120, 120, 140), (rx * CELL + 1, OY + ry * CELL + 1, 6, 6))
            low.fill((170, 170, 190), (rx * CELL + 1, OY + ry * CELL + 1, 3, 2))
        fx, fy = self.food
        low.fill((230, 50, 60), (fx * CELL + 1, OY + fy * CELL + 2, 6, 5))
        low.fill((255, 140, 140), (fx * CELL + 2, OY + fy * CELL + 3, 2, 1))
        low.fill((90, 200, 80), (fx * CELL + 4, OY + fy * CELL, 2, 2))
        if self.bonus:
            bx, by, left = self.bonus
            if left > 2 or int(self.t * 10) % 2:
                low.fill((255, 230, 90), (bx * CELL + 3, OY + by * CELL, 2, 8))
                low.fill((255, 230, 90), (bx * CELL, OY + by * CELL + 3, 8, 2))
                low.fill((255, 255, 200), (bx * CELL + 2, OY + by * CELL + 2, 4, 4))

        n = len(self.body)
        for i, (x, y) in enumerate(self.body):
            k = i / float(max(1, n - 1))
            col = (int(120 - 80 * k), int(255 - 105 * k), int(140 - 60 * k))
            if self.state == "dead" and int(self.t * 10) % 2:
                col = (255, 255, 255)
            low.fill(col, (x * CELL + 1, OY + y * CELL + 1, 6, 6))
            if i == 0:
                ex, ey = self.dir
                low.fill((10, 10, 20), (x * CELL + 2 + (1 if ex > 0 else 0) * 2,
                                        OY + y * CELL + 2 + (1 if ey > 0 else 0) * 2, 1, 1))
                low.fill((10, 10, 20), (x * CELL + 5 - (1 if ex < 0 else 0) * 2,
                                        OY + y * CELL + 5 - (1 if ey < 0 else 0) * 2, 1, 1))
        self.parts.draw(low)

        text(low, "SCORE %05d" % self.score, (6, 2), f.small)
        text(low, "HI %05d" % max(self.hi, self.score), (W // 2, 2), f.small,
             (255, 220, 80), "midtop")
        text(low, "LENGTH %d" % len(self.body), (W - 6, 2), f.small, (130, 255, 150), "topright")
        draw_hint(low, f, ["ARROWS / WASD TO STEER", "GRAB THE FLASHING STAR FOR BONUS"],
                  self.t, y=OY + 60)
        if self.state == "dead":
            text(low, "GAME OVER", (W // 2, 70), f.big, (255, 70, 70), "midtop")
        if self.paused:
            text(low, "PAUSED", (W // 2, 70), f.big, (255, 255, 255), "midtop")
