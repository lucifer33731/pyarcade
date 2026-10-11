#!/usr/bin/env python3
"""
RETRO ARCADE - a pixel-art arcade cabinet made with Pygame.

Install:  pip install pygame
Run:      python main.py

Menu:  arrows to browse, Enter to play, Esc to quit
Keys:  F1 toggles the CRT filter, F2 mutes sound, F11 toggles fullscreen
"""
import os
import sys

# Make sure imports work no matter where the game is launched from.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine import App          # noqa: E402
from menu import MenuScene      # noqa: E402


def main():
    App().run(MenuScene())


if __name__ == "__main__":
    main()
