---
name: skill-improver
description: Turns the feedback on a finished video into lasting rules in the style or skill that made it. Collects the video's notes (review-page notes, preview fixes, chat corrections), keeps only the ones meant for every future video, finds the style or skill behind the edit, checks for a similar rule and sharpens it instead of adding a twin, writes each rule as one short line with its reason and date, shows the exact lines and file, and saves only after the user says yes. A skill style (style.json "skill") gets the rules in that skill's SKILL.md under "## Learned rules" with a short log; a settings style gets them in its own rules and overrides. Runs the review page's "Teach your style from this video". Use when the user says "teach my style from this video", "turn my notes into rules", "make this feedback stick", "update my editing skill from this video" or "learn from this video's notes". Not for one correction said in the moment (taste), and not for fixing the editor for every user (improve).
license: MIT
compatibility: Python 3.9+, standard library only. Runs from the full ai-editor plugin folder (uses its lib/).
---

# Skill improver

Paths: `${CLAUDE_SKILL_DIR}` means the folder containing this SKILL.md, and `${CLAUDE_PLUGIN_ROOT}` the plugin folder two levels above it.

Every question to the user goes in the question box: call the AskUserQuestion tool (2-4 options, the recommended one first). Only in an agent without that tool, ask numbered questions in text.

taste saves one correction the moment the user says it. This skill works on a whole finished video: it reads
every note, keeps the lasting ones and writes them into the style or skill that made the video.

`K="${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/skillrules.py"`, `R="${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/review.py"`,
`T="${CLAUDE_PLUGIN_ROOT}/skills/taste/scripts/taste.py"`. Run them with `python3` on Mac and Linux, `py` on Windows.

Copy this checklist and tick it off:

```
- [ ] 1. Notes collected
- [ ] 2. One-offs left with the video
- [ ] 3. Target found
- [ ] 4. Each rule checked for a twin or a conflict
- [ ] 5. Lines shown, user said yes
- [ ] 6. Saved, log written
```

## 1. Collect the notes

- Review-page notes and your replies: `edits/<name>/review.json` (`comments`). After the final approve, `wait`'s
  `LEARN:` block already lists them.
- Hands-on edits and preview fixes: `edits/<name>/corrections.jsonl`, one row per change with `from` and `to`
  (the review page's rows have `"source": "review"`). After the final approve, `LEARN:` sums them up already:
  "moved 4 of 5 cards up by about 12% of the frame [visuals]". Word each as a rule; keep a `[set ...]` as its `set`.
- Corrections the user typed in this chat about this video.

## 2. Keep only notes for every future video

A note about one moment stays with the video. A note about how edits should look becomes a rule.

| note | rule? |
|---|---|
| "cut the um at 0:12" | no: one moment |
| "the Notion card covers my chin" (said twice) | yes: "Cards sit above the chin, never over the face" |
| "captions are tiny again" | yes: "Captions one size bigger" (with `set` captions.size_pct when the settings table in taste maps) |
| "wrong logo for Jev" | no: one asset (the logo-pack skill fixes it) |

Write the behaviour, not the instance: "Cards fill the space they have", not "make the router card bigger".

## 3. Find the target

```bash
python3 "$K" target edits/<name>
```

- `"kind": "skill"` with a `path`: a skill style. Rules go into that SKILL.md under `## Learned rules`.
  No `path`: the skill is not in the user's skill folders; say so and stop. A skill inside a plugin is never
  written (an update replaces it); save those rules with taste instead.
- `"kind": "settings"`: rules go to that style (`style` path) or, with `style` null, to My style, through
  `styleskill.learn` (rules.json, `style.overrides.json`, and the style's own skill rebuilt).

## 4. Check for a twin or a conflict

Skill style: `python3 "$K" similar <SKILL.md> "<rule>"` lists the learned rules that look alike.
Settings style: `python3 "$T" report` lists the rules saved so far.

- Same meaning, vaguer: sharpen the old line (`replace`), never add a second one.
- Opposite meaning ("logos bigger" vs a saved "logos small"): ask in the question box which wins, quoting
  both: `The new note (Recommended)` / `The saved rule`. Keep only the winner (`replace`). Never keep both.
- Nothing alike: a new line.

## 5. Show the lines, then ask

Each rule is one line: the rule, `Why:` the reason, and the date. Example, note to line:

```
note:  "the logo is on my face again" (rounds 1 and 2)
line:  - Logos sit beside the head, never over the face. Why: two notes said a logo covered the chin. (2026-10-13)
file:  ~/.claude/skills/my-edit/SKILL.md, ## Learned rules
```

Show every line exactly as it will be saved and the file it goes in. Then ask in the question box:
`Save these (Recommended)` / `Change one` / `Don't save`. Save nothing before the yes.

## 6. Save

**From the review page** (the final approve's "Teach <style> from this video" panel): post the rules, and
the boxes the user ticks are the yes:

```bash
python3 "$R" edits/<name> learn --propose '[{"rule": "Logos sit beside the head, never over the face", "section": "visuals", "why": "two notes said a logo covered the chin", "replace": "Logos beside the head"}]'
python3 "$R" edits/<name> learn --done      # after `wait` prints the ticked rules
```

`why` and `replace` are optional; `set` (a taste setting) only for a settings style. `to` says where each rule
goes, one id from the list the LEARN prompt prints (this video's style, My style, another style, or one of the
user's skills as `skill:<name>`): the page shows it pre-picked and the user can change it. `--done` writes a skill
style's rules into its SKILL.md and a settings style's through `styleskill.learn`. A round's
`learn --scope this-style` does the same for a skill style (the note is the reason).

Each saved rule shows on the review page as a receipt, "Saved to <style>: <rule>. Undo", and on the style's
page under "Learned rules" with its day and the video it came from, where the user can Remove it. Undo and
Remove take the line out again (`taste.py forget`, `skillrules.py remove`); never put it back by hand.

**From the Skills page** ("Improve with feedback", `JOB skill-change`): no video, only the user's words. Steps 3-6
the same; the target is the `path=` the job names. `start/references/home.md` has the status lines.

**From the chat**, after the yes:

```bash
python3 "$K" add <SKILL.md> "<rule>" --why "<reason>" [--replace "<old rule>"] --edit edits/<name>   # skill style
python3 "$T" add <section> "<rule>" [--set key=value] --style <style.json> --edit edits/<name>       # settings style
python3 "$T" add <section> "<rule>" [--set key=value] --edit edits/<name>                           # My style
```

`add` prints `duplicate` when the same rule is already there (nothing written), `sharpened` when it replaced
one, `added` otherwise. It also appends one line to `## Log` at the end of the SKILL.md (the last 20 kept).
A settings style's log is rules.json: `taste.py report` shows each rule's count and dates.

Tell the user in one line what was saved and where.

## Files

- `${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/skillrules.py`: `target`, `similar`, `add`, `remove`, `list`, `demo`.
- `${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/review.py`: `learn --propose` / `--done` (the Teach panel).
- `${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/styleskill.py`: `learn`, a settings style's rules and skill.
