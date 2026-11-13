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
| `text` | `text`, `font`, `weight`, `size` (px), `color`, `align` (left, center, right), `line_height`, `box` ({`color`, `pad`, `radius`, `opacity`} or null), `outline` ({`color`, `width`} or null), + visual (`w` is the wrap width, `h` is ignored) |
| `shape` | `fill`, `stroke` ({`color`, `width`} or null), + visual |
| `audio` | `asset`, `in`, `speed`, `volume`, `fade_in`, `fade_out` |
| `captions` | `words` [{`w`, `start`, `end`, `p`?, `emph`?}], `style` (the caption style keys plan.py uses today), `asset` (words on that asset's clock, shown through its clips; null: the scene's clock), `pages` ([{`start`, `end`, `treat`?...}] on the same clock, `p` indexes it; without them `style.words_per_caption` pages the words), `motion` |
| `card` | `card` (a cooked. plan card: an overlay format the composition's CardView draws), `look`, `motion`, + visual (the box) |

Visual fields: `x`, `y` (the item's centre), `w`, `h`, `rotation` (degrees), `opacity` (0-1), `fit` (cover or
contain), `crop` ({`l`, `t`, `r`, `b`} as fractions of the source), `radius` (px), `shadow` ({`blur`, `y`,
`opacity`, `color`, `distance`, `angle`} or null), `border` ({`width`, `color`} or null), `anim` ({`in`, `out`: none, cut, fade, pop,
slide-up; `dur` seconds}), `keys` ({prop: [[t, value, ease]]}, t from the item's start; props x, y, w, h,
scale, rotation, opacity; ease linear, in, out, inout, hold; scale is about the centre), `grade` ({`brightness`,
`saturate`}). Text `box.pad` is px or [x, y]; `box.block: true` is one box round the whole text, else a box behind
each line. `outline.width` is the CSS text stroke (half of it shows outside the letters).
`box.opacity` (0-1, default 1) is the box's fill only. `shadow.color` defaults to black, `shadow.opacity` to 0.35; a shadow
with `distance` sits that far away at `angle` (degrees, 90 is straight down), else straight down by `y`. On a text the shadow
is behind the letters (CSS text-shadow); on a picture, clip or shape it is behind the box.

## Page and server

- `GET /scene`: the scene. `POST /scene/ops {"ops": [...]}` applies ops in order and returns `{"ok", "scene", "j"}`
  (`j` is the undo journal id the page already uses with `/timeline/restore`). Ops:
  `{"op": "set", "item": id, "props": {...}}`, `{"op": "add", "track": id, "item": {...}, "index"?}`,
  `{"op": "remove", "item": id}`, `{"op": "move", "item": id, "track": id, "index"?}`,
  `{"op": "track", "track": id, "props": {...}}`, `{"op": "add_track", "track": {...}, "index"?}`,
  `{"op": "remove_track", "track": id}`, `{"op": "split", "item": id, "t": seconds}`,
  `{"op": "trim", "item": id, "edge": "start" | "end", "by": seconds}` (a later edge for by > 0: the in-point
  moves with a start edge), `{"op": "asset", "id": id, "asset": {"src": "media/x.mp4"}}` (a file in the edit,
  probed); `{"op": "asset", "id": id, "asset": null}` drops an asset no item uses (the undo of an add). The page gets
  each asset with `url` (`/scene/asset/<id>?v=`, never saved).
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
- scene.json is made on the first ask. When a new rendered draft comes in (not `round --scene`), it is made again from
  that draft, so everything the draft has is on the timeline, and the user's changes on the old one are carried over
  (`review.py scene_new_draft`, `scene.carry`): `.scene/scene.base.json` is the scene as the old draft was built, and
  every field the user changed, item they added or item they deleted goes onto the new one, unless the new draft changed
  that same field (then Claude was asked). Items are matched by kind, file or words and the nearest start, not by id.
  `built` names the draft a scene was made for; `carried` says how many changes came over. A scene from before 2.7.50
  is kept as it is, unless it is only the old draft's MP4.
- More menu, Duplicate this timeline: `POST /scene/duplicate {alt}` copies the scene on screen, hand edits and all, into
  a new version "<name> copy" with the same video, transcript and plan (`review.py scene_duplicate`).
- A speed change on a video or audio clip keeps its footage: the clip gets shorter or longer (and its keyframes); on the
  main footage everything after it moves and the captions over it are retimed (review-scene.js `scSpeed`).
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

Every one of them takes `--alt <version>` for a note on a version (a trial reel, marked `[t1]` in `wait`): the command
then reads and changes that version's `scene.<alt>.json`, and `round --scene --alt <version>` hands it back. The `SCENE:`
block names the versions the notes were left on.

- Each command is one change: with the page's server running it goes through `POST /scene/ops` with `"by": "claude"`
  and `"why"` (the server's journal, the page draws it on its next 3 s poll with no reload); with no server it is
  written to scene.json directly. A file outside the edit is copied into `media/` first.
- Items Claude added or changed carry `by: "claude"`: a small Claude mark on their timeline clip. Any change from the
  page clears it (`scene.touch`).
- Every change is kept in `review/claude.json` (a version's in `review/claude.<alt>.json`, `scene.changes_of`): `n`, `why`,
  `at` [stage, round], `t`, `items`, and the ops that undo (`back`) and redo (`fwd`) it. `/state`'s `claude_changes` lists
  the draft's own and those of the round `round --scene` came from (`scene_from`), each with its `alt` (null: the main
  draft); the notes panel shows the ones on the version on screen under **Claude's changes**, each with Undo or Redo, and
  each is one Cmd+Z ("Claude: <why>") in that version's undo history. `POST /scene/claude {"n", "undo", "alt"}` applies
  its own ops, so the user's edits since stay. `/state`'s `scene_v` is each version's scene stamp (`{"": main, "t1": ...}`):
  the page fetches the scene it shows when its stamp changes.
- `round --scene` opens the next round on the same video (or `cut.mp4` for the first edit) with the scene as the draft:
  the scene files are snapshotted with the round's files, the round's versions stay on it, no MP4 is made. Export
  renders it when the user wants the file.
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

The page shows the cuts at any zoom: a yellow tick per cut on the ruler (hover: why, the words, the seconds, Bring back;
click: the playhead goes there), the Video row's list button (every cut with its time, a row jumps there, Bring back),
and Up / Down jump between them.

## Editing on the page

- Split (S, Cmd+B, the scissors beside the timeline zoom): the picked clips at the playhead, or with none picked the clip
  under it on the main video track. Each part keeps all of the clip's keys, moved to its own start, so the picture never
  jumps. Delete / Backspace (or the bin beside it): the picked clips, or the clip under the mouse once it has moved off the
  pick; on the main track the gap closes. Each is one undo.
- The keyframe lane: a picked clip opens a thin row per animated property under its track (Scale, Position, Size,
  Rotation, Opacity), a diamond per key. A diamond stands for every key the clip has at that time (an AI zoom is scale,
  x and y together): click goes there and shows it in Properties (opened if closed: ease to the next key, Delete
  keyframe), drag moves it in time, Delete removes it. The ◇ beside a field in Properties adds or removes a key at the
  playhead; a keyed field shows in yellow. Scale has no plain field: one key holds it.
- A field being typed in lets go on any press on the video or the rows, so the next pick and its keys always work.

## Adding things: where they go

- A new item (Add text, a text look, + Shape, a picture or clip from Media, a dropped or pasted file, a sound, a paste, Claude's
  `scene.py add`) goes on a track of its own kind: texts with texts, pictures, clips, shapes and cards together, sounds with
  sounds. The first such track (top first) that is unlocked, shown and free for its whole time takes it; else a new track
  of that kind just above the others of its kind (`scene.lane`, the page's `scPlace`). Never the footage track (the magnet
  one), never over another clip. A drop onto a row (or `--track`) uses that row only when it holds that kind and is free.
- The Text panel (the rail's Text): Add text (the white box look) and a tile per look (`SCLOOK` in review-scene.js; the
  `p` ones are Properties' tiles). Click: at the playhead; drag: onto the video (there) or a timeline row (that time). One
  undo each, and the caret goes in the text. Double-click a text to type in it: Enter is a new line, Esc or a click away saves.
- Copy and paste: Cmd+C copies the picked items (not captions) to the system clipboard as `cooked-scene:` + JSON
  ({`from`: the edit folder, `items`: [{`it`, `tr`, `ti`}], `assets`}) and the page's memory; Cmd+V pastes at the playhead,
  each original track's items together on one free track of their kind, the gaps kept, new ids; Cmd+D duplicates right
  after, Cmd+X cuts; right-click has the same. A paste from another edit copies each file in first:
  `POST /scene/import-asset {from_edit, src}` (an edit in the library, a picture, clip or sound inside it) answers `{src}`
  in this edit's `media/` (`scene.bring_in`). A picture on the clipboard pastes as an image item. Each paste is one undo.

## Adding audio

- Every sound is a file in the edit's `media/`, an asset, and an `audio` item. `POST /scene/sound {"name"}` copies a
  library sound (`custom/sounds`) in (an APFS clone, the same file once: `scene.bring_in`); `POST /scene/upload?name=`
  streams an audio file, or a video whose sound is wanted, in. Both answer `{src, duration}` and the page adds the item.
- Where it goes: the Sounds panel's Add (or a row dragged onto the timeline), + Audio (a file picker) and a file dropped
  from Finder put it at the playhead or the drop time, on the first audio track that is unlocked, unmuted and free there,
  else a new one. It lasts the file, up to the scene's end. The panel lists the sounds picked for a moment first.
- `GET /scene/peaks/<id>?alt=` is an asset's waveform (`scene.peaks`: 50 values a second, cached in
  `.scene/<id>.peaks.json`); each audio clip draws the part it plays. A top corner of an audio clip drags its fade.
- `volume` is a gain: 1 is the file as it is, 0 silence, up to 3.981 (+12 dB, SceneEdit's `VMAX`). The export applies it
  in Remotion's ffmpeg mix (its `volume` filter takes any gain); the page's player routes each clip through a Web Audio
  GainNode (`useWebAudioApi`), since a media element's own volume stops at 1. There is no limiter: a loud clip boosted
  past full scale clips in the export, so boost quiet sound, not loud sound.
- Every clip with sound (audio, and video from its asset's sound, with its waveform from the same peaks route) has a volume
  line: drag it up or down (half a dB a pixel, Shift a tenth), a label shows the level in dB, it snaps to 0 dB within 1 dB,
  and below -48 dB is silence. Every picked clip with sound moves by the same dB. The waveform grows and shrinks with it.
  The player is heard changing while dragging; letting go is one op and one undo. The trim edges (8 px each side) and the
  fade handles (top corners) keep their own presses. Properties shows the same volume in dB.

## Footage covers the frame

`scene.cover` (from_plan, and once on load for a scene.json without `covered`, logged): a clip on the first visual
track that leaves an edge of the frame uncovered (a cut the house centre step slid sideways: the render mirrored the
strip in) has each short zoom key raised about the clip's centre, just enough, and grows if still short. The zooms that
already covered keep their framing. Each zoom key is scaled about its own zoom's origin (StyleEdit zoomAt).

## Migration

- A cooked. plan draft becomes a scene (`scene.py from-plan`): the footage as the clips above (from spans.json
  or the cut's decisions), framing and grade on each clip, zooms as keys on the clips they fall in, each card as an image or video item, each text as a text item, captions as one captions item, every
  sound as an audio item.
- Any other draft becomes a scene with its MP4 as clips on the bottom track and its hand edits as items (above).
- A skill writes a scene, never a flattened MP4: SCENE-SKILLS.md (what changes in a house skill).
- `scene.py` is also the helper skills call: `Scene(w, h, fps)`, `.video(src, ...)`, `.image(...)`,
  `.text(...)`, `.audio(...)`, `.captions(...)`, `.save(edit)`.
