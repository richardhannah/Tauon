---
name: clean-reinstall
description: Wipe Tauon and reinstall it from an installer built out of the current working tree - uninstall the existing app, delete the settings directory, build the PyInstaller bundle and Inno Setup installer, install silently, launch. Use when asked for a clean reinstall, to see the true first-run experience, or to verify that a changed default actually ships rather than living in local state.
---

# Clean reinstall (Windows)

Rebuilds and reinstalls Tauon from scratch, discarding all settings. The point is
a **genuine first run**: an empty profile plus a build of the current tree, which
is the only way to see what a new user gets and to prove a default ships in the
code rather than surviving in `state.p`.

**This destroys the library, playlists, ratings and keymap.** They live in
`%LOCALAPPDATA%\TauonMusicBox`, which the uninstaller deliberately leaves behind.
Only run this when the user has said losing them is fine.

## Prerequisites

All were present as of 2026-08-16; check before building, because PyInstaller
hard-errors late on a missing `fonts/`.

```bash
cd /d/projects/Tauon
ls fonts/ | wc -l                                  # expect 8 Noto fonts (~51 MB)
ls TauonSMTC.dll lrclib-solver.exe                 # repo root copies, for the spec
ls .venv/bin/pyinstaller.exe                       # not in requirements.txt; CI installs separately
ls "/c/Program Files (x86)/Inno Setup 6/ISCC.exe"  # choco install innosetup -y
```

The repo-root `TauonSMTC.dll` / `lrclib-solver.exe` are distinct from the
`src/tauon/` copies the source build reads. `/TauonSMTC.dll` is in
`.git/info/exclude` because `.gitignore` covers `lib/` and `*.exe` but not a root
`*.dll`.

## Steps

Run everything from `D:\projects\Tauon`. Build steps need **MSYS2 MINGW64**;
invoke it with an LF script file, never inline `-lc` from PowerShell 5.1 (it
mangles quotes and backslashes).

### 1. Stop and uninstall

```powershell
Get-Process | Where-Object { $_.MainWindowTitle -like "*Tauon*" } | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
$u = "C:\Program Files\Tauon Music Box\unins000.exe"
if (Test-Path $u) { Start-Process $u -ArgumentList "/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART" -Wait }
```

Inno's uninstaller relaunches itself from a temp copy, so `-Wait` can return
early. Confirm `C:\Program Files\Tauon Music Box` is gone before continuing; poll
for a few seconds if needed. If Tauon was never installed, skip this - the build
and install steps still work.

### 2. Delete the settings

```powershell
Remove-Item "$env:LOCALAPPDATA\TauonMusicBox" -Recurse -Force -ErrorAction SilentlyContinue
```

If the tool layer blocks deleting user data, rename instead - it achieves the
same clean profile and is reversible:

```powershell
Move-Item "$env:LOCALAPPDATA\TauonMusicBox" "$env:LOCALAPPDATA\TauonMusicBox.replaced" -Force
```

Contents for reference: `state.p` (library + playlists + view state), `star.p`
(ratings/playtime), `tauon.conf`, `window.p`, `custom_layouts.json`, `input.txt`
(keymap), artist images, scaled icons.

### 3. Build the bundle

Write an LF script and run it under MINGW64; takes about a minute.

```bash
#!/bin/bash
set -e
cd /d/projects/Tauon
source .venv/bin/activate
rm -rf dist/TauonMusicBox
pyinstaller packaging/pyinstaller/windows.spec --noconfirm
```

```powershell
$env:MSYSTEM='MINGW64'; & C:\msys64\usr\bin\bash.exe -l <script.sh>
```

Expect `dist/TauonMusicBox/` containing `Tauon Music Box.exe` and `_internal`.
**Do not create `dist/TauonMusicBox/_internal/portable`** - that marker is only
for the portable 7z, and CI deletes it before running Inno.

### 4. Generate the .iss and compile

`extra/setup.iss` cannot be compiled as-is, so derive a local copy (never edit
the original - CI seds it). The helper beside this skill does the substitution:

```powershell
$env:MSYSTEM='MINGW64'; & C:\msys64\usr\bin\bash.exe -l <script.sh>   # python .claude/skills/clean-reinstall/make_iss.py
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" "D:\projects\Tauon\dist\setup-local.iss"
```

Produces `dist/installer/tauonsetup-<version>.exe` (~90 MB, ~25 s to compress).
The version comes from `pyproject.toml`.

### 5. Install and launch

```powershell
Start-Process "D:\projects\Tauon\dist\installer\tauonsetup-<version>.exe" `
  -ArgumentList "/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART" -Wait
Start-Process "C:\Program Files\Tauon Music Box\Tauon Music Box.exe"
```

`/VERYSILENT` skips the installer's own post-install launch (its `[Run]` entry is
`skipifsilent`), so launch it explicitly.

## Verify

Screenshot the first run and check the shipped defaults are what the code says.
Use `PrintWindow(hwnd, hdc, 2)` rather than `CopyFromScreen` - it captures the
window even when another app covers it, which matters on this machine.

As of 2026-08-16 a correct first run shows: a 1120x600 window, the **Ember**
theme, the playlist side panel on the left, columns on with **Artist / Title / T
/ Album / Time**, the art panel on the right at 300px, and "Playlist is empty".

If a default looks wrong here but right in the source build, the source build was
reading a stale value out of `state.p` - which is exactly the failure this skill
exists to catch.

## Notes

- The installed build and a source run (`python src/tauon/__main__.py`) share
  `%LOCALAPPDATA%\TauonMusicBox`, so after this the source build also starts from
  the empty profile, and anything imported appears in both.
- Single-instancing keys off a lock on `program.pid` in that directory; a second
  instance exits silently. Stop the running one first.
- `run.sh`'s `win_build` also copies `/mingw64/etc/fonts` into
  `dist/TauonMusicBox/etc` for the `FONTCONFIG_PATH` set in pyinstaller mode. CI
  does not, and the bundle runs fine without it.
