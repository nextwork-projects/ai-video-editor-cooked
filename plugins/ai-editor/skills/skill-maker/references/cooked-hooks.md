# cooked. hooks for a video skill

What a skill made with skill-maker can read and call so it plugs into the editor. `<plugin>` is the ai-editor
plugin folder (the one holding `lib/` and `skills/`). Run Python with `python3` (`py` on Windows).

## Where a video lives

`python3 "<plugin>/lib/ai_editor/library.py" path` prints the library (default `~/Movies/AI Editor` on macOS,
`~/Videos/AI Editor` elsewhere). Each video is `edits/<name>/` in it:

| file | what |
|---|---|
| `cut.mp4` | the approved cut: the input a skill style gets |
| `cut.transcript.json`, `captions.json` | the cut's words: `[{"text", "start", "end", "type": "word"}]`, seconds |
| `style.json` | the style's numbers: `aspect`, `captions` (size_pct, y_pct, words_per_caption, colours), `zoom`, `graphics` |
| `images/`, `images.json` | the user's pictures: `[{"src": "images/x.png", "word", "nth"}]` |
| `logos.json`, `images/logo-<brand>.svg/png` | checked brand logos (the logo-pack skill) |
| `review.json` | review-page notes and replies (what skill-improver learns from) |

## Read the user's brand

`$AI_EDITOR_HOME/brand/BRAND.md` (default `~/.ai-video-editor/brand/BRAND.md`) is their brand kit from the home page's
Brand page: colours, fonts, logo, voice, words to use and avoid, do and don't. `brand.json` beside it is what cooked.
read from it. Use it when the profile's `brand.use_creator` is not true.

## Read the user's taste first

`python3 "<plugin>/skills/taste/scripts/taste.py" show --edit edits/<name>` prints their saved rules. Follow
them; they win over the skill's defaults.

## Run as a style

A style.json with `"skill": "<name>"` makes cooked. run `/<name>` on `edits/<name>/cut.mp4` after the cut is
approved (home page: My styles > New style > Use your own skill). The list only shows skills whose name or
first description sentence says video, edit, reel, clip or footage.

## Hand the draft back

**Write elements, not pixels.** Put the draft on the review page as a scene (below), then wait for the user's notes:

```bash
python3 "<plugin>/lib/ai_editor/scene.py" from-plan edits/<name>     # or the skill's own Scene(...).save(edit)
python3 "<plugin>/lib/ai_editor/review.py" edits/<name> round --stage edit --scene
python3 "<plugin>/lib/ai_editor/review.py" edits/<name> wait
```

A note comes back with a `SCENE:` block: answer it with `scene.py show`, `add` and `ops` (each `--why`), then
`round --scene`. Never re-render the draft or burn a title, frame, mask or mirror strip into the footage: each is an
item. `<plugin>/lib/ai_editor/SCENE-SKILLS.md` lists what changes in a skill that renders today. A split, board,
cover or cutout plan that `from-plan` refuses still renders: `round --stage edit --video edits/<name>/render.mp4`.

## Safe zone

Vertical 1080x1920: every caption, card, logo and title inside x 30-1010, y 150-1640 (the top bar, the right
button rail and the bottom caption block cover the rest). Wide 1920x1080: 3% left, 5% top, 3% right, 10% bottom.
Check a still with the box drawn before a full render.

## Reuse the editor's renderer

Instead of building a renderer, write the style's numbers into `edits/<name>/style.json` and the cards into
`images.json` / `visuals.json` (`<plugin>/skills/style-edit/references/shapes.md`), then follow style-edit
from its step 4 (plan, stills, render). Captions, zooms, cards, the safe zone and the review page come with it.

## Write a scene

What the skill puts on screen goes into `edits/<name>/scene.json` as items the user can move and trim
(`<plugin>/lib/ai_editor/SCENE.md`), never a flattened MP4 with titles, frames or masks burned in:

```python
sys.path.insert(0, "<plugin>/lib/ai_editor"); import scene
S = scene.Scene(1080, 1920, 30, edit=edit)
S.video("cut.mp4", 0, 30)                                   # the footage, full frame
S.video("motion/intro/renders/clip.webm", 1, 4, x=540, y=600, w=800, h=450)  # a self-animated clip with alpha (VP9 WebM): one item
S.text("Fact or Hype?", 0, 4, y=300, size=44, color="#000000", box={"color": "#FFFFFF", "pad": [26, 8], "radius": 18, "block": True})
S.save(edit)
```

`python3 <plugin>/lib/ai_editor/scene.py render edits/<name>` exports it; the review page plays and edits it live.

## Learned rules

Keep a `## Learned rules` section in the SKILL.md and say "Follow every rule in Learned rules". skill-improver
writes there (one line per rule, with its reason and date) and keeps a `## Log` at the end.
