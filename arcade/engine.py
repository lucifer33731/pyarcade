"""Shared engine for the retro arcade: display, input, sound, scenes."""
import array
import math
import random
import sys
from types import SimpleNamespace

import pygame

W, H = 320, 180            # low-res "pixel" canvas every game draws on
SCALE = 3                  # window is W*SCALE x H*SCALE
SW, SH = W * SCALE, H * SCALE
FPS = 60

# One place that maps physical keys to game actions.
KEYMAP = {
    "left": (pygame.K_LEFT, pygame.K_a),
    "right": (pygame.K_RIGHT, pygame.K_d),
    "up": (pygame.K_UP, pygame.K_w),
    "down": (pygame.K_DOWN, pygame.K_s),
    "fire": (pygame.K_SPACE, pygame.K_z, pygame.K_LCTRL),
    "start": (pygame.K_RETURN, pygame.K_KP_ENTER),
    "back": (pygame.K_ESCAPE,),
    "pause": (pygame.K_p,),
}


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def mix(a, b, t):
    return (int(a[0] + (b[0] - a[0]) * t),
            int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))


# --------------------------------------------------------------------------
# Drawing helpers
# --------------------------------------------------------------------------
def sprite_from_rows(rows, color, scale=1):
    """Build a pixel-art sprite from strings. 'X' = pixel, '.' = empty.
    `color` can be one RGB tuple or a dict mapping characters to colors."""
    h, w = len(rows), len(rows[0])
    s = pygame.Surface((w * scale, h * scale), pygame.SRCALPHA)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch == ".":
                continue
            c = color[ch] if isinstance(color, dict) else color
            s.fill(c, (x * scale, y * scale, scale, scale))
    return s


def text(surf, msg, pos, font, color=(255, 255, 255), anchor="topleft",
         shadow=(20, 10, 40)):
    img = font.render(msg, False, color)
    r = img.get_rect(**{anchor: pos})
    if shadow:
        surf.blit(font.render(msg, False, shadow), r.move(1, 1))
    surf.blit(img, r)
    return r


def wrap(msg, font, max_w):
    lines, cur = [], ""
    for word in msg.split():
        t = (cur + " " + word).strip()
        if font.size(t)[0] <= max_w:
            cur = t
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


_bg_cache = {}
HORIZON_Y = 100


def _sky_col(y):
    return mix((18, 8, 52), (255, 110, 150), (y / float(HORIZON_Y)) ** 1.5)


def draw_synth_bg(low, t):
    """Animated synthwave backdrop used by the menu screens."""
    sky = _bg_cache.get("sky")
    if sky is None:
        sky = pygame.Surface((W, H))
        for y in range(HORIZON_Y + 1):
            pygame.draw.line(sky, _sky_col(y), (0, y), (W, y))
        cx, cy = W // 2, HORIZON_Y - 8
        pygame.draw.circle(sky, (255, 120, 140), (cx, cy), 38)
        pygame.draw.circle(sky, (255, 210, 100), (cx, cy), 33)
        for k in range(6):
            y = cy + 2 + k * 5
            for yy in range(y, min(HORIZON_Y + 1, y + 1 + k // 2)):
                pygame.draw.line(sky, _sky_col(yy), (cx - 40, yy), (cx + 40, yy))
        sky.fill((14, 6, 38), (0, HORIZON_Y + 1, W, H - HORIZON_Y))
        _bg_cache["sky"] = sky
    low.blit(sky, (0, 0))
    vx = W / 2
    for i in range(-12, 13):
        pygame.draw.line(low, (150, 36, 150), (int(vx + i * 6), HORIZON_Y),
                         (int(vx + i * 55), H))
    for k in range(10):
        f = ((k + t * 0.7) % 10) / 10.0
        y = HORIZON_Y + (H - HORIZON_Y) * f * f
        pygame.draw.line(low, (255, 60, 200), (0, int(y)), (W, int(y)))


# --------------------------------------------------------------------------
# Input
# --------------------------------------------------------------------------
class Input:
    def __init__(self):
        self.keys = None
        self.pressed = set()      # actions that went down this frame

    def update(self, events):
        self.keys = pygame.key.get_pressed()
        self.pressed = set()
        for e in events:
            if e.type == pygame.KEYDOWN:
                for action, ks in KEYMAP.items():
                    if e.key in ks:
                        self.pressed.add(action)

    def held(self, action):
        return any(self.keys[k] for k in KEYMAP[action])


# --------------------------------------------------------------------------
# Sound: every effect is synthesized, no audio files needed
# --------------------------------------------------------------------------
class Sound:
    def __init__(self):
        self.enabled = False
        self.muted = False
        self.bank = {}
        try:
            init = pygame.mixer.get_init()
            if not init:
                pygame.mixer.init(22050, -16, 1, 512)
                init = pygame.mixer.get_init()
            self.rate, fmt, self.channels = init
            if fmt != -16:
                return
            self._build()
            self.enabled = True
        except (pygame.error, TypeError):
            self.enabled = False

    def _wave(self, freq, dur, wave="square", vol=0.3, slide=0.0, noise=False):
        n = int(self.rate * dur)
        out = array.array("h")
        phase = hold = 0.0
        for i in range(n):
            t = i / float(n)
            phase += freq * (1.0 + slide * t) / self.rate
            if noise:
                if phase >= 1.0:
                    phase -= 1.0
                    hold = random.uniform(-1, 1)
                v = hold
            else:
                p = phase % 1.0
                if wave == "square":
                    v = 1.0 if p < 0.5 else -1.0
                elif wave == "saw":
                    v = 2 * p - 1
                elif wave == "tri":
                    v = 4 * abs(p - 0.5) - 1
                else:
                    v = math.sin(2 * math.pi * p)
            out.append(int(v * (1.0 - t) * vol * 32767))
        return out

    def _sound(self, samples):
        if self.channels == 2:
            st = array.array("h")
            for s in samples:
                st.append(s)
                st.append(s)
            samples = st
        return pygame.mixer.Sound(buffer=samples.tobytes())

    def _jingle(self, notes, wave="square"):
        out = array.array("h")
        for f, d in notes:
            out.extend(self._wave(f, d, wave, 0.25))
        return self._sound(out)

    def _build(self):
        b = self.bank
        w, s = self._wave, self._sound
        b["shoot"] = s(w(900, 0.12, "square", 0.2, -0.7))
        b["enemy_shoot"] = s(w(300, 0.15, "saw", 0.18, -0.5))
        b["explode"] = s(w(260, 0.45, vol=0.45, slide=-0.7, noise=True))
        b["boom"] = s(w(700, 0.2, vol=0.3, slide=-0.8, noise=True))
        b["select"] = s(w(660, 0.05, "square", 0.22))
        b["back"] = s(w(440, 0.06, "square", 0.22))
        b["deny"] = s(w(160, 0.15, "saw", 0.22))
        b["powerup"] = s(w(500, 0.25, "square", 0.22, 1.5))
        b["ufo"] = s(w(1100, 0.1, "sine", 0.18, -0.3))
        b["start"] = self._jingle([(523, 0.07), (659, 0.07), (784, 0.07), (1047, 0.18)])
        b["jingle"] = self._jingle([(523, 0.1), (659, 0.1), (784, 0.1), (659, 0.1), (1047, 0.3)])
        b["gameover"] = self._jingle([(392, 0.2), (349, 0.2), (294, 0.2), (196, 0.5)], "tri")
        for i, f in enumerate((98, 87, 82, 73)):
            b["step%d" % i] = s(w(f, 0.07, "square", 0.28))

    def play(self, name):
        if self.enabled and not self.muted and name in self.bank:
            self.bank[name].play()


# --------------------------------------------------------------------------
# Scenes and the app
# --------------------------------------------------------------------------
class Scene:
    """Base class: every screen (menu, game, score table) is a Scene."""
    offset = (0, 0)           # screen-shake offset in window pixels
    app = None

    def on_enter(self):
        pass

    def handle_event(self, e):
        pass

    def update(self, dt, inp):
        pass

    def draw(self, low):      # draw onto the W x H canvas
        pass

    def draw_overlay(self, screen):  # optional full-res drawing (HUD text)
        pass


class App:
    def __init__(self):
        pygame.mixer.pre_init(22050, -16, 1, 512)
        pygame.init()
        pygame.display.set_caption("RETRO ARCADE")
        self.screen = pygame.display.set_mode((SW, SH))
        self.low = pygame.Surface((W, H))
        self.big = pygame.Surface((SW, SH))
        self.clock = pygame.time.Clock()
        self.fonts = SimpleNamespace(small=pygame.font.Font(None, 16),
                                     med=pygame.font.Font(None, 26),
                                     big=pygame.font.Font(None, 46))
        self.sound = Sound()
        self.input = Input()
        self.crt = self._build_crt()
        self.crt_on = True
        self.scene = None
        self.menu_state = (0, 0)

    def _build_crt(self):
        """Scanlines + vignette, built once and laid over every frame."""
        scan = pygame.Surface((SW, SH), pygame.SRCALPHA)
        for y in range(SCALE - 1, SH, SCALE):
            scan.fill((0, 0, 0, 60), (0, y, SW, 1))
        sw, sh = SW // 8, SH // 8
        vig = pygame.Surface((sw, sh), pygame.SRCALPHA)
        for y in range(sh):
            for x in range(sw):
                dx = (x / (sw - 1.0) - 0.5) * 2
                dy = (y / (sh - 1.0) - 0.5) * 2
                d = math.sqrt(dx * dx * 0.9 + dy * dy)
                a = int(clamp((d - 0.6) / 0.9, 0.0, 1.0) ** 2 * 170)
                vig.set_at((x, y), (0, 0, 0, a))
        vig = pygame.transform.smoothscale(vig, (SW, SH))
        vig.blit(scan, (0, 0))
        return vig

    # -- navigation helpers used by scenes ---------------------------------
    def change(self, scene):
        scene.app = self
        self.scene = scene
        scene.on_enter()

    def go_menu(self):
        from menu import MenuScene
        self.change(MenuScene())

    def finish_game(self, game_id, score):
        """Called by a game when it ends: high-score entry or back to menu."""
        import scores
        if scores.qualifies(game_id, score):
            from menu import NameEntryScene
            self.change(NameEntryScene(game_id, score))
        else:
            self.go_menu()

    def quit(self):
        pygame.quit()
        sys.exit()

    # -- main loop ----------------------------------------------------------
    def run(self, first_scene):
        self.change(first_scene)
        while True:
            dt = min(self.clock.tick(FPS) / 1000.0, 1 / 30.0)
            events = pygame.event.get()
            for e in events:
                if e.type == pygame.QUIT:
                    self.quit()
                if e.type == pygame.KEYDOWN:
                    if e.key == pygame.K_F1:
                        self.crt_on = not self.crt_on
                    elif e.key == pygame.K_F2:
                        self.sound.muted = not self.sound.muted
                    elif e.key == pygame.K_F11:
                        pygame.display.toggle_fullscreen()
            self.input.update(events)
            for e in events:
                self.scene.handle_event(e)
            self.scene.update(dt, self.input)
            self.scene.draw(self.low)
            pygame.transform.scale(self.low, (SW, SH), self.big)
            self.screen.fill((0, 0, 0))
            self.screen.blit(self.big, self.scene.offset)
            self.scene.draw_overlay(self.screen)
            if self.crt_on:
                self.screen.blit(self.crt, (0, 0))
            pygame.display.flip()
