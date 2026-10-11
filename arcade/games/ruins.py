"""RUINS - a retro raycasting first-person shooter for the retro arcade.

W/S (or Up/Down) walk, A/D strafe, Shift run.
Mouse (or Left/Right arrows) to look. Click / Space / Ctrl to shoot.
R reload, Tab toggles the minimap, P pauses, Esc returns to the menu.
Clear every hostile in the sector to advance; health and ammo packs help.
"""
import math
import random

import pygame

import scores
from engine import Scene, W, H, clamp, mix, sprite_from_rows, text
from toolkit import draw_hint

TEX = 32
COLW = 2
NRAYS = W // COLW
FOV = math.radians(66)
PLANE = math.tan(FOV / 2)
MAXD = 18.0
SHADES = 6
HAZE = (205, 185, 160)
MAG_SIZE = 12

MAP = [
    "########################",
    "#P.....#........S.....e#",
    "#......#........S......#",
    "#..##..####.SSS..S..CC.#",
    "#..##..e.............C.#",
    "#.......####.###..e..C.#",
    "###.#####..#.#a#.....C.#",
    "#.......e..#.#.#..SSS..#",
    "#..CC......#.#.#..S....#",
    "#..C...##..#...#..S..e.#",
    "#......##..##.###......#",
    "#...e.................a#",
    "#####.######..######.###",
    "#...............#.....e#",
    "#.SSS...C.......#..CC..#",
    "#.S.....C...e...#..C...#",
    "#.S..h..CCC.....#......#",
    "#...............#..###.#",
    "#...######.####.#..#e..#",
    "#...#..........#..#....#",
    "#...#..a..SS...#..###h.#",
    "#.e.#......S...#.......#",
    "#...#######....#...e...#",
    "########################",
]
MW, MH = 24, 24
TILE_IDS = {"#": 1, "S": 2, "C": 3}


def parse_map():
    grid, spawns, items, start = [], [], [], (1.5, 1.5)
    for y in range(MH):
        row = MAP[y].ljust(MW, "#")[:MW]
        grid_row = []
        for x, ch in enumerate(row):
            grid_row.append(TILE_IDS.get(ch, 0))
            if ch == "e":
                spawns.append((x + 0.5, y + 0.5))
            elif ch == "a":
                items.append((x + 0.5, y + 0.5, "ammo"))
            elif ch == "h":
                items.append((x + 0.5, y + 0.5, "health"))
            elif ch == "P":
                start = (x + 0.5, y + 0.5)
        grid.append(grid_row)
    return grid, spawns, items, start


# --------------------------------------------------------------------------
# Procedural textures (brick, sandstone, concrete) with distance-fog variants
# --------------------------------------------------------------------------
def tex_brick(rng):
    g = []
    for y in range(TEX):
        row = []
        for x in range(TEX):
            off = 8 if (y // 8) % 2 else 0
            if y % 8 == 0 or (x + off) % 16 == 0:
                row.append((160, 146, 128))
            else:
                v = rng.randint(-14, 14)
                row.append((152 + v, 84 + v // 2, 62 + v // 2))
        g.append(row)
    for _ in range(45):
        g[rng.randrange(TEX)][rng.randrange(TEX)] = (76, 52, 46)
    return g


def tex_sand(rng):
    g = []
    for y in range(TEX):
        row = []
        for x in range(TEX):
            band = 12 if (y // 6) % 2 else 0
            v = rng.randint(-8, 8)
            c = (206 - band + v, 176 - band + v, 128 - band + v)
            if (x * 3 + y * 5) % 37 == 0:
                c = (150, 124, 90)
            row.append(c)
        g.append(row)
    return g


def tex_concrete(rng):
    g = []
    for y in range(TEX):
        row = []
        for x in range(TEX):
            v = rng.randint(-10, 10)
            c = (138 + v, 138 + v, 140 + v)
            if x % 16 == 0 or y % 16 == 0:
                c = (96, 96, 100)
            row.append(c)
        g.append(row)
    for _ in range(60):
        g[rng.randrange(TEX)][rng.randrange(TEX)] = (128, 98, 78)
    return g


def build_strips():
    """strips[tex][variant][x] -> a 1xTEX column of that texture.
    variant = side * SHADES + fog level."""
    rng = random.Random(5)
    out = []
    for g in (tex_brick(rng), tex_sand(rng), tex_concrete(rng)):
        variants = []
        for side in (0, 1):
            for lv in range(SHADES):
                f = lv / float(SHADES - 1)
                s = pygame.Surface((TEX, TEX))
                for y in range(TEX):
                    for x in range(TEX):
                        c = g[y][x]
                        if side:
                            c = (c[0] * 3 // 4, c[1] * 3 // 4, c[2] * 3 // 4)
                        s.set_at((x, y), mix(c, HAZE, f * 0.85))
                variants.append([s.subsurface((x, 0, 1, TEX)) for x in range(TEX)])
        out.append(variants)
    return out


def build_bg():
    bg = pygame.Surface((W, H))
    top, hz, bot = (92, 128, 172), HAZE, (112, 92, 72)
    for y in range(H // 2):
        pygame.draw.line(bg, mix(top, hz, y / float(H // 2)), (0, y), (W, y))
    for y in range(H // 2, H):
        pygame.draw.line(bg, mix(hz, bot, (y - H // 2) / float(H // 2)), (0, y), (W, y))
    return bg


# --------------------------------------------------------------------------
# Sprites
# --------------------------------------------------------------------------
PAL = {"H": (105, 112, 100), "F": (215, 172, 132), "T": (200, 62, 52), "D": (140, 40, 38),
       "S": (200, 150, 110), "P": (62, 58, 52), "B": (28, 26, 26), "G": (36, 36, 42),
       "Y": (255, 230, 90)}
BODY = [
    "......HHHH......", ".....HHHHHH.....", ".....HFFFFH.....", ".....FFFFFF.....",
    ".....F.FF.F.....", "......FFFF......", ".....TTTTTT.....", "....TTTTTTTT....",
    "...TTTTTTTTTT.GG", "...TTDTTTTDTGGGG", "...SSDTTTTDSGGG.", "...SS.TTTT.SS...",
    "......TTTT......", "......TTTT......", ".....PPPPPP.....", ".....PPPPPP....."]
LEGS_A = [".....PP..PP.....", ".....PP..PP.....", ".....PP..PP.....", ".....PP..PP.....",
          ".....PP..PP.....", ".....BB..BB.....", "....BBB..BBB....", "................"]
LEGS_B = ["....PPP..PPP....", "....PP....PP....", "...PP......PP...", "...PP......PP...",
          "...PP......PP...", "...BB......BB...", "..BBB......BBB..", "................"]
SHOOT = ["...TTTTGGTTTT...", "...TTDTGGTDTT...", "...SSDTGGTDSS...", "...SS.TYYT.SS..."]
DEAD = ["........TTTTTTTT........", ".HHFF.TTTTTTTTTTTPPPP...",
        "HHHFFFTTDTTTTTTDPPPPPBB.", ".HHFF.TTTTTTTTTTTPPPPBB.",
        "........DDDDDDDD........"]
AMMO = ["AAAAAAAAAA", "AYYAAAYYAA", "AAAAAAAAAA", "AAAAAAAAAA", "AAAAAAAAAA", "DDDDDDDDDD"]
HEALTH = ["WWWWWWWWW", "WWWWRWWWW", "WWWWRWWWW", "WWRRRRRWW", "WWWWRWWWW",
          "WWWWRWWWW", "WWWWWWWWW"]


def flash_version(img):
    v = img.copy()
    v.fill((110, 110, 110), special_flags=pygame.BLEND_RGB_ADD)
    return v


def build_sprites():
    s = {}
    s["stand"] = sprite_from_rows(BODY + LEGS_A, PAL)
    s["walk"] = sprite_from_rows(BODY + LEGS_B, PAL)
    s["shoot"] = sprite_from_rows(BODY[:8] + SHOOT + BODY[12:] + LEGS_A, PAL)
    s["dead"] = sprite_from_rows(DEAD, PAL)
    for k in ("stand", "walk", "shoot", "dead"):
        s[k + "_hit"] = flash_version(s[k])
    s["ammo"] = sprite_from_rows(AMMO, {"A": (96, 108, 62), "Y": (240, 200, 60), "D": (52, 58, 36)})
    s["health"] = sprite_from_rows(HEALTH, {"W": (238, 238, 238), "R": (220, 40, 40)})
    return s


def build_gun():
    g = pygame.Surface((100, 66), pygame.SRCALPHA)
    skin, skin_d = (150, 95, 70), (112, 70, 52)
    pygame.draw.polygon(g, skin, [(50, 66), (100, 66), (100, 36), (72, 30), (58, 42)])
    pygame.draw.polygon(g, skin_d, [(70, 66), (100, 66), (100, 50), (84, 52)])
    g.fill((34, 34, 40), (46, 28, 28, 22))               # grip
    g.fill((46, 46, 56), (28, 10, 40, 22))               # slide
    g.fill((92, 92, 106), (28, 10, 40, 3))
    for i in range(6):
        g.fill((30, 30, 38), (54 + i * 2, 16, 1, 12))     # serrations
    g.fill((36, 36, 44), (20, 14, 10, 12))               # barrel
    g.fill((26, 26, 32), (44, 1, 20, 10))                # red-dot sight
    g.fill((40, 10, 10), (47, 3, 14, 6))
    g.fill((255, 60, 60), (53, 5, 2, 2))
    g.fill(skin_d, (56, 40, 8, 6))                       # fingers
    g.fill(skin_d, (64, 42, 8, 6))
    flash = g.copy()
    pygame.draw.polygon(flash, (255, 205, 70), [(22, 20), (4, 8), (10, 19), (0, 28), (14, 23),
                                                 (10, 34), (22, 26)])
    pygame.draw.polygon(flash, (255, 255, 200), [(22, 21), (10, 15), (14, 21), (8, 27), (22, 24)])
    return g, flash


class Enemy:
    def __init__(self, x, y, hp):
        self.x, self.y = x, y
        self.hp = hp
        self.state = "idle"          # idle | chase | shoot | dead
        self.cool = random.uniform(0.5, 1.2)
        self.hurt = 0.0
        self.muzzle = 0.0
        self.walk = 0.0
        self.lost = 0.0
        self.range = random.uniform(4.5, 7.0)


class RuinsScene(Scene):
    def __init__(self):
        self.grid, self.spawns, self.item_spots, self.start = parse_map()
        self.strips = build_strips()
        self.bg = build_bg()
        self.spr = build_sprites()
        self.gun, self.gun_flash = build_gun()
        self.red = pygame.Surface((W, H))
        self.red.fill((200, 20, 20))
        self.mini = pygame.Surface((MW * 2, MH * 2), pygame.SRCALPHA)
        self.mini.fill((10, 5, 30, 150))
        for y in range(MH):
            for x in range(MW):
                if self.grid[y][x]:
                    self.mini.fill((210, 190, 160), (x * 2, y * 2, 2, 2))
        self.camx = [2.0 * (i * COLW + COLW / 2.0) / W - 1.0 for i in range(NRAYS)]
        self.zbuf = [MAXD] * NRAYS
        self.scaled = {}
        self.floor_cells = [(x + 0.5, y + 0.5) for y in range(MH) for x in range(MW)
                            if not self.grid[y][x]]
        self.t = 0.0
        self.paused = False
        self.show_map = True
        self.new_game()

    # ------------------------------------------------------------------
    def on_enter(self):
        pygame.mouse.set_visible(False)
        pygame.event.set_grab(True)
        pygame.mouse.get_rel()

    def on_exit(self):
        pygame.mouse.set_visible(True)
        pygame.event.set_grab(False)

    def new_game(self):
        self.level = 1
        self.score = 0
        self.kills = 0
        self.health = 100
        self.mag = MAG_SIZE
        self.reserve = 36
        self.hi = scores.top("ruins")[0]["score"]
        self.state = "play"          # play | clear | dead
        self.timer = 0.0
        self.setup_level()

    def setup_level(self):
        self.px, self.py = self.start
        self.ang = math.radians(25)
        self.cool = 0.0
        self.reload_t = 0.0
        self.muzzle = 0.0
        self.kick = 0.0
        self.bob = 0.0
        self.hurt_t = 0.0
        self.hit_t = 0.0
        self.noise = 0.0
        self.banner = 2.0
        hp = 3 + (self.level - 1) // 2
        self.enemies = [Enemy(x, y, hp) for x, y in self.spawns]
        want = min(14, len(self.spawns) + 2 * (self.level - 1))
        tries = 0
        while len(self.enemies) < want and tries < 400:
            tries += 1
            x, y = random.choice(self.floor_cells)
            if math.hypot(x - self.px, y - self.py) > 9:
                self.enemies.append(Enemy(x, y, hp))
        self.items = [[x, y, k] for x, y, k in self.item_spots]
        pygame.mouse.get_rel()

    def snd(self, n):
        self.app.sound.play(n)

    # ------------------------------------------------------------------
    # geometry helpers
    # ------------------------------------------------------------------
    def blocked(self, x, y, r=0.22):
        for cx in (x - r, x + r):
            for cy in (y - r, y + r):
                ix, iy = int(cx), int(cy)
                if ix < 0 or iy < 0 or ix >= MW or iy >= MH or self.grid[iy][ix]:
                    return True
        return False

    def ray_dist(self, ox, oy, a, maxd=40.0):
        dx, dy = math.cos(a), math.sin(a)
        mx, my = int(ox), int(oy)
        ddx = abs(1.0 / dx) if dx else 1e30
        ddy = abs(1.0 / dy) if dy else 1e30
        if dx < 0:
            sx, sdx = -1, (ox - mx) * ddx
        else:
            sx, sdx = 1, (mx + 1.0 - ox) * ddx
        if dy < 0:
            sy, sdy = -1, (oy - my) * ddy
        else:
            sy, sdy = 1, (my + 1.0 - oy) * ddy
        for _ in range(64):
            if sdx < sdy:
                dist = sdx
                sdx += ddx
                mx += sx
            else:
                dist = sdy
                sdy += ddy
                my += sy
            if mx < 0 or my < 0 or mx >= MW or my >= MH or self.grid[my][mx]:
                return dist
        return maxd

    def los(self, x0, y0, x1, y1):
        d = math.hypot(x1 - x0, y1 - y0)
        return self.ray_dist(x0, y0, math.atan2(y1 - y0, x1 - x0)) >= d - 0.3

    # ------------------------------------------------------------------
    # update
    # ------------------------------------------------------------------
    def handle_event(self, e):
        if e.type != pygame.KEYDOWN or self.state != "play" or self.paused:
            return
        if e.key == pygame.K_r:
            self.start_reload()
        elif e.key == pygame.K_TAB:
            self.show_map = not self.show_map

    def update(self, dt, inp):
        p = inp.pressed
        if "back" in p:
            self.app.go_menu()
            return
        if "pause" in p and self.state == "play":
            self.paused = not self.paused
            pygame.mouse.get_rel()
        if self.paused:
            return
        self.t += dt
        self.banner = max(0.0, self.banner - dt)
        self.hurt_t = max(0.0, self.hurt_t - dt)
        self.hit_t = max(0.0, self.hit_t - dt)
        self.muzzle = max(0.0, self.muzzle - dt)
        self.kick = max(0.0, self.kick - dt * 5)
        self.noise = max(0.0, self.noise - dt)

        if self.state == "dead":
            self.timer -= dt
            if self.timer <= 0 or (self.timer < 1.6 and ({"start", "fire"} & p)):
                self.app.finish_game("ruins", self.score)
            return
        if self.state == "clear":
            self.timer -= dt
            if self.timer <= 0:
                self.level += 1
                self.health = min(100, self.health + 30)
                self.reserve = min(90, self.reserve + 24)
                self.state = "play"
                self.setup_level()
            return

        self.update_player(dt, inp)
        self.update_enemies(dt)
        self.update_items()
        if self.state == "play" and not any(e.state != "dead" for e in self.enemies):
            self.state = "clear"
            self.timer = 3.0
            self.score += 500 * self.level + self.health * 5
            self.snd("jingle")

    def update_player(self, dt, inp):
        k = inp.keys
        fwd = int(bool(k[pygame.K_w] or k[pygame.K_UP])) - int(bool(k[pygame.K_s] or k[pygame.K_DOWN]))
        strafe = int(bool(k[pygame.K_d])) - int(bool(k[pygame.K_a]))
        turn = int(bool(k[pygame.K_RIGHT])) - int(bool(k[pygame.K_LEFT]))
        dx, dy = pygame.mouse.get_rel()
        self.ang += turn * 2.2 * dt + dx * 0.0028
        speed = (3.4 if k[pygame.K_LSHIFT] else 2.2) * dt
        ca, sa = math.cos(self.ang), math.sin(self.ang)
        mx = (ca * fwd - sa * strafe)
        my = (sa * fwd + ca * strafe)
        norm = math.hypot(mx, my)
        if norm > 0:
            mx, my = mx / norm * speed, my / norm * speed
            if not self.blocked(self.px + mx, self.py):
                self.px += mx
            if not self.blocked(self.px, self.py + my):
                self.py += my
            self.bob += dt * (9 if k[pygame.K_LSHIFT] else 6)
        else:
            self.bob *= 0.9

        self.cool = max(0.0, self.cool - dt)
        if self.reload_t > 0:
            self.reload_t -= dt
            if self.reload_t <= 0:
                take = min(MAG_SIZE - self.mag, self.reserve)
                self.mag += take
                self.reserve -= take
        elif (inp.held("fire") or pygame.mouse.get_pressed()[0]) and self.cool <= 0:
            if self.mag > 0:
                self.shoot()
            else:
                self.cool = 0.3
                if self.reserve > 0:
                    self.start_reload()
                else:
                    self.snd("click")

    def start_reload(self):
        if self.reload_t <= 0 and self.mag < MAG_SIZE and self.reserve > 0:
            self.reload_t = 1.1
            self.snd("reload")

    def shoot(self):
        self.mag -= 1
        self.cool = 0.26
        self.muzzle = 0.07
        self.kick = 1.0
        self.noise = 1.0
        self.snd("shoot")
        a = self.ang + random.uniform(-0.012, 0.012)
        wall = self.ray_dist(self.px, self.py, a)
        ca, sa = math.cos(a), math.sin(a)
        best, bf = None, 1e9
        for e in self.enemies:
            if e.state == "dead":
                continue
            ex, ey = e.x - self.px, e.y - self.py
            f = ex * ca + ey * sa
            if f < 0.15 or f > wall or f >= bf:
                continue
            if abs(-ex * sa + ey * ca) < 0.3:
                best, bf = e, f
        if best:
            best.hp -= random.choice((1, 1, 2))
            best.hurt = 0.12
            self.hit_t = 0.12
            if best.state == "idle":
                best.state = "chase"
            if best.hp <= 0:
                best.state = "dead"
                self.kills += 1
                self.score += 100
                self.snd("boom")
                if random.random() < 0.3:
                    self.items.append([best.x, best.y, random.choice(("ammo", "health"))])
            else:
                self.snd("hurt")

    def hurt(self, dmg):
        self.health -= dmg
        self.hurt_t = 0.5
        self.snd("hurt")
        if self.health <= 0:
            self.health = 0
            self.state = "dead"
            self.timer = 3.0
            self.snd("gameover")

    def update_enemies(self, dt):
        speed = 1.1 + 0.05 * self.level
        for e in self.enemies:
            if e.state == "dead":
                continue
            e.hurt = max(0.0, e.hurt - dt)
            e.muzzle = max(0.0, e.muzzle - dt)
            dx, dy = self.px - e.x, self.py - e.y
            d = math.hypot(dx, dy)
            see = d < 15 and self.los(e.x, e.y, self.px, self.py)
            if e.state == "idle":
                if (see and d < 10) or (self.noise > 0 and d < 13):
                    e.state = "chase"
                    e.lost = 0.0
            elif e.state == "chase":
                if see:
                    e.lost = 0.0
                    if d < e.range:
                        e.state = "shoot"
                        e.cool = random.uniform(0.35, 0.8)
                else:
                    e.lost += dt
                    if e.lost > 7:
                        e.state = "idle"
                if e.state == "chase" and d > 1.0:
                    self.move_enemy(e, dx / d, dy / d, speed * dt)
                    e.walk += dt
            elif e.state == "shoot":
                if not see or d > e.range + 1.5:
                    e.state = "chase"
                else:
                    e.cool -= dt
                    if e.cool <= 0:
                        e.cool = random.uniform(0.9, 1.6) / (1 + 0.05 * self.level)
                        e.muzzle = 0.15
                        self.snd("enemy_shoot")
                        chance = clamp(0.85 - d * 0.08, 0.12, 0.7)
                        if random.random() < chance and self.state == "play":
                            self.hurt(random.randint(5, 10) + self.level // 2)

    def move_enemy(self, e, ux, uy, step):
        nx, ny = e.x + ux * step, e.y + uy * step
        if not self.blocked(nx, e.y, 0.25):
            e.x = nx
        elif not self.blocked(e.x, e.y + uy * step * 1.4, 0.25):
            e.y += uy * step * 1.4
        if not self.blocked(e.x, ny, 0.25):
            e.y = ny
        elif not self.blocked(e.x + ux * step * 1.4, e.y, 0.25):
            e.x += ux * step * 1.4

    def update_items(self):
        for it in self.items[:]:
            if math.hypot(it[0] - self.px, it[1] - self.py) < 0.6:
                if it[2] == "health":
                    if self.health >= 100:
                        continue
                    self.health = min(100, self.health + 25)
                else:
                    if self.reserve >= 90:
                        continue
                    self.reserve = min(90, self.reserve + 12)
                self.items.remove(it)
                self.snd("pickup")

    # ------------------------------------------------------------------
    # rendering
    # ------------------------------------------------------------------
    def render_walls(self, low):
        px, py = self.px, self.py
        dirx, diry = math.cos(self.ang), math.sin(self.ang)
        plx, ply = -diry * PLANE, dirx * PLANE
        grid, zbuf, strips, camx = self.grid, self.zbuf, self.strips, self.camx
        half = H // 2
        scale = pygame.transform.scale
        for i in range(NRAYS):
            cam = camx[i]
            rdx, rdy = dirx + plx * cam, diry + ply * cam
            mx, my = int(px), int(py)
            ddx = abs(1.0 / rdx) if rdx else 1e30
            ddy = abs(1.0 / rdy) if rdy else 1e30
            if rdx < 0:
                sx, sdx = -1, (px - mx) * ddx
            else:
                sx, sdx = 1, (mx + 1.0 - px) * ddx
            if rdy < 0:
                sy, sdy = -1, (py - my) * ddy
            else:
                sy, sdy = 1, (my + 1.0 - py) * ddy
            side = 0
            tile = 0
            for _ in range(48):
                if sdx < sdy:
                    sdx += ddx
                    mx += sx
                    side = 0
                else:
                    sdy += ddy
                    my += sy
                    side = 1
                if mx < 0 or my < 0 or mx >= MW or my >= MH:
                    tile = 1
                    break
                tile = grid[my][mx]
                if tile:
                    break
            if not tile:
                zbuf[i] = MAXD * 2
                continue
            dist = (sdx - ddx) if side == 0 else (sdy - ddy)
            if dist < 0.05:
                dist = 0.05
            zbuf[i] = dist
            wx = (py + dist * rdy) if side == 0 else (px + dist * rdx)
            wx -= math.floor(wx)
            texx = int(wx * TEX)
            if (side == 0 and rdx > 0) or (side == 1 and rdy < 0):
                texx = TEX - 1 - texx
            lh = int(H / dist)
            level = min(SHADES - 1, int(dist / MAXD * (SHADES - 1) * 1.15))
            strip = strips[tile - 1][side * SHADES + level][texx]
            col = i * COLW
            if lh <= H:
                low.blit(scale(strip, (COLW, max(1, lh))), (col, half - lh // 2))
            else:
                src_h = TEX * H / float(lh)
                sy0 = int((TEX - src_h) / 2)
                sub = strip.subsurface((0, sy0, 1, max(1, int(src_h))))
                low.blit(scale(sub, (COLW, H)), (col, 0))

    def scaled_img(self, img, w, h):
        key = (id(img), w, h)
        s = self.scaled.get(key)
        if s is None:
            if len(self.scaled) > 500:
                self.scaled.clear()
            s = pygame.transform.scale(img, (w, h))
            self.scaled[key] = s
        return s

    def draw_billboard(self, low, img, tx, ty, w, h, ybot):
        sx = int(W / 2.0 * (1 + tx / ty))
        x0 = sx - w // 2
        if x0 > W or x0 + w < 0 or w < 1 or h < 1:
            return
        scaled = self.scaled_img(img, w, h)
        ystart = ybot - h
        zbuf = self.zbuf
        c0 = max(0, x0) // COLW
        c1 = min(W - 1, x0 + w) // COLW
        for idx in range(c0, min(c1, NRAYS - 1) + 1):
            if zbuf[idx] < ty:
                continue
            col = idx * COLW
            off = col - x0
            if off < 0 or off >= w:
                continue
            low.blit(scaled, (col, ystart), (off, 0, COLW, h))

    def render_sprites(self, low):
        dirx, diry = math.cos(self.ang), math.sin(self.ang)
        plx, ply = -diry * PLANE, dirx * PLANE
        inv = 1.0 / (plx * diry - dirx * ply)
        objs = []
        for e in self.enemies:
            objs.append((math.hypot(e.x - self.px, e.y - self.py), 0, e))
        for it in self.items:
            objs.append((math.hypot(it[0] - self.px, it[1] - self.py), 1, it))
        objs.sort(key=lambda o: -o[0])
        for d, kind, o in objs:
            sx, sy = o.x - self.px if kind == 0 else o[0] - self.px, \
                (o.y if kind == 0 else o[1]) - self.py
            tx = inv * (diry * sx - dirx * sy)
            ty = inv * (-ply * sx + plx * sy)
            if ty < 0.3 or ty > MAXD:
                continue
            unit = H / ty
            ybot = H // 2 + int(unit / 2)
            if kind == 1:
                img = self.spr[o[2]]
                w = max(1, int(unit * 0.32))
                h = max(1, int(w * img.get_height() / float(img.get_width())))
                self.draw_billboard(low, img, tx, ty, w, h, ybot)
                continue
            hit = "_hit" if o.hurt > 0 else ""
            if o.state == "dead":
                img = self.spr["dead" + hit]
                w = max(1, int(unit * 0.9))
                h = max(1, int(w * img.get_height() / float(img.get_width())))
            else:
                if o.muzzle > 0:
                    name = "shoot"
                elif o.state == "chase":
                    name = "walk" if int(o.walk * 6) % 2 else "stand"
                else:
                    name = "stand"
                img = self.spr[name + hit]
                h = max(1, int(unit * 0.85))
                w = max(1, int(h * 16 / 24.0))
            self.draw_billboard(low, img, tx, ty, w, h, ybot)

    def draw(self, low):
        f = self.app.fonts
        low.blit(self.bg, (0, 0))
        self.render_walls(low)
        self.render_sprites(low)

        # weapon
        bx = W - 104 + int(math.sin(self.bob) * 3) + int(self.kick * 6)
        by = H - 58 + int(abs(math.cos(self.bob)) * 2) + int(self.kick * 5)
        if self.reload_t > 0:
            by += int(math.sin(min(1.0, (1.1 - self.reload_t) / 1.1) * math.pi) * 40)
        low.blit(self.gun_flash if self.muzzle > 0 else self.gun, (bx, by))

        # crosshair
        cx, cy = W // 2, H // 2
        for ox, oy in ((-5, 0), (3, 0), (0, -5), (0, 3)):
            low.fill((255, 255, 255), (cx + ox, cy + oy, 2, 2) if ox else (cx + ox, cy + oy, 2, 2))
        low.fill((255, 60, 60), (cx, cy, 2, 2))
        if self.hit_t > 0:
            for ox, oy in ((-7, -7), (7, -7), (-7, 7), (7, 7)):
                low.fill((255, 80, 80), (cx + ox, cy + oy, 2, 2))

        # film grain
        for _ in range(90):
            c = random.choice(((235, 235, 235), (20, 20, 20)))
            low.fill(c, (random.randrange(W), random.randrange(H), 1, 1))

        if self.hurt_t > 0:
            self.red.set_alpha(int(min(1.0, self.hurt_t / 0.5) * 120))
            low.blit(self.red, (0, 0))

        # HUD
        alive = sum(1 for e in self.enemies if e.state != "dead")
        text(low, "HOSTILES %d" % alive, (6, 2), f.small, (255, 130, 110))
        text(low, "SCORE %06d" % self.score, (W // 2, 2), f.small, (255, 255, 255), "midtop")
        ammo_col = (255, 255, 255) if self.mag > 3 else (255, 90, 90)
        text(low, "AMMO %d/%d" % (self.mag, self.reserve), (W - 6, 2), f.small, ammo_col, "topright")
        if self.reload_t > 0:
            text(low, "RELOADING", (W - 6, 13), f.small, (255, 220, 80), "topright")
        low.fill((20, 10, 30), (5, H - 15, 62, 9))
        low.fill((220, 50, 50) if self.health < 35 else (80, 220, 100),
                 (6, H - 14, int(60 * self.health / 100.0), 7))
        text(low, "HP %d" % self.health, (6, H - 26), f.small)
        text(low, "SECTOR %d" % self.level, (W // 2, H - 12), f.small, (230, 220, 255), "midtop")

        if self.show_map:
            low.blit(self.mini, (4, 26))
            low.fill((255, 230, 80), (4 + int(self.px * 2) - 1, 26 + int(self.py * 2) - 1, 3, 3))
            for e in self.enemies:
                if e.state != "dead":
                    low.fill((255, 60, 60), (4 + int(e.x * 2), 26 + int(e.y * 2), 2, 2))

        draw_hint(low, f, ["WASD: MOVE   MOUSE / ARROWS: LOOK",
                           "CLICK or SPACE: FIRE   R: RELOAD   TAB: MAP"], self.t, y=60, show=7.0)
        if self.banner > 0 and self.state == "play":
            text(low, "SECTOR %d" % self.level, (W // 2, 36), f.med, (255, 255, 255), "midtop")
        if self.state == "clear":
            text(low, "SECTOR CLEARED", (W // 2, 60), f.big, (120, 255, 140), "midtop")
        elif self.state == "dead":
            text(low, "YOU DIED", (W // 2, 60), f.big, (255, 70, 70), "midtop")
            text(low, "SCORE %d" % self.score, (W // 2, 100), f.med, (255, 255, 255), "midtop")
        if self.paused:
            text(low, "PAUSED", (W // 2, 70), f.big, (255, 255, 255), "midtop")
