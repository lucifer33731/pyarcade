"""SPACE INVADERS for the retro arcade.

Left/Right (or A/D) move, Space (or Z) fires, P pauses, Esc returns to the menu.
"""
import math
import random

import pygame

import scores
from engine import Scene, W, H, clamp, sprite_from_rows, text

COLS, ROWS = 9, 5
CELL_W, CELL_H = 18, 14
AL_W, AL_H = 11, 8
PLAYER_Y = 150
BUNKER_Y = 122
GROUND_Y = 162
ROW_TYPE = [0, 1, 1, 2, 2]
ROW_POINTS = [30, 20, 20, 10, 10]

SQUID = [
    ["....XXX....", "..XXXXXXX..", ".XXXXXXXXX.", ".XX.XXX.XX.",
     ".XXXXXXXXX.", "...XX.XX...", "..XX...XX..", ".XX.....XX."],
    ["....XXX....", "..XXXXXXX..", ".XXXXXXXXX.", ".XX.XXX.XX.",
     ".XXXXXXXXX.", "..XX...XX..", ".XX.XXX.XX.", "..X.....X.."],
]
CRAB = [
    ["..X.....X..", "...X...X...", "..XXXXXXX..", ".XX.XXX.XX.",
     "XXXXXXXXXXX", "X.XXXXXXX.X", "X.X.....X.X", "...XX.XX..."],
    ["..X.....X..", "X..X...X..X", "X.XXXXXXX.X", "XXX.XXX.XXX",
     "XXXXXXXXXXX", ".XXXXXXXXX.", "..X.....X..", ".X.......X."],
]
OCTO = [
    ["...XXXXX...", ".XXXXXXXXX.", "XXXXXXXXXXX", "XXX..X..XXX",
     "XXXXXXXXXXX", "..XX...XX..", ".XX.XXX.XX.", "XX.......XX"],
    ["...XXXXX...", ".XXXXXXXXX.", "XXXXXXXXXXX", "XXX..X..XXX",
     "XXXXXXXXXXX", "...XX.XX...", "..XX.X.XX..", "...XX.XX..."],
]
PLAYER = ["......X......", ".....XXX.....", ".....XXX.....", ".XXXXXXXXXXX.",
          "XXXXXXXXXXXXX", "XXXXXXXXXXXXX", "XXXXXXXXXXXXX"]
UFO = [".....XXXXXX.....", "...XXXXXXXXXX...", "..XXXXXXXXXXXX..",
       ".XX.XX.XX.XX.XX.", "XXXXXXXXXXXXXXXX", "..XXX..XX..XXX..",
       "...X........X..."]
BUNKER = ["..XXXXXXX..", ".XXXXXXXXX.", "XXXXXXXXXXX", "XXXXXXXXXXX",
          "XXXXXXXXXXX", "XXX.....XXX", "XX.......XX"]
GREEN = (80, 230, 110)


class Bunker:
    """A destructible shield made of 2x2 pixel blocks."""

    def __init__(self, x, y):
        self.x, self.y = x, y
        self.blocks = {(gx, gy) for gy, row in enumerate(BUNKER)
                       for gx, ch in enumerate(row) if ch == "X"}

    def hit(self, px, py):
        gx, gy = int((px - self.x) // 2), int((py - self.y) // 2)
        if (gx, gy) not in self.blocks:
            return False
        self.blocks.discard((gx, gy))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if (dx or dy) and random.random() < 0.35:
                    self.blocks.discard((gx + dx, gy + dy))
        return True

    def erase_rect(self, r):
        for gx in range(int((r.left - self.x) // 2), int((r.right - self.x) // 2) + 1):
            for gy in range(int((r.top - self.y) // 2), int((r.bottom - self.y) // 2) + 1):
                self.blocks.discard((gx, gy))

    def draw(self, low):
        for gx, gy in self.blocks:
            low.fill(GREEN, (self.x + gx * 2, self.y + gy * 2, 2, 2))


class InvadersScene(Scene):
    def __init__(self):
        self.alien_spr = [
            [sprite_from_rows(f, c) for f in frames]
            for frames, c in ((SQUID, (255, 100, 210)), (CRAB, (100, 230, 255)),
                              (OCTO, (130, 255, 130)))]
        self.player_spr = sprite_from_rows(PLAYER, (235, 240, 255))
        self.ufo_spr = sprite_from_rows(UFO, (255, 70, 70))
        rng = random.Random(3)
        self.stars = [(rng.randint(0, W - 1), rng.randint(16, GROUND_Y - 2),
                       rng.randint(50, 130)) for _ in range(60)]
        self.paused = False
        self.t = 0.0
        self.new_game()

    # ---------------------------------------------------------------- setup
    def new_game(self):
        self.score = 0
        self.lives = 3
        self.wave = 1
        self.px = W / 2
        self.hi = scores.top("invaders")[0]["score"]
        self.particles, self.popups = [], []
        self.start_wave()

    def start_wave(self):
        self.alive = [[True] * COLS for _ in range(ROWS)]
        self.ox = 24.0
        self.oy = 30.0 + min(self.wave - 1, 5) * 6
        self.dir = 1
        self.frame = 0
        self.step_t = 0.0
        self.step_i = 0
        self.pbullets, self.abullets = [], []
        self.bunkers = [Bunker(int(W * (i + 0.5) / 4 - 11), BUNKER_Y) for i in range(4)]
        self.ufo = None
        self.ufo_t = random.uniform(12, 20)
        self.ufo_snd = 0.0
        self.fire_t = 1.2
        self.cool = 0.0
        self.dead_t = 0.0
        self.invuln = 0.0
        self.state = "ready"
        self.timer = 1.6

    # ------------------------------------------------------------- helpers
    def alien_rect(self, r, c):
        return pygame.Rect(int(self.ox + c * CELL_W), int(self.oy + r * CELL_H), AL_W, AL_H)

    def count_alive(self):
        return sum(sum(row) for row in self.alive)

    def burst(self, x, y, color, n=12, speed=55):
        for _ in range(n):
            a = random.uniform(0, 6.283)
            s = random.uniform(0.3, 1.0) * speed
            self.particles.append([x, y, s * math.cos(a), s * math.sin(a),
                                   random.uniform(0.3, 0.7), color])

    def shield_hit(self, x, y):
        for b in self.bunkers:
            if b.hit(x, y):
                return True
        return False

    def snd(self, name):
        self.app.sound.play(name)

    # -------------------------------------------------------------- update
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
        self.update_particles(dt)

        if self.state == "ready":
            self.timer -= dt
            if self.timer <= 0:
                self.state = "play"
        elif self.state == "play":
            self.update_play(dt, inp)
        elif self.state == "gameover":
            self.timer -= dt
            if self.timer <= 0 or ({"start", "fire"} & p and self.timer < 2.2):
                self.app.finish_game("invaders", self.score)

    def update_particles(self, dt):
        for q in self.particles:
            q[0] += q[2] * dt
            q[1] += q[3] * dt
            q[4] -= dt
        self.particles = [q for q in self.particles if q[4] > 0]
        for q in self.popups:
            q[1] -= 12 * dt
            q[3] -= dt
        self.popups = [q for q in self.popups if q[3] > 0]

    def update_play(self, dt, inp):
        self.update_player(dt, inp)
        self.update_aliens(dt)
        self.update_ufo(dt)
        self.update_bullets(dt)
        if self.state == "play" and self.count_alive() == 0:
            self.wave += 1
            self.snd("jingle")
            self.start_wave()

    def update_player(self, dt, inp):
        if self.dead_t > 0:
            self.dead_t -= dt
            if self.dead_t <= 0:
                if self.lives <= 0:
                    self.state = "gameover"
                    self.timer = 3.0
                    self.snd("gameover")
                else:
                    self.invuln = 2.0
            return
        self.invuln = max(0.0, self.invuln - dt)
        mv = int(inp.held("right")) - int(inp.held("left"))
        self.px = clamp(self.px + mv * 105 * dt, 9, W - 9)
        self.cool -= dt
        if inp.held("fire") and self.cool <= 0 and len(self.pbullets) < 3:
            self.pbullets.append([self.px, PLAYER_Y - 4.0])
            self.cool = 0.33
            self.snd("shoot")

    def update_aliens(self, dt):
        n = self.count_alive()
        interval = (0.02 + 0.5 * n / float(COLS * ROWS)) / (1 + 0.12 * (self.wave - 1))
        self.step_t += dt
        if self.step_t >= interval:
            self.step_t = 0.0
            self.frame ^= 1
            self.snd("step%d" % (self.step_i % 4))
            self.step_i += 1
            cols = [c for c in range(COLS) if any(self.alive[r][c] for r in range(ROWS))]
            minx = self.ox + min(cols) * CELL_W
            maxx = self.ox + max(cols) * CELL_W + AL_W
            nx = 3 * self.dir
            if (self.dir > 0 and maxx + nx > W - 4) or (self.dir < 0 and minx + nx < 4):
                self.oy += 6
                self.dir = -self.dir
            else:
                self.ox += nx

        # aliens that reach the shields chew through them / reaching the
        # player's row ends the game
        bottom = 0
        for r in range(ROWS):
            for c in range(COLS):
                if self.alive[r][c]:
                    rect = self.alien_rect(r, c)
                    bottom = max(bottom, rect.bottom)
                    if rect.bottom > BUNKER_Y:
                        for b in self.bunkers:
                            b.erase_rect(rect)
        if bottom >= PLAYER_Y and self.dead_t <= 0:
            self.lives = 0
            self.kill_player()

        # alien fire
        self.fire_t -= dt
        if self.fire_t <= 0 and len(self.abullets) < 3 + self.wave // 2:
            self.fire_t = random.uniform(0.5, 1.3) / (1 + 0.1 * (self.wave - 1))
            cols = [c for c in range(COLS) if any(self.alive[r][c] for r in range(ROWS))]
            if cols:
                c = random.choice(cols)
                r = max(rr for rr in range(ROWS) if self.alive[rr][c])
                rect = self.alien_rect(r, c)
                self.abullets.append([rect.centerx, rect.bottom, 0.0])
                self.snd("enemy_shoot")

    def update_ufo(self, dt):
        if self.ufo is None:
            self.ufo_t -= dt
            if self.ufo_t <= 0 and self.count_alive() > 6:
                d = random.choice((1, -1))
                self.ufo = {"x": -16.0 if d > 0 else float(W), "dir": d,
                            "pts": random.choice((50, 100, 150, 300))}
                self.ufo_t = random.uniform(15, 25)
        else:
            self.ufo["x"] += self.ufo["dir"] * 55 * dt
            self.ufo_snd -= dt
            if self.ufo_snd <= 0:
                self.ufo_snd = 0.22
                self.snd("ufo")
            if self.ufo["x"] < -20 or self.ufo["x"] > W + 4:
                self.ufo = None

    def kill_player(self):
        self.lives = max(0, self.lives - 1) if self.lives > 0 else 0
        self.dead_t = 1.4
        self.burst(self.px, PLAYER_Y + 3, (255, 255, 255), 24, 70)
        self.burst(self.px, PLAYER_Y + 3, (255, 140, 40), 16, 50)
        self.abullets = []
        self.snd("explode")

    def update_bullets(self, dt):
        # player bullets
        for b in self.pbullets[:]:
            b[1] -= 230 * dt
            if b[1] < 16 or self.shield_hit(b[0], b[1]) or self.shield_hit(b[0], b[1] + 3):
                self.pbullets.remove(b)
                continue
            brect = pygame.Rect(int(b[0]), int(b[1]), 1, 4)
            if self.ufo and brect.colliderect(pygame.Rect(int(self.ufo["x"]), 17, 16, 7)):
                pts = self.ufo["pts"]
                self.score += pts
                self.popups.append([self.ufo["x"] + 4, 18.0, str(pts), 1.0])
                self.burst(self.ufo["x"] + 8, 20, (255, 70, 70), 18, 60)
                self.snd("explode")
                self.ufo = None
                self.pbullets.remove(b)
                continue
            hit = False
            for r in range(ROWS):
                for c in range(COLS):
                    if self.alive[r][c] and brect.colliderect(self.alien_rect(r, c)):
                        self.alive[r][c] = False
                        self.score += ROW_POINTS[r]
                        rect = self.alien_rect(r, c)
                        color = ((255, 100, 210), (100, 230, 255), (130, 255, 130))[ROW_TYPE[r]]
                        self.burst(rect.centerx, rect.centery, color, 10, 45)
                        self.snd("boom")
                        hit = True
                        break
                if hit:
                    break
            if hit:
                self.pbullets.remove(b)

        # alien bullets
        prect = pygame.Rect(int(self.px - 6), PLAYER_Y, 13, 7)
        for b in self.abullets[:]:
            b[1] += (75 + self.wave * 6) * dt
            b[2] += dt
            if b[1] >= GROUND_Y:
                self.burst(b[0], GROUND_Y, (255, 200, 90), 4, 25)
                self.abullets.remove(b)
                continue
            if self.shield_hit(b[0], b[1] + 4) or self.shield_hit(b[0], b[1] + 6):
                self.abullets.remove(b)
                continue
            if (self.dead_t <= 0 and self.invuln <= 0
                    and pygame.Rect(int(b[0]) - 1, int(b[1]), 3, 5).colliderect(prect)):
                self.abullets.remove(b)
                self.kill_player()
                break

    # ---------------------------------------------------------------- draw
    def draw(self, low):
        f = self.app.fonts
        low.fill((6, 4, 20))
        for x, y, b in self.stars:
            low.fill((b, b, min(255, b + 30)), (x, y, 1, 1))

        for r in range(ROWS):
            for c in range(COLS):
                if self.alive[r][c]:
                    rect = self.alien_rect(r, c)
                    low.blit(self.alien_spr[ROW_TYPE[r]][self.frame], rect.topleft)
        for b in self.bunkers:
            b.draw(low)

        for x, y in self.pbullets:
            low.fill((255, 255, 255), (int(x), int(y), 1, 4))
        for x, y, tm in self.abullets:
            off = 1 if int(tm * 10) % 2 else -1
            low.fill((255, 220, 90), (int(x) + off, int(y), 1, 2))
            low.fill((255, 220, 90), (int(x) - off, int(y) + 2, 1, 2))

        if self.dead_t <= 0 and (self.invuln <= 0 or int(self.t * 16) % 2 == 0):
            low.blit(self.player_spr, (int(self.px - 6), PLAYER_Y))
        if self.ufo:
            low.blit(self.ufo_spr, (int(self.ufo["x"]), 17))
        for x, y, vx, vy, life, col in self.particles:
            low.fill(col, (int(x), int(y), 2, 2))
        for x, y, msg, life in self.popups:
            text(low, msg, (int(x), int(y)), f.small, (255, 255, 120))

        # HUD
        low.fill((60, 200, 90), (0, GROUND_Y, W, 1))
        text(low, "SCORE %06d" % self.score, (6, 2), f.small)
        text(low, "HI %06d" % max(self.hi, self.score), (W // 2, 2), f.small,
             (255, 220, 80), "midtop")
        text(low, "WAVE %d" % self.wave, (W - 6, 2), f.small, (130, 255, 130), "topright")
        low.blit(self.player_spr, (6, GROUND_Y + 5))
        text(low, "x %d" % self.lives, (24, GROUND_Y + 4), f.small)

        if self.state == "ready":
            text(low, "WAVE %d" % self.wave, (W // 2, 102), f.med, (255, 255, 255), "midtop")
        elif self.state == "gameover":
            text(low, "GAME OVER", (W // 2, 70), f.big, (255, 70, 70), "midtop")
            text(low, "SCORE %d" % self.score, (W // 2, 108), f.med, (255, 255, 255), "midtop")
        if self.paused:
            text(low, "PAUSED", (W // 2, 76), f.big, (255, 255, 255), "midtop")
