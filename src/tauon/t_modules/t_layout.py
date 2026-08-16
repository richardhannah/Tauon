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

from typing import NamedTuple


class Rect(NamedTuple):
	"""An (x, y, w, h) rectangle that is still an ordinary tuple.

	Subclassing tuple is the whole point: every existing call site reads rects
	positionally - `ddt.rect(r, colour)`, `coll(r)`, `fields.add(r)` all index
	r[0..3] - so a Rect can be handed to any of them unchanged, while new code
	reads and writes it by name. Migration is therefore per-expression, not
	per-call-site.

	Every method returns a new Rect; nothing mutates. Deriving one rect from
	another is how a panel stops re-typing coordinates: the derived rect carries
	no scale literal of its own, because the rect it came from already applied
	scale (see docs/layout-manager.md, R4).
	"""

	x: float
	y: float
	w: float
	h: float

	@property
	def right(self) -> float:
		return self.x + self.w

	@property
	def bottom(self) -> float:
		return self.y + self.h

	@property
	def centre_x(self) -> float:
		return self.x + self.w / 2

	@property
	def centre_y(self) -> float:
		return self.y + self.h / 2

	def inset(self, left: float = 0.0, top: float = 0.0, right: float = 0.0, bottom: float = 0.0) -> Rect:
		"""Shrink by the given amount on each edge."""
		return Rect(self.x + left, self.y + top, self.w - left - right, self.h - top - bottom)

	def grow(self, left: float = 0.0, top: float = 0.0, right: float = 0.0, bottom: float = 0.0) -> Rect:
		"""Expand by the given amount on each edge - inset outwards."""
		return self.inset(-left, -top, -right, -bottom)

	def move(self, dx: float = 0.0, dy: float = 0.0) -> Rect:
		return Rect(self.x + dx, self.y + dy, self.w, self.h)

	def resize(self, w: float | None = None, h: float | None = None) -> Rect:
		"""Same origin, new size. Omitted dimensions are kept."""
		return Rect(self.x, self.y, self.w if w is None else w, self.h if h is None else h)

	def left_edge(self, w: float) -> Rect:
		"""A full-height strip `w` wide, flush to the left edge."""
		return Rect(self.x, self.y, w, self.h)

	def right_edge(self, w: float) -> Rect:
		"""A full-height strip `w` wide, flush to the right edge."""
		return Rect(self.right - w, self.y, w, self.h)

	def top_edge(self, h: float) -> Rect:
		"""A full-width strip `h` tall, flush to the top edge."""
		return Rect(self.x, self.y, self.w, h)

	def bottom_edge(self, h: float) -> Rect:
		"""A full-width strip `h` tall, flush to the bottom edge."""
		return Rect(self.x, self.bottom - h, self.w, h)

	def clip_to(self, other: Rect) -> Rect | None:
		"""Intersection with `other`, or None if they do not overlap.

		For hit rects. TDraw clips drawing (R1) but input is not clipped, so a
		control that is only half inside its panel must have its hit rect
		trimmed separately or it answers clicks landing outside the panel.
		"""
		x1 = max(self.x, other.x)
		y1 = max(self.y, other.y)
		x2 = min(self.right, other.right)
		y2 = min(self.bottom, other.bottom)
		if x2 <= x1 or y2 <= y1:
			return None
		return Rect(x1, y1, x2 - x1, y2 - y1)


class Column:
	"""Fixed-height rows walking down a rect, addressed by index.

		rows = Column(panel.inset(top=pad), row_h=tab_h, gap=gap)
		for i in range(rows.whole_rows()):
			draw(rows.row(i))

	Indexed rather than cursor-driven because immediate-mode panels commonly
	walk the same list twice - once to handle input, once to draw - and two
	hand-advanced `y` cursors are two chances to disagree about where row n is.
	Asking for row n twice gives the same rect by construction.

	Rows past the bottom of the rect are still returned; the caller decides
	whether to skip them, clip them, or draw them as an overflow affordance.
	"""

	def __init__(self, rect: Rect, row_h: float, gap: float = 0.0) -> None:
		self.rect = rect
		self.row_h = row_h
		self.gap = gap

	@property
	def step(self) -> float:
		"""Distance from one row's top to the next."""
		return self.row_h + self.gap

	def whole_rows(self) -> int:
		"""How many rows fit entirely inside the rect.

		The trailing gap does not need to fit, only the last row's height.
		"""
		if self.step <= 0:
			return 0
		return max(0, int((self.rect.h + self.gap) // self.step))

	def row(self, index: int) -> Rect:
		return Rect(self.rect.x, self.rect.y + index * self.step, self.rect.w, self.row_h)


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
