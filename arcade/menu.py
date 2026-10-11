"""Menu, initials entry and high-score table screens."""
import math

import pygame

import scores
from engine import Scene, W, H, text, wrap, draw_synth_bg


# --- game catalog -----------------------------------------------------------
# (id, title, description, factory). factory=None means "coming soon".
def _invaders():
    from games.invaders import InvadersScene
    return InvadersScene()


def _drift():
    from games.drift import DriftScene
    return DriftScene()


CATALOG = [
    ("SHOOTERS", [
        ("invaders", "SPACE INVADERS",
         "Defend Earth from waves of alien invaders. Hide behind the shields "
         "and shoot the mystery ship for bonus points.", _invaders),
        ("galaga", "STAR STRIKE",
         "Vertical shoot-'em-up with enemy formations, power-ups and bosses.", None),
        ("asteroids", "ROCK BLASTER",
         "Rotate, thrust and blast drifting asteroids. Screen wraps around.", None),
        ("ruins", "RUINS",
         "Retro first-person shooter. Clear the ruined village.", None),
    ]),
    ("RACING", [
        ("drift", "TURBO DRIFT",
         "Pseudo-3D racer. Drift for turbos, dodge traffic, grab power-ups and "
         "beat 5 rivals over 3 laps.", _drift),
        ("rally", "RALLY RUSH",
         "Top-down rally racing with tight tracks and drifting.", None),
    ]),
    ("CLASSICS", [
        ("pong", "PONG", "The original. First to 7 wins.", None),
        ("snake", "SNAKE", "Eat, grow, don't crash.", None),
        ("breakout", "BREAKOUT", "Smash every brick with the bouncing ball.", None),
    ]),
]

TITLES = {gid: title for _, entries in CATALOG for gid, title, _, _ in entries}

YELLOW = (255, 220, 80)
DIM = (120, 110, 160)


class MenuScene(Scene):
    def __init__(self):
        self.tab = 0
        self.idx = 0
        self.t = 0.0
        self.panel = pygame.Surface((148, 92), pygame.SRCALPHA)
        self.panel.fill((10, 5, 30, 200))

    def on_enter(self):
        self.tab, self.idx = self.app.menu_state

    def entries(self):
        return CATALOG[self.tab][1]

    def update(self, dt, inp):
        self.t += dt
        p, snd = inp.pressed, self.app.sound
        if "left" in p or "right" in p:
            self.tab = (self.tab + (1 if "right" in p else -1)) % len(CATALOG)
            self.idx = 0
            snd.play("select")
        if "up" in p or "down" in p:
            n = len(self.entries())
            self.idx = (self.idx + (1 if "down" in p else -1)) % n
            snd.play("select")
        if "start" in p or "fire" in p:
            gid, title, desc, factory = self.entries()[self.idx]
            if factory:
                self.app.menu_state = (self.tab, self.idx)
                snd.play("start")
                self.app.change(factory())
            else:
                snd.play("deny")
        if "back" in p:
            self.app.quit()

    def draw(self, low):
        f = self.app.fonts
        draw_synth_bg(low, self.t)

        # bouncing, colour-cycling title
        title = "RETRO ARCADE"
        cols = [(255, 80, 200), (80, 220, 255), (255, 230, 90)]
        widths = [f.big.size(ch)[0] for ch in title]
        x = W / 2 - sum(widths) / 2
        for i, ch in enumerate(title):
            y = 6 + math.sin(self.t * 3 + i * 0.6) * 2
            text(low, ch, (int(x), int(y)), f.big, cols[(i + int(self.t * 3)) % 3])
            x += widths[i]

        # category tabs
        for i, (name, _) in enumerate(CATALOG):
            cx = int(W * (i + 0.5) / len(CATALOG))
            if i == self.tab:
                text(low, "< %s >" % name, (cx, 40), f.med, YELLOW, "midtop")
            else:
                text(low, name, (cx, 43), f.small, DIM, "midtop")

        # game list
        blink = int(self.t * 4) % 2 == 0
        for i, (gid, title, desc, factory) in enumerate(self.entries()):
            y = 66 + i * 14
            if i == self.idx:
                col = (255, 255, 255) if factory else (170, 160, 200)
                text(low, ">" if blink else " ", (10, y), f.small, YELLOW)
            else:
                col = (200, 190, 240) if factory else DIM
            text(low, title, (20, y), f.small, col)

        # info panel
        low.blit(self.panel, (166, 60))
        gid, title, desc, factory = self.entries()[self.idx]
        text(low, title, (172, 64), f.small, YELLOW)
        y = 77
        for line in wrap(desc, f.small, 136)[:5]:
            text(low, line, (172, y), f.small, (225, 220, 245))
            y += 10
        if factory:
            text(low, "HI-SCORES", (172, 128), f.small, (255, 130, 200))
            for i, e in enumerate(scores.top(gid)[:2]):
                text(low, "%s %6d" % (e["name"], e["score"]),
                     (172, 137 + i * 9), f.small, (255, 255, 255))
        else:
            text(low, "COMING SOON", (172, 134), f.small, (255, 130, 200))

        text(low, "ARROWS: SELECT   ENTER: PLAY   ESC: QUIT", (W // 2, 168),
             f.small, (230, 220, 255), "midtop")
        text(low, "F1 CRT  F2 SOUND  F11 FULLSCREEN", (W - 4, 2), f.small, DIM, "topright")


class NameEntryScene(Scene):
    """Classic three-letter initials entry."""

    def __init__(self, game_id, score):
        self.game_id, self.score = game_id, score
        self.letters = [0, 0, 0]
        self.pos = 0
        self.t = 0.0

    def update(self, dt, inp):
        self.t += dt
        p, snd = inp.pressed, self.app.sound
        if "up" in p:
            self.letters[self.pos] = (self.letters[self.pos] + 1) % 26
            snd.play("select")
        if "down" in p:
            self.letters[self.pos] = (self.letters[self.pos] - 1) % 26
            snd.play("select")
        if "left" in p and self.pos > 0:
            self.pos -= 1
            snd.play("select")
        if "right" in p and self.pos < 2:
            self.pos += 1
            snd.play("select")
        if "start" in p or "fire" in p:
            if self.pos < 2:
                self.pos += 1
                snd.play("select")
            else:
                name = "".join(chr(65 + i) for i in self.letters)
                rank = scores.add(self.game_id, name, self.score)
                snd.play("jingle")
                self.app.change(ScoreTableScene(self.game_id, rank))

    def draw(self, low):
        f = self.app.fonts
        draw_synth_bg(low, self.t)
        text(low, "NEW HIGH SCORE!", (W // 2, 18), f.med, YELLOW, "midtop")
        text(low, "%d" % self.score, (W // 2, 44), f.big, (255, 255, 255), "midtop")
        text(low, "ENTER YOUR INITIALS", (W // 2, 84), f.small, (230, 220, 255), "midtop")
        for i, v in enumerate(self.letters):
            x = W // 2 - 45 + i * 45
            col = YELLOW if i == self.pos else (255, 255, 255)
            text(low, chr(65 + v), (x, 100), f.big, col, "midtop")
            if i == self.pos and int(self.t * 4) % 2 == 0:
                low.fill(YELLOW, (x - 10, 128, 20, 2))
        text(low, "UP/DOWN: LETTER   ENTER: OK", (W // 2, 160), f.small,
             (230, 220, 255), "midtop")


class ScoreTableScene(Scene):
    def __init__(self, game_id, highlight=-1):
        self.game_id, self.highlight = game_id, highlight
        self.t = 0.0

    def update(self, dt, inp):
        self.t += dt
        if self.t > 0.4 and ({"start", "fire", "back"} & inp.pressed):
            self.app.sound.play("back")
            self.app.go_menu()

    def draw(self, low):
        f = self.app.fonts
        draw_synth_bg(low, self.t)
        text(low, "HIGH SCORES", (W // 2, 14), f.med, YELLOW, "midtop")
        text(low, TITLES.get(self.game_id, ""), (W // 2, 40), f.small,
             (255, 130, 200), "midtop")
        for i, e in enumerate(scores.top(self.game_id)):
            y = 62 + i * 18
            hot = i == self.highlight
            col = YELLOW if hot and int(self.t * 4) % 2 == 0 else (255, 255, 255)
            text(low, "%d." % (i + 1), (80, y), f.med, col)
            text(low, e["name"], (110, y), f.med, col)
            text(low, "%7d" % e["score"], (240, y), f.med, col, "topright")
        text(low, "PRESS ENTER", (W // 2, 164), f.small, (230, 220, 255), "midtop")
