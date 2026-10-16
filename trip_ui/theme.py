"""Shared UI colors and the bundled asset location.

Change colors here to update all screens. Assets stay in the project's assets
folder, independent of the directory used to launch the application.
"""
from pathlib import Path
from kivy.utils import get_color_from_hex

BLACK, WHITE, BLUE, MUTED, RED = map(get_color_from_hex, ('#000000', '#ffffff', '#6b83ff', '#bdbdbd', '#ff8686'))
ASSETS = Path(__file__).resolve().parents[1] / 'assets'
