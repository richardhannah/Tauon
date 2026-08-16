"""Generate a locally-compilable Inno Setup script from extra/setup.iss.

extra/setup.iss is CI-shaped and cannot be compiled on a normal checkout: it
carries {{ tauon_version }} placeholders that CI substitutes from pyproject.toml,
and its Source:/SetupIconFile paths are hardcoded to the CI runner workspace
(C:\\a\\Tauon\\Tauon\\dist\\TauonMusicBox). CI's drive-letter rewrite only swaps
C:\\, so those paths never resolve locally.

Derive a local copy rather than editing the original, so CI's sed targets stay
intact. Run from the repo root; writes dist/setup-local.iss.
"""

from __future__ import annotations

import re
from pathlib import Path

CI_PREFIX = r"C:\a\Tauon\Tauon\dist\TauonMusicBox"


def main() -> None:
	repo = Path.cwd()
	src = repo / "extra" / "setup.iss"
	if not src.is_file():
		msg = f"not in the repo root: {src} missing"
		raise SystemExit(msg)

	pyproject = (repo / "pyproject.toml").read_text(encoding="utf-8")
	match = re.search(r'^\s*version\s*=\s*"([^"]+)"', pyproject, re.M)
	if not match:
		msg = "could not read version from pyproject.toml"
		raise SystemExit(msg)
	version = match.group(1)

	bundle = repo / "dist" / "TauonMusicBox"
	out_dir = repo / "dist" / "installer"

	text = src.read_text(encoding="utf-8")
	text = text.replace("{{ tauon_version }}", version)
	text = text.replace(CI_PREFIX, str(bundle).replace("/", "\\"))
	# CI passes the output directory on the command line; make it explicit here.
	text = text.replace("Compression=lzma", f"OutputDir={str(out_dir).replace('/', chr(92))}\nCompression=lzma")

	dest = repo / "dist" / "setup-local.iss"
	dest.parent.mkdir(parents=True, exist_ok=True)
	dest.write_text(text, encoding="utf-8")

	print(f"version:   {version}")
	print(f"bundle:    {bundle}")
	print(f"installer: {out_dir / f'tauonsetup-{version}.exe'}")
	print(f"wrote:     {dest}")


if __name__ == "__main__":
	main()
