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

## Hand the render back

Put the finished video on the review page, then wait for the user's notes:

```bash
python3 "<plugin>/lib/ai_editor/review.py" edits/<name> round --stage edit --video edits/<name>/render.mp4
python3 "<plugin>/lib/ai_editor/review.py" edits/<name> wait
```

## Safe zone

Vertical 1080x1920: every caption, card, logo and title inside x 60-940, y 250-1440 (the top bar, the right
button rail and the bottom caption block cover the rest). Wide 1920x1080: 3% left, 5% top, 3% right, 10% bottom.
Check a still with the box drawn before a full render.

## Reuse the editor's renderer

Instead of building a renderer, write the style's numbers into `edits/<name>/style.json` and the cards into
`images.json` / `visuals.json` (`<plugin>/skills/style-edit/references/shapes.md`), then follow style-edit
from its step 4 (plan, stills, render). Captions, zooms, cards, the safe zone and the review page come with it.

## Learned rules

Keep a `## Learned rules` section in the SKILL.md and say "Follow every rule in Learned rules". skill-improver
writes there (one line per rule, with its reason and date) and keeps a `## Log` at the end.
