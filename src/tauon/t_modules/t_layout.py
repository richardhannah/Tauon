"""Tauon Music Box - Layout helpers for the immediate-mode UI

Small primitives that compute rects, so panels stop carrying hand-written
coordinates for every control. See docs/layout-manager.md for the requirements
these are meant to satisfy; the important ones here are that a row measures
itself (so nothing has to maintain a magic width constant alongside it) and that
one rect serves both drawing and hit-testing.

These deliberately do no drawing, own no colour, and do not nest. They hand back
rectangles; the caller draws.
"""

# Copyright © 2015-2026, Taiko2k captain(dot)gxj(at)gmail.com

#     This file is part of Tauon Music Box.
#
#     Tauon Music Box is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
#
#     Tauon Music Box is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU Lesser General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with Tauon Music Box.  If not, see <http://www.gnu.org/licenses/>.
from __future__ import annotations


class ControlRow:
	"""A horizontal run of controls that measures and positions itself.

	Usage is immediate mode: declare the items every frame, place the row, then
	read back a rect per item.

		row = ControlRow(spacing=36 * scale, hit_y=y, hit_h=h)
		if show_play:
			row.add("play", play_icon.w)
		row.add("pause", 14 * scale)
		row.place_centred(window_w / 2)

		rect = row.hit("pause", pad=12 * scale)
		if coll(rect):
			...
		draw_at(row.x("pause"))

	Because the row is built from the items actually present, a conditionally
	hidden control needs no compensating offset - you simply do not add it.
	"""

	def __init__(self, spacing: float, hit_y: float = 0.0, hit_h: float = 0.0) -> None:
		self.spacing = spacing
		self.hit_y = hit_y
		self.hit_h = hit_h
		self._widths: dict[str, float] = {}
		self._order: list[str] = []
		self._x: dict[str, float] = {}

	def add(self, key: str, width: float) -> None:
		"""Append an item of the given content width."""
		if key in self._widths:
			raise ValueError(f"duplicate ControlRow key: {key}")
		self._order.append(key)
		self._widths[key] = width

	def has(self, key: str) -> bool:
		return key in self._widths

	@property
	def width(self) -> float:
		"""Total width of the row, including the gaps between items."""
		if not self._order:
			return 0.0
		return sum(self._widths.values()) + self.spacing * (len(self._order) - 1)

	def place(self, left: float) -> None:
		"""Position the row with its left edge at `left`."""
		x = left
		self._x.clear()
		for key in self._order:
			self._x[key] = x
			x += self._widths[key] + self.spacing

	def place_centred(self, centre: float) -> None:
		self.place(round(centre - (self.width / 2)))

	def place_right(self, right: float) -> None:
		"""Position the row with its right edge at `right`."""
		self.place(round(right - self.width))

	@property
	def left(self) -> float:
		"""Left edge of the row itself. Valid only after placing."""
		return self._x[self._order[0]] if self._order else 0.0

	def x(self, key: str) -> float:
		"""Left edge of an item's content. Valid only after placing."""
		return self._x[key]

	def hit(self, key: str, pad: float = 0.0) -> tuple[float, float, float, float]:
		"""Hit rect for an item, widened by `pad` on each side.

		Derived from the same position the caller draws at, so the two cannot
		drift apart. Keep `pad` below half the row spacing or adjacent items'
		rects will overlap and the wrong control will take the click.
		"""
		return (self._x[key] - pad, self.hit_y, self._widths[key] + (pad * 2), self.hit_h)
