"""Tests for the layout primitives in t_layout.

These are pure geometry with no SDL, window or theme dependency, which is the
point: the panels that use them cannot be tested without running the app, but
the rect algebra underneath them can be. See docs/layout-manager.md.
"""

from tauon.t_modules.t_layout import Column, ControlRow, Rect


def test_rect_is_a_plain_tuple() -> None:
	"""Existing call sites index rects positionally, so Rect must stay a tuple."""
	r = Rect(10, 20, 30, 40)
	assert r[0] == 10
	assert r[1] == 20
	assert r[2] == 30
	assert r[3] == 40
	assert tuple(r) == (10, 20, 30, 40)
	x, y, w, h = r
	assert (x, y, w, h) == (10, 20, 30, 40)
	assert r == (10, 20, 30, 40)


def test_rect_edges() -> None:
	r = Rect(10, 20, 30, 40)
	assert r.right == 40
	assert r.bottom == 60
	assert r.centre_x == 25
	assert r.centre_y == 40


def test_rect_inset_and_grow() -> None:
	r = Rect(0, 0, 100, 50)
	assert r.inset(left=10) == (10, 0, 90, 50)
	assert r.inset(right=10) == (0, 0, 90, 50)
	assert r.inset(top=5, bottom=5) == (0, 5, 100, 40)
	assert r.inset(left=10, top=5, right=10, bottom=5) == (10, 5, 80, 40)
	# grow is inset outwards, so the two undo each other
	assert r.inset(left=4, top=3).grow(left=4, top=3) == r
	assert r.grow(top=1) == (0, -1, 100, 51)


def test_rect_move_and_resize() -> None:
	r = Rect(10, 10, 100, 50)
	assert r.move(dx=5) == (15, 10, 100, 50)
	assert r.move(dy=-5) == (10, 5, 100, 50)
	assert r.resize(w=20) == (10, 10, 20, 50)
	assert r.resize(h=20) == (10, 10, 100, 20)
	assert r.resize() == r


def test_rect_edge_strips() -> None:
	r = Rect(10, 20, 100, 50)
	assert r.left_edge(4) == (10, 20, 4, 50)
	assert r.right_edge(4) == (106, 20, 4, 50)
	assert r.top_edge(4) == (10, 20, 100, 4)
	assert r.bottom_edge(4) == (10, 66, 100, 4)


def test_rect_clip_to() -> None:
	panel = Rect(0, 100, 200, 400)
	assert Rect(10, 150, 50, 20).clip_to(panel) == (10, 150, 50, 20)  # wholly inside
	assert Rect(10, 600, 50, 20).clip_to(panel) is None               # below
	assert Rect(300, 150, 50, 20).clip_to(panel) is None              # beside
	# The case the playlist panel relies on: a row hanging off the bottom edge
	# keeps only its visible part, so it cannot answer clicks below the panel.
	assert Rect(10, 480, 50, 40).clip_to(panel) == (10, 480, 50, 20)
	# Touching but not overlapping is not an overlap
	assert Rect(10, 500, 50, 20).clip_to(panel) is None


def test_column_whole_rows() -> None:
	def fits(h: float) -> int:
		return Column(Rect(0, 0, 100, h), row_h=25, gap=2).whole_rows()

	# Three rows need 25*3 + 2*2 = 79: the gaps between them count, the one
	# that would follow the last row does not.
	assert fits(79) == 3
	assert fits(78) == 2
	assert fits(81) == 3  # 79 plus slack, still three
	assert fits(25) == 1  # exactly one row, no gap needed
	assert fits(24) == 0
	assert fits(0) == 0
	# A zero step would divide by zero rather than loop forever
	assert Column(Rect(0, 0, 100, 500), row_h=0, gap=0).whole_rows() == 0


def test_column_rows_are_positioned_by_index() -> None:
	col = Column(Rect(10, 100, 80, 200), row_h=25, gap=2)
	assert col.step == 27
	assert col.row(0) == (10, 100, 80, 25)
	assert col.row(1) == (10, 127, 80, 25)
	assert col.row(2) == (10, 154, 80, 25)
	# Asking twice gives the same rect: this is what lets an input pass and a
	# draw pass over the same list agree without a shared y cursor.
	assert col.row(5) == col.row(5)
	# Rows past the bottom are still returned; the caller clips or skips them.
	assert col.row(20).y == 100 + 20 * 27


def test_column_row_derives_a_tab_rect() -> None:
	"""The shape PlaylistBox uses: a row, narrowed to the tab area."""
	panel = Rect(0, 30, 200, 300)
	col = Column(panel.inset(top=5), row_h=25, gap=2)
	tab = col.row(0).inset(left=10, right=6)
	assert tab == (10, 35, 184, 25)
	assert tab.grow(top=1).clip_to(panel) == (10, 34, 184, 26)


def test_control_row_measures_itself() -> None:
	row = ControlRow(spacing=10, hit_y=5, hit_h=20)
	row.add("a", 30)
	row.add("b", 40)
	assert row.width == 80
	row.place_centred(100)
	assert row.left == 60
	assert row.x("a") == 60
	assert row.x("b") == 100
	assert row.hit("b", pad=4) == (96, 5, 48, 20)
	assert row.has("a")
	assert not row.has("c")


def test_control_row_omitted_item_needs_no_compensation() -> None:
	"""A conditionally hidden control just is not added; nothing else shifts."""
	both = ControlRow(spacing=10)
	both.add("a", 20)
	both.add("b", 20)
	both.place(0)

	one = ControlRow(spacing=10)
	one.add("b", 20)
	one.place(0)

	assert both.width == 50
	assert one.width == 20
	assert one.x("b") == 0
