# The review page

Every render is handed over on one local page, never as a file path alone: the cut (cut skill), the
styled edit (style-edit), each clip (clips) and a product video (product-video). The user watches it,
pauses, and leaves a note at the moment. Claude reads the notes, fixes, renders again and opens the
next round on the same page. The stills before the render are Claude's own check, never a round on the page: the cut's Approve
means make the edit (SKILL.md step 5). `round --stills` still works for a user who asks to see the frames first.
The live preview (`preview.py`) is only for a user who asks to move cards by hand.

Script: `${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/review.py` (stdlib), page `review.html` beside it.
`review.py demo` self-checks. Mac, Windows and Linux: it opens the default browser.

Notes save in the edit folder: `review.json` (rounds, notes, replies, send and approve) and
`review/` (a frame still per note, any image the user pasted or dropped on a note, and a copy of
each round's video, so a new render to the same path never changes an earlier round's tab).

## The loop

```bash
R="${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/review.py"
python3 "$R" edits/<name> start --video edits/<name>/cut.mp4 --stage cut --transcript edits/<name>/words.json
python3 "$R" edits/<name> serve      # run in the background: opens the page; one server per folder, reused
python3 "$R" edits/<name> wait       # run in the background: it exits when the user presses send or approve
```

(`py` instead of `python3` on Windows.) Tell the user in one line that the page is open: watch,
pause, add a note, then **Submit feedback to Claude** or **approve**. Then wait for `wait` to exit. Do not ask in
the question box meanwhile.

`wait` prints `SEND` or `APPROVE`, then every note of the round:

```
SEND: <name> the cut, round 1, 2 notes. video /abs/edits/<name>/review/v-cut1.mp4
#1 0:02.6 (2.6s): the pause before "editor" still feels long
    said: "is how I cut my videos in one go"
    frame: /abs/edits/<name>/review/rcut1-c1.jpg
```

An edit-stage note started with `--plan plan.json` also names the card on screen
(`[card 3 image 'notion']`: the index in `plan.json` `cards`). Look at the frame still and any
`image:` line before deciding the fix. `wait` ends with a `LEARN:` line and the `learn` command.

## Transcript edits (the cut): `EDITS`

The **transcript beside the player** (cut stage) shows the whole take: kept words, cut words struck,
removed pauses as `1.2s` chips. Each cut is flagged inline with its reason (a red band: `Filler`,
`Retake`, `False start`, `Your cut`, `Cut with a pause`, `Pause 1.2s`): the tick keeps it, the cross
brings it back. Selecting words shows a dark pill: **Restore**, **Copy**, **Cut** (Backspace or Delete
cuts too). Changes wait on the page (highlighted) until **Apply**; Cmd/Ctrl+Z undoes the last one.
**Preview** plays the raw take skipping every cut range plus the pending changes, without a render.
Clicking a word seeks; while the video plays the word said now is highlighted and kept in view. On the
edit stage it is read only.

Apply posts `/edits` `{"restore": [[start, end], ...], "cut": [[start, end], ...], "pause": [[start, end], ...]}`
(raw-take seconds). The server changes `spans.json` itself: a restored word leaves the span covering it
(the span narrows or splits), a cut adds a span with `kind: "manual"` quoting those words (whole words,
`occurrence` when the phrase repeats; spans that then overlap in time merge into one). A restored word
no span covers was taken by the pause trim: its time goes into `keep.json` (`../../cut/references/shapes.md`),
as does a pause put back. Only spoken words are picked, never a hidden `(cough)` span. The result is
checked with `build_timeline.py`'s own span check before anything is written; a change that would not
build is refused. The old files are kept as `spans.prev.json` and `keep.prev.json`. Then `wait` exits with:

```
EDITS 2 transcript edits applied to spans.json: rebuild, render, verify, round
  5 word(s) restored, 1 cut (kind manual); the spans before are in .../spans.prev.json
  restore 2.86-4.80s: "including this view right here."
  then: python3 .../build_timeline.py <source> <edit>; python3 .../render.py <source> <edit>; verify_cut.py; ... round --video <edit>/cut.mp4
SEND: <name> the cut, round 1, 0 notes. ...
```

Do exactly that, with `status` lines on the page: `build_timeline.py`, `render.py`, `verify_cut.py`
(cut skill steps 3-5), fix any notes listed under the `SEND` line too, then `round --video
<edit>/cut.mp4`. Never undo a `manual` span, re-cut a restored word or edit `keep.json`. Stop on the page
puts `spans.prev.json` and `keep.prev.json` back, unless spans.json changed since the Apply; `round`
refuses while stopped. Send and approve are refused while Claude has the changes.

## After send or approve: learn from the notes

Review notes flow into the user's taste (memory) and, when marked for everyone, to the maintainers.

1. Only the notes the user ticked "Keep as a rule" on the page become rules (`wait` marks them
   `[keep as a rule for <style>]`, and its `LEARN:` line names them). Save them with no question: the
   tick is the answer. Every other note is a one-off fix. Never ask a scope or "save as a rule?"
   question about a note the user did not tick. Nothing ticked: `learn --none`.
2. Name a style the way the page does (`LEARN:` gives it: "50/50", "My style"), never its folder
   or `@id` (`@sample-50-50`).
3. Run `learn`. One `--rule` per ticked note; add `key=value` when a taste setting maps:

```bash
python3 "$R" edits/<name> learn --scope style --rule 2 captions "Captions bigger" captions.size_pct=6 --rule 4 visuals "Logos stay small"
python3 "$R" edits/<name> learn --none     # no preferences in this round
```

It saves each rule with `taste.py add` (`everyone` also adds a suggestion), marks every other note of
the round one-off, and writes on each note what happened: `"taste"` = rule id, `video-only`,
`suggested` or `one-off`. Tell the user in one line what was saved. On `everyone`, offer the GitHub
issue as the taste skill does (`taste.py issue`). `round` lists notes not learned yet.

## The final approve: teach the style

The edit's approve (or the cut's, after `final`) ends the video. Its `LEARN:` block replaces the one
above: it lists every note of the session with your replies, and the page shows "Teach <style> from
this video" with "Claude is reading your notes...". Turn them into at most 6 one-line rules
("Captions one size smaller", "Fewer zooms in the first 5 s"), leaving out one-off fixes, and post them:

```bash
python3 "$R" edits/<name> learn --propose '[{"rule": "Captions one size smaller", "section": "captions", "set": "captions.size_pct=4.5"}]'
```

`[]` when none is about the style; `set` only when a taste setting maps; `to` on each rule: where it belongs, an
id from the LEARN prompt's list (this video's style, My style, a style, or a skill `skill:<name>`). Run `wait`
again. The user ticks rules, changes any pick, and presses Save (or Not now). `wait` prints the ticked rules; then
`learn --done` saves them with `styleskill.learn` into the style the edit used (one creator style,
else My style) and the page says "Saved to <style>. Next video uses it." No notes all session: the
page says so and LEARN asks nothing. Round 1 of the user's first 3 videos also shows a one-time line:
their first videos teach it their style (dismissed for good with Got it; count in `ui.json`).

With no `wait` running the page says Claude is not listening, and notes still save. The next
`wait` returns at once with them.

## After send: fix, show the work, open the next round

Show each step on the page while working. Each `status` ticks off the one before:

```bash
python3 "$R" edits/<name> status "moved the card on 'notion' 0.3 s later"
python3 "$R" edits/<name> status "rendering" --log edits/<name>/render.log
```

`--log` shows the last `N/M` in that file as a progress bar (Remotion prints `Rendered 812/3255`), so
write the render's output to a log. Never make up a percent.

While Claude works the user can keep adding notes. They are queued for the next round (`"queued": true`)
and `wait` does not see them. `round` makes them open notes of the new round: each moves to where its
words are said on the new cut when both rounds have the cut's transcript (`"moved": "words"`, old time
in `t_was`), else it keeps its time (`"moved": "time"` when the length changed: check it), with a new
frame still and the words said there. The next `wait` hands them over like any note.

The user can edit any note they wrote while it is unsent or queued: its text, its moment (moved to the
playhead with a new frame still and words), its version scope and its images. Same note id, with an
`edited` time; `wait` prints the final text. Once Claude has the round its notes are read-only (`/edit`
answers 409); a change then is a new note or **fix it anyway**.

The page has a **Stop** button while Claude works. When the user presses it, the round's notes open
again (queued notes join them) and the next `status` exits 3 with `STOPPED`: stop the work, say so in one line, run `wait`.

Answer every note, then open the round with the new render. The answer goes in `--reply`, never in `status`:
a `status` line is work in progress, not an answer to a note.

```bash
python3 "$R" edits/<name> resolve 1 fixed --reply "pause is 0.10 s now" --new-t 2.4
python3 "$R" edits/<name> resolve 2 wontfix --reply "<why>" --new-t 8.0
python3 "$R" edits/<name> round --video edits/<name>/cut.mp4 --changed "Captions one size smaller"
```

What each kind of note changes, so the fix survives the next re-plan (plan.py rewrites plan.json, so never
hand-edit plan.json alone):

| The note | Change it in | Then |
|---|---|---|
| a caption word is wrong | `overrides.json` `words` (preview.py), or the word in captions.json | plan, stills, render |
| bigger / smaller captions, caption colour | the taste setting (`captions.size_pct`, ...) for this video or the style | plan, stills, render |
| cut this pause, keep this bit, cut these words | the cut skill: spans.json / keep.json, rebuild, render, verify | style-edit again on the new cut |
| a card: swap, remove, bigger, move | overlays skill: `plan.py beat` (visuals.json, images.json) | capture if new, plan, patch render |
| no zoom here | `plan.py beat edits/<name> zoom@7.2 --drop` (kept in overrides.json) | plan, render |
| quieter / louder music | `sfx.py music edits/<name> --under-db N` | plan, render |
| a motion clip: colour, words | motion skill `note` | plan, render |
| the title | the `title` beat in visuals.json (`plan.py beat`) | plan, render |

Every `--reply` is one plain line saying what you did ("Swapped it for the notion.so page"), never "done".
`--changed` (repeat it) lists anything you changed that no note asked for. The page shows both under
**Changed in this draft**, with what the files themselves say changed (cards swapped, removed, added or
bigger, zooms, caption look and words, the title, the music, cut words), each one a link to its moment.

A note resolved `fixed` turns green on the next round ("Done in round N: <reply>"); `wontfix` turns grey with the reply. `--new-t` pins the note on the new render's timeline (a cut moves later moments). `wontfix` shows as
**left as is** with the reply as the reason; the user can press **fix it anyway**, which comes back
as a new note starting `fix it anyway:`. Do it. Then run `wait` in the background again. The open
tab follows the new round by itself; `round` never opens another.

## After approve

- **The cut:** the cut is approved. Go on to style-edit. On "just the cut", run `python3 "$R" edits/<name> final`
  (before or after the approve): Approve then reads "Approve the cut" and the page waits for no edit. The page
  turns at once: Approve goes green, the stepper moves to **The edit**, and the player shows a
  **Making the edit** card over the dimmed cut, with a bar, a clock and the steps in the panel. The bar
  moves only on real steps: `captions`, `visuals`, `plan`, `render` (the last by its log's percent).
  `retakes.py captions`, `route.py beats`, `plan.py`, `edit.py stills` and `edit.py render` report their
  own; before plan and render also run `python3 "$R" edits/<name> status --step plan|render`, which
  exits 3 with `STOPPED` if the user pressed **Stop** (that takes the approve back and reopens the cut;
  `round --stage edit` then also exits 3: do not open the edit, say so, run `wait`). With no report from
  Claude for 15 minutes and no render log moving in the last 2, the card says so instead of a bar. When the edit's `round`
  lands, the bar fills green and the page switches to it with "The edit is ready".
- **The styled edit:** the same page moves on to it:
  `round --stage edit --video edits/<name>/render.mp4 --transcript edits/<name>/words.json --plan edits/<name>/plan.json`.
  Approve there finishes the video. Stop the background `serve`.

## Going back

The **Drafts** tab plays any round at the same moment, compares two side by side, and has **Go back to
this draft** on earlier rounds of the open stage. It needs no Claude: review.py puts that round's files
back (`review/snap-<stage><n>/`: plan.json, spans.json, visuals.json and the other top-level .json/.txt, and
`.sfx/music.wav`, and every picture and clip its plan.json shows) and its render (`cut.mp4`, `render.mp4`), and opens them as a new round, "Back to draft N".
The user's unsent notes move onto it. The next `wait` says `this round is round N again`: fix from those
files. In the terminal, "go back to round 2" is `python3 "$R" edits/<name> back 2`.

## Several videos in one round

Both shapes of one edit, or every clip of a long video, go on one page as tabs over the player:

```bash
python3 "$R" clips/<name> start --video edits/<name>-clip1/render.mp4 --name clip1 --transcript edits/<name>-clip1/words.json
python3 "$R" clips/<name> alt clip2 --video edits/<name>-clip2/render.mp4 --transcript edits/<name>-clip2/words.json
```

Each video keeps its own notes; a note can be ticked **all videos** (`wait` tags it `[all videos]`;
fix it in each). `wait` tags the rest with the video's name. **compare** puts two side by side,
in sync. **approve all** approves every video in the round. `round` clears the extra videos: add
the ones still in play again with `alt`.

## On the page

The cut stage shows the transcript beside the video: every word, cut words and removed pauses struck
through, the line playing now highlighted (built from `decisions.json` and `words.raw.json` when they
add up to the video). The timeline is split at the cut points, or at `chapters.txt` on the edit, and
the edit adds Cards / Zooms / Captions tracks from `plan.json`. A missing file leaves that part out.
**Compare** plays an earlier round (or another version) beside this one, in sync. The **Drafts** tab
replays every earlier render. The page follows the system's light or dark setting; the switch beside
the help button picks one and the browser remembers it. The timeline has a pin per note, and last round's notes
pinned where `--new-t` put them. A vertical render gets a **safe zone** button (`z`) that shades
where the app's buttons and text sit (plan.py's `SAFE` for 9:16). The cut stage links to
`cut-check.html` (the transcript, cut words struck through) when it exists. Shortcuts: space,
`j`/`l`, arrows, `,`/`.` one frame, `[`/`]` speed, `c` add a note, `i`/`o` mark a range.

The server listens on 127.0.0.1 only, and every request needs the random token in the URL `serve`
prints, so another page in the browser cannot read the notes or press send.
