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
- Export is one route family. `POST /export` starts it and renders the scene with Remotion (the `Scene` composition,
  `scene.render`). It lands in `<edit>/exports/<download name>` and the library's `exports/`. `GET /export` and
  `/state`'s `export` are the same `{state: working | done | failed, pct, elapsed, why, note, name, done_at, left_out,
  url}` (`left_out` is always null on a scene). `GET /export/file` downloads it (`url` points there once done);
  `POST /export/reveal` shows it in Finder. A scene edit never writes a note for Claude.

## When a draft opens in scene mode

- Every draft on the edit opens in the scene editor, by itself. There is no other editor and no switch. The cut stage
  and the stills sheet keep their own pages: they are not the edit. `/state`'s `scene` is true on the edit.
- scene.json is made on the first ask and never over one that is there.
- A cooked. plan draft goes through `scene.from_plan` (with texts.json, overrides.json and sounds.json laid on) when its
  video is that plan's render (`review.py plan_draft`): render.stamp.json matches, or render.plan.json is plan.json, and
  the draft is that render (or render.cut.mp4); or the round came from render.mp4 (review.json `src`). A render that
  came back without its stamp still counts.
- Any other draft goes through `scene.from_video` (`review.py video_scene`): a house skill's finished MP4, one finished
  by hand, or a plan `from_plan` refuses (split, board, cover, cutouts) or fails on (logged in the server log). Its
  untouched MP4 (`base_video`) is the clips on the Video track, the Video row's cuts (overrides.json `cuts.gone`) the
  gaps between them, each clip after one with `cut.before` {`reason`: "by hand"}. Every hand edit already on it comes
  over as items on the cut's clock: the typed texts (minus the ones burned in, `burned_labels`), the placed sounds
  (minus the ones mixed in), a track per lane (a hidden or muted lane is a hidden or muted track).
- Every version (a trial reel, any other version in the Version menu, review.json `alts`) is its own scene in
  `<edit>/scene.<alt>.json` (`scene.name_of`: a name with characters other than letters, digits, - and _ becomes those
  plus a short hash). It is made the same way: `from_plan` when the version has its own `plan`, else `from_video` with
  its MP4 as one clip (the main draft's texts.json, sounds.json and overrides.json are the main draft's only). The
  routes take the version: `GET /scene?alt=`, `/scene/asset/<id>?alt=`, `POST /scene/ops {"ops", "alt"}`,
  `POST /export {"alt"}` (saved as `<download name> - <alt>.mp4`, `/export`'s `alt` says which). The page swaps the
  scene when the version changes, with no reload, and keeps an undo history per version.

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
- Any other draft becomes a scene with its MP4 as clips on the bottom track and its hand edits as items (above).
- `scene.py` is also the helper skills call: `Scene(w, h, fps)`, `.video(src, ...)`, `.image(...)`,
  `.text(...)`, `.audio(...)`, `.captions(...)`, `.save(edit)`.
