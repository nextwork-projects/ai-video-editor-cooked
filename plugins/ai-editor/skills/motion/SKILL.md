---
name: motion
description: Builds bespoke motion graphics for an edit, one animated clip per beat (HyperFrames + GSAP), each designed for its line and landing on the spoken word, then lays them on the footage through the style-edit render. Picks the beats that need motion (a count, a list, a flow, a before and after, a run, a mechanism), writes a brief per clip, runs one clip-builder agent per clip at once, gates every clip (lint, layout, render, a frame-to-frame motion check, contact sheets), and falls back to the template card for a clip that fails. Use when the user says "animation", "motion graphic", "animate this", "animate the part where I say X", "make a clip for", "build the animations", or when style-edit or visual-prep reaches the beats that need motion. Not for captions or zooms (style-edit), not for real screenshots and logos alone (overlays), not for a product demo film (product-video).
license: MIT
compatibility: Node 20+, ffmpeg and the HyperFrames CLI with GSAP, installed once by the setup skill's motion step (10-60 s, about 120 MB, plus a 200 MB headless Chrome when no Chrome is installed). Runs from the full ai-editor plugin folder.
---

# Motion

Paths: `${CLAUDE_SKILL_DIR}` means the folder containing this SKILL.md, and `${CLAUDE_PLUGIN_ROOT}` the plugin folder two levels above it.

Every question goes in the question box: the AskUserQuestion tool (2-4 options, recommended first).

One clip per beat, built for that line, never a template filled in. The template card is the fallback.
`M="${CLAUDE_SKILL_DIR}/scripts/motion.py"`; paths are relative to the library, like style-edit's. Run the
scripts with `python3` on Mac and Linux, `py` on Windows.

```
visuals.json (style-edit step 3) -> motion.py pick -> motion/<id>/{index.html, brief.md, beat.json}
  -> one clip-builder agent per clip -> motion.py check (gates + render) -> motion.py place
  -> visuals.json video_card beats -> plan.py -> stills -> render (the clip plays on its word)
```

## 0. Ready?

`python3 "${CLAUDE_PLUGIN_ROOT}/skills/setup/scripts/setup.py" doctor` shows `motion clips` ok. Setup installs
them by default; an install from before the motion step has none, so `pick` installs them itself (a few seconds,
once). If that install fails, pick prints `Animations fell back: ...` once and makes no clip folders: say that line
to the user once. The visual templates stay, and a beat whose template is only words gets no card (plan.py).

## 1. Pick the beats

```bash
python3 "$M" pick edits/<name>
```

Reads visuals.json (written by style-edit step 3 or the visual-prep agent) and style.json's `motion` block:
`{"engine": "clips" | "templates", "amount": 0-1, "kinds": {"counter", "list", "flow", "before_after",
"ui_demo", "curve", "logo": true|false}, "look": "default"}`. Every beat routed to a moving template
(`likes`, `notes`, `flow`, `side_by_side`, `progress`, `terminal`, `chat`, `toasts`, `curve`,
`logo_cluster`) with at least 1 s of room becomes a clip, up to `amount` of them. So does a beat routed anywhere
else (a card, a capture, a sticker) whose sentence is a natural list (four or more items: `notes`), a number
(`likes`), steps (first... then...: `flow`) or a before and after (`side_by_side`), one per sentence with no
animation in it already, if that kind is on; a clip that fails its checks falls back to the original beat. Each gets
`edits/<name>/motion/<id>/`: the template with its size, duration, look and the said words' times filled,
`beat.json` (cut clock) and `brief.md`. The look: `references/looks.md` (`default`, or the style's palette
and font). A user asking in chat ("animate the part where I say X"): add or change that beat in
visuals.json first (style-edit `references/shapes.md`), then pick.

## 2. Build: one clip-builder agent per clip, all in one message

For each `motion/<id>/brief.md` pick printed, launch the `clip-builder` agent
(`${CLAUDE_PLUGIN_ROOT}/agents/clip-builder.md`, opus, background) with that brief's full path, every
clip in ONE message. Each reads only its brief and `references/clip-brief-card.md`, builds `index.html`,
and runs `motion.py check` at most 3 times. Never build the clips in the main session.

During a whole edit the cut skill launches them as soon as visual-prep returns, while the user is still
reviewing the cut, so the clips are ready when the cut is approved.

## 3. Check a clip (what each agent runs)

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/run.py" "$M" check edits/<name>/motion/<id>
```

In order: `check_clip.py` (source gotchas, free), `hyperframes lint`, `hyperframes check --at-transitions`,
render, `check_motion.py` (no stall, no spike, no frame-0 flash), `check_composition.py` (advisory),
`measure_ink.py`, then `renders/sheet.png` (1 fps) and `renders/strip.png` (10 fps over the first 1.2 s).
Writes `gates.json`. Thresholds: `references/clip-brief-card.md`. Why each gotcha bites:
`references/build-loop.md`. The full rules: `references/visual-system.md`; several ideas in one clip:
`references/scenes.md`.

## 4. Look, then place

When the agents return, read each `renders/sheet.png` yourself against its line (a fresh reader who was not
told the beat is better: does it say the line?). A clip that reads wrong: send its agent the note, one more
round. Then:

```bash
python3 "$M" place edits/<name>
```

A passed clip becomes a `video_card` beat with the render (`images/motion-<id>.mp4`); `clip_motion.py`
sets `start_s` so its motion finishes 0.25 s before the card leaves. A clip that did not pass after its
rounds keeps its template beat (kept under `fallback`, restored by place). Then style-edit carries on
from step 4 (plan, stills, render). Re-run place after any rebuild.

## 5. Check it moving

Stills hide flicker. After the render, strips round at least four clip entrances, with the safe zone drawn:

```bash
python3 "$M" strips edits/<name>/render.mp4 --at <t1>,<t2>,<t3>,<t4> --out edits/<name>/stills/motion-strips.png --safe
```

Each row runs 0.4 s before to 1.1 s after its time at 10 fps. Look for a part on one frame and gone, a blank
frame between cards, a part that never moves while held, anything over the face, anything outside the box.

## On a scene draft

A clip is a `video` item the user moves, scales and trims (`lib/ai_editor/SCENE.md` "Animations are elements"). Make
its page `background: transparent` (html, body and #root) when it sits over the footage, render it with alpha, and
add it at its word, as `wait`'s `SCENE:` block says:

```bash
npx hyperframes render edits/<name>/motion/<id> --format webm -o edits/<name>/motion/<id>/renders/clip.webm
python3 "${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/scene.py" add edits/<name> video --src edits/<name>/motion/<id>/renders/clip.webm \
  --start <word time - 0.1> --x <centre x> --y <centre y> --w <width> --why "<the line it shows>"
```

VP9 WebM keeps the alpha in the page's player and in the export; an MP4 is an opaque box. A clip on its own card
ground can stay MP4 (`place`, plan, then `scene.py cards --at <t>`). Never patch-render a scene draft.

## Notes on a clip

A review-page note at a moment a clip is up ("make the counter bigger", "use blue"):

```bash
python3 "$M" note edits/<name> "make the counter bigger" --at <note time>
```

It writes the note into that clip's `notes.md` and prints the clip. Give one `clip-builder` its `brief.md`
(up to 2 more checks), then `place`, plan, and `edit.py patch` (style-edit): only that clip is rebuilt and only its
span re-rendered (each placed render has its own file name, so the patch sees the change).

## The motion library

When the user approves the render: `python3 "$M" save edits/<name>`. Each placed clip goes to
`$AI_EDITOR_HOME/motion-library/<id>/` (composition, brief, thumbnail, the style it came from). `pick` gives a beat
of the same kind the newest one (or the one marked "use again") as `start.html`: a starting point the agent
re-times and changes, never a copy (`check` fails an unchanged one). Archived clips are never used. The
window's style page lists them (Archive, Delete, Use again); in chat: `python3 "$M" library [archive|unarchive|use <id>]`.

## Settings

style.json `motion` (the style page's Motion section writes it through the user's corrections): `amount` (0
none, 0.5 some, 1 lots; unset, a measured style's animation share), `kinds` (each on or off), `look`
(`default`, `editorial`, `editorial-dark`, `mono`, `poster-red`, `poster-green`, `poster-blue`). `engine:
"templates"` keeps the template cards.

## The 50/50 style

A split-layout style (style.json `layout.mode: "split"`, the sample `50/50`): every clip is built for the panel's
art box on the panel's ground and plays edge to edge; the `panel` gate (ground at the corners, ink over 55%) and
the four proofs (`verify.mjs`) block. Variants, rules and the cutout: `references/fifty-fifty.md`.

## The Motion design style

A board-layout style (style.json `layout.mode: "board"`, the sample `Motion design`, 16:9): clips are overlays
beside the speaker, 1200x964 in the `board` look (near-black ground, silver-white ink). Logos are not clips: they
land as tiles on the canvas. The rules: `references/board.md`.

## Skill styles

A user's own style skill gets bespoke animations with one line: "Animations: use the motion skill".

## If a script stops

| message | do |
|---|---|
| `the motion tools are not installed` / `Animations fell back` | `setup.py motion`, then the same command; it fails again: say the line once and carry on without clips |
| a clip still `FAIL` after its checks (3 to build, 2 more per note) | leave it: place restores its template |
| `no frames read` (strips) | the render path is wrong or the render failed: style-edit step 7 |

## Files

- `scripts/motion.py` (pick, check, place, status, strips), `check_clip.py`, `check_motion.py`,
  `check_composition.py`, `measure_ink.py`, `clip_motion.py`: each with a `demo` self-check.
- `template/`: the HyperFrames composition every clip starts from.
- `scripts/verify.mjs`: the four proofs (clipped, rails, neighbour, reading), frame by frame in Chrome.
- `references/`: `clip-brief-card.md` (the core every agent reads), `visual-system.md`, `build-loop.md`,
  `scenes.md`, `looks.md`, `fifty-fifty.md`, `board.md`.
- HyperFrames is Apache-2.0 (github.com/heygen-com/hyperframes), GSAP is under its standard no-charge licence
  (gsap.com/standard-license); both are installed from npm by setup, not shipped here.
