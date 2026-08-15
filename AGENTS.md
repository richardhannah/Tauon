# AGENTS.md

## Purpose

This repository is Tauon, a desktop music player with a large Python/SDL UI layer.

## Big Picture

- Main Python package: `src/tauon`
- Main entrypoint: `src/tauon/__main__.py`
- Main UI/application logic: `src/tauon/t_modules/t_main.py`
- Preferences and persisted settings: `src/tauon/t_modules/t_prefs.py`
- Native audio backend implementation: `src/phazor/phazor.c`
- Integration modules live in `src/tauon/t_modules/`:
  - `t_discord.py`
  - `t_jellyfin.py`
  - `t_subsonic.py`
  - `t_tidal.py`
  - `t_webserve.py`
  - `t_lyrics.py`
  - `t_phazor.py`

## UI Layer

There is no GUI toolkit. The UI is immediate mode: panels compute rects by hand,
hit-test them with `Tauon.coll()`, and draw them directly. Useful entry points:

- `t_modules/t_draw.py` — the drawing layer (`TDraw`). Rectangles, lines and
  textures go to SDL3. **Text does not**: it is laid out with Pango and
  rasterised with Cairo, then cached as SDL textures. This is why PyGObject is a
  hard dependency, and why shaping for CJK and RTL works. There is no SDL_ttf.
- `t_modules/t_custom.py` — the user-composable layout system. A `Widget` base
  with `draw(tauon, x, y, w, h)`, a `WidgetSpec` registry of 19 widget kinds, and
  an engine that renders widgets offscreen and reframes their input. User layouts
  persist to `custom_layouts.json`.
- `t_modules/t_themeload.py` and `theme/*.ttheme` — colour themes. Theme files
  are parsed by matching a **label substring** on each line, not by line order,
  so entries can be omitted or reordered but labels must match exactly.

## Building and Running

`run.sh` is the development driver. It takes a numbered option, or presents a
menu when run with no arguments:

```bash
./run.sh 1   # clean venv: fetch sources, build the wheel, install, launch
./run.sh 2   # dirty venv: activate the existing .venv and launch
./run.sh 3   # Windows: build with PyInstaller
./run.sh 4   # compile phazor only
```

**Windows builds and runs under MSYS2 MINGW64, not native Python.**
`__main__.py` imports `gi.repository` at module scope, and PyGObject/GTK do not
build under MSVC. Install the packages listed in `extra/msyspac.txt`. The
Windows CI job in `.github/workflows/build_and_release.yaml` is the reference
setup.

Note for Windows contributors: if git is configured with `core.autocrlf=true`,
`run.sh` is checked out with CRLF line endings and MSYS2 bash will refuse it
with a bad interpreter error. The same applies to any repository text file read
by a shell loop, such as `extra/msyspac.txt`.

## Tests

```bash
PYTHONPATH=src pytest src/tauon/tests
```

Coverage is thin — a few unit tests plus `test_launch.py`, which starts
`python -m tauon` and asserts it survives a second. There is no UI test suite;
UI changes are verified by running the app and looking at it.

## Project-Specific Rules

- Do not shadow `_`. It is treated as the translation builtin in this project.

Fast syntax check:

```bash
python3 -m py_compile src/tauon/t_modules/t_main.py
```
