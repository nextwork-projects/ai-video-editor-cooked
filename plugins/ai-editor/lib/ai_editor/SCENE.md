# scene.json: every video is a scene

Every element on screen is an item in `<edit>/scene.json`. The page edits it, the same Remotion composition
(`Scene`) draws it live in the page and renders the export. Claude and every skill write a scene, never a
flattened MP4 with things burned in. A clip that has its own animation (a HyperFrames clip, a Blender shot) is
one video item: it moves, resizes, crops and trims like any other.

```json
{
  "version": 1, "width": 1080, "height": 1920, "fps": 30, "duration": 82.5, "background": "#000000",
  "assets": {"cam": {"src": "cut.mp4", "kind": "video", "w": 1080, "h": 1920, "duration": 82.5}},
  "tracks": [
    {"id": "v1", "kind": "visual", "name": "Video", "hidden": false, "locked": false, "items": []},
    {"id": "a1", "kind": "audio", "name": "Sounds", "muted": false, "locked": false, "items": []},
    {"id": "c1", "kind": "captions", "name": "Captions", "hidden": false, "locked": false, "items": []}
  ]
}
```

- Track order is draw order: the first visual track is the bottom. Audio tracks all play.
- Times are seconds on the scene's clock. Positions and sizes are canvas pixels. `src` is relative to the edit (a raw
  take outside it may be absolute). An asset's `proxy` (`.scene/<id>.mp4`, made by scene.py) is the seek-friendly
  copy both the page and the export play once it exists. A hidden visual track still plays its clips' sound;
  `muted` on a visual track silences them. An item with `locked: true` takes no op but `set {"locked": false}`.

## Items (every item: `id`, `type`, `start`, `end`, `name`)

| type | fields |
|---|---|
| `video` | `asset`, `in` (source seconds), `speed` 1, `volume` 1, `fade_in`, `fade_out`, + visual |
| `image` | `asset`, + visual |
| `text` | `text`, `font`, `weight`, `size` (px), `color`, `align` (left, center, right), `line_height`, `box` ({`color`, `pad`, `radius`} or null), `outline` ({`color`, `width`} or null), + visual (`w` is the wrap width, `h` is ignored) |
| `shape` | `fill`, `stroke` ({`color`, `width`} or null), + visual |
| `audio` | `asset`, `in`, `speed`, `volume`, `fade_in`, `fade_out` |
| `captions` | `words` [{`w`, `start`, `end`, `p`?, `emph`?}], `style` (the caption style keys plan.py uses today), `asset` (words on that asset's clock, shown through its clips; null: the scene's clock), `pages` ([{`start`, `end`, `treat`?...}] on the same clock, `p` indexes it; without them `style.words_per_caption` pages the words), `motion` |
| `card` | `card` (a cooked. plan card: an overlay format the composition's CardView draws), `look`, `motion`, + visual (the box) |

Visual fields: `x`, `y` (the item's centre), `w`, `h`, `rotation` (degrees), `opacity` (0-1), `fit` (cover or
contain), `crop` ({`l`, `t`, `r`, `b`} as fractions of the source), `radius` (px), `shadow` ({`blur`, `y`,
`opacity`} or null), `border` ({`width`, `color`} or null), `anim` ({`in`, `out`: none, cut, fade, pop,
slide-up; `dur` seconds}), `keys` ({prop: [[t, value, ease]]}, t from the item's start; props x, y, w, h,
scale, rotation, opacity; ease linear, in, out, inout, hold; scale is about the centre), `grade` ({`brightness`,
`saturate`}). Text `box.pad` is px or [x, y]; `box.block: true` is one box round the whole text, else a box behind
each line. `outline.width` is the CSS text stroke (half of it shows outside the letters).

## Page and server

- `GET /scene`: the scene. `POST /scene/ops {"ops": [...]}` applies ops in order and returns `{"ok", "scene", "j"}`
  (`j` is the undo journal id the page already uses with `/timeline/restore`). Ops:
  `{"op": "set", "item": id, "props": {...}}`, `{"op": "add", "track": id, "item": {...}, "index"?}`,
  `{"op": "remove", "item": id}`, `{"op": "move", "item": id, "track": id, "index"?}`,
  `{"op": "track", "track": id, "props": {...}}`, `{"op": "add_track", "track": {...}, "index"?}`,
  `{"op": "remove_track", "track": id}`, `{"op": "split", "item": id, "t": seconds}`,
  `{"op": "trim", "item": id, "edge": "start" | "end", "by": seconds}` (a later edge for by > 0: the in-point
  moves with a start edge), `{"op": "asset", "id": id, "asset": {"src": "media/x.mp4"}}` (a file in the edit,
  probed). The page gets each asset with `url` (`/scene/asset/<id>?v=`, never saved).
- `window.CookedLive.mountScene(el, scene)` returns the same player stand-in `mount()` does; `.update(scene)`
  redraws at once without a reload.
- Export is one route family for both editors. `POST /export` starts it; in scene mode it renders the scene with
  Remotion (the `Scene` composition, `scene.render`), in the Classic editor it is 2.7.39's `export_src` (the draft, or
  its bake). Either way it lands in `<edit>/exports/<download name>` and the library's `exports/`. `GET /export` and
  `/state`'s `export` are the same `{state: working | done | failed, pct, elapsed, why, note, name, done_at, left_out,
  url}` (`left_out` is always null on a scene). `GET /export/file` downloads it (`url` points there once done);
  `POST /export/reveal` shows it in Finder. A scene edit never writes a note for Claude.

## Claude edits the scene

Claude's work on a scene arrives as items, never as a new render. `review.py wait` hands a send on a scene draft over with
a `SCENE:` block that says so; Claude answers each note with:

```bash
python3 scene.py show <edit> [--at t]       # the items on screen then: ids, times, boxes; the words said around t
python3 scene.py add <edit> text --text "Link in bio" --start 80 --end 82.5 [--x --y --w] [--json '{"box": {...}}'] --why "..."
python3 scene.py add <edit> image|video|audio --src <file> --start t [--end t] [--x --y --w --h] [--track name] --why "..."
python3 scene.py ops <edit> '<json ops>'|ops.json --why "<one line>"     # any op above
python3 scene.py cards <edit> [--at t,t]    # plan.json's new cards (overlays, template-filler) as items
python3 review.py <edit> round --scene       # the notes answered (resolve --reply), a round with no MP4
```

- Each command is one change: with the page's server running it goes through `POST /scene/ops` with `"by": "claude"`
  and `"why"` (the server's journal, the page draws it on its next 3 s poll with no reload); with no server it is
  written to scene.json directly. A file outside the edit is copied into `media/` first.
- Items Claude added or changed carry `by: "claude"`: a small Claude mark on their timeline clip. Any change from the
  page clears it (`scene.touch`).
- Every change is kept in `review/claude.json`: `n`, `why`, `at` [stage, round], `t`, `items`, and the ops that undo
  (`back`) and redo (`fwd`) it. `/state`'s `claude_changes` lists the draft's own and those of the round `round --scene`
  came from (`scene_from`); the notes panel shows them under **Claude's changes**, each with Undo or Redo, and each is
  one Cmd+Z ("Claude: <why>"). `POST /scene/claude {"n", "undo"}` applies its own ops, so the user's edits since stay.
- `round --scene` opens the next round on the same video (or `cut.mp4` for the first edit) with the scene as the draft:
  scene.json is snapshotted with the round's files, no MP4 is made. Export renders it when the user wants the file.
- Never `scene.py from-plan` again on a draft the user has edited: it rebuilds scene.json from plan.json and drops their
  moves. After the first draft, every change is an op.

## Animations are elements

An animated graphic (a HyperFrames or motion clip, a Blender shot) is a `video` item with alpha, moved, scaled, cropped
and trimmed like any other. The format is **VP9 WebM with alpha** (`yuva420p`; `hyperframes render <dir> --format webm`
on a `background: transparent` page writes it, `ALPHA_MODE=1`). Checked 2026-11-06 on the sample take: the page's player
(`mountScene`, Chrome's `<video>`) draws it transparent over the footage, and the export keeps the alpha because
`SceneEdit.tsx` gives `OffthreadVideo` `transparent` for an asset with `alpha: true` (frames extracted as PNG).
`probe` sets `alpha` (VP9's `alpha_mode` tag, or a `yuva`/`rgba`/`gbrap` pix_fmt). ProRes 4444 `.mov` has alpha but
Chrome cannot play it: such an asset gets a VP9 alpha proxy (`.scene/<id>.webm`) that both the page and the export
play. An H.264 MP4 has no alpha: a clip on its own ground is an opaque box.

## When a draft is a scene

- A draft opens in scene mode when `scene.json` is there, or when it is a cooked. plan draft that `scene.from_plan`
  converts: the edit (not the stills sheet), `plan.json` there, the cut it was made from, and not a draft finished by
  hand (a layer draft). A plan `from_plan` refuses (split, board, cover, cutouts) opens in the Classic editor.
- Every other draft opens in the Classic editor (texts.json, overrides.json, the bake) until `from_video` is proven.
- The ⋯ menu's "Classic editor" puts this video back in the old editor, and "Back to the scene editor" undoes it. It is
  the file `<edit>/.classic` (`POST /scene/classic {"on": true | false}`). scene.json stays as it was while the video
  is in the Classic editor: edits made there do not reach it.
- `/state` has `scene` (the page edits the scene now), `scene_able` (the switch shows) and `classic`.

## The AI's cuts are clips

The footage is never one baked cut. The main video track holds one `video` item per piece the cut kept, all on
the RAW take (`asset` = the source the cut was made from, `in` = where that piece starts in it), back to back.
Each item carries `cut` ({`before`: {`reason`: retake, false start, pause, filler, by hand, `words`: "...",
`dur`: seconds}}) for what was taken out just before it. Dragging a clip's edge outward brings removed footage
back, inward cuts more (`trim`); the track's `magnet: true` (the default on the first visual track only) closes
or opens the gap and moves every later item on every track by the same amount (an item across the edge grows or
shrinks), so captions, texts and cards stay on their words. `remove` of a clip on it closes the gap; `set` of
start, end or in never ripples. Captions are timed
from the raw take's words through the same clips, so a restored piece gets its captions back.

## Migration

- A cooked. plan draft becomes a scene (`scene.py from-plan`): the footage as the clips above (from spans.json
  or the cut's decisions), framing and grade on each clip, zooms as keys on the clips they fall in, each card as an image or video item, each text as a text item, captions as one captions item, every
  sound as an audio item.
- Any other draft becomes a scene with its MP4 as one locked video item on the bottom track; new items go above.
- A skill writes a scene, never a flattened MP4: SCENE-SKILLS.md (what changes in a house skill).
- `scene.py` is also the helper skills call: `Scene(w, h, fps)`, `.video(src, ...)`, `.image(...)`,
  `.text(...)`, `.audio(...)`, `.captions(...)`, `.save(edit)`.
