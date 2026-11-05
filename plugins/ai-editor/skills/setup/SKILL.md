---
name: setup
description: Installs and checks everything cooked. needs on Mac, Windows or Linux (Python, ffmpeg, Node, git, the Python packages, the free transcription model and the Remotion renderer): on a first run it opens the editor's window first, then installs in the background. Then saves the user's style once. Also walks through the optional API keys (Gemini for reading a creator's look, ElevenLabs for verbatim transcripts), the optional CrisperWhisper model, cloud renders on Modal ($30 free credit a month), the GitHub CLI for free GitHub Actions renders and AWS Lambda. Use when the user says "set up the editor", "install ai-editor", "setup", "finish setup", "set up Modal", "cloud renders", "add my Gemini key", "add my ElevenLabs key", when they have just installed the plugin, or when another ai-editor or creator-teardown step fails because a tool is missing. Not for editing a video (that is start) and not for changing one edit preference (that is taste).
license: MIT
compatibility: Claude Code or any agent with a shell, on Mac, Windows or Linux. Installs Python 3.10+, ffmpeg 4.4+, Node 20+, git and the Remotion renderer; needs internet. Runs from the full ai-editor plugin folder.
---

# Setup

Paths: `${CLAUDE_SKILL_DIR}` means the folder containing this SKILL.md, and `${CLAUDE_PLUGIN_ROOT}` the plugin folder two levels above it.

Every question goes in the question box: the AskUserQuestion tool (2-4 options, recommended first). Only in an agent without it, ask numbered questions in text.

The user may never have used a terminal. In the terminal flow, say what each tool is for in one
sentence before installing it, and check after every step.

`U="${CLAUDE_SKILL_DIR}/scripts/setup.py"`. Run it with `python3` on Mac and Linux, `py` on Windows.

## 0. Window first

On a first run (no profile, or doctor not `Ready.`; the session-start line says "First run"), before
any install or question, and with no question box (the page is the setup; keys are typed there):

1. Open the window: `python3 "$H" serve` and `python3 "$H" wait`, both `run_in_background`,
   `H="${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/home.py"` (stdlib only: it needs nothing installed). Say one line: "The editor is open in your browser.
   It is getting your computer ready; pick a creator there meanwhile."
2. Install in the background: `python3 "$U" install-all --report` (`run_in_background`). It runs steps
   3-4 in order, never asks, and shows each on the page's "Getting your computer ready" bar.
3. Take the page's jobs as `${CLAUDE_PLUGIN_ROOT}/skills/start/references/home.md` says. A teardown
   job needs the Python packages step done first (it uses yt-dlp).
4. It exits 1 with `Not ready.` and one fix per line, also shown on the page: do each fix (step 2 for
   ffmpeg, Node, git, Python), then run `install-all --report` again. Done steps take seconds.

No browser, or the user wants the terminal: say the plan (**Tools** 2-10 min, required; **Keys** 5 min,
optional; **Cloud renders** 3 min, optional; **Your style** 2 min), then steps 1-8 here.

Every step can be skipped and finished later: on a skip, run `python3 "$U" later <step>`
(`gemini`, `elevenlabs`, `modal`, `style`, `matte`) and say "Saved. Say *finish setup*
any time to add it." When the user says "finish setup" (or "add my <x> key"), run
`python3 "$U" todo` and go to the steps it lists (every optional step not done yet).

Put a header on every step, e.g. **Step 2 of 4, keys: Gemini (1 of 2)**, and say in one short
line each what it is, why it helps, what it costs, what skipping means.

If a script prints an error, say its message in plain words. Never open or debug the setup
scripts: their messages say what to do.

## 1. Doctor

```bash
python3 "$U" doctor
```

Every line reads `ok` or `FIX` with the exact command for this computer. `Ready.` at the end means
the tools are done: skip to step 5 (keys). A `FIX ... run: setup.py repair` line means something
moved off the pinned versions (an update, or a package changed by hand): run `python3 "$U" repair`,
it puts back the exact pinned set. What is installed is recorded in `~/.ai-video-editor/env.json`.

A `saved login` row is a browser profile product-video logged in to a site with: it stays logged in
on this computer. Say which sites and how long ago each was used, and ask in the question box
"Delete these saved logins?" (Keep them (Recommended) / Delete <domain>, one option a site); on a
delete, `node "${CLAUDE_PLUGIN_ROOT}/skills/product-video/scripts/login.mjs" logout <domain>`.

If `python3` itself is missing:
- Mac: `brew install python`. No Homebrew? See step 2.
- Windows: `winget install -e --id Python.Python.3.12`, then open a new terminal.
- Linux: `sudo apt install -y python3 python3-venv` (Fedora: `sudo dnf install -y python3`; Arch:
  `sudo pacman -S --needed python`).

## 2. System tools (ffmpeg, Node, git)

Fix each `FIX` line top to bottom with the command doctor printed. What each one is for:
- **ffmpeg** cuts and joins video.
- **Node** runs the renderer that draws captions, zooms and cards.
- **git** is needed by the package installers.

The user runs these themselves, in their own terminal, because they ask for a password or open a
window:
- **Homebrew on a Mac** (if `brew` is missing). Give them
  `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`
  and tell them to run the **Next steps** lines it prints at the end.
- Anything starting with `sudo`.
- `xcode-select --install` opens a window. Tell them to click **Install** and wait.

On Windows, a `winget` install only shows up in a **new** terminal. Ask them to close and reopen
Claude Code after installing, then run doctor again.

## 3. Python packages and the transcription model

Steps 3 and 4 are what `install-all` runs (step 0). Every step is safe to re-run: done work prints
`up to date` and downloads nothing. Without the user watching (CI), `python3 "$U" bootstrap` runs
them and ends with doctor.

```bash
python3 "$U" venv
python3 "$U" model
```

`venv` installs faster-whisper (free transcription on this computer), numpy, pillow and yt-dlp
into the venv in `AI_EDITOR_HOME`, at the exact versions in `requirements/requirements.lock`. `model` downloads the transcription model once, about 500 MB, and checks its sha256.
`Python 3.10+ needed`: go back to step 1's Python line. `Run the venv step first.`: run `venv`.

## 4. The renderer

```bash
python3 "$U" remotion
```

Copies the renderer to `~/.ai-video-editor/remotion` and installs exactly its `package-lock.json`
with `npm ci` (about 700 MB with Chrome's headless shell). This is the biggest download: say so
first. A creator teardown can run meanwhile: it does not need the renderer. `npm missing`: install Node (step 2) first.

Then the motion clip tools, for bespoke animations (the motion skill):

```bash
python3 "$U" motion
```

`npm install` of the pinned HyperFrames CLI and GSAP into `~/.ai-video-editor/motion` (about 120 MB, 10-60 s),
and a headless Chrome for them (uses the installed Chrome, else downloads about 200 MB). Say the time first.
Skipped: animations fall back to the template cards.

Remotion is free for individuals and companies of up to 3 people. Bigger companies need a
Remotion company licence (remotion.dev/license). Say this once.

## 5. API keys

Two keys, one at a time, each optional. Recommend Gemini. For each key, say what it is for
and what it costs (`references/keys.md` has both lines per key), walk the click path, save it, then
check it. If the user says no, the editor still works and Claude does that job instead.

The direct links (give them as clickable links and open them too):
- Gemini: https://aistudio.google.com/apikey
- ElevenLabs: https://elevenlabs.io/app/settings/api-keys (sign up first at https://elevenlabs.io/app/sign-up)
- Modal: https://modal.com/signup

**Never ask for a key in the chat.** Anything pasted here stays in the conversation. The key goes
from the clipboard straight into the key file. For each key: open its page (`open <url>` on Mac,
`start <url>` on Windows, `xdg-open <url>` on Linux), list the clicks, say what the key looks like
(a long line of letters and numbers), then ask in the question box: **Copied (I save it from your
clipboard) (Recommended)** / **Skip**. Tell them to copy only the key right before they pick Copied.

- **Mac:** on "Copied" run `pbpaste | python3 "$U" setkey <name>`.
- **Windows:** run `powershell -NoProfile -Command Get-Clipboard | py "$U" setkey <name>`.
- **Linux, or if that fails:** the user opens a terminal themselves (Ctrl+Alt+T on most Linux,
  Terminal from Spotlight on a Mac, PowerShell from the Start menu on Windows). Give them
  `python3 "<full path>/setup.py" setkey <name>` to paste in; they paste the key when it asks (it
  stays hidden).

`<name>` is `gemini` or `elevenlabs`. `setkey` sends one free test request before saving
and never prints the key:
- `Tested: the <name> key works.`: done.
- `Nothing saved: ...` (the clipboard held something else) or `Not saved: the service rejected this
  key`: they copied it wrong or only part of it; ask them to copy it again.
- "can't check secure websites", or the user says "fix my certificates": run `python3 "$U" certs`.

Keys live in `~/.config/creator-teardown/.env`, readable by the user only and shared with
creator-teardown (`$AI_EDITOR_HOME/.env` instead when `AI_EDITOR_HOME` is set). Check them all at the end:

```bash
python3 "$U" keys
```

Only to a user who skipped ElevenLabs and wants better cuts, offer CrisperWhisper
(`references/keys.md`, last section: non-commercial weights, 1 GB).

## 6. Cloud renders with Modal (offer it)

Offer it once, in the question box: "Set up cloud renders with Modal? (one login in the browser)" with
**Later (Recommended)** first and **Connect Modal** second. Also run it when the user picks Modal at
render time and doctor shows `modal` as not ready. Follow `references/cloud.md` "Modal": what it
is, what it costs, the card, then one step (`setup.py modal-connect`, or Connect Modal in the window).

## 7. Check

Run doctor again until it prints `Ready.` Skipped keys show as `--`; that is fine. Then
`python3 "$U" install-launcher`: the `nextwork-editor` command opens the editor's window from any
terminal, with a listening Claude (`--window-only`: the window alone; `uninstall-launcher` takes it off).

Then say this line once: "Turn on auto-updates: type /plugin, open Marketplaces, pick nextwork,
choose Enable auto-update." Never write to their `~/.claude` files for them.

## 8. Your style (asked once)

Last, taste. Ask what is still missing:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/profile.py" missing --style
```

Ask those ids in the question box, at most four per call, using the wording, options and `set`
commands in `${CLAUDE_PLUGIN_ROOT}/skills/start/references/intake.md` (the rows that are not
per video), in its three style calls: what to copy (platform, creators, what to take, liked videos),
what makes it yours (brand, own photos, avoid, captions; a brand file goes on the home page's Brand page or
through `lib/ai_editor/brandkit.py import <file>`, and a kit there answers brand), then sound, "Let graphics sit behind
you?" and "Have a raw take and the version you posted? I can learn how you cut." Every question has
a recommended first option. On yes to the last, run the taste skill's "Learn from a past edit".
On "use the defaults" (or once the three calls are done), run `python3 "${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/profile.py" defaults`:
anything left unanswered is saved as its default, so start never asks these again.

On **Yes** to graphics behind you, `install-all` has already downloaded the matting model (15 MB). Run
this to test it (it downloads the model too if that step failed):

```bash
python3 "$U" matte
```

Check: it prints `Tested: cutting the speaker out works.` On **No**, skip it: the cutout step never runs.

Then offer, in one question box, to study those creators now so the first edit is quick:
"Break down @handle's style now? (about a minute per creator)" with yes first. On yes, run the
creator-teardown skill in quick mode for each creator and each liked video link. On no, start does
it later. End with: "Ready. Type nextwork-editor in a terminal, or say edit my video."

## Optional: GitHub Actions and AWS Lambda renders

Only when the user picks **Other** at render time, or asks:
- **GitHub Actions** (free, a private repo in their account): `references/cloud.md` "The GitHub CLI".
- **AWS Lambda** (many machines at once, costs money on their own AWS account; style-edit quotes
  each render first): `references/lambda.md`.
