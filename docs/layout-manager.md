# Requirements for a Tauon layout manager

This document sets out what a layout abstraction in Tauon has to satisfy before
it is worth building, and in what order it should be built. It is a requirements
note, not a design: it deliberately stops short of proposing an API.

It exists because Tauon's UI is drawn in immediate mode with hand-computed
coordinates, and every UI change currently costs more than it should. The
requirements below are drawn from the failure modes that actually occur when
editing this code, each of which is cited against real call sites.

## Where things stand

Tauon is not built on a GUI toolkit. It is best described as an immediate-mode
application drawn on SDL with a real text stack attached. Three layers, only one
of which is hand-rolled:

| Layer | Implementation |
| --- | --- |
| Widgets, layout, hit-testing | Hand-written, immediate mode |
| Drawing primitives | SDL3 via `PySDL3` (`TDraw` in `t_draw.py`) |
| Text | Pango (shaping, bidi, line-breaking) + Cairo (rasterisation), cached to SDL textures |

Images go through SDL3_image and Pillow, SVG through `Rsvg`, notifications
through `Notify`. GTK 3 appears once, only to read `gtk-decoration-layout` so
the custom-drawn window buttons match the desktop's button order
(`t_main.py`, `ColoursClass` setup) — it draws nothing.

Approximate scale of the immediate-mode surface, measured in `t_main.py`:

| Metric | Count |
| --- | --- |
| Lines | 60,529 |
| Top-level classes | 101 |
| `.coll(` hit tests | 324 |
| `fields.add(` registrations | 154 |
| `ddt.rect` calls | 521 |
| `ddt.text` calls | 601 |
| `gui.scale` occurrences | 2,601 |

That last figure is the problem in one number: roughly 2,600 independently
hand-scaled literals, none of which derive from a parent rect.

The entire input model is one function:

```python
def coll(self, r: list[int]) -> bool:
    return r[0] < self.inp.mouse_position[0] <= r[0] + r[2] and r[1] <= self.inp.mouse_position[1] <= r[1] + r[3]
```

A button is: compute a rect, ask `coll()` whether the pointer is inside it, draw
a hover colour, check `inp.mouse_click`. There is no parent, no clipping, and no
reflow.

### What already exists

`t_custom.py` (4,829 lines) is a partly-built retained layer and should be the
foundation rather than a competitor to it. It provides:

- a `Widget` base with the right contract —
  `draw(self, tauon, x, y, w, h, content_rect=None)`
- size constraints per widget: `min_w`, `min_h`, `fixed_w`, `fixed_h`, `lock_v`,
  `lock_h`
- `get_config()` / `set_config()` for persistence, serialised to
  `custom_layouts.json`
- a `WidgetSpec` registry with 19 registered widget kinds
- an engine that renders `offscreen` widgets at a `(0, 0)` origin and **reframes
  input, menus and fields** for them, via `inp.view_offset`
- `RectPanelWidget`, an adapter that wraps any panel already drawing into an
  `(x, y, w, h)` rect in about five lines

The hard part of a retained layer — reframing input for a widget that does not
know where it is on screen — is therefore already solved.

## Non-goals

**Do not adopt an off-the-shelf widget toolkit.** Dear ImGui, Nuklear and
microui all ship their own font rasterisation, which would run alongside Pango
and produce two text stacks with different shaping — Tauon currently gets CJK
and RTL right and would lose that consistency. Their visual language also
targets tools and debug UIs, which is the opposite of the goal. RmlUi can
produce a custom look, but it is a full HTML/CSS document engine and adopting it
means re-expressing the UI in RML: a rewrite, not an integration.

If an external library is ever used it should be a **layout-only** one — an
engine that computes rects and does no drawing, text or theming, so it composes
with the existing Pango/Cairo/SDL pipeline instead of replacing it.

**Do not attempt a big-bang migration.** There is no UI test suite. Changes are
verified by running the app and looking at it. A sweeping change across 500+
draw sites cannot be validated that way.

**Do not diverge gratuitously from upstream.** Every refactor of `t_main.py`
makes future upstream merges harder. Prefer changes that are additive or local.

## Requirements

### R1. Clipping is a prerequisite, not a feature — **done**

A widget must be preventable from drawing outside its own bounds, otherwise "a
widget stays inside its rect" is unenforceable and no layout abstraction built on
top can be made robust.

This was not hypothetical. `PlaylistBox.draw` renders one tab beyond the panel as
a scroll affordance, and the `clipped_to_box()` helper defined right there guards
only the *hit* rect — not the background rect, not the text. The overflow row
painted through the bottom panel. Because nothing could clip it, the fix had to
be "do not draw the row" rather than "clip the row"; that panel has since been
put back on the affordance, with the row clipped at the panel edge.

`TDraw` now has a clip stack over `SDL_SetRenderClipRect`:

```python
with ddt.clip(rect):
    ...  # or ddt.push_clip(rect) / ddt.pop_clip()
```

Because SDL applies the clip at the renderer level it covers everything —
`rect()`, `text()`, lines, images and raw `SDL_RenderTexture` calls — not just
the two primitives. Pushes nest by intersection, so a child can only shrink its
parent's region; an empty intersection draws nothing rather than silently
disabling the clip. `ddt.clipped_out(rect)` reports whether something is wholly
outside the active clip, for callers that want to skip the work rather than pay
for invisible drawing. The stack is reset in `new_frame()`, so an unbalanced push
warns once and cannot blank the session.

Two behaviours worth knowing, both verified against SDL 3.4:

- The clip belongs to the **current render target's** view. SDL keeps one per
  target and swaps it in `SDL_SetRenderTarget`, so a push and its pop must
  bracket drawing on one target. Code that renders into its own texture inside a
  clip draws unclipped in that texture's own coordinate space — correct, since it
  has its own origin — and the blit back is clipped as normal.
- Call sites must not set `SDL_SetRenderClipRect` directly. Resetting it to
  `None` by hand discards whatever clip an outer caller had pushed.

### R2. A widget receives its rect and never reads the window

A widget must derive every coordinate from the `(x, y, w, h)` it is given.
Reading `window_size` directly defeats the abstraction and breaks the offscreen
path, where the widget is rendered at a `(0, 0)` origin and reframed.

`BottomBarType1` was the counter-example: it positioned everything from
`window_size[1] - <literal>`, 29 times, and worked only because
`PlaybackPanelWidget.draw()` calls `bar.update()` and `bar.render()` against the
real window with `window_size` temporarily narrowed to the segment.

It now derives from `self.rect` instead, and reads the window in exactly one
place — `place()`, which supplies the default bottom-anchored rect when no rect
is passed. `update(rect)` and `render(rect)` accept one, so the custom layout
engine can hand the bar its segment directly rather than lying to it about the
window size. That last step is not yet taken: it cannot be exercised without
being in custom mode, so the engine still narrows `window_size` as before and
the bar computes the same rect it always did.

`PlaylistBox` is the other side of this: it took a rect already, but computed
`tab_width` as `w - tab_start` with `tab_start` absolute, which is only correct
at `x == 0`. Taking a rect is not the same as being position-independent.

### R3. Draw geometry and hit geometry share one source

Hit rects must be derived from the same rect as the drawing, not written out a
second time by hand. When they are independent, they drift.

Concretely: centring the transport cluster moved five buttons whose hit rects
were separately hardcoded and did not follow, and the play icon and its tooltip
carried literal x positions outside the shared `buttons_x_offset` and were left
behind entirely. Separately, all five hit rects extended 10–13px above their
icons — harmless while the cluster sat far left, but once centred they overhung
the panel into the content area.

Note that hit-testing (`coll`) and hover invalidation (`fields.add`) are two
separate registrations that must otherwise be kept in sync by hand. This is what
`Tauon.control()` is for (Phase 1): one rect, both registrations. Controls that
have not been migrated to it still make them separately.

### R4. Scale is applied by the layout layer

`gui.scale` appears 2,601 times in `t_main.py`. Multiplying by scale at every
literal is the mechanism by which layout knowledge is spread across the file. A
layout layer should take logical units and apply scale once, at the boundary.

### R5. Input reframing must be preserved

`Fields.add()` already translates rects by `inp.view_offset` so a widget
rendering in local view space registers hover regions in real screen
coordinates. Any new abstraction must route through this rather than around it,
or offscreen widgets will draw correctly and be un-clickable.

### R6. Fixed sizes need a single source of truth — **done**

`gui.panelBY` was `round(51 * scale)` while `PlaybackPanelWidget` separately
declared `fixed_h = 51  # = panelBY at scale 1`: two copies of one fact kept in
agreement by a comment. The bottom-bar work had to leave `panelBY` at 51
specifically to avoid desyncing them — a taller bottom bar would have silently
broken the custom layout engine.

The widget now publishes the fact and both paths read it:

```python
self.panelBY = round(PlaybackPanelWidget.fixed_h * self.scale)
self.panelY = round(TopPanelWidget.fixed_h * self.scale)
```

Note what is *not* folded in. `gui.panelY` becomes `round(100 * scale)` in the
art-header mode, which is a different layout mode rather than a second copy of
the header's intrinsic height, and `gui.panelY2` is the tab-strip height that
merely happens to equal 30. Collapsing either into the widget's `fixed_h` would
be a coincidence encoded as a dependency.

### R7. Layouts must degrade explicitly at small sizes

Constraints must be expressible well enough that a layout can state what it does
when it does not fit, rather than overlapping silently.

The centred transport cluster collides with the mode buttons below roughly
1030px, because the right-hand controls begin at `W - 380`. That is currently
handled by a hand-written width threshold and a fallback to the old left-aligned
position. A layout manager should express this as a constraint, not an `if`.

### R8. Persisted layouts must survive schema change

`custom_layouts.json` holds user layouts via `get_config`/`set_config`. Any
change to the widget model needs a migration path, or user layouts break on
upgrade. `t_db_migrate.py` is the existing precedent for versioned migration.

### R9. Layout must not own colour

Colours come from `.ttheme` files parsed in `t_themeload.py` into
`ColoursClass`. Layout code must not hardcode colour values; conversely, theme
files must not encode geometry. Keeping these orthogonal is what let the Ember
theme change the entire look without touching a layout call site.

## Suggested phasing

Ordered cheapest-first, each phase independently useful and shippable.

**Phase 0 — clipping in `TDraw`. Done.** Push/pop clip stack over
`SDL_SetRenderClipRect`, honoured by every draw path. Everything else depends on
it (R1). Applied so far to `PlaylistBox`, which bounds its tabs to the panel and
draws the overflow row again, and to `SpectrogramWidget`, which was setting the
SDL clip rect by hand. The custom-layout engine could bound each widget to its
segment, which would enforce R1 everywhere at once — but it would also clip menus
opened from inside a widget, so it needs a "chrome escapes the clip" rule first.

Note that clipping constrains *drawing* only. Hit rects are still trimmed by hand
(`clipped_to_box()`), so a partially visible row stays clickable exactly where it
is visible — the R3 problem in miniature, and one of the things a control helper
should absorb.

**Phase 1 — a control helper. Exists; migration is opportunistic.**
`Tauon.control(rect, ...)` takes one rect and does the four registrations that
were previously written out per control — `fields.add`, `coll`, the click flags,
and a tooltip — returning a `Control` with `hover`, `click`, `right_click`,
`middle_click` and `down`. The click flags are gated on hover, so `if c.click:`
is the whole test and there is no separate hit test to forget.

Two things it deliberately does not do:

- **It does not consume clicks.** A control that must stop later handlers seeing
  a click still clears `inp.mouse_click` itself, so that stays visible at the
  call site instead of becoming a hidden side effect of the helper.
- **It does not choose colour.** Appearance depends on more than hover — latched,
  active, menu-open — and layout code owns no colour (R9). The helper's
  contribution is that hover is computed once from the same rect that was
  registered, so the colour decision cannot disagree with the hit test.

Sites whose tooltip depends on state that settles later in the frame (the back
button suppresses its tip right after a click; repeat suppresses it while a mode
menu is open) skip the `tooltip=` argument and call the tooltip themselves,
gated on `c.hover`.

Migrated so far: the five transport buttons in `BottomBarType1` — the cluster
whose hit rects drifted, so the R3 case is now expressed in the API — and the
two `display_*_heart` hover rows, which exercise the `field_callback` path. The
remaining ~140 sites should be converted when they are being edited anyway, not
in a sweep.

**Phase 2 — layout primitives. Started.** `t_layout.py` holds `Rect`, `Column`
and `ControlRow`. They compute rects and nothing else: no drawing, no colour, no
app state, so they are unit-testable — `src/tauon/tests/test_layout.py` is the
first test coverage this work has had.

`Rect` is a `NamedTuple`, which is the load-bearing decision: existing call sites
read rects positionally (`ddt.rect`, `coll`, `fields.add` all index `r[0..3]`),
so a `Rect` can be passed to any of them unchanged. Migration is therefore per
expression rather than per call site, and a panel can be converted in pieces.
Its operations are `inset`/`grow`, `move`/`resize`, the edge strips
(`left_edge`, `right_edge`, `top_edge`, `bottom_edge`) and `clip_to`, which is
the general form of the hit-rect trimming that panels were writing by hand.

`Column` hands out fixed-height rows by index rather than from a cursor,
because immediate-mode panels commonly walk the same list twice — once for
input, once for drawing — and two hand-advanced `y` cursors are two chances to
disagree about where row *n* is (R3).

On R4, measured on `PlaylistBox.draw` (372 lines before, 369 after):

| | before | after |
| --- | --- | --- |
| references to `tab_start` / `tab_width` / `yy` | 62 | 0 |
| reads of the raw `x, y, w, h` parameters | 34 | 2 |
| `gui.scale` multiplications | 31 | 32 |

The scale count is the honest part: primitives do **not** reduce it, and a
wrapper renaming `10 * gui.scale` to `u(10)` would only have moved it. What they
remove is coordinate re-typing — 62 uses of three hand-maintained scalars became
zero, and the panel's own parameters are now read exactly twice, in the signature
and in `panel = Rect(x, y, w, h)`. Every rect after that is derived, and a
derived rect carries no coordinate and no scale of its own:
`tab.right_edge(self.indicate_w)`, `row.inset(left=indent)`. Scale is applied
where a panel establishes its metrics; everything downstream inherits it. The
`gui.scale` figure will fall when the *metrics* move behind the layer, not from
renaming multiplications.

Migrated: `PlaylistBox`, whose rows, tab rects, indicators, hit rects and
trailing drop area are all derived from the rect it is given. This also fixed a
latent R2 bug: `tab_width` was computed as `w - tab_start` with `tab_start`
absolute, which is only correct while the panel sits at `x == 0`. It always does
today, so nothing changed visibly — but the panel is now genuinely
position-independent.

Verified by capturing the panel before and after, with and without the hit-rect
overlay: all four images are pixel-identical, so neither the drawing nor any hit
rect moved. That only proves it at `gui.scale == 1`, which is what the
development machine runs.

**Phase 3 — migrate panels onto `Widget`. Started.** The rect-based panels
(playlist list, queue, artist list, folder nav, artist info) were already
widgets through `RectPanelWidget` and are fully interactive in custom mode. What
remained were the two window-reading panels, wrapped by narrowing `window_size`
and rendering offscreen — the workaround R2 describes.

Done so far: R6 (above), so the two panel heights have one source; and the R2
conversion of `BottomBarType1`, from 29 window reads to one. The header bar is
the same shape of work and has 11.

The step after that is the payoff: `PlaybackPanelWidget.draw()` passing its own
rect to `bar.update()`/`bar.render()` instead of relying on the engine narrowing
`window_size`. The bar already accepts it. It is held back because it can only be
exercised from custom mode, which needs a custom layout configured to test —
worth doing by someone who runs custom mode, not blind.

`BottomBarType_ao1`, the shuffle-lock variant, still reads the window 22 times.
It duplicates `BottomBarType1` with small differences and has already drifted;
see the open question below before converting it, because the answer changes
whether it is worth converting at all.

**Phase 4 — consider an external layout engine.** Only if real flexbox
semantics turn out to be needed. Any candidate must build for the MSYS2/MINGW64
toolchain — the mingw ABI rules out wheel-only distributions.

## Verification

There is no UI test suite, so changes are verified by running the app and
inspecting it. The checks that caught real regressions during the bottom-bar and
side-panel work, and which should be repeated for layout changes:

1. Render at a wide window and confirm no element overlaps another.
2. Render at a narrow window (< 650 logical px triggers `compact`) and confirm
   the layout degrades rather than collides.
3. Scroll any list to both ends; confirm the last item is fully drawn and
   reachable.
4. Confirm every interactive element is clickable where it appears, and *not*
   clickable where it does not.

Check 4 used to be the weakest, because hit rects are invisible. There is now an
overlay for it: **Settings → Advanced → Editing and diagnostics → "Show hit
rectangles"**. It strokes, over the finished frame:

- every hover field in `Fields.field_array` (blue),
- every rect passed to `coll()` this frame (green),
- anything under the pointer (red), which answers "what would this click hit",
- a count of each in the corner.

Hit rects are recorded inside `coll()` itself, so all 300-odd call sites are
covered without touching any of them, and they are translated by
`inp.view_offset` exactly as `Fields.add()` does — an offscreen widget is drawn
where it is actually clickable, so a reframing bug shows up as an offset outline
rather than staying invisible (R5).

Drawing the two registrations in two colours is the point: they are kept in sync
by hand, so when a control moves and only one of them follows, the outlines come
apart on screen. That is the R3 failure mode, made visible. The flag is runtime
only and resets on restart.

## Open questions

- Should the standard (non-custom) layout eventually be expressed as a default
  `custom_layouts.json`, collapsing the two rendering paths into one? That would
  remove the R6 class of duplication entirely, but it is a large change.
- `BottomBarType_ao1` duplicates `BottomBarType1` with small differences and has
  already drifted. Should the shuffle-lock variant be a configuration of one bar
  rather than a second class?
- How much of `t_main.py` is worth migrating at all, versus leaving stable panels
  untouched? Migration has a cost and no user-visible benefit on its own.
