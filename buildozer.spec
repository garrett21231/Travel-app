[app]
title = Trip Planner
package.name = tripplanner
package.domain = org.local
source.dir = .
source.include_exts = py,png
source.exclude_dirs = .venv-kivy,tests,__pycache__,.git
version = 0.1.0
requirements = python3,kivy==2.3.1
orientation = portrait
fullscreen = 0
android.api = 35
android.minapi = 23
android.archs = arm64-v8a

[buildozer]
log_level = 2
warn_on_root = 1
