# Moving a house skill onto scenes

A skill that puts things on screen writes them into `scene.json` as items (SCENE.md), never into a flattened MP4.
The rule for every skill: **write elements, not pixels.** The review page then plays the scene live, the user drags
and trims each element, Claude's later notes are scene ops, and Export renders the file.

## The general change

| today | on a scene |
|---|---|
| plan.json, then `edit.py render` (or `edit.py patch`), then `review.py round --stage edit --video render.mp4` | plan.json, then `scene.py from-plan edits/<name>`, then `review.py edits/<name> round --stage edit --scene` |
| a note: change the json files, `plan.py`, the skill's post-plan step, `edit.py patch`, `round --video render.mp4` | `scene.py show --at t`, then `scene.py add` / `ops` / `cards` (each `--why`), `resolve`, `round --scene` |
| a picture, a screenshot, a card baked into the render | an `image` item, or `scene.py cards --at t` for a plan card |
| a motion clip in a `video_card` | a `video` item from `hyperframes render <clip> --format webm` (alpha) |
| a zoom in plan.json | `scale` keys (and `x`, `y` to hold the origin) on the footage clip under it |
| a sound in plan.json `sfx` | an `audio` item |
| ffmpeg on cut.mp4 (a reframe, a slide, a mirror strip) | the footage clip's `x`, `y`, `w`, `h`, `crop` or `keys` |

`scene.py from-plan` runs once, for the first edit draft. After that the user's page edits live in scene.json only:
never run plan.py + from-plan again on that draft (it rebuilds the scene and drops their moves). A plan `from-plan`
refuses (split, board, cover, cutouts) is rendered as today; the page then opens that MP4 as a scene (`from-video`) and
the notes on it are answered as items like any other. A note on a version (a trial reel, `[t1]` in `wait`) is answered
on that version's scene: `--alt t1` on every scene.py command and on `round --scene`.

## The house just-talking skill

Read: the house repo's `skills/<house>-just-talking/SKILL.md` § Run and `scripts/just_talking.py` (`finish`, `reframe`, `centre`).

**First draft (Run steps 4 to 7).** Steps 1 to 5 stay. `finish` still runs after plan.py: it is a plan.json
post-processor (hard cuts, `ambient: still`, each picture fitted between y 13% and his hairline, captions at y 73.3,
no caption `treat`, the zooms held on his face x, his page moves from overrides.json), and `from-plan` carries every
one of those into the scene. What changes:

- Step 6 **Render** goes. In its place:
  ```bash
  python3 "$A/lib/ai_editor/scene.py" from-plan $E
  python3 "$A/lib/ai_editor/scene.py" stills $E $E/stills/scene a=<frame> b=<frame> ...   # the still checks of step 5, on the scene
  ```
  The frame-to-frame card-band scan runs on the export instead (`scene.py render $E --draft`), only when checking.
- Step 7 **Review page** becomes `review.py $E round --stage edit --scene` (no `--video`). The page opens the scene.
- The `const still` renderer patch (StyleEdit.tsx) no longer matters for cards `from-plan` turns into items: a
  `format: "plain"` picture becomes an `image` item and a bare `video_card` with cut enter and exit a `video` item,
  both drawn by `SceneEdit.tsx` with no entrance, exit fade or push-in. A `video_card` that is not bare (the 2x2 intro
  wall) stays a `card` item drawn by `CardView`: check it there on a still, and set `"bare": true` in `finish` for
  the wall if it shows the push-in.

**After his notes.** No `plan.py`, no `finish`, no render. Each fix is an op on the item, and `--why` is the line the
page shows:

| his note | the command |
|---|---|
| a picture moves or resizes | `scene.py ops $E '[{"op": "set", "item": "<id>", "props": {"x": 540, "y": 520, "w": 900, "h": 506}}]' --why "..."` |
| a new picture above his head | `scene.py add $E image --src <file> --start <t> --end <t> --x 540 --y <above the hairline> --w <safe width> --why "..."` |
| the title | `scene.py ops $E '[{"op": "set", "item": "<title text id>", "props": {"text": "..."}}]'` |
| a punch-in here, none there | `scale` keys on the footage clip (`show --at t` names it); a zoom keeps his face x (Learned rules: he never moves left or right), so the `x` key holds the face column |
| a caption word | `set` the captions item's `words` |

`finish`'s fit rules (y 13% to the hairline, centred on x 540, inside x 60-940 and y 250-1440) are now Claude's to
keep when placing an item: read the head top from `face.json` at the item's time.

**reframe and centre.** Both re-encode `cut.mp4` (a mirror strip on top, or a sideways slide). A scene plays the raw
take through the cut's clips, not `cut.mp4`: `from-plan` measures the slide (`scene.framing`) and puts it on the clips'
`x` and `y`, but the mirrored strip is not there, so a black edge shows where nothing covers it. On a scene: skip
`reframe` and `centre`; move him with the footage clips' `y` (down by the px `reframe` would mirror) or `x` instead,
and cover the uncovered edge with a `scale` key of about 1.12 (his punch-in size) or a `crop`. Check the edge on a
still at the start, the middle and the end.

**Learned rules** that name a script step (`finish --no-lift`, "`finish` strips every treat") hold for the first
draft. Add one line under them: "On a scene draft, a note is a scene op (SCENE-SKILLS.md), never plan + finish +
render."

## Other house skills

The same table applies. A skill whose script ends in `edit.py render` or an ffmpeg overlay of the render ends in
`scene.py from-plan` (or `scene.Scene(...)...save(edit)` for a skill that builds its own layout) and `round --scene`.
A post-render burn-in (finish.sh overlays, a mirrored strip, a drawtext title) becomes an item.
