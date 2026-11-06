---
name: trial-reels
description: Makes Instagram Trial Reels of a reel the user already made or posted. A trial reel is a re-cut of the same take, never the posted file again. Names the video's type first (story, list or pitch), because that decides what may change, then makes 2-4 versions that each look like a different video at a glance (their own hook, start point, opening, overlays, caption look and sound), every element inside the Reels safe zone, all in the user's own style. Each version goes on the review page as a trial, and only the ones the user names are posted as Trial Reels through post.py, spread over the day. Use when the user says "trial reels", "make trial reels of this", "a few more versions of this reel", "post the trial reels", "test other hooks on this", presses Make on the review page's Trial reels tab, or `wait` prints TRIALS. Not the main edit of a new video (start, cut, style-edit), not clips from a long video (clips).
license: MIT
compatibility: Python 3.9+, ffmpeg, Node and the renderer the setup skill installs. Posting needs a Zernio key and an Instagram account (the post skill). Runs from the full ai-editor plugin folder (uses lib/, the cut, style-edit and post skills).
---

# Trial reels

Paths: `${CLAUDE_SKILL_DIR}` means the folder containing this SKILL.md, and `${CLAUDE_PLUGIN_ROOT}` the plugin folder two levels above it.

Read `${CLAUDE_PLUGIN_ROOT}/PRINCIPLES.md` first: the rules every video in this plugin follows (asking, looking real, motion, story and framing, privacy, cost).

Every question to the user goes in the question box: call the AskUserQuestion tool (2-4 options, the recommended one first). Only in an agent without that tool, ask numbered questions in text.

`L="${CLAUDE_PLUGIN_ROOT}/lib/ai_editor"`, `C="${CLAUDE_PLUGIN_ROOT}/skills/cut/scripts"`,
`S="${CLAUDE_PLUGIN_ROOT}/skills/style-edit/scripts"`, `EDIT` the approved reel's folder (`edits/<name>`).
Run the scripts with `python3` on Mac and Linux, `py` on Windows.

A trial reel tests a new opening on people who do not follow the user. Same take, same story, a different first
3 seconds and a different look. Instagram shows it to non-followers first and passes it to followers only if it
does well (or when the user says, with manual graduation).

## 1. The source

The take, never the posted file: a posted reel has its captions and title burned in.

- **From the review page** (TRIALS from `wait`, or the user asks on an approved reel): `EDIT` already holds the
  take, its transcript (`words.raw.json`), the cut (`spans.json`) and the style. Use them.
- **From a reel link or a posted file:** ask for the raw take (the phone's camera roll, the editing app's project
  folder). Never re-cut the posted file. With the take, run the cut skill as for any new video first.

## 2. Name the type, then plan

Split the transcript into lines. Then name the type, because it decides what may change between versions:

| type | what it is | versions differ by |
|---|---|---|
| **story** | a personal story, an update, a before and after | hook, opening, cards, punch-ins. Always from the top, in the posted order. No cold open from a later line |
| **list** | numbered items where the order is the content | hook, item titles, background, cards. The order never changes |
| **pitch** | one product, offer or idea, a proof, a call to action | length (drop a line or two), hook, on-screen text, overlays; the order holds unless the user asks. The CTA stays near the end |

Say the type and why in one line in the plan. When the user names what to change, that wins over the table.

**Versions must look like different videos**, or Instagram can treat them as copies. Give each version, beyond its
hook, at least three of:

- a start point: trim the front so it opens on a later line, in order (story: no)
- the opening: a row of 3 real photos with the hook under it, a text box at the top, or a hook over the first line
- overlays: other cards or motion clips, a different size or side
- the caption look: size, font, outline (the user's style first, then vary it)
- punch-ins or slow zooms on different lines
- the sound: a quiet music bed one version has and the others do not
- the call to action's style

**Hooks:** lowercase, short, naming what the video is (a claim, a number, a quote, a "why", a mistake). Never the
main reel's hook, never one hook twice. Spare hooks: a retake of the opening line (`hooks.json`), a strong later
line said to camera.

On the review page, post the plan to the Trial reels tab and wait for the pick:

```bash
python3 "$L/review.py" EDIT trials --propose '{"message": "...", "hooks": [{"text": "...", "from": "a retake at 0:41"}],
  "versions": [{"kinds": ["hooks", "same"], "line": "t1: ..."}]}'
python3 "$L/review.py" EDIT wait
```

`kinds` per version: `"claude"` (you decide) or some of `hooks`, `same` (posted order), `rewind` (a later start),
`section` (one section only), `animations`. TRIALS ASK is a question from the tab: answer with `--propose` and a
`"reply"`, then `wait` again.

## 3. Build each version

One folder per version beside the reel, `EDIT-t1`, `EDIT-t2`, ...: copy only the inputs from `EDIT`
(`words.raw.json`, `fixes.json`, `spans.json`, `style.json`, `images/`, `images.json`, `visuals.json`), never
`review.json`, `review/` or a render. An alternate hook take makes its own: `python3 "$C/retakes.py" hook EDIT <n>`
writes `EDIT-hook<n>/` opening on it. In each folder change only what its plan line says:

- **A later start or a dropped line:** a `manual` span in `spans.json` (quoted words, `cut/references/shapes.md`).
- **The hook, opening, cards, overlays, caption look, zooms:** the style-edit skill's files (`images.json`,
  `visuals.json`, the style's captions).

Then the cut skill's build and render (steps 3-4, the take from `EDIT/report.json` `source`) and the style-edit
skill from its step 2 on that folder.

The look in every version:

- **Inside the safe zone.** Every element inside x 30-1010, y 150-1640 of a 1080x1920 frame: the like and comment
  buttons sit on the right, the header on top, the caption and username at the bottom.
- **Never over the face.** Look at frames of the opening before placing a photo row or a title. Head high: put
  the row mid-frame with the hook under it. Never at the bottom (the caption covers it).
- **Real pictures only.** Frames of the user's own footage, the real person, the real product or page. No stock.
- **The user's taste and style win.** Read `taste.md` and the reel's style first; vary within them.
- **Voice over music.** The reel's own music at its own level, the voice a little above it.

```bash
python3 "$S/edit.py" stills EDIT-t1    # look at the opening and every card before rendering
python3 "$S/edit.py" render EDIT-t1
python3 "$L/review.py" EDIT alt t1 --video EDIT-t1/render.mp4 --trial
```

Put each version on the page as it lands, so the user can watch them side by side. Before the last one
lands, look at every version's first 3 seconds together: two that look alike get changed again.

## 4. Post (only the ones the user names)

Ask which versions to post, then follow the post skill with `--trial`. Ask once, in one question box: the
graduation (**Automatic (Recommended)**: followers see it when it does well / **Manual**: only when you say).

- **Account:** the user's Instagram only. A trial reel is an Instagram feature.
- **Caption:** the main reel's caption, never empty.
- **When:** pick the times yourself; do not ask. `python3 "$L/post.py" scheduled` lists what is already queued.
  Spread the trials over the next days, several a day, each 3 hours or more from every other post. Use odd
  minutes (8:06, 13:41, 20:13), never on the hour.

```bash
python3 "$L/post.py" send EDIT-t1/render.mp4 --to <instagram id> --caption "..." --trial --graduate auto --at 2026-10-24T08:06 --tz <their tz>
```

Then tell the user each time it goes live (`post.py status <id>`).

## 5. Notes on a trial

A note on a trial reel is taste: save it with the taste skill (the "this style" scope when it is about trial
reels only, e.g. "trial reels keep the posted order") before the next render, so the next batch starts from it.
"Captions" in a note about a version means its on-screen word captions, not the post caption. A start named by a
word ("start it from Rita") cuts everything before that word, not before the next line that has it.
