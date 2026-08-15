# CLAUDE.md

Project guidance for Claude Code. See also `AGENTS.md`, which holds the
repository's general orientation and rules (notably: **never shadow `_`** — it is
the gettext translation builtin — and `python -m py_compile` as a fast syntax
check).

## Improving the layout system as we go

`docs/layout-manager.md` records what a layout abstraction in Tauon has to
satisfy, and why. **Read it before making non-trivial changes to UI drawing
code**, and treat it as a live document.

The UI is immediate mode with hand-computed coordinates — roughly 2,600
`gui.scale` literals and 324 `coll()` hit tests in `t_main.py`, none derived from
a parent rect. The standing goal is to leave that surface slightly better than we
found it, incrementally, without a rewrite.

### When editing UI code

Apply the requirements from the doc to whatever you are already touching:

- **Derive, don't re-type.** Hit geometry must come from the same rect as the
  drawing (R3). If you move something visually, its hit rect and its
  `fields.add()` registration must move with it — they are separate
  registrations and drift silently.
- **Prefer a rect over the window.** Code that reads `window_size` directly
  cannot be reframed by the custom layout engine (R2). If a panel is already
  rect-based, keep it that way.
- **Don't add new magic numbers where a derivation exists.** If nearby code
  computes a shared offset, hang off it rather than adding another literal (R4).
- **Watch for duplicated size facts.** `gui.panelBY` and
  `PlaybackPanelWidget.fixed_h` are the known case (R6); don't add more.
- **State what happens when it doesn't fit.** Layouts must degrade explicitly at
  small window sizes rather than overlapping (R7).

### Surface opportunities, don't take them unasked

When you notice a change that would advance the requirements — a panel that
could be rect-based, a hand-rolled button that could use a shared helper, a
duplicated size constant — **mention it and let the user decide**. Do not fold a
speculative refactor into an unrelated task. `t_main.py` is 60k lines with no UI
test suite, and every refactor makes upstream merges harder.

The exception is when the requirement is directly implicated in the bug you were
asked to fix; then fix it properly rather than working around it.

### The blocker worth remembering

`TDraw` has **no scissor or clip support**, so a widget cannot be prevented from
drawing outside its bounds. This is why several fixes have to be "do not draw it"
rather than "clip it". Adding a clip stack over `SDL_SetRenderClipRect` is the
recommended first move (R1) — if a task is heading somewhere that needs
clipping, say so rather than working around it again.

### Verifying UI changes

There is no UI test suite; changes are verified by running the app and looking
at it. At minimum, after a layout change: check a wide window and a narrow one
(< 650 logical px triggers `compact`), scroll any affected list to both ends, and
confirm interactive elements are clickable exactly where they appear. Hit rects
are invisible, which is how they drift — a debug overlay stroking
`Fields.field_array` is the proposed fix for that and is worth building when
layout work starts in earnest.
