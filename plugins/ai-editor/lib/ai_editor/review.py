#!/usr/bin/env python3
"""The review page: the user watches a render and leaves notes at moments on its timeline. Stdlib only.

One page per edit folder, the hand-over after every render (the cut, the styled edit, a clip, a
product video). Notes save with the edit, never in the plugin:

    <folder>/review.json    every round, note, reply and send/approve event
    <folder>/review/        a frame still per note, and any image the user attached

    python3 review.py <folder> start --video cut.mp4 [--stage cut|edit] [--transcript words.json] [--plan plan.json]
                                     [--name NAME] [--note "..."]
    python3 review.py <folder> start --raw --video raw.mov --stage cut   round 0: the raw clip, open while the cut runs.
                                     No Approve or Stop; notes queue for round 1, which the next `start` or
                                     `round` opens (each raw time moved onto the cut by decisions.json)
    python3 review.py <folder> round --stage edit --stills --video stills.mp4 --plan plan.json
                                     the stills before the render (edit.py storyboard): one frame per beat over the
                                     cut's sound, notes and Approve on the same page; that approve means render it
    python3 review.py <folder> serve [--no-open]   serve the page and open it (run in the background)
    python3 review.py <folder> wait                block until the user presses send or approve (run in the background)
    python3 review.py <folder> status "rendering" [--log render.log] [--done]   what Claude is doing, live on the page
    python3 review.py <folder> final               the cut is the finished video ("just the cut"): no edit follows
    python3 review.py <folder> status --step captions|visuals|plan|render [--log ..]   a step of the styled edit:
                                     fills the page's "Making the edit" bar (the scripts report their own, step())
    python3 review.py <folder> resolve <id> fixed|wontfix|open [--reply "..."] [--new-t 12.3]
    python3 review.py <folder> round --video v2.mp4 [--stage cut|edit] [--transcript ..] [--plan ..] [--note ".."]
                                     [--changed "Captions one size smaller" ...]   anything changed beyond the notes
    python3 review.py <folder> back <n>             "Go back to draft N" (the Drafts tab does the same): that round's files
                                     (review/snap-<stage><n>/) and its render return as a new round
    python3 review.py <folder> alt <name> --video other.mp4 [--transcript ..]   another video in this round
    python3 review.py <folder> learn --scope this-style|style|video|everyone --rule <id> <section> "<rule>" [key=value] ...
                                     the round's preference notes into the user's taste (taste.py add); --none if
                                     none. Each note records it: "taste": rule id | video-only | suggested | one-off.
                                     this-style: the creator style the edit used (<folder>/style.json "source", or
                                     --style <style.json>): its overrides and its edit-like-<slug> skill; a skill
                                     style's rules go into that skill's SKILL.md "## Learned rules" (skillrules.py)
    python3 review.py <folder> learn --propose '<json>'   the final approve's LEARN block: candidate rules
                                     [{"rule", "section", "set"?, "why"?, "replace"?}] onto the page's "Teach <style>"
                                     panel (the skill-improver skill writes them)
    python3 review.py <folder> learn --done ["summary"]   save the rules the user ticked (styleskill.learn; a skill
                                     style's rules go into its SKILL.md, skillrules.py) and
                                     show "Saved to <style>. Next video uses it."
    python3 review.py <folder> trials --propose '<json>'   after a reel's final approve: the Trial reels tab
    python3 review.py <folder> trials --reply "..."        answer the user's notes on the made trial reels (TRIALS NOTE)
                                     {"message", "hooks": [{"text", "from"}], "versions": [{"kinds": "claude" |
                                     ["hooks"|"same"|"rewind"|"section"|"animations", ...], "line"}], "idea"?, "reply"?}.
                                     `wait` prints the user's Make (TRIALS), Skip, or question (TRIALS ASK);
                                     each render goes up with `alt t1 --video t1.mp4 --trial`
    python3 review.py demo                         self-check on a generated 6 s clip

A note that reads as a lasting preference ("always ...", "never ...", "too many zooms") is offered as a rule: the page
ticks "Keep as a rule for <style>" (POST /keep unticks it) and `wait` marks it [keep as a rule for <style>]. Every
rule `learn` saves (a note at a style scope, or the Teach panel's `--done`) adds a receipt to review.json
("receipts"): the page shows "Saved to <style>: <rule>. Undo", and POST /undo takes a rule that save added out again.

Every round also rewrites <folder>/timings.json: each stage's real time (the cut, the user's review, the edit up to
the stills, the stills check, the render) from the home job and review.json, and once the edit is back the line
the page shows under it, "Made in 6 min (cut 3:10, edit 1:40, render 0:52)". `round --stills` starts the laptop
render in the background (edit.py render --speculative); notes sent on the stills, or Stop, end it.
Every round snapshots the edit's own files (top-level .json/.txt under 2 MB, .sfx/music.wav and the card files plan.json shows) into
review/snap-<stage><round>/, so the page can show what changed ("Changed in this draft": the notes Claude answered,
then cards, zooms, captions, title, music and cut words that differ from the round before, plus each --changed line)
and go back to any round. On the edit, a click on a card, caption, title or zoom on the frame starts a note naming it
(the round's data "items"), and `wait` prints what is on screen at each note ([caption '...'], [zoom ...]).
Each round also gets review/data-<stage><round>.json for the page, built from the edit folder when
the files are there: the cut's transcript with every cut word and pause struck (decisions.json +
words.raw.json), the timeline's segments (cut points, or chapters.txt on the edit), and the edit's
Cards / Zooms / Captions tracks (plan.json). A missing file leaves that part out.
A note saved while a round is with Claude (after send) is queued for the next round: "queued": true, round
n+1. `wait` never sees it. `round` makes it an open note of the new round, moved to where the same words
are said when both rounds have the cut's transcript (else at the same time), with a new frame still.
Stop merges queued notes into the reopened round.
`status` exits 3 with STOPPED when the user pressed Stop on the page: stop the round and run `wait`.
The Transcript tab (cut stage) restores or cuts words: POST /edits {"restore": [[s, e]], "cut": [[s, e]]} in raw-take
seconds (and "pause": removed pauses to put back) rewrites spans.json and keep.json (apply_edits; *.prev.json kept) and `wait` prints "EDITS <n> transcript edits applied
to spans.json: rebuild, render, verify, round". Stop puts spans.prev.json and keep.prev.json back.

`wait` exits when the user presses send or approve, and prints every note of the round: its time,
the text, the words being said, the card on screen (from plan.json) and the frame still's path.
While `wait` runs the page says Claude is listening; without it the notes still save, and the next
`wait` returns at once with them.

The server listens on 127.0.0.1 only, and every request needs the random token in the URL it
prints (then a SameSite cookie), as preview.py does: another page open in the browser cannot read
the notes or press send.
"""
import argparse
import base64
import contextlib
import difflib
import filecmp
import hashlib
import hmac
import io
import json
import mimetypes
import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import threading
import time
import uuid
import urllib.error
import urllib.request
import webbrowser
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(1, str(Path(__file__).resolve().parent.parent))   # `from ai_editor import ...` (styleskill, taste)
import askhook  # noqa: E402
import assets  # noqa: E402
import live  # noqa: E402

HTML = Path(__file__).with_name("review.html")
LOCK = threading.RLock()   # re-entrant: /edits holds it across apply_edits and update
BEAT_S = 6          # `wait` touches review/.listening at least this often; older = nobody listening
IMAGE_TYPES = ("png", "jpeg", "gif", "webp")


def load(path):
    for i in range(20):   # Windows refuses a read for the instant another thread's os.replace swaps the file in
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except PermissionError:
            if i == 19:
                raise
            time.sleep(0.02)


def save(path, d):
    tmp = path.with_name(f"{path.stem}.{os.getpid()}.{threading.get_ident()}.tmp")   # one per writer, never shared
    tmp.write_text(json.dumps(d, indent=1), encoding="utf-8")
    for i in range(20):   # Windows refuses to replace a file another process is reading this instant
        try:
            return os.replace(tmp, path)
        except PermissionError:
            if i == 19:
                raise
            time.sleep(0.05)


class FileLock:
    """Cross-process and cross-thread: the page's server, the CLI and the style-edit scripts (step()) all write
    review.json. A lock file beside it made with O_EXCL (home.py's _Lock)."""
    def __init__(self, path, wait=10):
        self.p, self.tries = Path(path).with_name(Path(path).name + ".lock"), int(wait / 0.02)

    def __enter__(self):
        for _ in range(self.tries):
            try:
                os.close(os.open(self.p, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                return self
            except (FileExistsError, PermissionError):   # Windows: a lock being deleted refuses a new open
                try:   # a writer that died holding it: older than 10 s is stale
                    if time.time() - self.p.stat().st_mtime > 10:
                        self.p.unlink(missing_ok=True)
                except OSError:
                    pass
                time.sleep(0.02)
        raise TimeoutError(f"{self.p} is held; delete it if no review.py is running")

    def __exit__(self, *a):
        self.p.unlink(missing_ok=True)


def update(path, fn):
    with FileLock(path):
        d = load(path)
        out = fn(d)
        save(path, d)
        return out


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def probe(video):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", str(video)], capture_output=True, text=True).stdout.strip().split(",")
    return len(r) >= 2 and r[1].isdigit() and int(r[1]) > int(r[0])   # ffprobe can print a trailing comma


def duration(video):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                       capture_output=True, text=True).stdout.strip()
    try:
        return float(r)
    except ValueError:
        return None


def kept_s(w, spans):
    """Seconds of a word inside the kept spans (build_timeline.is_kept's measure)."""
    return sum(max(0.0, min(w["end"], s["end"]) - max(w["start"], s["start"])) for s in spans)


def cut_transcript(folder, dur):
    """The source transcript laid on the cut: every word, cut ones marked, removed pauses as chips, in lines.
    None unless decisions.json (kept source spans) and words.raw.json are there and add up to this video."""
    try:
        spans = sorted(load(folder / "decisions.json"), key=lambda s: s["start"])
        words = [w for w in load(folder / "words.raw.json") if w.get("type", "word") == "word"]
    except (OSError, ValueError, TypeError, AttributeError):
        return None
    if not spans or not words or dur is None or abs(sum(s["end"] - s["start"] for s in spans) - dur) > 0.5:
        return None
    offs, t = [], 0.0
    for s in spans:
        offs.append(t)
        t += s["end"] - s["start"]

    def on_cut(w):   # a kept word's start on the cut's timeline, in the span it plays in (build_timeline.retime)
        i = max(range(len(spans)), key=lambda k: min(w["end"], spans[k]["end"]) - max(w["start"], spans[k]["start"]))
        return round(max(w["start"], spans[i]["start"]) - spans[i]["start"] + offs[i], 2)

    why = span_times(folder)
    lines, line, prev = [], [], 0.0
    for w in words:
        if not all(isinstance(w.get(k), (int, float)) for k in ("start", "end")):   # no timing: shown, never editable
            line.append({"w": str(w.get("text", "")).strip(), "t": None, "nt": 1})
            continue
        gap = {"start": prev, "end": w["start"]}
        removed = (gap["end"] - gap["start"]) - kept_s(gap, spans)
        if removed >= 0.3:
            line.append({"p": round(removed, 1)})
        kept = kept_s(w, spans) >= min(0.1, (w["end"] - w["start"]) / 2)
        # s/e: the word on the raw take, for the transcript editor (select, restore or cut, preview)
        x = {"w": w["text"].strip(), "t": on_cut(w) if kept else None, "s": round(w["start"], 3), "e": round(w["end"], 3)}
        if not kept:   # why it is cut: g = the spans.json entry, k = its kind; no span = the pause trim
            g = next((i for i, (a, b, _, _) in enumerate(why) if a - 1e-3 <= w["start"] and w["end"] <= b + 1e-3), None)
            x.update({"k": why[g][2], "g": g, "n": why[g][3]} if g is not None else {"k": "pause"})
        line.append(x)
        prev = w["end"]
        if w["text"].strip()[-1:] in ".?!" or len(line) >= 24:
            lines.append(line)
            line = []
    lines += [line] if line else []
    try:
        src = float(load(folder / "report.json")["duration"])
    except (OSError, ValueError, KeyError, TypeError):
        src = max((w["end"] for w in words if isinstance(w.get("end"), (int, float))), default=0.0)
    cuts = sum(1 for a, b in zip([{"end": 0.0}] + spans, spans + [{"start": src}]) if b["start"] - a["end"] > 0.05)
    return {"lines": [{"t": next((x["t"] for x in ln if x.get("t") is not None), None), "tokens": ln} for ln in lines],
            "cuts": cuts, "source_s": round(src, 1), "points": [round(o, 2) for o in offs[1:]],
            "kept": [[round(s["start"], 3), round(s["end"], 3)] for s in spans]}


def chapters_of(folder):
    """chapters.txt ("0:00 title" lines, chapters.py) as [[seconds, title], ...]."""
    try:
        rows = (folder / "chapters.txt").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for r in rows:
        m = re.match(r"(?:(\d+):)?(\d+):(\d+)\s+(.+)", r.strip())
        if m:
            out.append([int(m[1] or 0) * 3600 + int(m[2]) * 60 + int(m[3]), m[4]])
    return out


def data_of(folder, name):
    try:
        return load(folder / "review" / Path(name).name) if name else {}
    except (OSError, ValueError):
        return {}


def upgrade_transcript(folder, p):
    """A cut round's data file written before words carried their raw-take times (s/e): every word looked untimed, so
    the page could neither edit nor follow it. Rebuilt from decisions.json + words.raw.json when they still add up."""
    try:
        data = load(p)
        toks = [x for ln in (data.get("transcript") or {}).get("lines", []) for x in ln["tokens"] if "w" in x]
        if not toks or any("s" in x or x.get("nt") for x in toks):
            return
        tx = cut_transcript(folder, data.get("duration"))
        if tx:
            data["transcript"] = tx
            save(p, data)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass


def round_data(folder, video, stage, rnd, plan, prev=None):
    """review/data-<stage><round>.json: what the page draws beside the video. Every part optional.
    prev: the round before on this stage ({"data", "snap"}), for "Changed in this round" (changes)."""
    dur = duration(video)
    d = {"duration": dur}
    tx = cut_transcript(folder, dur)
    if tx and stage == "cut":
        d["transcript"] = tx
    if stage == "edit" and chapters_of(folder):
        d["chapters"] = chapters_of(folder)
    elif tx:
        d["points"] = tx["points"]
    try:
        p = load(plan) if plan else None
    except (OSError, ValueError):
        p = None
    if stage == "edit" and isinstance(p, dict):
        span = lambda xs: [[round(x["start"], 2), round(x["end"], 2)] for x in xs or [] if "start" in x and "end" in x]
        d["tracks"] = {"cards": span(p.get("cards")), "zooms": span(p.get("zooms")),
                       "captions": span((p.get("captions") or {}).get("chunks"))}
        d["items"] = screen_items(folder, p)
    if prev:
        old = data_of(folder, prev.get("data"))
        if stage == "cut":
            d["changes"] = cut_changes(old.get("transcript"), d.get("transcript"))
        else:
            d["changes"] = plan_changes(snap_file(folder, prev.get("snap"), "plan.json"), p,
                                        music=snap_sha(folder, prev.get("snap")) != music_sha(folder))
        if old.get("duration") and dur and abs(old["duration"] - dur) >= 0.1:
            d["changes"].append({"t": None, "text": f"{abs(old['duration'] - dur):.1f} s {'shorter' if dur < old['duration'] else 'longer'}"})
    name = f"data-{stage}{rnd}.json"
    (folder / "review" / name).write_text(json.dumps(d), encoding="utf-8")
    return name


def _host(url):
    return re.sub(r"^www\.", "", urlsplit(str(url)).netloc) or str(url)


CARD_IMG = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg")


def card_key(c):
    """A card's key in overrides.json (style-edit preview.py card_key): plan.py finds it again after a re-plan."""
    return c.get("override") or f"{c.get('trigger_word', '')}@{c['start']:.3f}"


CAP_GROUPS = {"1": 1, "3": 3, "5": 5, "sentence": 12}   # the Captions panel's words at a time (12: breaks at the sentence's own commas and stops)


CAP_STYLE = {"size": ("size_pct", 2, 12), "y": ("y_pct", 15, 85), "color": ("color",), "highlight": ("highlight_color",)}   # the panel's style rows


def captions_info(folder, plan=None):
    """The Captions panel: the looks (presets.py, built in then the user's) and this video's words at a time and look,
    from taste (this video's settings win, as plan.py reads them); "base" the caption style in the draft (its plan), and
    "mine" this video's own size, place and colours, which the page draws over the video until a draft has them."""
    from ai_editor import presets, taste
    looks = {k: {f: v.get(f) for f in ("size_pct", "weight", "case", "color", "stroke", "stroke_color", "box", "box_color",
                                     "shadow", "highlight_color", "words_per_caption", "font_match") if v.get(f) is not None}
             for k, v in presets.captions().items()}
    cap = (taste.load_json(folder, count=False) or {}).get("captions") or {}
    n = cap.get("words_per_caption")
    keys = {f"captions.{k[0]}" for k in CAP_STYLE.values()}
    mine = {r["setting"][9:]: r["value"] for r in taste.load_rules() if r.get("scope") == f"video:{folder.name}" and r.get("setting") in keys} \
        if taste.rules_path().exists() else {}
    try:
        st = (load(plan).get("captions") or {}).get("style") or {} if plan else {}
    except (OSError, ValueError):
        st = {}
    base = {f: st[f] for f in ("size_pct", "y_pct", "width_pct", "weight", "case", "color", "highlight_color", "stroke", "box",
                               "box_color", "shadow", "font_match", "style") if st.get(f) is not None}
    return {"looks": looks, "look": cap.get("preset"), "base": base, "mine": mine,
            "words": next((k for k, v in CAP_GROUPS.items() if v == n), str(n) if n else None)}


def set_captions(folder, words=None, look=None, style=None):
    """Save the Captions panel's choice for this video only (taste scope video:<name>), the way the taste skill does.
    style: {"size", "y", "color", "highlight"} (CAP_STYLE), each one a setting plan.py lays over the look."""
    from ai_editor import presets, taste
    said = []
    if words is not None:
        if str(words) not in CAP_GROUPS:
            raise ValueError("words: 1, 3, 5 or sentence")
        n = CAP_GROUPS[str(words)]
        taste.add("Captions", "Captions a sentence at a time" if n == 12 else f"Captions {n} word{'' if n == 1 else 's'} at a time",
                  "captions.words_per_caption", n, scope=f"video:{folder.name}", edit=str(folder), source="review")
        said.append("a sentence at a time" if n == 12 else f"{n} word{'' if n == 1 else 's'} at a time")
    if look is not None:
        if look not in presets.captions():
            raise ValueError("look: one of the caption presets")
        taste.add("Captions", f"Captions look: {look}", "captions.preset", look, scope=f"video:{folder.name}", edit=str(folder),
                  source="review")
        said.append(f"the {look} look")
    for k, (key, *lim) in CAP_STYLE.items():
        v = (style or {}).get(k)
        if v is None:
            continue
        if lim:
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not lim[0] <= v <= lim[1]:
                raise ValueError(f"{k}: a number from {lim[0]} to {lim[1]}")
            v = round(float(v), 1 if k == "size" else None)   # the place in whole percent, as the slider moves it
        elif not isinstance(v, str) or not presets.HEX.fullmatch(v):
            raise ValueError(f"{k}: a colour like #FFD60A")
        else:
            v = v.upper()
        what = {"size": f"size {v}", "y": f"{v}% down the frame", "color": f"colour {v}", "highlight": f"highlight {v}"}[k]
        taste.add("Captions", f"Captions {what}", f"captions.{key}", v, scope=f"video:{folder.name}", edit=str(folder), source="review")
        said.append(what)
    return said


def sfx_mod():
    """style-edit's sfx.py (the sound kit and the sound library)."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills" / "style-edit" / "scripts"))
    import sfx
    return sfx


def sounds_info():
    """The Sounds panel: each moment that can have a sound, what plays there now, and the user's own files."""
    sfx = sfx_mod()
    c = sfx.choices()
    own = sfx.own_sounds()
    return {"cues": [{"cue": k, "label": sfx.LABELS[k][0], "when": sfx.LABELS[k][1], "choice": c[k]} for k in sfx.LABELS],
            "own": own, "own_len": {n: sound_shape(sfx.library_dir() / n, n=8).get("d") for n in own}}


SOUND_MAX_MB = 10
LIBRARY_MAX_MB = 100   # a sound file put in the library from the Sounds panel (a song fits)


def library_upload(name, stream, n):
    """One sound file into the sound library (custom/sounds, kept for every video), streamed. Returns its saved name;
    ValueError with the words to show."""
    sfx = sfx_mod()
    name = re.sub(r"[^A-Za-z0-9._ -]", "", Path(str(name or "")).name).strip()[:80]
    if not name or Path(name).suffix.lower() not in sfx.SOUND_EXT:
        raise ValueError("Add a sound file: wav, mp3, m4a, aac, flac, ogg or opus.")
    if not 0 < n <= LIBRARY_MAX_MB * 1024 * 1024:
        raise ValueError(f"Sounds under {LIBRARY_MAX_MB} MB only.")
    lib = sfx.library_dir()
    lib.mkdir(parents=True, exist_ok=True)
    out, k = lib / name, 1
    while out.exists():
        out, k = lib / f"{Path(name).stem} {k}{Path(name).suffix}", k + 1
    tmp, left = out.with_name("." + out.name + ".part"), n
    with open(tmp, "wb") as f:
        while left > 0:
            b = stream.read(min(1 << 20, left))
            if not b:
                break
            f.write(b)
            left -= len(b)
    if left:
        tmp.unlink(missing_ok=True)
        raise ValueError("The upload stopped part way. Add it again.")
    os.replace(tmp, out)
    if not sound_shape(out, n=8).get("d"):
        out.unlink(missing_ok=True)
        raise ValueError(f"{name} did not play as audio.")
    return out.name


def library_remove(name):
    """A sound out of the library, into custom/sounds/.removed (kept, not deleted); a moment that used it goes back
    to the built-in sound."""
    sfx = sfx_mod()
    if name not in sfx.own_sounds():
        raise ValueError("That sound is not in your library.")
    lib = sfx.library_dir()
    (lib / ".removed").mkdir(exist_ok=True)
    os.replace(lib / name, lib / ".removed" / name)
    for cue, pick in sfx.choices().items():
        if pick == name:
            sfx.choose(cue, "default")


def placed_raw(folder):
    """<edit>/sounds.json's items as saved: {id, t, sound}."""
    f = Path(folder) / "sounds.json"
    return (load(f).get("items") or []) if f.exists() else []


def placed_sounds(folder):
    """placed_raw with each sound's length and waveform, for the page. A dropped audio file (kind "clip") is its whole
    file's: the page draws its in..in+dur part."""
    items = placed_raw(folder)
    lib = sfx_mod().library_dir()
    return [{**x, **(sound_shape(Path(folder) / "audio" / x["sound"], n=240) if x.get("kind") == "clip"
                     else sound_shape(lib / x["sound"], cap=sfx_mod().MAX_OWN_S))} for x in items if isinstance(x, dict) and "sound" in x]


AUDIO_MAX_MB = 200   # a song dropped on the timeline


def save_audio(folder, name, stream, n, t, dur_of):
    """One audio file dropped on the timeline: n bytes into <edit>/audio/, and a sounds.json clip at t for its length
    (up to the video's end). Returns the item; ValueError with the words to show."""
    sfx = sfx_mod()
    name = re.sub(r"[^A-Za-z0-9._ -]", "", Path(str(name or "")).name).strip()[:80]
    if not name or Path(name).suffix.lower() not in sfx.SOUND_EXT:
        raise ValueError("Drop an audio file: wav, mp3, m4a, aac, flac, ogg or opus.")
    if not 0 < n <= AUDIO_MAX_MB * 1024 * 1024:
        raise ValueError(f"Audio under {AUDIO_MAX_MB} MB only.")
    d = Path(folder) / "audio"
    d.mkdir(exist_ok=True)
    out, k = d / name, 1
    while out.exists():   # never over another clip's file
        out, k = d / f"{Path(name).stem}-{k}{Path(name).suffix}", k + 1
    tmp, left = out.with_name(out.name + ".part"), n
    with open(tmp, "wb") as f:
        while left > 0:
            b = stream.read(min(1 << 20, left))
            if not b:
                break
            f.write(b)
            left -= len(b)
    if left:
        tmp.unlink(missing_ok=True)
        raise ValueError("The upload stopped part way. Drop it again.")
    os.replace(tmp, out)
    length = sound_shape(out, n=240).get("d")
    if not length:
        out.unlink(missing_ok=True)
        raise ValueError(f"{name} did not play as audio.")
    t = round(max(0.0, t), 2)
    x = {"id": secrets.token_hex(4), "t": t, "sound": out.name, "kind": "clip", "in": 0.0,
         "dur": round(max(0.1, min(length, dur_of - t if dur_of else length)), 2), "vol": 1.0}
    f = Path(folder) / "sounds.json"
    f.write_text(json.dumps({"items": placed_raw(folder) + [x]}, indent=1), encoding="utf-8")
    return x


_SHAPE = {}


def sound_shape(f, cap=None, n=48):
    """{"d": seconds, "peaks": n values 0-1}: how long a sound is and its waveform, for the timeline's sound clips
    (a CapCut-style clip). Cached by file and time; {} when the file cannot be read."""
    try:
        k = (str(f), Path(f).stat().st_mtime, cap)
    except OSError:
        return {}
    if k not in _SHAPE:
        try:
            x = sfx_mod().pcm(src=f)
        except Exception:
            return {}
        if cap:
            x = x[:int(cap * sfx_mod().SR)]
        step = max(1, len(x) // n)
        peaks = [max((abs(v) for v in x[i:i + step]), default=0.0) for i in range(0, step * n, step)]
        top = max(peaks) or 1.0
        _SHAPE[k] = {"d": round(len(x) / sfx_mod().SR, 3), "peaks": [round(v / top, 2) for v in peaks]}
    return _SHAPE[k]


def sound_name(src):
    """What the timeline calls a sound: "glide-short-wind" for .sfx/own-house-glide-short-wind.wav, "whoosh-in" for .sfx/whoosh-in.wav."""
    n = Path(str(src)).stem
    return re.sub(r"^own-(house|skit|simple|swoop|windy|digital)-", "", n).removeprefix("own-")


def caption_words(starts, text):
    """A caption line's new text onto its words (overrides.json "words": {start: text}, preview.apply_overrides): one
    word each while they last, the rest on the last word; a line with fewer words blanks the extra ones ("" deletes)."""
    new = str(text).split()
    if not starts:
        raise ValueError("a caption line with no words")
    out = {k: (new[i] if i < len(new) else "") for i, k in enumerate(starts)}
    if len(new) > len(starts):
        out[starts[-1]] = " ".join(new[len(starts) - 1:])
    return out


def card_override(folder, key, change):
    """The video page's move, resize or delete of a card into <edit>/overrides.json (preview.py apply_overrides,
    which plan.py runs after planning, so a re-plan keeps it). change: {"box": [x, y, w, h]}, {"start", "end"} or {"deleted": True}."""
    f = Path(folder) / "overrides.json"
    ov = load(f) if f.exists() else {}
    cards = ov.setdefault("cards", {})
    cards[key] = {**(cards.get(key) or {}), **change}
    f.write_text(json.dumps(ov, indent=1), encoding="utf-8")
    return cards[key]


def screen_items(folder, p):
    """What the page can click on the frame, from plan.json: each card's box and what it shows ("the github.com page"),
    the caption chunks and where captions sit, the zooms and the title texts. Boxes are % of the frame."""
    names = {}   # a card's src, or its word, -> what it shows (images.json / visuals.json)
    for f in ("images.json", "visuals.json"):
        try:
            xs = load(folder / f)
        except (OSError, ValueError):
            continue
        for x in xs if isinstance(xs, list) else []:
            if not isinstance(x, dict):
                continue
            what = (f"the {x['brand']} logo" if x.get("brand") else f"the {_host(x['url'])} page" if x.get("url")
                    else f"the {x['type']} animation" if x.get("kind") == "anim" and x.get("type") else None)
            if what and x.get("src"):
                names.setdefault(x["src"], what)
            if what and x.get("word"):
                names.setdefault(str(x["word"]).lower(), what)
    cards = []
    for i, c in enumerate(p.get("cards") or []):
        if "start" not in c or "end" not in c:
            continue
        w, an = (c.get("trigger_word") or "").strip(), c.get("anim") or {}
        what = (names.get(c.get("src")) or ("the motion clip" if an.get("type") == "video_card" else f"the {an['type']} animation" if an.get("type") else None)
                or names.get(w.lower()) or (f"the {c['format']}" if c.get("format") in ("logo", "browser", "post") else "the picture"))
        box = c.get("box") if isinstance(c.get("box"), list) and len(c["box"]) == 4 else [0, 0, 100, 50] if c.get("layout") == "split" else [0, 0, 100, 100]
        src = c.get("src") if isinstance(c.get("src"), str) and Path(c["src"]).suffix.lower() in CARD_IMG else None
        cards.append({"i": i, "s": round(c["start"], 2), "e": round(c["end"], 2), "box": [round(float(v), 1) for v in box],
                      "label": what + (f' on "{w}"' if w else ""), "key": card_key(c),   # the page moves, resizes or deletes it
                      **({"src": src} if src and (folder / src).is_file() else {})})
    cap = (p.get("captions") or {}).get("style") or {}
    size = float(cap.get("size_pct") or 6) * max(p.get("width") or 1, p.get("height") or 1) / (p.get("height") or 1)
    texts = []
    for x in p.get("texts") or []:   # Texts.tsx: a title or cta across the middle 74%, a list from its x_pct
        if "start" not in x or "end" not in x:
            continue
        items = [str(i.get("text") or "") for i in x.get("items") or [] if isinstance(i, dict)]
        text = ", ".join(items) if items else str(x.get("text") or "")
        lines = len(items) if items else 1 + text.count("\n")
        size = float(x.get("size_pct") or 4) * (2 if items else 1.3) * max(1, lines)
        texts.append({"s": round(x["start"], 2), "e": round(x["end"], 2), "kind": x.get("kind") or "text", "text": text,
                      "box": [float(x.get("x_pct") or 50) - 30, float(x.get("y_pct") or 50) - size / 2, 60, round(size, 1)]
                      if x.get("kind") == "label" else [float(x.get("x_pct") or 6), float(x.get("y_pct") or 10), 60, round(size, 1)] if items
                      else [13, float(x.get("y_pct") or 10), 74, round(size, 1)]})
    return {"cards": cards, "texts": texts,
            # each caption line with its words' starts (overrides.json "words" keys), so the page can edit the line
            "captions": [{"s": round(x["start"], 2), "e": round(x["end"], 2), "text": str(x.get("text") or ""),
                          "w": [f"{w['start']:.3f}" for w in x.get("words") or [] if "start" in w]}
                         for x in (p.get("captions") or {}).get("chunks") or [] if "start" in x and "end" in x],
            "cap": None if cap.get("present") is False else {"y": float(cap.get("y_pct") or 70), "h": round(size * 2.2, 1),
                                                               "w": float(cap.get("width_pct") or 86)},
            "zooms": [{"s": round(z["start"], 2), "e": round(z["end"], 2)} for z in p.get("zooms") or [] if "start" in z and "end" in z],
            # the sounds in the draft, for the timeline's Sounds row: when each is heard, and which it is
            "sfx": [{"t": round(float(x.get("event", x["t"])), 3), "start": round(float(x["t"]), 3), "src": str(x.get("src") or ""),
                     "placed": x.get("placed"), **sound_shape(folder / str(x.get("src") or ""))}
                    for x in p.get("sfx") or [] if isinstance(x, dict) and "t" in x]}


SNAP_MAX = 2 << 20   # a snapshot keeps the edit's small files; a bigger one is media, never a setting
SNAP_NAMES = ".names"   # in a snapshot: the names of the files the edit had then


def clone(src, dst):
    """A copy that costs no disk on a Mac (APFS clone, cp -c) until one side changes; a plain copy elsewhere."""
    dst.unlink(missing_ok=True)
    if sys.platform != "darwin" or subprocess.run(["cp", "-c", str(src), str(dst)], capture_output=True).returncode:
        shutil.copyfile(src, dst)


def snapshot(folder, stage, rnd):
    """review/snap-<stage><round>/: the edit's own files as this round was made (every top-level .json and .txt under
    2 MB, and the music bed), so "Go back to round N" can put them back. The render is the round's kept video."""
    dst = folder / "review" / f"snap-{stage}{rnd}"
    shutil.rmtree(dst, ignore_errors=True)
    dst.mkdir(parents=True)
    names = []   # every top-level setting file, big ones too: going back removes any file this list lacks
    for f in folder.iterdir():
        if f.is_file() and f.suffix in (".json", ".txt") and f.name != "review.json":
            names.append(f.name)
            if f.stat().st_size <= SNAP_MAX:
                clone(f, dst / f.name)
    if (folder / ".sfx" / "music.wav").is_file():
        clone(folder / ".sfx" / "music.wav", dst / "music.wav")
        names.append("music.wav")
    (dst / SNAP_NAMES).write_text("\n".join(sorted(names)), encoding="utf-8")
    try:   # the pictures and clips the plan shows: a fix can rebuild one in place (a motion clip, a capture)
        p = load(folder / "plan.json")
    except (OSError, ValueError):
        p = {}
    for c in p.get("cards") or [] if isinstance(p, dict) else []:
        for rel in (c.get("src"), ((c.get("anim") or {}).get("props") or {}).get("src")):
            f = folder / str(rel or "-")
            if rel and f.is_file() and folder.resolve() in f.resolve().parents:
                (dst / "files" / rel).parent.mkdir(parents=True, exist_ok=True)
                clone(f, dst / "files" / rel)
    return dst.name


def snap_file(folder, snap, name):
    try:
        return load(folder / "review" / Path(snap).name / name) if snap else None
    except (OSError, ValueError):
        return None


def music_sha(folder, f=None):
    f = f or folder / ".sfx" / "music.wav"
    try:
        return hashlib.sha1(f.read_bytes()).hexdigest()
    except OSError:
        return None


def snap_sha(folder, snap):
    return music_sha(folder, folder / "review" / Path(snap).name / "music.wav") if snap else music_sha(folder)


def _said(w):
    w = (w or "").strip()
    return f' on "{w}"' if w else ""


def plan_changes(a, b, music=False):
    """What changed between two plan.json: cards swapped, removed, added, bigger, moved or retimed; zooms; the
    caption look and words; the title; the music. [{"t": seconds or None, "text"}], in time order."""
    if not isinstance(a, dict) or not isinstance(b, dict):
        return []
    out = []
    key = lambda c: (c.get("src") or (c.get("anim") or {}).get("type") or c.get("format") or "card", (c.get("trigger_word") or "").strip().lower())
    A = {key(c): c for c in a.get("cards") or [] if "start" in c}
    B = {key(c): c for c in b.get("cards") or [] if "start" in c}
    gone, new = [c for k, c in A.items() if k not in B], [c for k, c in B.items() if k not in A]
    for c in list(new):   # the same word, another picture: a swap
        o = next((g for g in gone if key(g)[1] and key(g)[1] == key(c)[1]), None)
        if o:
            gone.remove(o)
            new.remove(c)
            out.append((c["start"], "Swapped the card" + _said(c.get("trigger_word"))))
    out += [(c["start"], "Removed the card" + _said(c.get("trigger_word"))) for c in gone]
    out += [(c["start"], "Added a card" + _said(c.get("trigger_word"))) for c in new]
    area = lambda c: (c.get("box") or [0, 0, 100, 100])[2] * (c.get("box") or [0, 0, 100, 100])[3]
    px = lambda c: (lambda z: z[0] * z[1] if isinstance(z, list) and len(z) == 2 else 0)(c.get("size") or ((c.get("anim") or {}).get("props") or {}).get("size"))
    shows = lambda c: ((c.get("props") or {}).get("url"), c.get("format"), ((c.get("anim") or {}).get("props") or {}).get("motion"))
    grew = lambda f, x, y: f(x) and f(y) and abs(f(y) - f(x)) > 0.05 * f(x)
    for k in A.keys() & B.keys():
        x, y, w = A[k], B[k], _said(B[k].get("trigger_word"))
        if shows(x) != shows(y):   # the same file name, another page or clip in it
            out.append((y["start"], "Swapped the card" + w))
        elif grew(area, x, y) or grew(px, x, y):   # the box on the frame, else the picture inside it
            big = area(y) > area(x) if grew(area, x, y) else px(y) > px(x)
            out.append((y["start"], f"Made the card{w} {'bigger' if big else 'smaller'}"))
        elif x.get("box") != y.get("box"):
            out.append((y["start"], f"Moved the card{w}"))
        elif abs(x["start"] - y["start"]) >= 0.05 or abs(x.get("end", 0) - y.get("end", 0)) >= 0.05:
            out.append((y["start"], f"Retimed the card{w}"))
        elif x != y:
            out.append((y["start"], f"Changed the card{w}"))
    za = {round(z["start"], 1): z for z in a.get("zooms") or [] if "start" in z}
    zb = {round(z["start"], 1): z for z in b.get("zooms") or [] if "start" in z}
    out += [(t, f"Removed the zoom at {fmt(t)}") for t in za.keys() - zb.keys()]
    out += [(t, f"Added a zoom at {fmt(t)}") for t in zb.keys() - za.keys()]
    out += [(t, f"Zoom at {fmt(t)} {'stronger' if zb[t].get('scale', 1) > za[t].get('scale', 1) else 'softer'}")
            for t in za.keys() & zb.keys() if abs(zb[t].get("scale", 1) - za[t].get("scale", 1)) >= 0.01]
    ca, cb = a.get("captions") or {}, b.get("captions") or {}
    sa, sb = ca.get("style") or {}, cb.get("style") or {}
    if (sa.get("size_pct") or 0) != (sb.get("size_pct") or 0) and sa.get("size_pct") and sb.get("size_pct"):
        out.append((None, f"Captions {'bigger' if sb['size_pct'] > sa['size_pct'] else 'smaller'}"))
    rest = sorted(k for k in sa.keys() | sb.keys() if k != "size_pct" and sa.get(k) != sb.get(k))
    if rest:
        out.append((None, "Caption look changed: " + ", ".join(k.replace("_pct", "").replace("_", " ") for k in rest[:4])))
    # the caption words in order, both rounds: a word fixed reads differently, words cut or put back go or come
    # (by order, not time: a cut moves every later caption)
    def cwords(cap):
        out_ = []
        for ch in cap.get("chunks") or []:
            ws = ch.get("words") or [{"text": w, "start": ch.get("start", 0)} for w in str(ch.get("text", "")).split()]
            out_ += [(str(w.get("text", "")).strip(), w.get("start", ch.get("start", 0))) for w in ws if str(w.get("text", "")).strip()]
        return out_
    wa, wb = cwords(ca), cwords(cb)
    norm = lambda ws: [re.sub(r"[^\w']", "", w) for w, _ in ws]   # "song" -> "SONG" is a fix; "reels." -> "reels" is not
    say = lambda ws: " ".join(w for w, _ in ws[:6]) + (" ..." if len(ws) > 6 else "")
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, norm(wa), norm(wb), autojunk=False).get_opcodes():
        if op == "replace":
            out.append((wb[j1][1], f'Caption now reads "{say(wb[j1:j2])}"'))
        elif op == "insert":
            out.append((wb[j1][1], f'Put back "{say(wb[j1:j2])}"'))
        elif op == "delete":
            out.append((wb[j1][1] if j1 < len(wb) else wa[i1][1], f'Cut "{say(wa[i1:i2])}"'))
    xa, xb = a.get("texts") or [], b.get("texts") or []
    for i in range(max(len(xa), len(xb))):
        x, y = (xa[i] if i < len(xa) else None), (xb[i] if i < len(xb) else None)
        kind = ((y or x).get("kind") or "text").capitalize()
        if x and not y:
            out.append((x.get("start"), f"Removed the {kind.lower()}"))
        elif y and not x:
            out.append((y.get("start"), f'Added a {kind.lower()}: "{y.get("text", "")}"'))
        elif str(x.get("text", "")).split() != str(y.get("text", "")).split():
            out.append((y.get("start"), f'{kind} now reads "{y.get("text", "")}"'))
        elif (y.get("size_pct") or 0) != (x.get("size_pct") or 0) and x.get("size_pct") and y.get("size_pct"):
            out.append((y.get("start"), f"{kind} {'bigger' if y['size_pct'] > x['size_pct'] else 'smaller'}"))
        elif x != y:
            out.append((y.get("start"), f"Changed the {kind.lower()}"))
    if ("music" in a) != ("music" in b):
        out.append((None, "Added music" if "music" in b else "Removed the music"))
    elif music and "music" in b:
        out.append((None, "Changed the music"))
    out = [{"t": None if t is None else round(t, 2), "text": x.replace("\n", " ")} for t, x in out]
    return sorted(out, key=lambda c: (c["t"] is not None, c["t"] or 0))


def cut_changes(old, new):
    """Words the new cut takes out or puts back against the round before (both cut transcripts come from words.raw.json,
    so word n is the same word). [{"t", "text"}]; nothing when the two cannot be lined up."""
    flat = lambda tx: [x for ln in tx["lines"] for x in ln["tokens"] if "w" in x]
    if not old or not new or len(flat(old)) != len(flat(new)):
        return []
    a, b, out, k = flat(old), flat(new), [], 0
    while k < len(b):
        was, now = a[k].get("t") is not None, b[k].get("t") is not None
        if was == now:
            k += 1
            continue
        j = k
        while j + 1 < len(b) and (a[j + 1].get("t") is not None) == was and (b[j + 1].get("t") is not None) == now:
            j += 1
        words = [x["w"] for x in b[k:j + 1]]
        said = " ".join(words[:6]) + (" ..." if len(words) > 6 else "")
        t = b[k]["t"] if now else next((x["t"] for x in b[j + 1:] if x.get("t") is not None), None)
        out.append({"t": t, "text": f'{"Put back" if now else "Cut"} "{said}"'})
        k = j + 1
    return out


def words_of(transcript):
    """A transcript's words: the plugin's list shape, or {"words": [...]} from other tools."""
    if not transcript or not Path(transcript).exists():
        return []
    d = load(transcript)
    ws = d.get("words", []) if isinstance(d, dict) else d
    return [w for w in ws if isinstance(w, dict) and w.get("type", "word") == "word"]


def words_at(transcript, t0, t1):
    got = [w["text"].strip() for w in words_of(transcript) if w["end"] >= t0 - 1.5 and w["start"] <= t1 + 1.5]
    return " ".join(x for x in got if x)


def card_at(plan, t):
    """The plan.json card on screen at t, so a note maps to the card it is about."""
    if not plan or not Path(plan).exists():
        return None
    for i, c in enumerate(load(plan).get("cards", [])):
        if c.get("start", 0) <= t < c.get("end", 0):
            kind = (c.get("anim") or {}).get("type") or c.get("lane") or "image"
            return {"i": i, "kind": kind, "trigger_word": c.get("trigger_word"), "src": c.get("src"),
                    "start": c["start"], "end": c["end"]}
    return None


def note_tags(plan, transcript, stage, t, te=None, on=None):
    """(words, card) for a note: what the user clicked ("on": {"k": cards|captions|texts|zooms, "text"}), else what is on
    screen at t exactly. The quote is the caption page showing then, not seconds of speech; a zoom or a caption click is
    never tagged with the card under it (QA round 4: "Card 1 on 'tutorials'" on a zoom note)."""
    if stage != "edit":
        return words_at(transcript, t, te if te is not None else t), None
    k = (on or {}).get("k") if isinstance(on, dict) else None
    card = card_at(plan, t) if k in (None, "cards") else None
    try:
        chunks = (load(plan).get("captions") or {}).get("chunks") or [] if plan else []
    except (OSError, ValueError):
        chunks = []
    cap = next((x.get("text") for x in chunks if x.get("start", 0) <= t < x.get("end", 0)), None)
    if k == "captions" and str(on.get("text") or "").strip():
        return str(on["text"]).strip(), card
    if cap:
        return str(cap).strip(), card
    return (words_at(transcript, t, te if te is not None else t) if not chunks else ""), card


TEXT_STYLES = ("plain", "outline", "box", "block")   # TikTok's and Instagram's own: white, white with a black edge, black on
# white (each line its own box); block: one box that hugs the whole text
TEXT_SIZE, TEXT_HOLD_S = 6.0, 3.0   # % of the frame's short side; seconds on screen when no range is marked
TEXT_FONTS = ("TikTok Sans", "Inter", "Montserrat", "Poppins", "Bebas Neue", "Anton", "Playfair Display",
              "Permanent Marker", "Lobster", "Roboto Mono")   # Google fonts Texts.tsx loads; TikTok Sans is the default


def text_look(add):
    """The Text tool's look on a note or a texts.json row: {style, x_pct, y_pct, size_pct}. ValueError when it is not one."""
    try:
        out = {"style": add["style"], **{k: round(min(100.0, max(0.0, float(add[k]))), 1) for k in ("x_pct", "y_pct")},
               "size_pct": round(min(20.0, max(2.0, float(add.get("size_pct") or TEXT_SIZE))), 1)}
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError("add_text takes style, x_pct and y_pct") from e
    if out["style"] not in TEXT_STYLES:
        raise ValueError("Text goes on the edit, in plain, outline or box.")
    if add.get("font") and add["font"] != "TikTok Sans":   # only set when picked, so older rows keep their bake key
        if add["font"] not in TEXT_FONTS:
            raise ValueError(f"Pick one of the fonts: {', '.join(TEXT_FONTS)}.")
        out["font"] = add["font"]
    if add.get("color") and str(add["color"]).upper() != "#FFFFFF":
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", str(add["color"])):
            raise ValueError("A colour is #RRGGBB.")
        out["color"] = str(add["color"]).upper()
    if add.get("width_pct") is not None and float(add["width_pct"]) < 84:   # the text's width brought in: it wraps sooner
        out["width_pct"] = round(max(15.0, float(add["width_pct"])), 1)
    return out


def put_texts(folder, notes):
    """The Text tool's notes into <edit>/texts.json (plan.py typed_texts), one row per note, replaced if sent again.
    Returns how many rows came from these notes."""
    rows = [{"id": f"{c['stage']}{c['round']}-{c['id']}", "text": c["text"], **c["add_text"], "start": c["t"], "end": c["t_end"]}
            for c in notes if c.get("add_text")]
    if rows:
        f = Path(folder) / "texts.json"
        old = load(f).get("items") or [] if f.exists() else []
        ids = {r["id"] for r in rows}
        f.write_text(json.dumps({"items": [x for x in old if x.get("id") not in ids] + rows}, indent=1), encoding="utf-8")
    return len(rows)


def timeline_cuts(body):
    """The Video row's {splits, gone} cleaned: splits sorted and unique, gone ranges merged, at most 200 of each.
    ValueError when they are not numbers."""
    splits = sorted({round(float(t), 2) for t in body.get("splits") or [] if float(t) > 0})[:200]
    gone = []
    for a, b in sorted([round(float(a), 2), round(float(b), 2)] for a, b in (body.get("gone") or [])[:200]):
        if b - a < 0.05:
            continue
        if gone and a <= gone[-1][1]:
            gone[-1][1] = max(gone[-1][1], b)
        else:
            gone.append([a, b])
    return {"splits": splits, "gone": gone}


def cuts_text(transcript, gone):
    """The note for the timeline's cut pieces: each range on the edit's clock with the words said in it (a word is
    in when its middle is, apply_edits' rule), for Claude to take out of spans.json and render again. "" for none."""
    if not gone:
        return ""
    try:
        words = [w for w in words_of(transcript) if "start" in w]
    except (OSError, ValueError, TypeError):
        words = []
    said = lambda a, b: " ".join(w["text"].strip() for w in words if a - 1e-3 <= (w["start"] + w["end"]) / 2 <= b + 1e-3)
    parts = [f'{fmt(a)}-{fmt(b)}' + (f' ("{said(a, b)}")' if said(a, b) else " (no words)") for a, b in gone]
    return (f"Cut from the video on the timeline: {'; '.join(parts)}. Take these out of the cut (spans.json, the words "
            f"quoted), then plan and render again. The page plays the draft without them already.")


def typed_labels(folder):
    """texts.json as plan.json's "label" texts (plan.py typed_texts does the same when Claude plans)."""
    f = Path(folder) / "texts.json"
    keep = ("text", "style", "start", "end", "x_pct", "y_pct", "size_pct", "font", "color", "width_pct")
    return [{"kind": "label", "size_pct": TEXT_SIZE, **{k: x[k] for k in keep if k in x}}
            for x in ((load(f).get("items") or []) if f.exists() else [])]


def label_key(x):
    return (str(x.get("text")), x.get("style"), *(round(float(x.get(k) or 0), 2) for k in ("start", "end", "x_pct", "y_pct")),
            round(float(x.get("size_pct") or TEXT_SIZE), 1), x.get("font"), x.get("color"), x.get("width_pct"))


def baked_texts(folder, d):
    """The texts.json rows already in the video on the page (its plan, as the round snapshot or the last bake kept it):
    the page draws the others live over the video until they are baked in."""
    try:
        plan = load(Path(folder) / "review" / Path(d["snap"]).name / Path(d["plan"]).name)
    except (KeyError, TypeError, OSError, ValueError):
        return []
    have = {label_key(x) for x in plan.get("texts") or [] if x.get("kind") == "label"}
    f = Path(folder) / "texts.json"
    return [x["id"] for x in ((load(f).get("items") or []) if f.exists() else [])
            if label_key({"size_pct": TEXT_SIZE, **x}) in have]


def cards_pending(folder, d):
    """The cards moved, resized or deleted on the page (overrides.json) that the video on the page does not show yet:
    [{"key", "box"?, "start"?, "end"?} or {"key", "deleted"}]. The page draws them at their new place until the bake puts them in."""
    f = Path(folder) / "overrides.json"
    try:
        ov = (load(f).get("cards") or {}) if f.exists() else {}
    except (OSError, ValueError):
        return []
    shown = {c.get("key"): c for c in (data_of(Path(folder), d.get("data")).get("items") or {}).get("cards") or []}
    out = []
    for k, o in ov.items():
        c = shown.get(k)
        if not c:
            continue
        p = {"deleted": True} if o.get("deleted") else {
            **({"box": o["box"]} if o.get("box") and [round(float(v), 1) for v in o["box"]] != c["box"] else {}),
            **{a: o[a] for a, b in (("start", "s"), ("end", "e")) if a in o and abs(float(o[a]) - c[b]) > 0.01}}
        if p:
            out.append({"key": k, **p})
    return out


def bake_ready(folder, d):
    """Why the typed texts cannot go into this draft by themselves now (None: they can). A patch render needs the
    edit's final render and the plan it was made from; while Claude has the round it plans them in itself."""
    plan = Path(d.get("plan") or "-")
    src = plan.with_name("render" + plan.stem[len("plan"):] + ".mp4")
    return ("not the edit" if d.get("stage") != "edit" or d.get("stills") or d.get("raw") else
            "Claude has this draft" if d.get("sent") or busy(folder) and not listening(folder) else   # waiting for notes: idle
            "no plan" if not plan.is_file() or not plan.stem.startswith("plan") else
            "no render to patch" if not src.is_file() or not src.with_suffix(".plan.json").is_file() else
            "the render was finished by hand" if not render_stamped(src) else
            "the draft is not the render" if not Path(d.get("video") or "-").is_file()
            or Path(d["video"]).stat().st_size != src.stat().st_size else None)


def render_stamped(src):
    """render.mp4 is still the render edit.py made from the plan (its render.stamp.json): a patch keeps it whole. One
    changed after (finish.sh overlays) would lose what was laid on it."""
    try:
        st, s = src.stat(), load(src.with_suffix(".stamp.json"))
        return (s["size"], s["mtime_ns"]) == (st.st_size, st.st_mtime_ns)
    except (OSError, ValueError, KeyError, TypeError):
        return False


BAKE = {}   # folder -> {"state": "waiting" | "working" | "done" | "failed" | "off", "why", "timer", "again"}
BAKE_LOCK, BAKE_WAIT_S = threading.Lock(), 2.5   # seconds after the last text change before the render starts


def bake_soon(folder):
    """A text changed: bake the typed texts into the draft shortly (one patch render at a time per edit; a change made
    while one runs starts another after it)."""
    with BAKE_LOCK:
        b = BAKE.setdefault(str(folder), {})
        if b.get("state") == "working":
            b["again"] = True
            return
        if b.get("timer"):
            b["timer"].cancel()
        b.update(state="waiting", why=None, timer=threading.Timer(BAKE_WAIT_S, bake, (folder,)))
        b["timer"].daemon = True
        b["timer"].start()


def bake(folder, run=subprocess.run):
    """The texts in texts.json into the draft the page shows, with no Claude: plan.json's label texts swapped for
    them, `edit.py patch` re-renders those seconds into render.mp4, and the round's video and snapshot take it."""
    folder, rj = Path(folder), Path(folder) / "review.json"
    b = BAKE.setdefault(str(folder), {})
    with BAKE_LOCK:
        b.update(state="working", why=None, timer=None, again=False)
    d = load(rj)
    why = bake_ready(folder, d)
    if why:
        b.update(state="off", why=why)
        return why
    plan_f = Path(d["plan"])
    p = load(plan_f)
    p["texts"] = [x for x in p.get("texts") or [] if x.get("kind") != "label"] + typed_labels(folder)
    sys.path.insert(0, str(EDIT_PY.parent))
    from preview import apply_overrides   # the cards moved, resized or deleted on the page (overrides.json), as plan.py does
    p = apply_overrides(p, folder, plan_f.name)
    plan_f.write_text(json.dumps(p, indent=1), encoding="utf-8")
    r = run([sys.executable, str(EDIT_PY), "patch", str(folder), "--plan", plan_f.name], capture_output=True, text=True)
    if r.returncode:
        b.update(state="failed", why=((r.stderr or r.stdout).strip().splitlines() or ["the render stopped"])[-1])
        return b["why"]
    src = plan_f.with_name("render" + plan_f.stem[len("plan"):] + ".mp4")

    def swap(d):
        if d.get("sent") or d["stage"] != "edit" or Path(d.get("plan") or "-") != plan_f:   # Claude took it meanwhile
            return
        clone(src, Path(d["video"]))
        shutil.copy2(plan_f, folder / "review" / Path(d["snap"]).name / plan_f.name)
        old = data_of(folder, d.get("data"))
        d["data"] = round_data(folder, d["video"], d["stage"], d["round"], d.get("plan"))
        if old.get("changes") is not None:   # "Changed in this draft" stays the draft's, not the bake's
            new = data_of(folder, d["data"])
            new["changes"] = old["changes"]
            (folder / "review" / d["data"]).write_text(json.dumps(new), encoding="utf-8")
        d["baked"] = d.get("baked", 0) + 1
    update(rj, swap)
    with BAKE_LOCK:
        b["state"] = "done"
        if b.get("again"):
            b["again"] = False
            threading.Thread(target=bake_soon, args=(folder,), daemon=True).start()
    return None


def on_screen(plan, t):
    """For `wait`: the caption, title and zoom on screen at t (the card is card_at's), so a note like "this word is
    wrong" or "no zoom here" names what it is about."""
    try:
        p = load(plan)
    except (OSError, ValueError, TypeError):
        return ""
    at = lambda xs: next((x for x in xs or [] if x.get("start", 0) <= t < x.get("end", 0)), None)
    cap, z = at((p.get("captions") or {}).get("chunks")), at(p.get("zooms"))
    tx = [x for x in p.get("texts") or [] if x.get("start", 0) <= t < x.get("end", 0)]
    return ("".join(f" [{x.get('kind') or 'text'} '{str(x.get('text') or '').replace(chr(10), ' ')}']" for x in tx)
            + (f" [caption '{cap.get('text', '')}']" if cap else "") + (f" [zoom {z.get('start', 0):.1f}-{z.get('end', 0):.1f}s]" if z else "")
            + (" [music on]" if p.get("music") else ""))


def grab(video, t, out):
    """The frame at t as a jpg. At the very end (the playhead on the last frame) `-ss t` lands past the last
    frame and writes nothing, so a note lost its still: seek from the end instead."""
    d = duration(video)
    seek = ["-sseof", "-0.1"] if d and t >= d - 0.05 else ["-ss", f"{t:.3f}"]
    subprocess.run(["ffmpeg", "-v", "error", "-y", *seek, "-i", str(video), "-frames:v", "1",
                    "-vf", "scale=960:-2", "-q:v", "3", str(out)], check=False)


_HOME = {"at": 0.0, "url": None}
THEMES = ("light", "dark", "system")


def _ui_json():
    return Path(os.environ.get("AI_EDITOR_HOME", "").strip() or Path.home() / ".ai-video-editor") / "ui.json"


def ui():
    """$AI_EDITOR_HOME/ui.json: the theme, the first videos (the first-edit notice) and whether it was dismissed."""
    try:
        d = load(_ui_json())
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def set_ui(**kw):
    _ui_json().parent.mkdir(parents=True, exist_ok=True)
    with FileLock(_ui_json()):
        save(_ui_json(), {**ui(), **kw})


def theme():
    """The light/dark choice, one for the window and every review page (they run on different ports, so
    a browser's per-origin storage cannot share it). "system" until the user picks."""
    t = ui().get("theme")
    return t if t in THEMES else "system"


def set_theme(t):
    if t not in THEMES:
        raise ValueError(t)
    set_ui(theme=t)


INTRO_VIDEOS = 3   # the first-edit notice shows on round 1 of the cut and of the edit of the user's first 3 videos


def seen(folder):
    """Count this edit among the user's first videos. Never raises: the notice is a nicety."""
    try:
        vs = ui().get("videos") or []
        if str(folder) not in vs and len(vs) < INTRO_VIDEOS:
            set_ui(videos=vs + [str(folder)])
    except (OSError, TimeoutError):
        pass


# A note that reads as a lasting preference: the page offers it as a rule for the style ("Keep as a rule").
# ponytail: a word list, not a model; Claude still judges every kept note when it saves it
RULE_WORDS = re.compile(r"\b(always|never|every time|from now on|by default|in general|i prefer|prefer|i (?:don'?t |do not )?like|"
                        r"i hate|i'?d rather|i want (?:all|every|my)|too (?:many|much|few|little|big|small|long|short|fast|slow|loud|quiet)|"
                        r"fewer|stop (?:adding|using|putting))\b", re.I)


def looks_like_rule(text):
    return bool(RULE_WORDS.search(text or ""))


def receipt(d, style, rule, status, kind, ref, note=None, src="note"):
    """One saved rule the page shows as "Saved to <style>: <rule>. Undo" (Undo only for a rule this save added).
    kind "settings": ref is the rules.json id; "skill": ref is that skill's SKILL.md."""
    r = {"id": max([x["id"] for x in d.get("receipts") or []] + [0]) + 1, "style": style, "rule": rule, "status": status,
         "kind": kind, "ref": ref, "note": note, "from": src, "at": now()}
    d.setdefault("receipts", []).append(r)
    return r


def undo_receipt(folder, rid):
    """The page's Undo: the rule comes out of the style again (taste.forget, or skillrules.remove). The message, or None."""
    from ai_editor import skillrules, taste
    r = next((x for x in load(folder / "review.json").get("receipts") or [] if x["id"] == rid), None)
    if not r or r.get("undone") or r["status"] != "added":
        return None
    ok = skillrules.remove(r["ref"], r["rule"]) if r["kind"] == "skill" else taste.forget(int(r["ref"])) is not None
    def f(d):
        for x in d.get("receipts") or []:
            if x["id"] == rid:
                x["undone"] = now()
    update(folder / "review.json", f)
    return f"Removed from {r['style']}." if ok else f"It was no longer in {r['style']}."


def intro(folder, d):
    """Show "Your first videos teach it your style": round 1 of a stage, one of the first videos, not dismissed."""
    u = ui()
    return bool(not u.get("intro_off") and str(folder) in (u.get("videos") or []) and d.get("round") == 1 and not d.get("raw"))


def themed(html):
    """The page with the saved theme already on <html>, so it paints in it from the first frame."""
    t = theme()
    return html if t == "system" else html.replace(b"<html", f'<html data-theme="{t}"'.encode(), 1)


def home_url():
    """The home page's address (home.py keeps one fixed address in $AI_EDITOR_HOME/home/.server) when it
    answers, else None. Checked at most every 10 s."""
    if time.time() - _HOME["at"] < (1 if (_HOME.get("update") or {}).get("checking") else 10):   # a check running: follow it
        return _HOME["url"]
    f = Path(os.environ.get("AI_EDITOR_HOME", "").strip() or Path.home() / ".ai-video-editor") / "home" / ".server"
    upd = None
    try:
        url = f.read_text(encoding="utf-8").strip()
        st = json.loads(urllib.request.urlopen(url.replace("/?t=", "/state?t="), timeout=1).read() or b"{}")
        u = st.get("update") or {} if isinstance(st, dict) else {}
        j = next((x for x in reversed(st.get("jobs") or []) if isinstance(x, dict) and x.get("type") == "update"), None) \
            if isinstance(st.get("jobs"), list) else None
        busy = bool(j and j.get("state") == "taken")
        # the rail's Update: a newer version the window can install (never a fork), or one installing now
        err = j.get("error") if j and j.get("state") == "failed" and time.time() - float(j.get("finished") or 0) < 300 else None
        # always there, so the rail's Updates item can say Check for updates, Checking... or Update to <version>
        upd = {"latest": u.get("latest"), "installed": u.get("installed"), "busy": busy, "error": err,
               "newer": bool(u.get("newer") and not u.get("fork")), "checking": bool(u.get("checking"))}
    except (OSError, ValueError, AttributeError):
        url = None
    _HOME.update(at=time.time(), url=url, update=upd)
    return url


def ensure_home():
    """The home page's address, starting it (home.py serve) when it is not running. None when it does not start."""
    _HOME["at"] = 0.0
    if not home_url():
        subprocess.Popen([sys.executable, str(Path(__file__).with_name("home.py")), "serve", "--no-open"],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        for _ in range(40):
            time.sleep(0.5)
            _HOME["at"] = 0.0
            if home_url():
                break
    return home_url()


def start_update():
    """The rail's Update: the window runs it (home.py POST /job update), as Settings' button does. True when it started."""
    url = home_url()
    if not url:
        return False
    base, tok = url.split("/?t=", 1)
    try:
        req = urllib.request.Request(f"{base}/job?t={tok}", json.dumps({"type": "update"}).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5).read()
        _HOME["at"] = 0   # the next /state asks again: the rail shows it running
        return True
    except (OSError, ValueError):
        return False


def video_skills(folder, now=None):
    """The skills on this video, for the notes panel: each one Claude ran (toolhook.py, <edit>/review/skills.jsonl), "now"
    for the last one while the video is being made, then the style's skill and chained skills still to run ("next").
    [{"skill", "state": "done" | "now" | "next"}]."""
    import toolhook
    used = toolhook.used(folder)
    f = askhook.pages().parent / "home" / "state.json"
    try:
        jobs = [j for j in json.loads(f.read_text(encoding="utf-8")).get("jobs") or [] if isinstance(j, dict)
                and j.get("type") == "video" and Path((j.get("args") or {}).get("edit") or "/").resolve() == Path(folder).resolve()]
    except (OSError, ValueError, AttributeError):
        jobs = []
    a = (jobs[-1].get("args") or {}) if jobs else {}
    plan = [t.split(":", 1)[1] for t in str(a.get("chain") or "").split(",") if t.startswith("before:")] + \
        ([a["skill"]] if a.get("skill") else []) + [t.split(":", 1)[1] for t in str(a.get("chain") or "").split(",") if t.startswith("after:")]
    making = bool(jobs) and jobs[-1].get("state") == "taken" or (library_status(folder) in ("making", "cutting"))
    out = [{"skill": u["skill"], "state": "done"} for u in used]
    if out and making and (now or time.time()) - used[-1]["last"] < 3600:
        out[-1]["state"] = "now"
    ran = {u["skill"].split(":")[-1] for u in used}
    return out + [{"skill": x, "state": "next"} for x in plan if x.split(":")[-1] not in ran]


def library_status(folder):
    try:
        import library
        return library.status(library._review(Path(folder)))
    except Exception:
        return None


def home_jobs():
    """How many videos are being made (the home window's video jobs queued or taken, and every library video being cut,
    edited, previewed or rendered, as Home counts them): the rail's Making ring."""
    f = Path(os.environ.get("AI_EDITOR_HOME", "").strip() or Path.home() / ".ai-video-editor") / "home" / "state.json"
    try:
        jobs = json.loads(f.read_text(encoding="utf-8")).get("jobs") or []
    except (OSError, ValueError, AttributeError):
        return 0
    act = [j for j in jobs if isinstance(j, dict) and j.get("type") == "video" and j.get("state") in ("queued", "taken")]
    edits = {str(Path(j["args"]["edit"]).resolve()) for j in act if (j.get("args") or {}).get("edit")}
    try:   # the edit, the preview and the render run after the job: the library's videos being made count too
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import library
        edits |= {str(Path(e["dir"]).resolve()) for e in library.entries() if e["status"] in ("making", "cutting")}
    except (OSError, ValueError, ImportError):
        pass
    return len(edits) + sum(1 for j in act if not (j.get("args") or {}).get("edit"))


# The cut's steps, in order, as the scripts report them onto the home window's video job (progress.step, by text):
# join.py, transcribe.py (at its start, then "Finding" once the words are in), build_timeline.py, render.py,
# verify_cut.py. The page shows all of them while round 0 plays: done, the one now, the rest waiting.
CUT_STEPS = [("join", "Joining your clips"), ("words", "Writing down every word"), ("find", "Finding retakes and pauses"),
             ("cut", "Cutting out the mistakes"), ("render", "Rendering the cut"), ("check", "Checking the cut"),
             ("ready", "Ready to watch")]
CUT_ALIASES = {"Joined your clips in order": "join", "Wrote down every word you said": "words"}   # older scripts' words


def cut_steps(folder, d):
    """Round 0's checklist from the home window's job for this edit: [{text, state: done|now|todo}], or None when no
    job made this edit (Claude Code alone). Also the job's state and its own Claude ("claude": opened, command)."""
    f = Path(os.environ.get("AI_EDITOR_HOME", "").strip() or Path.home() / ".ai-video-editor") / "home" / "state.json"
    try:
        jobs = json.loads(f.read_text(encoding="utf-8")).get("jobs") or []
        j = next((j for j in reversed(jobs) if j.get("type") == "video" and (j.get("args") or {}).get("edit")
                  and Path(j["args"]["edit"]).resolve() == folder.resolve()), None)
    except (OSError, ValueError, AttributeError, TypeError):
        return None
    if not j:
        return None
    keys = [k for k, _ in CUT_STEPS if k != "join" or (j.get("args") or {}).get("takes")]
    by_text = {t: k for k, t in CUT_STEPS} | CUT_ALIASES
    seen = [by_text[s["text"]] for s in j.get("steps") or [] if s.get("text") in by_text]
    landed = any(r.get("stage") == "cut" and r.get("round", 0) >= 1 for r in d.get("rounds") or [])
    at = len(keys) if landed else max([keys.index(k) for k in seen if k in keys] or [-1])
    rows = [{"text": t, "state": "done" if i < at or landed else "now" if i == at else "todo"}
            for i, t in enumerate(dict(CUT_STEPS)[k] for k in keys)]
    if at < 0 and j.get("state") == "taken":   # Claude has it, no script has reported yet: the first step is under way
        rows[0]["state"] = "now"
    return {"steps": rows, "state": j.get("state"), "claude": j.get("claude"), "error": j.get("error")}


def listening(folder):
    try:
        return time.time() - (folder / "review" / ".listening").stat().st_mtime < BEAT_S
    except OSError:
        return False


BUSY_S = 900   # a Claude command on this edit in the last 15 min: Claude is mid-round, not gone


def busy(folder):
    """Claude ran a review command here recently (status, round, resolve...): it is working even with no
    `wait` running, and takes notes sent now next."""
    try:
        return time.time() - (folder / "review" / ".claude").stat().st_mtime < BUSY_S
    except OSError:
        return False


REOPEN_S = 900   # one new Claude per edit this often at most (a trust prompt can hold it in its Terminal)


def who_claude():
    """The Claude Code running this command: {session, pid, tty, cwd, app} from the process tree (the nearest
    `claude` above this process, and the app above that), or {} outside one (Windows has no ps: {})."""
    pid, out = os.getpid(), {}
    for _ in range(15):
        try:
            row = subprocess.run(["ps", "-o", "ppid=,tty=,comm=", "-p", str(pid)], capture_output=True, text=True,
                                 timeout=3).stdout.split(None, 2)
        except (OSError, subprocess.TimeoutExpired):
            return {}
        if len(row) < 3:
            break
        ppid, tty, comm = row[0], row[1], row[2].strip()
        if not out and Path(comm).name == "claude":
            out = {"pid": pid, "tty": "/dev/" + tty if tty not in ("?", "??") else ""}
        elif out and ".app/" in comm:
            out["app"] = comm.split(".app/")[0].rsplit("/", 1)[-1]
            break
        pid = int(ppid)
    if not out:
        return {}
    try:   # the folder it runs in: `claude --resume` finds a conversation only from there
        cwd = subprocess.run(["lsof", "-a", "-p", str(out["pid"]), "-d", "cwd", "-Fn"], capture_output=True, text=True,
                             timeout=3).stdout
        out["cwd"] = next((x[1:] for x in cwd.splitlines() if x.startswith("n")), "")
    except (OSError, subprocess.TimeoutExpired):
        out["cwd"] = ""
    return {**out, "session": askhook.session()}


def last_claude(folder):
    """The Claude that last ran a command on this edit (who_claude, kept in review/.claude), or {}."""
    try:
        return json.loads((folder / "review" / ".claude").read_text(encoding="utf-8") or "{}")
    except (OSError, ValueError):
        return {}


def claude_alive(w):
    """That Claude Code is still running (its pid is a `claude`)."""
    try:
        comm = subprocess.run(["ps", "-o", "comm=", "-p", str(int(w.get("pid") or 0))], capture_output=True, text=True,
                              timeout=3).stdout.strip()
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return False
    return Path(comm).name == "claude"


def claude_state(folder):
    """The page's Claude control: {"state": "working" | "waiting" | "open" | "off", "show": its Terminal tab can come
    to the front, "last": when it last ran a command here, "resume": the line that opens it again in any terminal}. waiting: a `wait` listens for notes; working: its process
    runs and it ran a command lately (no process info, as on Windows: a command lately); open: running, idle."""
    w, lis = last_claude(folder), listening(folder)
    alive = bool(w.get("pid")) and claude_alive(w)
    b = busy(folder)
    st = "waiting" if lis else ("working" if b else "open") if alive else "working" if b and not w.get("pid") else "off"
    try:
        last = (folder / "review" / ".claude").stat().st_mtime
    except OSError:
        last = None
    return {"state": st, "show": bool(alive and w.get("app") == "Terminal" and w.get("tty")), "last": last,
            "resume": resume_cmd(w)}


def show_claude(folder):
    """Show Claude: its Terminal tab to the front. True when it was found."""
    import launcher
    w = last_claude(folder)
    return bool(claude_alive(w) and w.get("app") == "Terminal" and launcher.show_tab(w.get("tty")))


def stop_claude(folder):
    """Stop: end this video's Claude Code (SIGTERM to its process). The video, notes and drafts stay; Start
    carries on from them. True when one was running."""
    import signal
    w = last_claude(folder)
    if not claude_alive(w):
        return False
    try:
        os.kill(int(w["pid"]), signal.SIGTERM)
    except (OSError, ValueError, KeyError):
        return False
    (folder / "review" / ".listening").unlink(missing_ok=True)
    return True


def resume_cmd(w):
    """What to paste into a terminal to open that Claude's conversation again."""
    return f"cd {shlex.quote(w['cwd'])} && claude --resume {w['session']}" if w.get("session") and w.get("cwd") else ""


def reopen(folder, rj, force=False):
    """Notes sent or approved with no Claude on this edit. The Claude that worked here first: still open in a
    Terminal tab, the carry-on prompt is typed into it; closed, its conversation opens again (`claude --resume`).
    Only with neither, a new Claude (`/ai-editor:start carry on edits/<name>`, in the library). Never while a `wait`
    listens; force (the page's "Open a new Claude") also when a Claude worked here lately, since it may have stopped.
    Kept on review.json as "claude": {opened, how, command, session, at} so the page says where it went."""
    if listening(folder) or not force and (busy(folder) or time.time() - ((load(rj).get("claude") or {}).get("at") or 0) < REOPEN_S):
        return None
    import launcher
    prompt, w = f"/ai-editor:start carry on edits/{folder.name}", last_claude(folder)
    alive = claude_alive(w)
    if alive and w.get("app") == "Terminal" and launcher.type_into(w.get("tty"), prompt):
        r = {"opened": True, "how": "typed", "command": resume_cmd(w), "session": w.get("session")}
    elif not alive and w.get("session") and w.get("cwd"):
        opened, cmd = launcher.open_claude(Path(w["cwd"]), prompt, session=w["session"], resume=True)
        r = {"opened": opened, "how": "resumed", "command": cmd, "session": w["session"]}
    else:   # none known, or one still open where it cannot be typed into: a second copy of it would clash
        sid = str(uuid.uuid4())
        opened, cmd = launcher.open_claude(folder.parent.parent, prompt, session=sid)
        r = {"opened": opened, "how": "new", "command": cmd, "session": sid}
        if opened:
            r["resume"] = f"cd {shlex.quote(str(folder.parent.parent))} && claude --resume {sid}"
    r.setdefault("resume", resume_cmd(w) if r["how"] != "new" else "")
    r["at"] = time.time()
    update(rj, lambda d: d.update(claude=r))
    return r


def log_pct(path):
    """The last "N/M" in a render log (Remotion prints "Rendered 812/3255"), as a percent."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 4096))
            tail = f.read().decode(errors="ignore")
    except OSError:
        return None
    m = re.findall(r"(\d+)/(\d+)", tail)
    return round(100 * int(m[-1][0]) / int(m[-1][1])) if m and int(m[-1][1]) else None


def log_round(d):
    """Every round's video is kept, so the page has a tab per round."""
    rs = [r for r in d.setdefault("rounds", []) if (r["stage"], r["round"]) != (d["stage"], d["round"])]
    old = next((r for r in d["rounds"] if (r["stage"], r["round"]) == (d["stage"], d["round"])), {})
    d["rounds"] = rs + [{**{k: d.get(k) for k in ("stage", "round", "video", "note", "label", "alts", "data", "stills",
                                                       "snap", "src", "changed", "back_to")},
                         "at": old.get("at") or now()}]


def alt_of(d, name, rnd=None):
    """A version's video and transcript. No name = the round's main video."""
    r = rnd or d
    a = next((a for a in r.get("alts") or [] if a["name"] == name), None)
    return a or {"video": r["video"], "transcript": d.get("transcript")}


def editable(d, c):
    """The page may change or delete a note of the open round, or one queued for the next."""
    return c.get("queued") or (c["round"] == d["round"] and c["stage"] == d["stage"] and not d.get("sent"))


def remap(t, old, new):
    """A time on the old round's cut moved to where the same word is said on the new one, by the two rounds'
    cut transcripts (both from words.raw.json, so word n is the same word). None when that cannot be told."""
    flat = lambda tx: [x for ln in tx["lines"] for x in ln["tokens"] if "w" in x]
    if not old or not new or len(flat(old)) != len(flat(new)):
        return None
    a, b = flat(old), flat(new)
    i = max((k for k, x in enumerate(a) if x["t"] is not None and x["t"] <= t), default=None)
    j = next((k for k in range(i, len(b)) if b[k]["t"] is not None), None) if i is not None else None
    if j is None:
        return None
    return round(b[j]["t"] + (t - a[i]["t"] if j == i else 0), 2)


def raw_to_cut(folder, t):
    """A time on the raw clip moved onto the cut by decisions.json (the kept source spans). A moment the cut
    removed lands where the cut picks up again. None without decisions.json."""
    try:
        spans = sorted(load(folder / "decisions.json"), key=lambda s: s["start"])
    except (OSError, ValueError, TypeError, KeyError):
        return None
    off = 0.0
    for s in spans:
        if t < s["end"]:
            return round(off + max(0.0, t - s["start"]), 2)
        off += s["end"] - s["start"]
    return round(off, 2) if spans else None


def raw_video(folder, d):
    """The raw take the cut came from: round 0's clip, else report.json's source. None when neither is there."""
    r0 = next((r for r in d.get("rounds", []) if (r["stage"], r["round"]) == ("cut", 0)), None)
    try:
        p = Path(r0["video"] if r0 else load(folder / "report.json")["source"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return p if p.is_file() else None


def _locate():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills" / "cut" / "scripts"))
    from textnorm import locate, nwords
    return locate, nwords


def timed(t):
    return all(isinstance(t.get(k), (int, float)) for k in ("start", "end"))


def span_range(sp, toks, locate):
    """The token range [a, b] a spans.json entry quotes, as build_timeline.resolve_spans picks it. None if it does not resolve."""
    hits = locate(sp.get("text", ""), toks)
    if "after" in sp:
        hits = [h for h in hits if toks[h[0]]["start"] >= float(sp["after"])]
    if "occurrence" in sp:
        k = int(sp["occurrence"]) - 1
        return hits[k] if 0 <= k < len(hits) else None
    return hits[0] if hits and ("after" in sp or len(hits) == 1) else None


def cut_toks(folder):
    """The tokens spans.json quotes, exactly as build_timeline.py lists them (untimed ones too, so "occurrence"
    counts the same words)."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills" / "cut" / "scripts"))
    from textnorm import load_words
    return [t for t in load_words(folder / "words.raw.json") if isinstance(t, dict) and t.get("type") in ("word", "audio_event")]


def files_sha(folder):
    """One hash over spans.json and keep.json as they are now: Stop only puts the old ones back over what /edits wrote."""
    h = hashlib.sha256()
    for n in ("spans.json", "keep.json"):
        f = folder / n
        h.update(f.read_bytes() if f.exists() else b"-")
    return h.hexdigest()


def span_times(folder):
    """[(start, end, kind, note)] in raw-take seconds for each spans.json entry that resolves; [] without the files."""
    try:
        locate, _ = _locate()
        toks, spans = cut_toks(folder), load(folder / "spans.json")
    except (OSError, ValueError, ImportError, KeyError, TypeError):
        return []
    out = []
    for sp in spans if isinstance(spans, list) else []:
        ab = span_range(sp, toks, locate) if isinstance(sp, dict) else None
        if ab and timed(toks[ab[0]]) and timed(toks[ab[1]]):
            out.append((toks[ab[0]]["start"], toks[ab[1]]["end"], sp.get("kind", "retake"), sp.get("note", "")))
    return out


def minus(ranges, cuts):
    """[[s, e]] ranges with every [a, b] of cuts taken out."""
    for a, b in cuts:
        ranges = [r for s, e in ranges for r in ([s, min(e, a)], [max(s, b), e]) if r[1] - r[0] > 1e-3]
    return ranges


def merged(ranges):
    out = []
    for s, e in sorted(ranges):
        if out and s <= out[-1][1] + 1e-3:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out


def apply_edits(folder, restore, cut, pause=()):
    """The review page's transcript edits onto spans.json and keep.json, deterministically. restore/cut/pause:
    [[start, end], ...] in raw-take seconds. A token is in a range when its middle is, or the range sits inside it (a
    cut inside a word takes the whole word). Restore drops those tokens from the spans covering them (a span loses them
    or splits); a restored word no span covers was taken by the pause trim, so its time goes into keep.json, which
    build_timeline.py leaves in. pause: removed pauses to put back whole (keep.json too). Cut adds a "manual" span
    quoting each run of kept tokens and takes those words out of keep.json. Each new span quotes its words, with
    "occurrence" when they are said more than once. spans.prev.json and keep.prev.json keep what was there.
    Spans that end up overlapping in time merge into one; the result is checked with build_timeline.resolve_spans
    before anything is written. Writes are atomic. Returns the counts, or raises ValueError."""
    locate, nwords = _locate()
    import build_timeline
    toks = cut_toks(folder)
    sp_path, kp_path = folder / "spans.json", folder / "keep.json"
    spans = load(sp_path) if sp_path.exists() else []
    keep0 = load(kp_path) if kp_path.exists() else []
    try:
        dec = load(folder / "decisions.json")
    except (OSError, ValueError):
        dec = None   # no build yet: nothing tells which words the pause trim took

    def picked(ranges):
        out = set()
        for r in ranges or []:
            a, b = float(r[0]), float(r[1])
            out |= {i for i, t in enumerate(toks) if t.get("type") == "word" and timed(t)   # never a hidden (cough) span
                    and (a - 1e-3 <= (t["start"] + t["end"]) / 2 <= b + 1e-3 or (t["start"] <= a and b <= t["end"]))}
        return out
    R, C = picked(restore), picked(cut)
    C -= R
    ranges = []
    for i, sp in enumerate(spans):
        ab = span_range(sp, toks, locate)
        if ab is None:
            raise ValueError(f"span {i} ({sp.get('text', '')[:40]!r}) does not match the transcript: fix spans.json first")
        ranges.append(ab)
    covered = {i for a, b in ranges for i in range(a, b + 1)}

    def runs(idx):
        out = []
        for i in sorted(idx):
            if out and i == out[-1][-1] + 1:
                out[-1].append(i)
            else:
                out.append([i])
        bad = lambda t: not nwords(t.get("text", "")) or not timed(t)
        for r in out:   # trim tokens with no words (a lone dash) or no timing: a quote cannot start or end on them
            while r and bad(toks[r[0]]):
                r.pop(0)
            while r and bad(toks[r[-1]]):
                r.pop()
        return [r for r in out if r]

    def quote(run, base):
        q = {k: v for k, v in base.items() if k not in ("text", "occurrence", "after")}
        q["text"] = " ".join(toks[i]["text"].strip() for i in run)
        hits = locate(q["text"], toks)
        if len(hits) > 1:
            q["occurrence"] = hits.index((run[0], run[-1])) + 1
        return q
    new = []
    for sp, (a, b) in zip(spans, ranges):
        keep = [i for i in range(a, b + 1) if i not in R]
        new += [sp] if len(keep) == b - a + 1 else [quote(r, sp) for r in runs(keep)]
    new += [quote(r, {"kind": "manual", "note": "cut on the review page"}) for r in runs(C - covered)]
    rng = []
    for q in new:   # the new file must build: every quote lands on the words it was made from
        ab = span_range(q, toks, locate)
        if ab is None or not (timed(toks[ab[0]]) and timed(toks[ab[1]])):
            raise ValueError(f"could not quote {q['text'][:40]!r} unambiguously")
        rng.append([toks[ab[0]]["start"], toks[ab[1]]["end"], ab, q])
    rng.sort(key=lambda x: x[0])
    new = []
    for x in rng:   # spans that overlap in time (a cut beside a sound token) become one, as build_timeline asks
        if new and x[0] < new[-1][1]:
            last = new[-1]
            a, b = min(last[2][0], x[2][0]), max(last[2][1], x[2][1])
            base = last[3] if last[3].get("kind") != "manual" else x[3]
            last[:] = [min(last[0], x[0]), max(last[1], x[1]), (a, b), quote(list(range(a, b + 1)), base)]
        else:
            new.append(x)
    new = [x[3] for x in new]
    try:
        with contextlib.redirect_stderr(io.StringIO()) as err:
            build_timeline.resolve_spans(new, toks)
    except SystemExit:
        raise ValueError("the changed cut would not build: " + err.getvalue().strip().replace("ERROR: ", "")[:200])
    # the pause trim's words: restored ones not in a span and not playing now (decisions.json), as runs of time
    trimmed = runs({i for i in R - covered if dec is not None and kept_s(toks[i], dec) < min(0.1, (toks[i]["end"] - toks[i]["start"]) / 2)})
    add = [[toks[r[0]]["start"], toks[r[-1]]["end"]] for r in trimmed] + [[float(a), float(b)] for a, b in pause or []]
    keep = merged(minus([[k["start"], k["end"]] for k in keep0] + add, [[toks[i]["start"], toks[i]["end"]] for i in C]))
    keep = [{"start": round(s, 3), "end": round(e, 3)} for s, e in keep]
    out = {"restored": len(R & covered) + sum(map(len, trimmed)), "cut": len(C - covered), "pauses": len(pause or []),
           "spans": len(new), "keep": len(keep)}
    if out["restored"] or out["cut"] or out["pauses"]:
        save(folder / "spans.prev.json", spans)
        save(folder / "keep.prev.json", keep0)
        save(sp_path, new)
        if keep or kp_path.exists():
            save(kp_path, keep)
        out["sha"] = files_sha(folder)
    return out


def fmt(t):
    return f"{int(t // 60)}:{t % 60:04.1f}"


def stage_name(s, stills=False):
    return "the stills" if stills else {"cut": "the cut", "edit": "the edit"}.get(s, s)


def resume_text(folder, d):
    """The page's Copy for Claude: everything a new Claude Code session needs to pick this edit up when the
    one that made it is closed (left overnight) or stopped answering."""
    doc = Path(__file__).resolve().parents[2] / "skills" / "style-edit" / "references" / "review.md"
    return (f'Pick up my cooked. edit "{d.get("name") or folder.name}" where I left it '
            f'({stage_name(d.get("stage"), d.get("stills"))}, round {d.get("round")}).\n'
            f"Read {doc}, then run this in the background and apply the notes it prints:\n"
            f'python3 "{Path(__file__).resolve()}" "{folder.resolve()}" wait')


# ---------------------------------------------------------------- server
def make_handler(folder, token):
    rj = folder / "review.json"

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def handle(self):   # a tab that closed mid-reply (an /ask poll, a reload): nothing to log
            try:
                super().handle()
            except (BrokenPipeError, ConnectionResetError):
                pass

        def cookie_name(self):
            return f"ave-review-{self.server.server_address[1]}"   # cookies ignore ports: one per server

        def authorized(self):
            q = parse_qs(urlsplit(self.path).query).get("t", [""])[0]
            c = SimpleCookie()
            try:
                c.load(self.headers.get("Cookie") or "")
            except Exception:
                pass
            got = c[self.cookie_name()].value if self.cookie_name() in c else ""
            return any(hmac.compare_digest(v.encode(), token.encode()) for v in (q, got) if v)

        def send(self, code, body, ctype="application/json", cookie=False):
            if isinstance(body, (dict, list)):
                body = json.dumps(body).encode()
            elif isinstance(body, str):
                body = body.encode()
            self.send_response(code)
            if cookie:
                self.send_header("Set-Cookie", f"{self.cookie_name()}={token}; Path=/; HttpOnly; SameSite=Strict")
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def file(self, p, ctype, name=None):
            # Range requests: without 206 the browser cannot seek a long mp4. name: a download, saved as that
            size = p.stat().st_size
            start, end = 0, size - 1
            m = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range") or "")
            if m and (m[1] or m[2]):
                start, end = (int(m[1]), int(m[2]) if m[2] else size - 1) if m[1] else (size - int(m[2]), size - 1)
                end = min(end, size - 1)
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            else:
                self.send_response(200)
            self.send_header("Content-Type", ctype)
            if name:
                self.send_header("Content-Disposition", disposition(name))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            self.end_headers()
            try:
                with open(p, "rb") as f:
                    f.seek(start)
                    left = end - start + 1
                    while left > 0:
                        b = f.read(min(1 << 20, left))
                        if not b:
                            break
                        self.wfile.write(b)
                        left -= len(b)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            if not self.authorized():
                return self.send(403, {"error": "open the page with the URL review.py printed"})
            path = urlsplit(self.path).path
            q = {k: v[0] for k, v in parse_qs(urlsplit(self.path).query).items()}
            if askhook.route(self, "GET", path, q):   # Claude's questions (askhook.py)
                return
            if path == "/":
                return self.send(200, themed(HTML.read_bytes()), "text/html; charset=utf-8", cookie=True)
            if path == "/state":
                d = load(rj)
                d["theme"] = theme()
                d["listening"], d["busy"] = listening(folder), busy(folder)
                d["resume"] = resume_text(folder, d)
                ovf = folder / "overrides.json"   # sounds taken out of the plan, waiting for the next draft
                d["sfx_removed"] = [float(k) for k, v in ((load(ovf).get("sfx") or {}) if ovf.exists() else {}).items()
                                    if isinstance(v, dict) and v.get("deleted")]
                d["cap_words"] = ((load(ovf).get("words") or {}) if ovf.exists() else {})   # caption words retyped, for the next draft
                d["cuts"] = ((load(ovf).get("cuts") or {}) if ovf.exists() else {})
                d["cap_times"] = ((load(ovf).get("cap_times") or {}) if ovf.exists() else {})   # caption pages retimed, until baked   # the timeline's splits and cut pieces
                d["placed_sounds"] = placed_sounds(folder)   # the timeline's Sounds row: the ones the user put there
                d["sounds_ui"] = sounds_info() if d.get("stage") == "edit" else None   # the Sounds panel
                snap_plan = folder / "review" / Path(d["snap"]).name / Path(d["plan"]).name if d.get("snap") and d.get("plan") else None
                d["captions_ui"] = captions_info(folder, snap_plan) if d.get("stage") == "edit" else None   # the Captions panel, its base the video shown
                d["texts"] = (load(folder / "texts.json").get("items") or []) if (folder / "texts.json").exists() else []   # the Text tab
                d["texts_baked"] = baked_texts(folder, d) if d.get("stage") == "edit" else []   # the rest the page draws live
                d["cards_pending"] = cards_pending(folder, d) if d.get("stage") == "edit" else []   # moved, not in the video yet
                b = BAKE.get(str(folder)) or {}
                d["bake"] = {"state": b.get("state"), "why": b.get("why")}   # putting the texts in the video
                d["session_cmd"] = resume_cmd(last_claude(folder)) or (d.get("claude") or {}).get("resume") or ""   # Start's fallback
                d["claude_ui"] = claude_state(folder)   # the Claude control: working, waiting, open or off
                d["page"] = live.page_version(HTML, HTML.with_name("ask.js"))   # the tab reloads when this changes
                d["cutcheck"] = (folder / "cut-check.html").exists()
                d["rawvideo"] = raw_video(folder, d) is not None   # the transcript editor's preview plays the raw take
                d["home"] = home_url()   # the Home button: back to the editor's window, or how to start it
                d["update"] = _HOME.get("update") if d["home"] else None   # the rail's Update
                d["jobs"] = home_jobs() if d["home"] else 0   # the rail's Making ring
                d["intro"] = intro(folder, d)
                d["style_name"] = style_label(folder)   # "Keep as a rule for <style>" and the receipts
                try:   # a sample style (the plugin's own): taught like any style, its rules in its style.overrides.json
                    sp = edit_style(folder)
                    d["style_sample"] = bool(sp and Path(sp).parent.name.startswith("sample-"))
                except Exception:
                    d["style_sample"] = False
                if isinstance(d.get("learn"), dict):   # "Teach <style>": its name now, even renamed after the approve
                    d["learn"]["style"] = d["style_name"]
                d["assets"] = assets.load(folder)   # "Anything to add?": the images and links added to this video
                try:
                    d["skills"] = video_skills(folder)   # the skills this video ran, runs now and will run
                except Exception:
                    d["skills"] = []
                try:   # "Made in 6 min (cut 3:10, edit 1:40, render 0:52)" under the finished video: real times only
                    d["made"] = json.loads((folder / "timings.json").read_text(encoding="utf-8")).get("line")
                except (OSError, ValueError, AttributeError):
                    d["made"] = None
                if d.get("raw"):   # the cut is being made: every step it takes, from the home window's job
                    d["cut_steps"] = cut_steps(folder, d)
                for x in d.get("activity", [])[-1:]:
                    if x.get("log") and not x.get("done"):
                        x["pct"] = log_pct(x["log"])
                        try:   # a render still writing its log is alive even when Claude is quiet
                            x["log_age"] = round(time.time() - Path(x["log"]).stat().st_mtime)
                        except OSError:
                            pass
                if making_edit(d):
                    d["making"] = {"style": making_style(folder), "steps": EDIT_STEPS}
                return self.send(200, d)
            if path == "/video":
                d = load(rj)
                if q.get("k") == "raw":
                    p = raw_video(folder, d)
                    return self.file(p, mimetypes.guess_type(p.name)[0] or "video/mp4") if p else self.send(404, {})
                r = next((r for r in d.get("rounds", []) if f"{r['stage']}-{r['round']}" == q.get("k")), d)
                p = Path(alt_of(d, q.get("alt", ""), r)["video"])
                return self.file(p, "video/mp4") if p.exists() else self.send(404, {})
            if path == "/download":   # the finished video, named "<video name> - <style name>.mp4"
                d = load(rj)
                p = Path(alt_of(d, q.get("alt", ""), d)["video"])
                return self.file(p, "video/mp4", download_name(folder, d)) if p.exists() else self.send(404, {})
            if path == "/data":   # the round's transcript, segments and tracks (round_data)
                d = load(rj)
                r = next((r for r in d.get("rounds", []) if f"{r['stage']}-{r['round']}" == q.get("k")), None)
                p = folder / "review" / Path(r.get("data") or "-").name if r else None
                if p and p.is_file() and (r["stage"], r["round"]) == (d["stage"], d["round"]) == ("cut", d["round"]):
                    upgrade_transcript(folder, p)
                return self.send(200, p.read_bytes() if p and p.is_file() else {})
            if path == "/sound-preview":   # the Sounds panel's play button: one pick of one moment, at a fixed level
                sfx = sfx_mod()
                cue, pick = q.get("cue", ""), q.get("c", "default")
                if cue not in sfx.KIT or pick not in ("default", *sfx.own_sounds()):
                    return self.send(404, {})
                cache = Path(os.environ.get("AI_EDITOR_HOME", "").strip() or Path.home() / ".ai-video-editor") / "cache" / "sound-previews"
                cache.mkdir(parents=True, exist_ok=True)
                sig = hashlib.sha1(f"{cue}|{pick}|{sfx.choice_sig()}".encode()).hexdigest()[:12]
                f = cache / f"{cue}-{sig}.wav"
                if not f.is_file():
                    try:
                        sfx.preview(cue, pick, f)
                    except (OSError, subprocess.CalledProcessError, ValueError):
                        return self.send(404, {})
                return self.file(f, "audio/wav")
            if path.startswith("/audio/"):   # a dropped audio file, played live on the page while the video plays
                p = folder / "audio" / Path(unquote(path)).name
                if not p.is_file():
                    return self.send(404, {})
                return self.file(p, mimetypes.guess_type(p.name)[0] or "audio/mpeg")
            if path == "/sound-file":   # a library sound as it is, for the same live playing
                sfx = sfx_mod()
                if q.get("name", "") not in sfx.own_sounds():
                    return self.send(404, {})
                p = sfx.library_dir() / q["name"]
                return self.file(p, mimetypes.guess_type(p.name)[0] or "audio/wav")
            if path.startswith("/card-img/"):   # a card's own picture, under this edit only: the move and resize preview
                p = (folder / unquote(path[len("/card-img/"):])).resolve()
                if folder.resolve() not in p.parents or p.suffix.lower() not in CARD_IMG or not p.is_file():
                    return self.send(404, {})
                return self.file(p, mimetypes.guess_type(p.name)[0] or "image/png")
            if path.startswith("/assets/"):   # an image or video the user added (assets.py); ?thumb=1: a video's picture
                p = folder / "assets" / Path(unquote(path)).name
                if not p.is_file():
                    return self.send(404, {})
                if assets.kind_of(p) == "video":
                    if q.get("thumb") == "1":
                        import library
                        t = library.thumb(p)
                        return self.file(t, "image/jpeg") if t else self.send(404, {})
                    return self.file(p, mimetypes.guess_type(p.name)[0] or "video/mp4")
                ct = {".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"}.get(p.suffix, "image/jpeg")
                return self.file(p, ct)
            if path.startswith("/frames/"):
                p = folder / "review" / Path(unquote(path)).name
                ct = {".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"}.get(p.suffix, "image/jpeg")
                return self.file(p, ct) if p.is_file() else self.send(404, {})
            # the cut skill's transcript page, with its video beside it
            if path in ("/cut-check.html", "/cut.mp4") and (folder / path[1:]).exists():
                return self.file(folder / path[1:], "text/html; charset=utf-8" if path.endswith("html") else "video/mp4")
            self.send(404, {})

        def do_POST(self):
            if not self.authorized():
                return self.send(403, {"error": "open the page with the URL review.py printed"})
            if not askhook.same_origin(self):   # a POST from another site's page, even with the cookie
                return self.send(403, {"error": "not from this page"})
            if urlsplit(self.path).path == "/assets/upload":   # "Anything to add?": one video or image, streamed in
                q = parse_qs(urlsplit(self.path).query)
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    items = assets.save_stream(folder, unquote(q.get("name", [""])[0]), self.rfile, n, unquote(q.get("say", [""])[0]))
                except ValueError as e:
                    self.close_connection = True   # the unread body must not be taken as the next request
                    return self.send(400, {"error": str(e)})
                return self.send(200, {"items": items})
            if urlsplit(self.path).path == "/sound/library/upload":   # the Sounds panel: a file into the sound library
                q = parse_qs(urlsplit(self.path).query)
                try:
                    name = library_upload(unquote(q.get("name", [""])[0]), self.rfile, int(self.headers.get("Content-Length") or 0))
                except ValueError as e:
                    self.close_connection = True
                    return self.send(400, {"error": str(e)})
                return self.send(200, {"ok": True, "name": name, "sounds": sounds_info()})
            if urlsplit(self.path).path == "/audio/upload":   # an audio file dropped on the timeline, streamed in
                q = parse_qs(urlsplit(self.path).query)
                d = load(rj)
                last = d["events"][-1]["type"] if d["events"] else None
                n = int(self.headers.get("Content-Length") or 0)
                try:
                    if d.get("stage") != "edit" or d.get("sent") and last not in ("send", "edits"):
                        raise ValueError("Audio goes on the edit, before it is approved.")
                    dur = float((data_of(folder, d.get("data")) or {}).get("duration") or 0)
                    x = save_audio(folder, unquote(q.get("name", [""])[0]), self.rfile, n, float(q.get("at", ["0"])[0]), dur)
                except ValueError as e:
                    self.close_connection = True
                    return self.send(400, {"error": str(e)})
                return self.timeline_note("sounds-timeline", "Sounds on the timeline", f"add {x['sound']} at {fmt(x['t'])} "
                                          f"for {x['dur']:.1f} s", "Plan again so they are in (sounds.json and overrides.json sfx).")
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            except ValueError:
                return self.send(400, {"error": "not json"})
            path = urlsplit(self.path).path
            if askhook.route(self, "POST", path, {}, body):
                return
            if path == "/theme":   # the toggle: one choice for the window and every review page
                try:
                    set_theme(body.get("theme"))
                except ValueError:
                    return self.send(400, {"error": "light, dark or system"})
                return self.send(200, {"theme": theme()})
            if path == "/home":   # the rail with the editor's window closed: start its page (home.py serve), then go there
                return self.send(200, {"url": ensure_home()}) if ensure_home() else self.send(503, {"error": "The editor's window did not start."})
            if path == "/update/check":   # the rail's Check for updates: the window asks GitHub (home.py /update/check)
                url = ensure_home()
                if not url:
                    return self.send(503, {"error": "The editor's window did not start."})
                base, tok = url.split("/?t=", 1)
                try:
                    urllib.request.urlopen(urllib.request.Request(f"{base}/update/check?t={tok}", b"{}", method="POST",
                                                                  headers={"Content-Type": "application/json"}), timeout=5).read()
                except (OSError, ValueError):
                    return self.send(503, {"error": "The editor's window did not answer."})
                _HOME["at"] = 0.0   # the next /state reads the check
                return self.send(200, {})
            if path == "/intro":   # "Got it" on the first-edit notice: never again
                set_ui(intro_off=True)
                return self.send(200, {})
            if path == "/keep":   # "Keep as a rule for <style>" ticked or unticked on an open note
                def kp(d):
                    for c in d["comments"]:
                        if c["id"] == body.get("id") and editable(d, c):
                            c["keep"], c["keep_set"] = bool(body.get("keep")), True
                            return True
                    return False
                return self.send(200, {}) if update(rj, kp) else self.send(409, {"error": "Claude has this note now."})
            if path == "/undo":   # a receipt's Undo: the saved rule comes out of the style
                try:
                    msg = undo_receipt(folder, int(body.get("id")))
                except (TypeError, ValueError):
                    msg = None
                return self.send(200, {"msg": msg}) if msg else self.send(409, {"error": "nothing to undo"})
            if path == "/learn":   # the learn panel: the ticked rules, or Not now. `wait` hands them to Claude
                def lc(d):
                    lr = d.get("learn") or {}
                    if lr.get("state") != "proposed":
                        return False
                    ids = sorted({i for i in body.get("chosen") or [] if isinstance(i, int) and 0 <= i < len(lr["rules"])})
                    lr.update(state="chosen" if ids and not body.get("skip") else "skipped", chosen=ids, handled=False)
                    if to and lr["state"] == "chosen":
                        lr["to"] = to
                    return True
                to, lr0 = None, load(rj).get("learn") or {}
                if body.get("new") and not body.get("skip") and lr0.get("state") == "proposed":   # "New style from this video"
                    try:
                        to = new_style_from(folder, body["new"])
                    except ValueError as e:
                        return self.send(409, {"error": str(e) or "That name is taken. Pick another."})
                elif body.get("to") is not None:   # "Save to": one of the styles the approve listed
                    to = next((dict(x) for x in lr0.get("styles") or [] if x["id"] == str(body["to"])), None)
                    if to is None:
                        return self.send(400, {"error": "pick a style from the list"})
                return self.send(200, {}) if update(rj, lc) else self.send(409, {"error": "nothing to choose"})
            if path == "/trials":   # the Trial reels tab: {"action": "make", versions, hooks} | "skip" | "ask" + text
                # | "note" + text, "for" (t1.., or all), "t" (seconds on that version): feedback once they are made
                act = body.get("action")
                try:
                    picks = {"versions": [{"kinds": trial_kinds(v.get("kinds")), "line": str(v.get("line") or "")}
                                          for v in body.get("versions") or []][:8],
                             "hooks": sorted({i for i in body.get("hooks") or [] if isinstance(i, int) and i >= 0})}
                except (ValueError, AttributeError) as e:
                    return self.send(400, {"error": str(e)})
                text = str(body.get("text") or "").strip()
                if act not in ("make", "skip", "ask", "note") or act == "make" and not picks["versions"] or act in ("ask", "note") and not text:
                    return self.send(400, {"error": "make takes versions, ask and note take text"})

                def tc(d):
                    t = d.get("trials") or {}
                    if act == "note":   # once made: notes queue up, Claude takes them all on its next `wait`
                        if t.get("state") != "chosen":
                            return False
                        n = len((t.get("picks") or {}).get("versions") or [])
                        who = str(body.get("for") or "all")
                        try:
                            at = round(float(body["t"]), 1) if body.get("t") is not None and who != "all" else None
                        except (TypeError, ValueError):
                            at = None
                        t.setdefault("notes", []).append({"text": text[:2000], "for": who if who in [f"t{i + 1}" for i in range(n)] else "all",
                                                          "t": at, "at": now()})
                        t["handled"] = False
                        return True
                    if t.get("state") != "proposed" or t.get("handled") is False:   # nothing to pick, or Claude has it
                        return False
                    if act == "ask":
                        t["asks"].append({"text": text, "at": now()})
                    else:
                        t.update(state="chosen" if act == "make" else "skipped", picks=picks)
                    t["handled"] = False
                    return True
                return self.send(200, {}) if update(rj, tc) else self.send(409, {"error": "Claude is on it"})
            if path == "/assets":   # "Anything to add?": add images or links ({"add": [...]}) or take one out ({"remove": i})
                if "remove" in body:
                    try:
                        return self.send(200, {"items": assets.remove(folder, int(body["remove"]))})
                    except (TypeError, ValueError):
                        return self.send(400, {"error": "remove takes an index"})
                return self.send(200, {"items": assets.add(folder, body.get("add") if isinstance(body.get("add"), list) else [])})
            if path == "/back":   # the Rounds tab's "Go back to round N"
                try:
                    d = go_back(folder, int(body.get("round")))
                except (TypeError, ValueError) as e:
                    return self.send(409, {"error": str(e) or "cannot go back"})
                return self.send(200, {"round": d["round"]})
            if path == "/comment":
                return self.comment(body)
            if path == "/edit":
                return self.edit(body)
            if path == "/edits":
                return self.transcript_edits(body)
            if path == "/scope":   # a saved note: all versions ("*") or one version (a name, None = main)
                def sc(d):
                    for c in d["comments"]:
                        if c["id"] == body.get("id") and editable(d, c):
                            c["alt"] = body.get("alt") or None
                update(rj, sc)
                return self.send(200, {})
            if path == "/captions":   # the Captions panel: words at a time and the look, for this video, with a note
                d = load(rj)
                last = d["events"][-1]["type"] if d["events"] else None
                if d.get("stage") != "edit" or d.get("sent") and last not in ("send", "edits"):
                    return self.send(409, {"error": "Captions change on the edit, before it is approved."})
                try:
                    said = set_captions(folder, body.get("words"), body.get("look"), body)
                except ValueError as e:
                    return self.send(400, {"error": str(e)})
                if not said:
                    return self.send(400, {"error": "captions takes words, look, size, y, color or highlight"})
                cur = captions_info(folder)   # one Captions note per round, saying where the choice is now
                mine = cur["mine"]
                now_said = [w for w in (("a sentence at a time" if cur["words"] == "sentence" else f"{cur['words']} word"
                                         f"{'' if cur['words'] == '1' else 's'} at a time") if cur["words"] else None,
                                        f"the {cur['look']} look" if cur["look"] else None,
                                        f"size {mine['size_pct']}" if "size_pct" in mine else None,
                                        f"{mine['y_pct']}% down the frame" if "y_pct" in mine else None,
                                        f"colour {mine['color']}" if "color" in mine else None,
                                        f"highlight {mine['highlight_color']}" if "highlight_color" in mine else None) if w]
                ws = now_said or said
                text = f"Captions: {', '.join(ws[:-1]) + ' and ' + ws[-1] if len(ws) > 1 else ws[0]}, for this video (saved to its taste). Plan again so it shows."
                old = next((c for c in d["comments"] if (c.get("on") or {}).get("k") == "captions" and c["stage"] == d["stage"]
                            and c["round"] >= d["round"] and editable(d, c)), None)
                if old:
                    def put(x):
                        for c in x["comments"]:
                            if c["id"] == old["id"]:
                                c.update(text=text, edited=now())
                    update(rj, put)
                    return self.send(200, {**old, "text": text})
                return self.comment({"t": 0.0, "text": text, "on": {"k": "captions", "text": "all captions"}})
            if path in ("/sound", "/sound/add"):   # the Sounds panel: a pick for one moment, or your own file, for every video
                sfx = sfx_mod()
                cue = str(body.get("cue") or "")
                if path == "/sound/add":
                    name = re.sub(r"[^A-Za-z0-9._ -]", "", Path(str(body.get("name") or "")).name).strip()[:80]
                    data = str(body.get("data") or "")
                    if cue not in sfx.KIT or not name or Path(name).suffix.lower() not in sfx.SOUND_EXT or not data.startswith("data:"):
                        return self.send(400, {"error": "Add a sound file: wav, mp3, m4a, aac, flac, ogg or opus."})
                    try:
                        raw = base64.b64decode(data.split(",", 1)[1], validate=True)
                    except (ValueError, IndexError):
                        return self.send(400, {"error": "That file did not come through."})
                    if len(raw) > SOUND_MAX_MB * 1024 * 1024:
                        return self.send(400, {"error": f"Sounds under {SOUND_MAX_MB} MB only."})
                    lib = sfx.library_dir()
                    lib.mkdir(parents=True, exist_ok=True)
                    (lib / name).write_bytes(raw)
                    body = {"cue": cue, "choice": name}
                try:
                    sfx.choose(cue, str(body.get("choice") or ""))
                except ValueError as e:
                    return self.send(400, {"error": str(e)})
                d = load(rj)
                last = d["events"][-1]["type"] if d["events"] else None
                if d.get("stage") != "edit" or d.get("sent") and last not in ("send", "edits"):
                    return self.send(200, {"ok": True, "sounds": sounds_info()})   # saved for the next videos; this one is done
                info = sounds_info()   # one Sounds note per round, saying what plays where now
                picked = [f"{x['label']} {'off' if x['choice'] == 'none' else 'is ' + x['choice']}" for x in info["cues"] if x["choice"] != "default"]
                text = (f"Sounds for every video: {'; '.join(picked)}." if picked else "Sounds for every video: all back to the built-in ones.") \
                    + " Plan again so they are in (custom/sounds/choices.json; sfx.py builds the kit from it)."
                old = next((c for c in d["comments"] if (c.get("on") or {}).get("k") == "sounds" and c["stage"] == d["stage"]
                            and c["round"] >= d["round"] and editable(d, c)), None)
                if old:
                    def put(x):
                        for c in x["comments"]:
                            if c["id"] == old["id"]:
                                c.update(text=text, edited=now())
                    update(rj, put)
                    return self.send(200, {**old, "text": text, "ok": True, "sounds": info})
                return self.comment({"t": 0.0, "text": text, "on": {"k": "sounds", "text": "all sounds"}})
            if path == "/sound/library/remove":   # the Sounds panel's x: out of the library (kept in .removed)
                try:
                    library_remove(str(body.get("name") or ""))
                except ValueError as e:
                    return self.send(400, {"error": str(e)})
                return self.send(200, {"ok": True, "sounds": sounds_info()})
            if path == "/sfx/move":   # the Sounds row: a sound the user put there dragged, trimmed or turned up or down
                d = load(rj)
                last = d["events"][-1]["type"] if d["events"] else None
                if d.get("stage") != "edit" or d.get("sent") and last not in ("send", "edits"):
                    return self.send(409, {"error": "Sounds change on the edit, before it is approved."})
                items = placed_raw(folder)
                x = next((i for i in items if i.get("id") == body.get("placed")), None)
                if not x:
                    return self.send(404, {"error": "That sound is gone already."})
                try:
                    x["t"] = round(max(0.0, float(body.get("t", x["t"]))), 2)
                    if x.get("kind") == "clip":
                        x["in"] = round(max(0.0, float(body.get("in", x.get("in", 0)))), 2)
                        x["dur"] = round(max(0.1, float(body.get("dur", x["dur"]))), 2)
                        x["vol"] = round(min(2.0, max(0.0, float(body.get("vol", x.get("vol", 1))))), 2)
                except (TypeError, ValueError):
                    return self.send(400, {"error": "sfx/move takes placed and t (a clip also in, dur, vol)"})
                (folder / "sounds.json").write_text(json.dumps({"items": items}, indent=1), encoding="utf-8")
                line = f"{Path(x['sound']).stem} at {fmt(x['t'])}" + (f" for {x['dur']:.1f} s at {round(x['vol'] * 100)}%" if x.get("kind") == "clip" else "")
                return self.timeline_note("sounds-timeline", "Sounds on the timeline", line,
                                          "Plan again so they are in (sounds.json and overrides.json sfx).")
            if path in ("/sfx/add", "/sfx/remove"):   # the timeline's Sounds row: put a library sound at a moment, or take one out
                d = load(rj)
                last = d["events"][-1]["type"] if d["events"] else None
                if d.get("stage") != "edit" or d.get("sent") and last not in ("send", "edits"):
                    return self.send(409, {"error": "Sounds change on the edit, before it is approved."})
                sfx, f = sfx_mod(), folder / "sounds.json"
                items = placed_raw(folder)
                try:
                    t = round(float(body["t"]), 2)
                    if path == "/sfx/add":
                        name = str(body.get("sound") or "")
                        if name not in sfx.own_sounds():
                            raise ValueError
                        x = {"id": secrets.token_hex(4), "t": t, "sound": name}
                        length = sound_shape(sfx.library_dir() / name, n=8).get("d") or 0
                        if length > sfx.MAX_OWN_S + 0.05:   # a song from the library: a clip as long as it is
                            (folder / "audio").mkdir(exist_ok=True)
                            shutil.copy2(sfx.library_dir() / name, folder / "audio" / name)
                            dur = float((data_of(folder, d.get("data")) or {}).get("duration") or 0)
                            x.update(kind="clip", **{"in": 0.0}, dur=round(max(0.1, min(length, dur - t if dur > t else length)), 2), vol=1.0)
                        f.write_text(json.dumps({"items": items + [x]}, indent=1), encoding="utf-8")
                        line = f"add {Path(name).stem} at {fmt(t)}"
                    elif body.get("placed"):
                        if not any(i["id"] == body["placed"] for i in items):
                            raise ValueError
                        f.write_text(json.dumps({"items": [i for i in items if i["id"] != body["placed"]]}, indent=1), encoding="utf-8")
                        line = f"remove {sound_name(body.get('src') or '')} at {fmt(t)}"
                    else:   # one the plan put there: overrides.json takes it out, so a re-plan keeps it out
                        ov_f = folder / "overrides.json"
                        ov = load(ov_f) if ov_f.exists() else {}
                        ov.setdefault("sfx", {})[f"{t:.3f}"] = {"deleted": True}
                        ov_f.write_text(json.dumps(ov, indent=1), encoding="utf-8")
                        line = f"remove {sound_name(body.get('src') or '')} at {fmt(t)}"
                except (KeyError, TypeError, ValueError):
                    return self.send(400, {"error": "sfx/add takes t and a library sound; sfx/remove takes t and placed or src"})
                return self.timeline_note("sounds-timeline", "Sounds on the timeline", line,
                                          "Plan again so they are in (sounds.json and overrides.json sfx).")
            if path == "/captions/text":   # the Captions panel's lines or the timeline: one caption line retyped, or deleted ("")
                d = load(rj)
                last = d["events"][-1]["type"] if d["events"] else None
                if d.get("stage") != "edit" or d.get("sent") and last not in ("send", "edits"):
                    return self.send(409, {"error": "Captions change on the edit, before it is approved."})
                try:
                    starts = [f"{float(k):.3f}" for k in body["w"]]
                    words = caption_words(starts, str(body.get("text") or "")[:300])
                    old, t = str(body.get("old") or "")[:300], float(body["s"])
                except (KeyError, TypeError, ValueError):
                    return self.send(400, {"error": "captions/text takes s, w (its word starts) and text"})
                ovf = folder / "overrides.json"
                ov = load(ovf) if ovf.exists() else {}
                ov.setdefault("words", {}).update(words)
                ovf.write_text(json.dumps(ov, indent=1), encoding="utf-8")
                new = " ".join(w for w in words.values() if w)
                line = f'"{old}" at {fmt(t)} now "{new}"' if new else f'"{old}" at {fmt(t)} taken out'
                return self.timeline_note("caption-text", "Captions retyped", line, "Plan again so they show (overrides.json words).")
            if path == "/captions/time":   # the timeline's Captions row: a page made longer, shorter or moved. overrides.json
                # cap_times, keyed by its first word's start so a new plan finds it; baked in by itself (bake_soon)
                d = load(rj)
                last = d["events"][-1]["type"] if d["events"] else None
                if d.get("stage") != "edit" or d.get("sent") and last not in ("send", "edits"):
                    return self.send(409, {"error": "Captions change on the edit, before it is approved."})
                try:
                    key, a, b = f"{float(body['w']):.3f}", round(float(body["s"]), 3), round(float(body["e"]), 3)
                    if a < 0 or b - a < 0.1:
                        raise ValueError
                except (KeyError, TypeError, ValueError):
                    return self.send(400, {"error": "captions/time takes w (its first word's start), s and e"})
                ovf = folder / "overrides.json"
                ov = load(ovf) if ovf.exists() else {}
                ov.setdefault("cap_times", {})[key] = [a, b]
                ovf.write_text(json.dumps(ov, indent=1), encoding="utf-8")
                bake_soon(folder)
                if not d.get("sent"):
                    return self.send(200, {"ok": True})
                return self.timeline_note("caption-times", "Caption timing", f'"{str(body.get("text") or "")[:60]}" now {fmt(a)}-{fmt(b)}',
                                          "Plan again so it shows (overrides.json cap_times).")
            if path == "/card/edit":   # the video page: a card moved, resized or deleted: overrides.json, baked in by itself
                # (bake_soon); a note for Claude only while it has the round
                d = load(rj)
                last = d["events"][-1]["type"] if d["events"] else None
                if d.get("stage") != "edit" or d.get("sent") and last not in ("send", "edits"):
                    return self.send(409, {"error": "Cards change on the edit, before it is approved."})
                key, label = str(body.get("key") or ""), str(body.get("label") or "the card")[:120]
                try:
                    if not re.fullmatch(r".*@\d+(\.\d+)?", key):
                        raise ValueError
                    if body.get("deleted"):
                        change, what = {"deleted": True}, "Remove"
                    else:
                        change, what = {}, "Move or resize"
                        if "box" in body:
                            box = [round(float(v), 1) for v in body["box"]]
                            if len(box) != 4 or box[2] < 3 or box[3] < 3 or not all(-50 <= v <= 150 for v in box):
                                raise ValueError
                            change["box"] = box
                        if "start" in body or "end" in body:   # the timeline's Images row: moved or trimmed in time
                            s, e = round(float(body["start"]), 2), round(float(body["end"]), 2)
                            if s < 0 or round(e - s, 2) < 0.2 or e > 36000:
                                raise ValueError
                            change.update(start=s, end=e)
                            what = f"Retime ({fmt(s)}-{fmt(e)})" if "box" not in change else what
                        if not change:
                            raise ValueError
                    t, te = float(body["t"]), float(body["t_end"])
                except (KeyError, TypeError, ValueError):
                    return self.send(400, {"error": "card/edit takes key, t, t_end and box [x, y, w, h], start and end, or deleted"})
                card_override(folder, key, change)
                bake_soon(folder)
                if not d.get("sent"):
                    return self.send(200, {"ok": True})
                return self.comment({"t": t, "t_end": te, "text": f"{what} {label} as shown on the page: overrides.json has it "
                                     f"(card {key}). Plan again so it shows."})
            if path == "/timeline/cut":   # the timeline's Video row: {splits: [t], gone: [[a, b]]} on the edit's clock.
                # The page skips the gone pieces at once; one note tells Claude the words to cut from the next draft
                d = load(rj)
                last = d["events"][-1]["type"] if d["events"] else None
                if d.get("stage") != "edit" or d.get("sent") and last not in ("send", "edits"):
                    return self.send(409, {"error": "The video is cut on the edit, before it is approved."})
                try:
                    cuts = timeline_cuts(body)
                except (KeyError, TypeError, ValueError):
                    return self.send(400, {"error": "timeline/cut takes splits [t] and gone [[start, end]]"})
                ovf = folder / "overrides.json"
                ov = load(ovf) if ovf.exists() else {}
                ov["cuts"] = cuts
                ovf.write_text(json.dumps(ov, indent=1), encoding="utf-8")
                old = next((c for c in d["comments"] if (c.get("on") or {}).get("k") == "cuts" and c["stage"] == d["stage"]
                            and c["round"] >= d["round"] and editable(d, c)), None)
                text = cuts_text(d.get("transcript"), cuts["gone"])
                if old:
                    def put(x):
                        if text:
                            for c in x["comments"]:
                                if c["id"] == old["id"]:
                                    c.update(text=text, t=cuts["gone"][0][0], t_end=cuts["gone"][-1][1], edited=now())
                        else:   # every piece put back: nothing to tell Claude
                            x["comments"] = [c for c in x["comments"] if c["id"] != old["id"]]
                    update(rj, put)
                    return self.send(200, {"ok": True, "cuts": cuts})
                if not text:
                    return self.send(200, {"ok": True, "cuts": cuts})
                return self.comment({"t": cuts["gone"][0][0], "t_end": cuts["gone"][-1][1], "text": text,
                                     "on": {"k": "cuts", "text": "cuts on the timeline"}})
            if path in ("/text/add", "/text/delete", "/text/edit"):   # the Text tool: texts.json changes on the spot and
                # the page draws it at once; bake_soon puts it in the video with no Claude. Only while Claude has the
                # round does a note tell it as well (it plans texts.json in itself)
                d, f = load(rj), folder / "texts.json"
                last = d["events"][-1]["type"] if d["events"] else None
                if d.get("sent") and last not in ("send", "edits"):
                    return self.send(409, {"error": "This draft is approved."})
                items = (load(f).get("items") or []) if f.exists() else []
                x = {"id": "t" + uuid.uuid4().hex[:8], "text": "", "style": "outline", "x_pct": 50, "y_pct": 40,
                     "start": 0.0, "end": TEXT_HOLD_S} if path == "/text/add" else \
                    next((i for i in items if i.get("id") == body.get("id")), None)
                if not x:
                    return self.send(404, {"error": "That text is gone already."})
                tell = lambda text, r=x: self.comment({"t": r["start"], "t_end": r["end"], "text": text}) if d.get("sent") else \
                    self.send(200, {"ok": True, "id": r["id"]})
                if path == "/text/delete":
                    f.write_text(json.dumps({"items": [i for i in items if i is not x]}, indent=1), encoding="utf-8")
                    bake_soon(folder)
                    return tell(f'Remove the on-screen text "{x["text"]}".')
                text = str(body.get("text") or x["text"]).strip()[:120]
                if not text:
                    return self.send(400, {"error": "Type the text first."})
                try:
                    new = {k: v for k, v in x.items() if k not in ("font", "color", "width_pct")}   # text_look sets them again when kept
                    new = {**new, "text": text, **text_look({**x, **{k: body[k] for k in ("style", "x_pct", "y_pct", "size_pct", "font", "color", "width_pct") if k in body}})}
                    if body.get("start") is not None:
                        new["start"] = round(max(0.0, float(body["start"])), 2)
                        new["end"] = round(max(new["start"] + 0.1, float(body.get("end") or new["start"] + TEXT_HOLD_S)), 2)
                except (ValueError, TypeError) as e:
                    return self.send(400, {"error": str(e) or "no time"})
                f.write_text(json.dumps({"items": [new if i is x else i for i in items] + ([new] if path == "/text/add" else [])},
                                        indent=1), encoding="utf-8")
                bake_soon(folder)
                if path == "/text/add":
                    return tell(f'Add the on-screen text "{text}": texts.json has it. Plan again so it shows.', new)
                what = [w for w, k in (("words", "text"), ("look", "style"), ("place", "x_pct"), ("place", "y_pct"),
                                       ("size", "size_pct"), ("font", "font"), ("colour", "color"), ("width", "width_pct"), ("time", "start"),
                                       ("time", "end")) if new.get(k) != x.get(k)]
                return tell(f'Change the on-screen text "{x["text"]}" ({", ".join(dict.fromkeys(what)) or "no change"}): '
                            f'texts.json has it now as "{text}". Plan again so it shows.', new)
            if path == "/delete":
                def rm(d):
                    d["comments"] = [c for c in d["comments"] if not (c["id"] == body.get("id") and editable(d, c))]
                update(rj, rm)
                return self.send(200, {})
            if path == "/check":   # "got it" on one of Claude's answers
                ids = set(body.get("ids", []))
                def ck(d):
                    for c in d["comments"]:
                        if c["id"] in ids:
                            c["checked"] = True
                update(rj, ck)
                return self.send(200, {})
            if path == "/update":   # the rail's Update: the window installs it; this server then moves onto it (live.py)
                return self.send(200 if start_update() else 409, {})
            if path == "/event":
                if body.get("type") not in ("send", "approve", "stop"):
                    return self.send(400, {})
                if body["type"] == "approve" and load(rj).get("raw"):   # nothing to approve before the first cut
                    return self.send(409, {"error": "The cut is not ready yet."})
                if body["type"] == "stop":   # the round's notes open again; `status` tells Claude to stop
                    err = stop_round(folder)
                    return self.send(409, {"error": err}) if err else self.send(200, {})
                style = style_label(folder) if body["type"] == "approve" else None
                choices = style_choices(folder) if body["type"] == "approve" else None

                def ev(d):
                    if d.get("sent") and d["events"] and d["events"][-1]["type"] == "edits":
                        return False   # Claude is applying transcript changes: Stop first
                    d["events"].append({"type": body["type"], "stage": d["stage"], "round": d["round"],
                                        "at": now(), "handled": False, **({"stills": True} if d.get("stills") else {})})
                    d["sent"] = True
                    d.pop("stopped", None)
                    if body["type"] == "approve" and (d["stage"] == "edit" and not d.get("stills") or d.get("final")):   # the finished video
                        d["learn"] = {"state": "reading" if session_notes(d) else "none", "style": style, "styles": choices}
                    elif body["type"] == "approve" and d["stage"] == "cut":
                        prepared_steps(folder, d)
                    return True
                if not update(rj, ev):
                    return self.send(409, {"error": "Claude is applying your transcript changes."})
                if body["type"] == "send" and load(rj).get("stills"):   # notes on the stills: that render is not the one
                    drop_spec(folder)
                with contextlib.suppress(Exception):   # the notes are saved either way
                    reopen(folder, rj)   # no Claude on this edit any more: a new one takes the notes
                return self.send(200, {})
            if path == "/claude":   # Start Claude: carry on in the Claude that worked here, else a new one
                return self.send(200, reopen(folder, rj, force=True) or {})
            if path == "/claude/show":   # Show Claude: its Terminal tab to the front
                return self.send(200, {"shown": show_claude(folder)})
            self.send(404, {})

        def timeline_note(self, k, title, line, tail):
            """One note per round for the timeline's changes of a kind, a line added for each change."""
            d = load(rj)
            old = next((c for c in d["comments"] if (c.get("on") or {}).get("k") == k and c["stage"] == d["stage"]
                        and c["round"] >= d["round"] and editable(d, c)), None)
            lines = ((old or {}).get("lines") or []) + [line]
            text = f"{title}: {'; '.join(lines)}. {tail}"
            if old:
                def put(x):
                    for c in x["comments"]:
                        if c["id"] == old["id"]:
                            c.update(text=text, lines=lines, edited=now())
                update(rj, put)
                return self.send(200, {**old, "text": text, "lines": lines})
            # lines go in with the note: set after the reply, a change sent right after it read a note without them
            self.comment({"t": 0.0, "text": text, "on": {"k": k, "text": title.lower()}, "lines": lines})

        def comment(self, body):
            text = str(body.get("text", "")).strip()
            imgs = body.get("images") or []
            if not text and not imgs:
                return self.send(400, {"error": "empty"})
            try:
                t = float(body["t"])
                te = float(body["t_end"]) if body.get("t_end") is not None else None
            except (KeyError, TypeError, ValueError):
                return self.send(400, {"error": "no time"})
            d = load(rj)
            last = d["events"][-1]["type"] if d["events"] else None
            if d.get("sent") and last not in ("send", "edits"):   # approved: nothing comes after it on this stage
                return self.send(409, {"error": "This draft is approved."})
            queued = bool(d.get("sent"))   # with Claude: the note waits for the next round
            alt = body.get("alt") or None
            src = alt_of(d, alt if alt != "*" else None)
            cid = max([c["id"] for c in d["comments"]] + [0]) + 1
            frame = f"r{d['stage']}{d['round']}-c{cid}.jpg"
            grab(src["video"], t, folder / "review" / frame)
            images = askhook.save_images(folder / "review", imgs, f"r{d['stage']}{d['round']}-c{cid}")
            on = body.get("on") if isinstance(body.get("on"), dict) else None
            add = body.get("add_text")
            if add is not None:   # the Text tool: the note's words go on screen as typed, in one of TikTok's three looks
                try:
                    add = text_look(add)
                except ValueError as e:
                    return self.send(400, {"error": str(e)})
                if not text or d["stage"] != "edit":
                    return self.send(400, {"error": "Text goes on the edit, in plain, outline or box."})
                if te is None:
                    te = t + TEXT_HOLD_S
            words, card = note_tags(d.get("plan"), src.get("transcript"), d["stage"], t, te, on)
            c = {"id": cid, "round": d["round"] + queued, "stage": d["stage"], "t": round(t, 2), "alt": alt,
                 "t_end": round(te, 2) if te is not None else None, "text": text, "words": words, "card": card,
                 "frame": frame, "images": images, "status": "open", "reply": None, "new_t": None, "at": now()}
            if looks_like_rule(text):   # offered as a rule, ticked: the user unticks it on the page
                c["keep"] = True
            if queued:
                c["queued"] = True
            if add:
                c["add_text"] = add
            if on:
                c["on"] = {"k": str(on.get("k") or ""), "text": str(on.get("text") or "")[:300]}
                if isinstance(body.get("lines"), list):   # a timeline note's running lines, saved with it before the reply
                    c["lines"] = [str(x) for x in body["lines"]]
            update(rj, lambda d: d["comments"].append(c))
            return self.send(200, c)

        def transcript_edits(self, body):
            """The transcript editor's Apply: restore/cut word ranges (raw-take seconds) into spans.json, then an
            "edits" event, so `wait` exits and Claude rebuilds, renders, verifies and opens the next round."""
            try:
                restore, cut, pause = (list(body.get(k) or []) for k in ("restore", "cut", "pause"))
                for r in restore + cut + pause:
                    if len(r) != 2 or float(r[0]) > float(r[1]):
                        raise ValueError
            except (TypeError, ValueError, AttributeError):
                return self.send(400, {"error": "restore, cut and pause take [[start, end], ...]"})
            with LOCK:   # one Apply at a time: the sent check, the files and the event move together
                d = load(rj)
                if d.get("stage") != "cut" or d.get("raw"):
                    return self.send(409, {"error": "Words can only change on the cut."})
                if d.get("sent"):
                    return self.send(409, {"error": "Claude is working on this draft."})
                try:
                    out = apply_edits(folder, restore, cut, pause)
                except Exception as e:   # a spans.json or transcript this cannot read: say so, never drop the connection
                    return self.send(409, {"error": str(e) or type(e).__name__})
                if not (out["restored"] or out["cut"] or out["pauses"]):
                    return self.send(200, {**out, "event": False})

                def ev(d):
                    d["events"].append({"type": "edits", "stage": d["stage"], "round": d["round"], "at": now(), "handled": False,
                                        "n": len(restore) + len(cut) + len(pause), "restore": restore, "cut": cut, "pause": pause,
                                        "counts": {k: v for k, v in out.items() if k != "sha"}, "sha": out["sha"]})
                    d["sent"] = True
                    d.pop("stopped", None)
                update(rj, ev)
            return self.send(200, {**out, "event": True})

        def edit(self, body):
            """A note changed in place: its text, its time (moved to the playhead: new frame still and words),
            its version scope, its images (kept names plus new data urls). Same id; refused once Claude has it."""
            d = load(rj)
            c = next((x for x in d["comments"] if x["id"] == body.get("id")), None)
            if not c:
                return self.send(404, {"error": "no such note"})
            if not editable(d, c):
                return self.send(409, {"error": "Claude is working on this draft." if d.get("sent") else "This note is from an earlier draft."})
            new = dict(c)
            if "text" in body:
                new["text"] = str(body["text"] or "").strip()
                if "keep_set" not in c:
                    new.pop("keep", None)
                    if looks_like_rule(new["text"]):
                        new["keep"] = True
            if "alt" in body:
                new["alt"] = body["alt"] or None
            if body.get("add_text") is not None and c.get("add_text"):   # the Text tab's Save: a new look or place
                try:
                    new["add_text"] = text_look(body["add_text"])
                except ValueError as e:
                    return self.send(400, {"error": str(e)})
            if "images" in body:
                new["images"] = askhook.save_images(folder / "review", body["images"] or [], f"r{c['stage']}{c['round']}-c{c['id']}",
                                            keep=c.get("images") or [])
            if not new["text"] and not new["images"]:
                return self.send(400, {"error": "empty"})
            src = alt_of(d, new["alt"] if new["alt"] != "*" else None)
            if "t" in body:
                try:
                    t = round(float(body["t"]), 2)
                except (TypeError, ValueError):
                    return self.send(400, {"error": "no time"})
                if body.get("t_end") is not None:   # a new span (the Text tab's i/o)
                    try:
                        new["t_end"] = round(max(t + 0.1, float(body["t_end"])), 2)
                    except (TypeError, ValueError):
                        return self.send(400, {"error": "no time"})
                elif c["t_end"] is not None:
                    new["t_end"] = round(t + c["t_end"] - c["t"], 2)
                new["t"], new["frame"] = t, f"r{c['stage']}{c['round']}-c{c['id']}-{int(time.time() * 1000) % 10 ** 8}.jpg"
                grab(src["video"], t, folder / "review" / new["frame"])
                new.pop("on", None)   # moved: no longer the thing clicked, what is on screen at the new time
            if "t" in body or "alt" in body:
                new["words"], new["card"] = note_tags(d.get("plan"), src.get("transcript"), c["stage"], new["t"], new["t_end"],
                                                      new.get("on"))
            new["edited"] = now()

            def put(d):   # again under the lock: the round may have gone to Claude meanwhile
                for i, x in enumerate(d["comments"]):
                    if x["id"] == new["id"]:
                        if not editable(d, x):
                            return False
                        d["comments"][i] = {**new, "round": x["round"], **({"queued": True} if x.get("queued") else {})}
                        return True
                return False
            if not update(rj, put):
                return self.send(409, {"error": "Claude is working on this draft."})
            return self.send(200, new)
    return H


def running(folder):
    """The URL of this folder's server if one answers, else None."""
    f = folder / "review" / ".server"
    try:
        url = f.read_text(encoding="utf-8").strip()
        s = json.loads(urllib.request.urlopen(url.replace("/?t=", "/state?t="), timeout=2).read())
        return url if s.get("folder") == str(folder) else None
    except (OSError, ValueError):
        return None


OPEN = webbrowser.open   # a new browser tab (the demo swaps it)


def taken_jobs():
    """The home page's taken jobs."""
    f = Path(os.environ.get("AI_EDITOR_HOME", "").strip() or Path.home() / ".ai-video-editor") / "home" / "state.json"
    try:
        jobs = json.loads(f.read_text(encoding="utf-8")).get("jobs") or []
    except (OSError, ValueError):
        return []
    return [j for j in jobs if isinstance(j, dict) and j.get("state") == "taken"]


def job_edit(j):
    """The edit folder a home job works on, resolved, or None."""
    e = (j.get("args") or {}).get("edit")
    return Path(e).resolve() if isinstance(e, str) and e else None


def video_jobs(folder):
    """The home page's taken video jobs for this edit folder."""
    return [j for j in taken_jobs() if j.get("type") == "video" and job_edit(j) == folder.resolve()]


def home_opens(folder):
    """True when a showing home window holds this edit's video job: it goes to this page in its own tab."""
    return bool(askhook.live("home")) and bool(video_jobs(folder))


def show(url, folder):
    """A new tab, unless the home window is about to show this page itself."""
    if not home_opens(folder):
        OPEN(url)


def asker(folder, started):
    """Questions on this page come from the session that last ran a review.py command on this edit
    (review/.session), else the one that started the server, and from the session holding this edit's video job
    on the home page. A session holding any job on the home page asks only on that job's edit page, never on
    another (a server the home window started knows no session of its own). They name the edit."""
    def session_of(f):
        try:
            return (f / "review" / ".session").read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def owner(sid):
        held = [j for j in taken_jobs() if sid and j.get("owner") == sid]
        if held:   # the job decides: its own edit's page, no other
            return folder.name if any(job_edit(j) == folder.resolve() for j in held) else None
        own = session_of(folder) or started
        if own:
            return folder.name if sid == own else None
        # no session known here: only a question with no session. A Claude on this video names it (askhook's
        # asking_edit), so a session that never touched it is another project's
        return None if sid else folder.name
    return owner


def serve(folder, port=0, open_browser=True):
    """(server, url). An already running server for this folder is reused: (None, its url)."""
    url = running(folder)
    if url:
        if open_browser:
            show(url, folder)
        return None, url
    token, want, last = secrets.token_urlsafe(32), port, folder / "review" / ".server"
    if last.is_file() and (os.name == "nt" or last.stat().st_mode & 0o077 == 0):   # only our own private file
        m = re.match(r"http://127\.0\.0\.1:(\d+)/\?t=([\w-]+)$", last.read_text(encoding="utf-8").strip())
        if m:   # the same address as last time, so an open tab or a saved link keeps working
            token, want = m.group(2), port or int(m.group(1))
    # exclusive bind on Windows, where SO_REUSEADDR (HTTPServer's default) lets two servers share a port
    cls = type("Server", (ThreadingHTTPServer,), {"allow_reuse_address": os.name != "nt"})
    try:
        srv = cls(("127.0.0.1", want), make_handler(folder, token))
    except OSError:   # the old port is taken now: a new one, same token
        srv = cls(("127.0.0.1", port), make_handler(folder, token))
    url = f"http://127.0.0.1:{srv.server_address[1]}/?t={token}"
    last.parent.mkdir(parents=True, exist_ok=True)   # a video made elsewhere has no review/ folder yet
    with os.fdopen(os.open(last, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
        f.write(url)   # private: the token in it lets a page in
    if os.name != "nt":
        os.chmod(last, 0o600)
    askhook.register(srv, url, "review", asker(folder, askhook.session()), lambda sid: folder / "review", folder)
    if open_browser:
        show(url, folder)
    return srv, url


# ---------------------------------------------------------------- cli
def keep(folder, video, stage, rnd, name=None):
    """A copy of the round's video in <folder>/review/, so the next render (written to the same cut.mp4)
    never changes what an earlier round's tab replays. A copy, not a hardlink: ffmpeg and Remotion rewrite
    the file in place, and a hardlink would change with it."""
    src = Path(video).resolve()
    tag = "-" + re.sub(r"[^\w-]", "_", name) if name else ""   # outside the f-string: Python 3.9 (a Mac's built-in) has no backslash there
    dst = folder / "review" / f"v-{stage}{rnd}{tag}{src.suffix}"
    if src != dst.resolve():
        # A Mac clones on APFS (cp -c: no extra disk until one side changes, and a rewrite of the cut
        # never reaches the clone); anything else, or a cp -c refused off APFS, copies.
        # ponytail: Linux btrfs/xfs could reflink with cp --reflink=auto if disk use matters there
        clone(src, dst)
    return str(dst)


def cmd_start(a, folder):
    (folder / "review").mkdir(parents=True, exist_ok=True)
    rj = folder / "review.json"
    d = load(rj) if rj.exists() else {"folder": str(folder), "name": folder.name, "comments": [], "events": []}
    raw = getattr(a, "raw", False)
    if d.get("raw") and not raw:   # the cut after the raw clip: round 1, with the notes left on the raw clip
        return cmd_round(a, folder)
    d.update(folder=str(folder), stage=a.stage, round=0 if raw else d.get("round", 0) + 1 if d.get("stage") == a.stage else 1,
             video=str(Path(a.video).resolve()), note=a.note or "", sent=False, alts=[],
             transcript=str(Path(a.transcript).resolve()) if a.transcript else None,
             plan=str(Path(a.plan).resolve()) if a.plan else None, vertical=probe(a.video), label=a.name,
             stills=bool(getattr(a, "stills", False)))
    d.pop("stopped", None)
    d.pop("raw", None)
    again = raw and d.get("raw")   # round 0 again (the page opened it; Claude swaps in joined.mp4): one send event
    if raw:   # with Claude from the start: notes queue for the cut, as after a send
        d.update(raw=True, sent=True)
    if raw and not again:
        d["events"].append({"type": "send", "stage": d["stage"], "round": 0, "at": now(), "handled": True, "raw": True})
    # the raw clip is a source, never rewritten: played where it is, not copied (it can be gigabytes)
    d["video"] = d["video"] if raw else keep(folder, a.video, d["stage"], d["round"])
    d.update(src=None if raw else str(Path(a.video).resolve()), snap=None if raw else snapshot(folder, d["stage"], d["round"]),
             changed=list(getattr(a, "changed", None) or []), back_to=None)
    d["data"] = round_data(folder, d["video"], d["stage"], d["round"], d["plan"])
    log_round(d)
    save(rj, d)
    if not raw:
        seen(folder)
        noted(folder)
    try:   # the home page's library lists this edit wherever it was made
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import library
        library.record(folder)
    except (OSError, ValueError, ImportError):
        pass
    print(f"{rj}: {stage_name(d['stage'], d.get('stills'))}, round {d['round']}")


def open_round(folder, video, stage=None, transcript=None, plan=None, note="", stills=False, name=None, changed=(),
               back_to=None, src=None, check=None):
    """The next round: the new render kept, the edit's files snapshotted, notes queued meanwhile moved onto it.
    check(d) runs under the lock first and may refuse (raise ValueError) before anything changes."""
    def f(d):
        if check:
            check(d)
        prev = None if stage and stage != d["stage"] else next(
            (r for r in d.get("rounds", []) if (r["stage"], r["round"]) == (d["stage"], d["round"])), None)
        if stage and stage != d["stage"]:
            d["stage"], d["round"] = stage, 1
        else:
            d["round"] += 1
        d["video"] = keep(folder, video, d["stage"], d["round"])
        d["vertical"] = probe(video)
        if transcript:
            d["transcript"] = str(Path(transcript).resolve())
        if plan:
            d["plan"] = str(Path(plan).resolve())
        d["note"], d["sent"], d["alts"] = note or "", False, []   # versions belong to a round: add them again
        d["stills"] = bool(stills)   # the stills (edit.py storyboard) before the render
        d["label"] = name or d.get("label")
        own = (folder / "review").resolve() in Path(video).resolve().parents   # a kept round's copy: never written back to
        d.update(src=src or (None if own else str(Path(video).resolve())), snap=snapshot(folder, d["stage"], d["round"]),
                 changed=[str(x) for x in changed or []], back_to=back_to)
        old = data_of(folder, d.get("data"))
        raw = d.pop("raw", False)
        d["data"] = round_data(folder, d["video"], d["stage"], d["round"], d.get("plan"),
                               prev=prev if prev and prev.get("round") and not raw else None)
        new = data_of(folder, d["data"])
        for c in d["comments"]:   # notes queued while Claude worked open on this round, where their words are said
            if c.pop("queued", None):
                nt = raw_to_cut(folder, c["t"]) if raw else remap(c["t"], old.get("transcript"), new.get("transcript"))
                if nt is None:
                    nt = min(c["t"], new.get("duration") or c["t"])
                    if old.get("duration") and new.get("duration") and abs(old["duration"] - new["duration"]) > 0.05:
                        c["moved"] = "time"   # the cut changed and no transcript says where: same time, check it
                elif abs(nt - c["t"]) >= 0.05:
                    c["moved"] = "words"
                if c.get("moved"):
                    c["t_was"] = c["t"]
                if c["t_end"] is not None:
                    c["t_end"] = round(c["t_end"] + nt - c["t"], 2)
                c.update(round=d["round"], stage=d["stage"], t=nt, frame=f"r{d['stage']}{d['round']}-c{c['id']}.jpg")
                src_ = alt_of(d, c["alt"] if c["alt"] != "*" else None)
                if c["alt"] not in (None, "*"):   # versions belong to a round: its version is gone, so the main video
                    c["alt"], src_ = None, alt_of(d, None)
                grab(src_["video"], nt, folder / "review" / c["frame"])
                c["words"], c["card"] = note_tags(d.get("plan"), src_.get("transcript"), d["stage"], nt, c["t_end"], c.get("on"))
        d.pop("stopped", None)
        for x in d.get("activity", []):
            x["done"] = True
        log_round(d)
        return d
    d = update(folder / "review.json", f)
    seen(folder)
    return d


def cmd_round(a, folder):
    d0 = load(folder / "review.json")
    if a.stage == "edit" and d0["stage"] == "cut" and d0.get("stopped"):
        print(f"STOPPED: the user pressed Stop on the page at {d0['stopped']}, which took the cut's approve back. "
              f"Do not open the edit: say so in one line and run `wait` again.")
        sys.exit(3)
    if d0.get("stopped"):
        sys.exit("STOPPED: the user pressed Stop on the page. Do not open a round; run `wait` for their next send.")
    if d0.get("sent") and getattr(a, "stage", None) in (None, d0["stage"]):
        unanswered = [c for c in d0["comments"] if (c["stage"], c["round"]) == (d0["stage"], d0["round"])
                      and c["status"] == "open" and not c.get("reply") and not c.get("queued")]
        if unanswered:   # the page shows each note done with its reply: a round with silent notes reads as ignored
            q = shlex.quote(str(Path(__file__).resolve()))
            sys.exit("REFUSED: answer every note of this round first, one line each on what you did, then run this `round` "
                     "again (the render is kept):\n" + "\n".join(
                         f"  python3 {q} {shlex.quote(str(folder))} resolve {c['id']} fixed --reply \"<what you changed>\"   "
                         f"# {c['text'][:60]}" for c in unanswered)
                     + "\n  (wontfix --reply \"<why>\" when you left it as is)")
    d = open_round(folder, a.video, a.stage, a.transcript, a.plan, a.note, getattr(a, "stills", False), a.name,
                   getattr(a, "changed", None))
    still = [str(c["id"]) for c in d["comments"]
             if c["status"] == "open" and c["stage"] == d["stage"] and c["round"] < d["round"]]
    print(f"{stage_name(d['stage'], d.get('stills'))}, round {d['round']}" + (f"; still open: {', '.join(still)}" if still else ""))
    unlearned = [str(c["id"]) for c in d["comments"] if "taste" not in c and (c["stage"], c["round"]) != (d["stage"], d["round"])]
    if unlearned:
        print(f"notes not learned yet: {', '.join(unlearned)}. Run `learn` (see `wait`'s last line)")
    if d.get("stills"):   # the user looks at the stills now: the render starts in the background
        why = speculate(folder, d.get("plan"))
        print("the edit renders in the background while the stills are up: an approve with no notes finds it ready"
              if why is None else f"no background render ({why})")
    noted(folder)
    if not running(folder):
        print("the page is not running: start it with `serve`")


def go_back(folder, n):
    """"Go back to draft N": that round's files (its snapshot) and its render return, as a new round of the same stage.
    The open round's unsent notes move onto it. ValueError says why it cannot."""
    d0 = load(folder / "review.json")
    r = next((r for r in d0.get("rounds", []) if (r["stage"], r["round"]) == (d0["stage"], n)), None)
    if not r or n < 1 or r.get("stills") or n == d0["round"]:
        raise ValueError(f"no round {n} to go back to")
    snap = folder / "review" / Path(r.get("snap") or "-").name
    if not r.get("snap") or not snap.is_dir() or not Path(r["video"]).is_file():
        raise ValueError("this round was made before rounds could be restored")

    def check(d):   # under the lock: Claude may have taken the round meanwhile
        if d.get("sent") or d.get("raw") or d.get("stopped"):
            raise ValueError("Claude has this round" if d.get("sent") else "this round cannot go back now")
        for c in d["comments"]:   # the open round's notes go with the user onto the restored round
            if c["stage"] == d["stage"] and c["round"] == d["round"] and c["status"] == "open":
                c["queued"] = True
        try:   # files made after that round (a "no zoom here" overrides.json, a contrast.json) go
            had = set((snap / SNAP_NAMES).read_text(encoding="utf-8").split())
        except OSError:   # a snapshot from before the list: the files it kept
            had = {f.name for f in snap.iterdir() if f.is_file()}
        for f in folder.iterdir():
            if f.is_file() and f.suffix in (".json", ".txt") and f.name != "review.json" and f.name not in had:
                f.unlink()
        if "music.wav" not in had:
            (folder / ".sfx" / "music.wav").unlink(missing_ok=True)
        for f in snap.rglob("*"):   # the files come back before the new round snapshots them
            if f.is_file() and f.name != SNAP_NAMES:
                rel = f.relative_to(snap)
                out_ = folder / ".sfx" / "music.wav" if rel.name == "music.wav" and len(rel.parts) == 1 else \
                    folder / Path(*rel.parts[1:]) if rel.parts[0] == "files" else folder / rel
                out_.parent.mkdir(parents=True, exist_ok=True)
                clone(f, out_)
        out = Path(r.get("src") or "-")
        if r.get("src") and folder.resolve() in out.resolve().parents and (folder / "review").resolve() not in out.resolve().parents:
            # the render the next fix starts from (cut.mp4, render.mp4)
            clone(Path(r["video"]), out)
        d["events"].append({"type": "back", "stage": d["stage"], "round": d["round"] + 1, "to": n, "at": now(), "handled": True})
    return open_round(folder, r["video"], note=f"Back to draft {n}", back_to=n, src=r.get("src"), check=check)


def cmd_resolve(a, folder):
    def f(d):
        for c in d["comments"]:
            if c["id"] == a.id:
                c["status"] = a.status
                if a.reply is not None:
                    c["reply"] = a.reply
                if a.new_t is not None:
                    c["new_t"] = a.new_t
                return c
        sys.exit(f"no note {a.id}")
    c = update(folder / "review.json", f)
    print(f"#{c['id']} {c['status']}")


# The style-edit's own steps, in order. The page fills its "Making the edit" bar from them (render by its log's
# percent); plan.py, retakes.py captions, route.py and edit.py report them with step(), Claude with status --step.
EDIT_STEPS = {"captions": "Writing the captions", "visuals": "Finding the visuals",
              "plan": "Planning zooms, cards and sound", "render": "Making the video"}


def add_step(d, text, log=None, key=None, done=False):
    """Close the open step and add this one. The same step key again only refreshes its log."""
    act = d.setdefault("activity", [])
    last = act[-1] if act else {}
    if key and last.get("step") == key and not last.get("done") and last.get("round") == d["round"]:
        last["log"] = str(Path(log).resolve()) if log else last.get("log")
        return
    for x in act:
        x["done"] = True
    if not done:
        act.append({"text": text or EDIT_STEPS.get(key, key), "at": now(), "round": d["round"], "done": False,
                    "log": str(Path(log).resolve()) if log else None, **({"step": key} if key else {})})
    d["activity"] = act[-30:]


def prepared_steps(folder, d):
    """visual-prep made these while the cut was reviewed, on this very cut (prep-decisions.json = decisions.json):
    the Making the edit card shows them done the moment the cut is approved, not as steps still to come."""
    try:
        if (folder / "prep-decisions.json").read_bytes() != (folder / "decisions.json").read_bytes():
            return []
    except OSError:
        return []
    keys = [k for k, f in (("captions", "captions.json"), ("visuals", "visuals.json"), ("plan", "stills/sheet.png"))
            if (folder / f).exists()]
    for k in keys:
        add_step(d, None, None, k)
    add_step(d, None, done=True)
    return keys


def making_edit(d):
    """Claude is making the styled edit: the cut was approved and no edit round has landed yet, or a sent edit
    round is being redone."""
    e = d["events"][-1] if d.get("events") else {}
    return bool(d.get("sent") and not d.get("stopped") and not d.get("final") and
                ((e.get("type") == "approve" and e.get("stage") == "cut" and d.get("stage") == "cut")
                 or (e.get("type") == "approve" and e.get("stills") and d.get("stills"))   # the stills approved: rendering
                 or (e.get("type") == "send" and d.get("stage") == "edit")))


def step(folder, key, log=None):
    """A style-edit script's step on the review page while Claude makes the edit. No page, not making the edit,
    or stopped: nothing. Never raises: the page is a nicety."""
    try:
        folder = Path(folder).resolve()
        rj = folder / "review.json"
        if key not in EDIT_STEPS or not rj.is_file():
            return False
        if not update(rj, lambda d: making_edit(d) and (add_step(d, None, log, key) or True)):
            return False
        (folder / "review" / ".claude").touch()   # Claude is working on it: the page shows the bar, not "not listening"
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- real times, after the fact
def _epoch(at):
    try:
        return time.mktime(time.strptime(at, "%Y-%m-%dT%H:%M:%S"))
    except (TypeError, ValueError):
        return None


def mmss(s):
    return f"{int(s // 60)}:{int(round(s)) % 60:02d}" if s < 3600 else f"{int(s // 3600)}:{int(s % 3600 // 60):02d}:{int(s % 60):02d}"


JOB_TIMES = ("added", "make", "transcribe_start", "transcribe_end")


def timings(folder):
    """How long this video took, stage by stage, from what is already recorded: the home window's job (when the clip
    was added, Make, the cut's script steps with their clock times) and review.json (each round's time, the user's
    approves, the render step). Never an estimate: a stage shows once it has happened. Writes <folder>/timings.json
    (times kept from an earlier write when the job has since left state.json) and returns it.
    "made" = the machine's time only (the cut, the edit up to the stills, the render), not the user's turns: their
    reviews, each earlier draft until they sent notes, and a question of Claude's while it was open."""
    folder = Path(folder)
    f = folder / "timings.json"
    try:   # the home job's times only: everything else is read again from review.json
        t = {k: v for k, v in json.loads(f.read_text(encoding="utf-8")).items() if k in JOB_TIMES}
    except (OSError, ValueError, AttributeError):
        t = {}
    try:
        jobs = json.loads((Path(os.environ.get("AI_EDITOR_HOME", "").strip() or Path.home() / ".ai-video-editor") / "home"
                           / "state.json").read_text(encoding="utf-8")).get("jobs") or []
        j = next((j for j in reversed(jobs) if j.get("type") == "video" and (j.get("args") or {}).get("edit")
                  and Path(j["args"]["edit"]).resolve() == folder.resolve()), None)
    except (OSError, ValueError, AttributeError, TypeError):
        j = None
    if j:
        steps = j.get("steps") or []
        i = next((k for k, x in enumerate(steps) if x.get("text") == "Writing down every word"), None)
        t.update({k: v for k, v in (("make", _epoch(j.get("at"))), ("added", (j.get("args") or {}).get("added")),
                                    ("transcribe_start", steps[i]["t"] if i is not None else None),
                                    ("transcribe_end", steps[i + 1]["t"] if i is not None and i + 1 < len(steps) else None))
                  if v is not None})
    try:
        d = load(folder / "review.json")
    except (OSError, ValueError):
        return t
    rounds = {(r["stage"], r["round"]): r for r in d.get("rounds") or []}
    ev = d.get("events") or []
    cut = next((r for k, r in sorted(rounds.items()) if k[0] == "cut" and k[1] >= 1), None)
    cut_ok = next((e for e in reversed(ev) if e["type"] == "approve" and e["stage"] == "cut"), None)
    st_ok = next((e for e in reversed(ev) if e["type"] == "approve" and e.get("stills")), None)
    st = rounds.get(("edit", st_ok["round"])) if st_ok else None
    done = next((r for k, r in sorted(rounds.items()) if st_ok and k[0] == "edit" and k[1] > st_ok["round"]
                 and not r.get("stills")), None)
    rstep = next((x for x in reversed(d.get("activity") or []) if x.get("step") == "render"), None)
    for k, at in (("cut_ready", cut and cut.get("at")), ("cut_approved", cut_ok and cut_ok.get("at")),
                  ("stills_ready", st and st.get("at")), ("stills_approved", st_ok and st_ok.get("at")),
                  ("render_start", rstep and rstep.get("at")), ("render_end", done and done.get("at"))):
        if _epoch(at) is not None:
            t[k] = _epoch(at)
    spec = folder / "render.spec.started"
    if spec.is_file():   # the render began in the background when the stills went up (edit.py --speculative)
        try:
            t["render_start"] = min(t.get("render_start") or 1e18, float(spec.read_text(encoding="utf-8")))
        except ValueError:
            pass
    gap = lambda a, b: round(t[b] - t[a], 1) if t.get(a) is not None and t.get(b) is not None and t[b] >= t[a] else None
    # the user's turns inside a machine stage: a question open (askhook asks.jsonl) and each draft until they sent notes
    # or approved. Merged, then taken out of the cut, the edit and the render, so "Made in" is the machine's time only
    waits = []
    try:
        waits = [(float(w["start"]), float(w["end"])) for w in map(json.loads, (folder / "review" / "asks.jsonl").read_text(
            encoding="utf-8").splitlines()) if w.get("end")]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    acts = sorted(_epoch(e.get("at")) or 0 for e in ev if e.get("type") in ("send", "approve"))
    for (sg_, n), r in sorted(rounds.items()):
        a = _epoch(r.get("at"))
        b = next((x for x in acts if a is not None and x >= a), None)
        if n >= 1 and a is not None and b is not None:
            waits.append((a, b))
    merged = []
    for a, b in sorted(waits):
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    t["waits_s"] = round(sum(b - a for a, b in merged), 1)

    def busy(a, b):
        g = gap(a, b)
        if g is None:
            return None
        lo, hi = t[a], t[b]
        return round(g - sum(max(0, min(hi, y) - max(lo, x)) for x, y in merged), 1)
    t["stages"] = {k: v for k, v in (("cut", busy("make", "cut_ready")), ("your_review", gap("cut_ready", "cut_approved")),
                                     ("edit", busy("cut_approved", "stills_ready")), ("your_stills_check", gap("stills_ready", "stills_approved")),
                                     ("render", busy("stills_approved", "render_end")),
                                     ("transcribe", gap("transcribe_start", "transcribe_end"))) if v is not None}
    sg = t["stages"]
    if all(k in sg for k in ("cut", "edit", "render")):
        made = sg["cut"] + sg["edit"] + sg["render"]
        t["made_s"] = round(made, 1)
        t["line"] = (f"Made in {round(made / 60)} min" if made >= 90 else f"Made in {round(made)} s") + \
            f" (cut {mmss(sg['cut'])}, edit {mmss(sg['edit'])}, render {mmss(sg['render'])})"
    tmp = f.with_name(f"timings.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(t, indent=1), encoding="utf-8")
    os.replace(tmp, f)
    return t


# ---------------------------------------------------------------- the render that starts with the stills
EDIT_PY = Path(__file__).resolve().parents[2] / "skills" / "style-edit" / "scripts" / "edit.py"


def alive(pid):
    if os.name == "nt":
        r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True)
        return str(pid) in r.stdout
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except OSError:
        return True


def on_battery():
    """True when a laptop runs on its battery (macOS pmset, Linux power_supply). Unknown: False."""
    try:
        if sys.platform == "darwin":
            return "Battery Power" in subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=5).stdout
        if sys.platform.startswith("linux"):
            mains = [p for p in Path("/sys/class/power_supply").glob("*") if (p / "type").is_file()
                     and (p / "type").read_text(encoding="utf-8").strip() == "Mains"]
            return bool(mains) and all((p / "online").read_text(encoding="utf-8").strip() == "0" for p in mains)
    except (OSError, subprocess.SubprocessError):
        pass
    return False   # ponytail: Windows reads no battery state; GetSystemPowerStatus via ctypes if laptops complain


def speculate(folder, plan):
    """The stills went up: start the laptop render now, at low priority (edit.py render --speculative), so an approve
    with no notes finds it done or nearly. Only for a laptop render (the profile's render unset or "laptop": a cloud
    render costs money), with the renderer installed, not on battery. Returns the reason it did not start, or None."""
    home = Path(os.environ.get("AI_EDITOR_HOME", "").strip() or Path.home() / ".ai-video-editor")
    try:
        target = json.loads((home / "profile.json").read_text(encoding="utf-8")).get("render")
    except (OSError, ValueError, AttributeError):
        target = None
    why = ("off (AI_EDITOR_NO_SPECULATE)" if os.environ.get("AI_EDITOR_NO_SPECULATE") else
           f"renders on {target}" if target not in (None, "", "laptop") else
           "no renderer" if not (home / "remotion" / "node_modules" / "remotion").exists() else
           "no plan" if not plan or not Path(plan).is_file() else
           "on battery" if on_battery() else None)
    if why:
        return why
    drop_spec(folder)
    (folder / "render.spec.started").write_text(str(time.time()), encoding="utf-8")
    subprocess.Popen([sys.executable, str(EDIT_PY), "render", str(folder), "--plan", Path(plan).name, "--speculative"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=os.name != "nt",
                     creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    return None


def noted(folder):
    """timings.json after each round, so the job's times are kept while the home window still lists the job."""
    try:
        t = timings(folder)
        if t.get("line"):
            print(t["line"])
    except Exception:   # a nicety: a round never fails over it
        pass


def stop_round(folder):
    """Stop: the round Claude has goes back to the user, its notes open again, and `status` tells Claude to stop.
    The review page's Stop and the home window's sidebar Stop (home.py /stop with an edit). Returns an error or None."""
    folder = Path(folder)
    rj = folder / "review.json"
    if load(rj).get("raw"):   # the first cut cannot be stopped from here
        return "The first cut is on its way."

    def st(d):
        last = d["events"][-1]["type"] if d["events"] else None
        # an approve (even the final one) can be taken back too: the draft opens for notes again
        if last == "approve" or d.get("sent") and (last in ("send", "edits") or making_edit(d)):
            e = d["events"][-1]
            for ev in d["events"]:   # a send or approve `wait` has not taken yet is taken back
                ev["handled"] = True
            # stop undoes the edits, but only over the files /edits wrote: never over Claude's later change
            if e["type"] == "edits" and e.get("sha") == files_sha(folder) and (folder / "spans.prev.json").exists():
                save(folder / "spans.json", load(folder / "spans.prev.json"))
                if (folder / "keep.prev.json").exists():
                    save(folder / "keep.json", load(folder / "keep.prev.json"))
            d["events"].append({"type": "stop", "stage": d["stage"], "round": d["round"],
                                "at": now(), "handled": True})
            d["sent"], d["stopped"] = False, now()
            for c in d["comments"]:   # notes queued meanwhile join the reopened round
                if c.pop("queued", None):
                    c["round"] = d["round"]
            for x in d.get("activity", []):
                x["done"] = True
    update(rj, st)
    drop_spec(folder)
    return None


def drop_spec(folder):
    """Stop the background render and remove its files: notes were sent, the plan changed, or another target."""
    folder = Path(folder)
    for meta in folder.glob("render*.spec.json"):
        try:
            pid = json.loads(meta.read_text(encoding="utf-8")).get("pid")
        except (OSError, ValueError):
            pid = None
        if pid and pid != os.getpid() and alive(pid):   # never itself: taskkill /T on Windows ended the caller (edit.py demo)
            try:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)
                else:
                    os.killpg(pid, 15)   # its own group: node and Chrome under it go too
            except OSError:
                pass
        stem = meta.name[:-len(".json")]
        for f in (meta, folder / f"{stem}.mp4", folder / f"{stem}.renderer.log", folder / f"{stem}.tmp.mkv"):
            f.unlink(missing_ok=True)
    (folder / "render.spec.started").unlink(missing_ok=True)


def making_style(folder):
    """What the edit is styled as, for the page's "Making the edit" card."""
    try:
        from ai_editor import styleskill
        src = styleskill.sources(folder)
    except Exception:
        src = []
    if len(src) == 1:   # the name the style has on the home page ("Card edit"), never the folder id
        try:
            n = shown_style(src[0])
        except Exception:
            n = "@" + re.sub(r"-mine$", "", src[0].parent.name)
        return f"{n}'s style" if n.startswith("@") else "your style" if n == "My style" else f"the {n} style"
    return "your blended style" if src else None   # not known yet (no style.json in the edit): the page names none


def cmd_final(folder):
    """The cut is the finished video ("just the cut"): Approve says so and the page waits for no edit."""
    update(folder / "review.json", lambda d: d.update(final=True))
    print("the cut is final: no styled edit follows")


def cmd_status(a, folder):
    """One step of what Claude is doing for the next round. Each new step closes the one before."""
    stopped = load(folder / "review.json").get("stopped")
    if stopped:
        print(f"STOPPED: the user pressed Stop on the page at {stopped}. Stop this round's work, say so in one "
              f"line, and run `wait` again: the notes are open for more.")
        sys.exit(3)
    key = getattr(a, "step", None)
    if not (a.text or key or a.done):
        sys.exit("status takes a text, --step or --done")
    update(folder / "review.json", lambda d: add_step(d, a.text, a.log, key, a.done))
    print("done" if a.done else f"status: {a.text or EDIT_STEPS[key]}")


def cmd_alt(a, folder):
    """Add (or replace) another video in this round: the other aspect, another clip."""
    def f(d):
        d["alts"] = [x for x in d.get("alts") or [] if x["name"] != a.name] + [
            {"name": a.name, "video": keep(folder, a.video, d["stage"], d["round"], a.name),
             "transcript": str(Path(a.transcript).resolve()) if a.transcript else None,
             **({"trial": True} if getattr(a, "trial", False) else {})}]
        log_round(d)
        return d
    d = update(folder / "review.json", f)
    print(f"round {d['round']}: {1 + len(d['alts'])} videos "
          f"({', '.join([d.get('label') or 'main'] + [x['name'] for x in d['alts']])})")


def cmd_wait(folder, poll=1.0):
    rj = folder / "review.json"
    beat = folder / "review" / ".listening"
    try:
        while True:
            beat.touch()
            # read only: a write here could drop a note the page saves in the same instant
            d0 = load(rj)
            if any(not e["handled"] for e in d0["events"]) or (d0.get("learn") or {}).get("handled") is False \
                    or (d0.get("trials") or {}).get("handled") is False:
                break
            time.sleep(poll)
    finally:
        beat.unlink(missing_ok=True)

    (folder / "review" / ".claude").touch()   # Claude has the send or approve now: working, not gone

    def take(d):
        ev = [e for e in d["events"] if not e["handled"]]
        for e in ev:
            e["handled"] = True
        if not ev and (d.get("trials") or {}).get("handled") is False:   # the Trial reels tab: Make, Skip or a question
            d["trials"]["handled"] = True
            return "trials", d
        if not ev:   # the user answered the learn panel
            d["learn"]["handled"] = True
        return ev, d
    ev, d = update(rj, take)
    if ev == "trials":
        return trials_chosen(folder, d)
    if not ev:
        return learn_chosen(folder, d)
    e = ev[-1]
    r = next((r for r in d.get("rounds", []) if (r["stage"], r["round"]) == (e["stage"], e["round"])), d)
    cs = sorted((c for c in d["comments"] if c["stage"] == e["stage"] and c["round"] == e["round"]), key=lambda c: c["t"])
    for x in ev:   # an Apply then a send: the edits still have to be built
        if x["type"] == "edits":
            print(edits_text(folder, x))
    print(f"{'SEND' if e['type'] == 'edits' else e['type'].upper()}: {d['name']} {stage_name(e['stage'], e.get('stills'))}, round {e['round']}, "
          f"{len(cs)} note{'' if len(cs) == 1 else 's'}. video {r['video']}")
    for x in r.get("alts") or []:
        print(f"  also {x['name']}: {x['video']}")
    if r.get("back_to"):
        print(f"  this round is round {r['back_to']} again: the user pressed Go back, which put that round's files "
              f"(plan.json, spans.json, visuals.json, ...) and its render back. Fix from these files.")
    for c in cs:
        span = fmt(c["t"]) + (f"-{fmt(c['t_end'])}" if c["t_end"] is not None else "")
        ver = " [all videos]" if c.get("alt") == "*" else f" [{c['alt']}]" if c.get("alt") else (
            f" [{r.get('label') or 'main'}]" if r.get("alts") else "")
        k = c.get("card")
        card = f" [card {k['i']} {k['kind']} '{k['trigger_word'] or ''}']" if k else ""
        card += on_screen(r.get("plan") or d.get("plan"), c["t"]) if e["stage"] == "edit" else ""
        keep = f" [keep as a rule for {style_label(folder)}]" if c.get("keep") else ""
        keep += f" [add text: {c['add_text']['style']}]" if c.get("add_text") else ""
        print(f"#{c['id']} {span} ({c['t']}s){ver}{card}: {c['text']}{keep}\n    said: \"{c['words']}\""
              f"\n    frame: {folder / 'review' / c['frame']}"
              + "".join(f"\n    image: {folder / 'review' / x}" for x in c.get("images") or []))
    typed = put_texts(folder, cs)
    if typed:
        print(f"texts: {folder / 'texts.json'} ({typed} on-screen text{'' if typed == 1 else 's'} the user typed with the Text tool, "
              "the notes marked [add text]. plan.py puts every one in plan.json as typed: plan again and render. "
              "Never reword, restyle or move them; a later note about one edits its row in texts.json.)")
    added = assets.load(folder)
    if added:   # New video's "Add images or links" and the editor's "Anything to add?": they go in first
        print(f"assets: {folder / 'assets.json'} ({len(added)} video{'' if len(added) == 1 else 's'}, image{'' if len(added) == 1 else 's'} "
              f"or link{'' if len(added) == 1 else 's'} the user added. "
              "Each one goes in first, as a card on its say words (a video as a video_card), before anything searched; one "
              "not in images.json or visuals.json yet is new.)")
    if e["type"] == "approve" and d.get("learn"):
        print(learn_prompt(folder, d))
        if d.get("vertical") and not d.get("trials"):   # a finished reel: offer re-cuts for trial reels
            print(f"TRIALS: a reel. Offer trial reels on the page's Trial reels tab (the trial-reels skill): find spare hooks (a retake of the "
                  f"opener, a strong later line), plan 2-4 versions that each look like a different video, then\n"
                  f"  python3 {Path(__file__).resolve()} {folder} trials --propose '<json>'   and `wait` for the pick.")
    elif cs:
        print(learn_hint(folder, [c["id"] for c in cs if c.get("keep")]))
    return e["type"]


def edits_text(folder, e):
    """What `wait` prints for the transcript editor's Apply: the line Claude acts on, the words, the commands."""
    try:
        words = [w for w in load(folder / "words.raw.json") if w.get("type", "word") == "word" and "start" in w]
    except (OSError, ValueError):
        words = []
    said = lambda a, b: " ".join(w["text"].strip() for w in words if a - 1e-3 <= (w["start"] + w["end"]) / 2 <= b + 1e-3
                                 or w["start"] <= a and b <= w["end"])   # apply_edits' rule
    try:
        src = load(folder / "report.json")["source"]
    except (OSError, ValueError, KeyError):
        src = "<source>"
    cut = Path(__file__).resolve().parents[2] / "skills" / "cut" / "scripts"
    rows = [f"EDITS {e['n']} transcript edit{'' if e['n'] == 1 else 's'} applied to spans.json: rebuild, render, verify, round",
            f"  {e['counts']['restored']} word(s) restored, {e['counts']['cut']} cut (kind manual); the spans before are in {folder / 'spans.prev.json'}"]
    rows += [f"  restore {a:.2f}-{b:.2f}s: \"{said(a, b)}\"" for a, b in e["restore"]]
    rows += [f"  cut {a:.2f}-{b:.2f}s: \"{said(a, b)}\"" for a, b in e["cut"]]
    rows += [f"  pause back {a:.2f}-{b:.2f}s" for a, b in e.get("pause") or []]
    if e["counts"].get("keep"):
        rows.append(f"  keep.json: {e['counts']['keep']} range(s) the pause trim leaves in (build_timeline.py reads it)")
    q = (lambda x: subprocess.list2cmdline([str(x)])) if os.name == "nt" else (lambda x: shlex.quote(str(x)))
    rows.append(f"  then: python3 {q(cut / 'build_timeline.py')} {q(src)} {q(folder)}; python3 {q(cut / 'render.py')} {q(src)} {q(folder)}; "
                f"verify_cut.py; python3 {q(Path(__file__).resolve())} {q(folder)} round --video {q(folder / 'cut.mp4')}")
    return "\n".join(rows)


def session_notes(d):
    return [c for c in d["comments"] if c.get("text") and not c.get("queued")]


def shown_style(sp):
    """A style's name as the user reads it (the home page's): the name they gave, else its own; a format analysed
    from links and never named is "New format", never its folder id. The skill file name stays the slug."""
    from ai_editor import styleskill
    n = styleskill.display(sp)
    return "New format" if n.startswith("@links-") else n


def style_choices(folder):
    """The learn panel's Save to list: this video's style first, then every saved style, each with its rule count.
    id is the style.json path ("" = My style)."""
    try:
        from ai_editor import styleskill
        here = edit_style(folder)
        key = lambda sp: str(Path(sp).resolve()) if sp else ""
        out, seen = [], set()
        for sp in [here] + [x for x, _ in styleskill.saved()]:
            if key(sp) in seen:
                continue
            seen.add(key(sp))
            try:
                n = len(styleskill.learned(styleskill.scope(sp)))
            except Exception:
                n = 0
            out.append({"id": key(sp), "name": shown_style(sp), "rules": n, "here": sp is here, "mine": sp is None})
        return out
    except Exception:
        return [{"id": "", "name": "My style", "rules": 0, "here": True, "mine": True}]


def new_style_from(folder, name):
    """"New style from this video": a copy of the style the edit used (home.new_own_style, own: true), named.
    Returns the Save to entry for it. ValueError when the name is empty or taken."""
    import library
    from home import new_own_style
    name = " ".join(str(name or "").split())[:40]
    if not name:
        raise ValueError("Give the new style a name.")
    sp = edit_style(folder)
    try:
        start = json.loads(Path(sp).read_text(encoding="utf-8")) if sp else None
    except (OSError, ValueError):
        start = None
    if start:
        start = {k: v for k, v in start.items() if k not in ("handle", "own", "name")}
    sid = new_own_style(library.path(), name, start=start)
    p = library.path() / "creator-teardowns" / sid.lstrip("@") / "style.json"
    return {"id": str(p.resolve()), "name": name, "rules": 0, "here": False, "mine": False, "new": True}


def style_label(folder):
    """What the learn panel calls the style the edit used: its name on the home page, else My style."""
    try:
        from ai_editor import styleskill
        return shown_style(edit_style(folder))
    except Exception:
        return "My style"


def download_name(folder, d=None):
    """What the finished video is saved as: "<video name> - <style name>.mp4" ("<video name>.mp4" for a cut).
    A slash in a name becomes a dash ("50/50" saves as "50-50"); other characters a file name cannot hold go."""
    d = d or load(folder / "review.json")
    base = d.get("name") or folder.name
    if d.get("stage") == "edit":
        base += " - " + style_label(folder)
    return (re.sub(r'[\\:*?"<>|\x00-\x1f]', "", base.replace("/", "-")).strip() or "video") + ".mp4"


def disposition(name):
    """A Content-Disposition that keeps spaces and accents in the saved name (RFC 6266), with a plain fallback."""
    plain = name.encode("ascii", "ignore").decode().replace('"', "").replace("\\", "") or "video.mp4"
    return f"attachment; filename=\"{plain}\"; filename*=UTF-8''{quote(name)}"


def learn_prompt(folder, d):
    """The final approve: Claude turns the whole session's notes into rules the page offers with checkboxes."""
    if d["learn"]["state"] == "none":
        return "LEARN: no notes this session, so nothing to learn. The page says so; say nothing about it."
    st = d["learn"]["style"]
    lines = [f"LEARN: the video is approved. Turn this session's notes and your replies (below) into at most 6 "
             f"one-line rules for how {st} edits next time, e.g. \"Captions one size smaller\", \"Fewer zooms in the "
             f"first 5 s\". Leave out one-off fixes (a word cut at 0:12) and notes already saved as rules. Post them "
             f"([] when none is about the style); the page shows them with checkboxes:",
             f"  python3 {Path(__file__).resolve()} {folder} learn --propose "
             f"'[{{\"rule\": \"...\", \"section\": \"cut|captions|visuals|sound|layout\", \"set\": \"captions.size_pct=4.5\"}}]'",
             "  (or a path to a .json file holding that list). \"set\" only when a taste setting maps (the taste "
             "skill's table). Then run `wait` again: it returns with the rules the user ticked. The skill-improver "
             "skill has the steps (one-offs stay with the video, sharpen an old rule rather than add a twin)."]
    try:
        from ai_editor import skillrules
        tg = skillrules.target(folder)
    except Exception:
        tg = {"kind": "settings"}
    if tg["kind"] == "skill":
        lines.append(f"This style runs the {tg['skill']} skill: rules go into "
                     + (f"{tg['path']} under \"## Learned rules\". Give each a \"why\" (the reason, one line); "
                        "to sharpen or overrule one already there, add \"replace\": \"<its rule>\". Rules there now:"
                        if tg["path"] else "its SKILL.md, which is not in your skill folders: say so and propose [].")
                     )
        if tg["path"]:
            lines += ["  " + ln for ln in skillrules.learned(Path(tg["path"]).read_text(encoding="utf-8"))] or ["  (none yet)"]
    for c in sorted(session_notes(d), key=lambda c: (c["stage"] != "cut", c["round"], c["t"])):
        saved = f" [saved as rule {c['taste']}]" if isinstance(c.get("taste"), int) else ""
        keep = " [the user asked to keep this as a rule: propose it]" if c.get("keep") and not saved else ""
        lines.append(f"#{c['id']} {stage_name(c['stage'])} r{c['round']}: {c['text']}"
                     + (f" -> reply: {c['reply']}" if c.get("reply") else "") + saved + keep)
    return "\n".join(lines)


def learn_chosen(folder, d):
    lr = d["learn"]
    if lr["state"] == "skipped":
        print("LEARN: the user pressed Not now. Nothing is saved; say nothing more about it.")
        return "learn"
    rules = [lr["rules"][i] for i in lr["chosen"]]
    to = lr.get("to")
    if to and not to.get("here"):   # Save to: learn --done saves them there
        lr = {**lr, "style": to["name"] + (f" (a new style, a copy of {lr['style']})" if to.get("new") else "")}
    print(f"LEARN: the user ticked {len(rules)} rule{'s' if len(rules) != 1 else ''} for {lr['style']}:")
    for r in rules:
        print(f"  - [{r['section']}] {r['rule']}" + (f" ({r['set']})" if r.get("set") else ""))
    print(f"Save them (styleskill.learn: the style's overrides, rules and skill) and tell the page:\n"
          f"  python3 {Path(__file__).resolve()} {folder} learn --done")
    return "learn"


SECTIONS = ("cut", "captions", "visuals", "sound", "layout")


def learn_propose(folder, raw):
    """Claude's candidate rules onto the page's learn panel."""
    try:
        f = Path(raw)
        rules = json.loads(f.read_text(encoding="utf-8") if raw.endswith(".json") and f.is_file() else raw)
    except (OSError, ValueError) as e:
        sys.exit(f"--propose takes a JSON list: {e}")
    if not isinstance(rules, list):
        sys.exit("--propose takes a JSON list")
    out = []
    for r in rules[:8]:
        if not isinstance(r, dict) or not str(r.get("rule", "")).strip():
            sys.exit(f"each rule needs a \"rule\": {r}")
        sec = str(r.get("section", "")).lower()
        if sec not in SECTIONS:
            sys.exit(f"section must be one of {', '.join(SECTIONS)}: {r}")
        st = r.get("set") or None
        if st is not None and (not isinstance(st, str) or "=" not in st):
            sys.exit(f"\"set\" is key.path=value: {r}")
        out.append({"rule": str(r["rule"]).strip().rstrip("."), "section": sec, "set": st,
                    **{k: str(r[k]).strip() for k in ("why", "replace") if r.get(k)}})

    def f(d):
        if not d.get("learn"):
            sys.exit("learn --propose comes after the final approve")
        d["learn"].update(state="proposed" if out else "empty", rules=out, chosen=[], handled=None)
    update(folder / "review.json", f)
    print(f"{len(out)} rule{'s' if len(out) != 1 else ''} on the page" + ("; run `wait` for the user's pick" if out else ""))


def learn_done(folder, summary):
    """Save the ticked rules into the edit's style (one creator style, else My style) and show it on the page."""
    from ai_editor import styleskill, taste
    lr = load(folder / "review.json").get("learn") or {}
    if lr.get("state") != "chosen":
        sys.exit("nothing ticked to save: run `wait` for the user's pick first")
    sp = edit_style(folder)
    style = shown_style(sp)
    from ai_editor import skillrules
    tg = skillrules.target(folder)
    to = lr.get("to")
    if to and not to.get("here"):   # Save to: another saved style, or a new one made from this video's style
        sp = Path(to["id"]) if to["id"] else None
        style, tg = to["name"], {"kind": "settings"}
    saved = []   # (rule, status, kind, ref) for the receipts
    if tg["kind"] == "skill":   # a skill style: its skill made the edit, so the rules go into its SKILL.md
        if not tg["path"]:
            sys.exit(f"the {tg['skill']} skill is not in your skill folders; nothing saved")
        for r in (lr["rules"][i] for i in lr["chosen"]):
            status, line = skillrules.add(tg["path"], r["rule"], r.get("why") or f"from the notes on {folder.name}",
                                          r.get("replace"), edit=str(folder))
            saved.append((skillrules.rule_of(line), status, "skill", tg["path"]))
            print(f"{status}: {line} ({tg['path']})")
    for r in (lr["rules"][i] for i in lr["chosen"] if tg["kind"] == "settings"):
        setting, _, raw = (r.get("set") or "").partition("=")
        status, x = styleskill.learn(sp, r["section"], r["rule"], setting or None, taste.parse(raw) if setting else None,
                                     edit=folder, source="review")
        saved.append((x["rule"], status, "settings", x["id"]))
        print(f"{status} rule #{x['id']} {x['section']}: {x['rule']} (skill {styleskill.name(sp)})")

    def done(d):
        d["learn"].update(state="done", style=style, summary=summary or f"Saved to {style}. Next video uses it.",
                          receipts=[receipt(d, style, *x, src="teach")["id"] for x in saved])
    update(folder / "review.json", done)
    print(f"saved to {style}")


def edit_style(folder):
    """The one creator style.json this edit used (styleskill.sources), else None."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from ai_editor import styleskill
    src = styleskill.sources(folder)
    return src[0] if len(src) == 1 else None


def learn_hint(folder, kept=()):
    """After a send: only the notes the user ticked "Keep as a rule" become rules, saved with no question (QA round 4:
    an unticked note was asked about, by its style's folder id)."""
    sp = edit_style(folder)
    if not kept:
        return ("LEARN: no note is ticked \"Keep as a rule\", so none becomes a rule. Ask nothing about rules or scope; run:\n"
                f"  python3 {Path(__file__).resolve()} {folder} learn --none")
    return (f"LEARN: notes {', '.join('#' + str(i) for i in kept)} are ticked \"keep as a rule for {style_label(folder)}\": the user"
            f" said yes on the page. Save each with --scope {'this-style' if sp else 'style'} (no question), one short rule"
            " in the user's words with its setting when the taste table maps (\"fewer zooms\" -> zoom.per_min); the page"
            " then shows a receipt with Undo. Every other note is a one-off fix: no rule, no question. Run:\n"
            f"  python3 {Path(__file__).resolve()} {folder} learn --scope {'this-style' if sp else 'style'}"
            f" --rule <id> <section> \"<rule>\" [key=value] ...\n"
            f"  Call the style {style_label(folder)} when you mention it, never by its folder or @id.")


def learned_round(d):
    """The round `wait` last handed over: the one `learn` acts on."""
    e = next((e for e in reversed(d["events"]) if e["handled"] and e["type"] != "stop"), None)
    return (e["stage"], e["round"]) if e else (d["stage"], d["round"])


TRIAL_KINDS = {"hooks": "New hooks", "same": "Same order", "rewind": "Rewind", "section": "One section",
               "animations": "New animations"}


def trial_kinds(k):
    """One version's kinds: ["claude"] (Claude decides) or some of TRIAL_KINDS. Same order and rewind both set the order."""
    if k in ("claude", ["claude"]):
        return ["claude"]
    if not isinstance(k, list) or not k or any(x not in TRIAL_KINDS for x in k):
        raise ValueError(f"kinds is \"claude\" or a list of {', '.join(TRIAL_KINDS)}: {k}")
    if "same" in k and "rewind" in k:
        raise ValueError("same and rewind both set the order: pick one")
    return [x for x in TRIAL_KINDS if x in k]


def trials_propose(folder, raw):
    """Claude's trial reel plan onto the page's Trial reels tab: its message, the spare hooks it found, one row per
    version (kinds + the one line saying what Claude picked), and an optional reply to the user's last question."""
    try:
        f = Path(raw)
        p = json.loads(f.read_text(encoding="utf-8") if raw.endswith(".json") and f.is_file() else raw)
        if not isinstance(p, dict) or not isinstance(p.get("versions"), list) or not p["versions"]:
            raise ValueError("needs \"versions\": [...]")
        vs = [{"kinds": trial_kinds(v.get("kinds")), "line": str(v.get("line") or "").strip()} for v in p["versions"][:8]]
        hooks = [{"text": str(h["text"]).strip(), "from": str(h.get("from") or "").strip()} for h in p.get("hooks") or []][:6]
        idea = p.get("idea")
        if idea:
            idea = {"kinds": trial_kinds(idea.get("kinds")), "line": str(idea.get("line") or "").strip()}
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as e:
        sys.exit(f"--propose takes a JSON object {{message, hooks: [{{text, from}}], versions: [{{kinds, line}}], idea?, reply?}}: {e}")

    def f(d):
        t = d.get("trials") or {"asks": []}
        if p.get("reply"):
            for q in reversed(t["asks"]):
                if not q.get("reply"):
                    q["reply"] = str(p["reply"]).strip()
                    break
        t.update(state="proposed", message=str(p.get("message") or "").strip(), hooks=hooks, versions=vs,
                 idea=idea or None, v=t.get("v", 0) + 1, handled=None)
        d["trials"] = t
    update(folder / "review.json", f)
    print(f"{len(vs)} trial reel{'s' if len(vs) != 1 else ''} on the page; run `wait` for the user's pick")


def trials_reply(folder, text):
    """Claude's answer to the notes on the made trial reels: on every note not answered yet, shown under them."""
    text = str(text or "").strip()
    if not text:
        sys.exit("--reply takes the words to show")

    def f(d):
        ns = [x for x in (d.get("trials") or {}).get("notes") or [] if "reply" not in x]
        if not ns:
            sys.exit("no trial reel notes to answer")
        for x in ns:
            x["reply"] = ""
        ns[-1]["reply"] = text
    update(folder / "review.json", f)
    print("reply on the Trial reels tab")


def trials_chosen(folder, d):
    """What `wait` prints for the Trial reels tab: Make, Skip, or a question for Claude."""
    t, me = d["trials"], f"python3 {Path(__file__).resolve()} {folder}"
    if t["state"] == "skipped":
        print("TRIALS: the user pressed Skip trial reels. Make none; say nothing more about it.")
    elif t["state"] == "chosen" and any("reply" not in x for x in t.get("notes") or []):   # notes on the made trials
        print("TRIALS NOTE: the user's notes on the trial reels:")
        for x in (x for x in t["notes"] if "reply" not in x):
            print(f"  {'all of them' if x['for'] == 'all' else x['for']}" + (f" at {x['t']:.1f}s" if x.get("t") is not None else "")
                  + f": {x['text']}")
        print(f"Change those versions (the trial-reels skill), render each again and put it back under the same name:\n"
              f"  {me} alt t1 --video <t1.mp4> --trial\nThen answer on the tab, one or two lines on what changed:\n"
              f"  {me} trials --reply \"...\"   and `wait` again. A note about how every trial reel should be is taste "
              f"(the taste skill) too.")
    elif t["state"] == "proposed":   # a question from the Ask Claude box
        print(f"TRIALS ASK: {t['asks'][-1]['text']}\nAnswer on the page: {me} trials --propose '<json>' with the "
              f"updated plan and \"reply\": one or two lines on what you changed. Then `wait` again.")
    else:
        pk = t["picks"]
        print(f"TRIALS: make {len(pk['versions'])} trial reel{'s' if len(pk['versions']) != 1 else ''}. Each must look like "
              "a different video: a new length, new animations or new words.")
        for i, v in enumerate(pk["versions"]):
            ks = "Claude decides" if v["kinds"] == ["claude"] else " + ".join(TRIAL_KINDS[k] for k in v["kinds"])
            print(f"  t{i + 1}: {ks}" + (f" ({v['line']})" if v.get("line") else ""))
        hs = [t["hooks"][i]["text"] for i in pk["hooks"] if i < len(t["hooks"])]
        if hs:
            print("  spare hooks to use: " + "; ".join(f'"{h}"' for h in hs))
        print(f"Follow the trial-reels skill (the type first, then versions that look different). You pick the lines, "
              f"sections, hooks and overlays. Put each render on the page as it lands:\n"
              f"  {me} alt t1 --video <t1.mp4> --trial")
    return "trials"


def cmd_learn(a, folder):
    """Review notes into the user's taste: each --rule note saved with taste.add (scope asked once for the
    batch), every other note of the round marked one-off, and each note records what happened to it."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    if getattr(a, "propose", None) is not None:
        return learn_propose(folder, a.propose)
    if getattr(a, "done", None) is not None:
        return learn_done(folder, a.done)
    from ai_editor import taste
    rules = {}
    for r in a.rule or []:
        if len(r) not in (3, 4) or not r[0].isdigit() or (len(r) == 4 and "=" not in r[3]):
            sys.exit(f"--rule takes <id> <section> \"<rule>\" [key=value], got {r}")
        rules[int(r[0])] = r[1:]
    if not rules and not a.none:
        sys.exit("give --rule for each preference note, or --none")
    if rules and not a.scope:
        sys.exit("--scope this-style|style|video|everyone: ask the user once for the batch")
    from ai_editor import styleskill
    sp = None
    if a.scope == "this-style":
        src = styleskill.sources(getattr(a, "style", None) or folder)
        if len(src) != 1:
            sys.exit("--scope this-style: " + ("this edit used no creator style" if not src else "this edit blends several creators")
                     + "; pass --style creator-teardowns/<handle>/style.json, or use --scope style")
        sp = src[0]
    skill_md = None   # a skill style ("skill" in its style.json): rules go into that skill's own SKILL.md
    if sp is not None:
        from ai_editor import skillrules
        sk = (json.loads(Path(sp).read_text(encoding="utf-8") or "{}") or {}).get("skill")
        if sk:
            skill_md = skillrules.find_skill(sk)
            if not skill_md:
                sys.exit(f"the {sk} skill is not in your skill folders; nothing saved")

    def f(d):
        stage, rnd = learned_round(d)
        known = {c["id"]: c for c in d["comments"]}
        if set(rules) - set(known):
            sys.exit(f"no note {', '.join(map(str, sorted(set(rules) - set(known))))}")
        out = []
        for c in d["comments"]:
            if c["id"] in rules:
                section, rule, *kv = rules[c["id"]]
                setting, _, raw = kv[0].partition("=") if kv else (None, "", "")
                value = taste.parse(raw) if setting else None
                if skill_md:
                    status, line = skillrules.add(skill_md, rule, f"review note: {c['text']}", edit=str(folder))
                    c.update(rule=rule, taste="skill",
                             receipt=receipt(d, shown_style(sp), skillrules.rule_of(line), status, "skill", str(skill_md), c["id"])["id"])
                    out.append(f"#{c['id']} -> {status}: {line} ({skill_md})"
                               + (f"; {setting} not saved (a skill style has no settings)" if setting else ""))
                    continue
                scope = f"video:{d['name']}" if a.scope == "video" else styleskill.scope(sp)
                status, r = taste.add(section, rule, setting, value, scope, folder, source="review", style=sp)
                c.update(rule=rule, taste={"style": r["id"], "this-style": r["id"], "video": "video-only"}.get(a.scope, "suggested"))
                if a.scope != "video":
                    c["receipt"] = receipt(d, shown_style(sp), r["rule"], status, "settings", r["id"], c["id"])["id"]
                if a.scope == "everyone":
                    taste.suggest(c["text"], rule, f"review note ({r['section']})", note=f"{d['name']}#{c['id']}")
                out.append(f"#{c['id']} -> {status} rule #{r['id']} {r['section']}: {rule}"
                           + {"video": " (this video only)", "everyone": " (+ suggested to everyone)",
                              "this-style": f" (this style, skill {styleskill.name(sp)})",
                              "style": " (every video, skill my-style)"}[a.scope])
            elif (c["stage"], c["round"]) == (stage, rnd) and "taste" not in c:
                c["taste"] = "one-off"
        return out
    for line in update(folder / "review.json", f) or ["no preference notes: all marked one-off"]:
        print(line)


def _post_code(url, body):
    """The HTTP status of a POST (the demo's concurrency and refusal checks)."""
    try:
        return urllib.request.urlopen(urllib.request.Request(url, json.dumps(body).encode(), method="POST")).status
    except urllib.error.HTTPError as err:
        return err.code


def demo_timings(tmp):
    """timings.json from the home job and review.json, and the background render's guards."""
    f = tmp / "timed"
    f.mkdir()
    at = lambda s: time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(1_800_000_000 + s))
    home = Path(os.environ["AI_EDITOR_HOME"]) / "home"
    home.mkdir(parents=True, exist_ok=True)
    job = {"type": "video", "state": "done", "at": at(0), "args": {"edit": str(f), "added": 1_800_000_000 - 30},
           "steps": [{"text": "Writing down every word", "t": 1_800_000_002}, {"text": "Finding retakes and pauses", "t": 1_800_000_040}]}
    (home / "state.json").write_text(json.dumps({"jobs": [job]}), encoding="utf-8")
    save(f / "review.json", {"rounds": [{"stage": "cut", "round": 0, "at": at(0)}, {"stage": "cut", "round": 1, "at": at(190)},
                                        {"stage": "edit", "round": 1, "at": at(400), "stills": True},
                                        {"stage": "edit", "round": 2, "at": at(560)}],
                             "events": [{"type": "approve", "stage": "cut", "round": 1, "at": at(300)},
                                        {"type": "approve", "stage": "edit", "round": 1, "at": at(500), "stills": True}],
                             "activity": [{"step": "render", "at": at(505)}]})
    t = timings(f)
    assert t["stages"] == {"cut": 190, "your_review": 110, "edit": 100, "your_stills_check": 100, "render": 60, "transcribe": 38}, t
    assert t["line"] == "Made in 6 min (cut 3:10, edit 1:40, render 1:00)" and t["added"] == 1_800_000_000 - 30, t["line"]
    (home / "state.json").write_text(json.dumps({"jobs": []}), encoding="utf-8")   # the job left the window's list
    assert timings(f)["transcribe_start"] == 1_800_000_002, "times kept from the earlier write"
    save(f / "review.json", {"rounds": [{"stage": "cut", "round": 1, "at": at(190)}], "events": []})
    t = timings(f)
    assert "line" not in t and set(t["stages"]) == {"cut", "transcribe"}, "a stage shows once it has happened"
    # QA round 3: "render 9:05", 8 min of it a question; and an earlier draft of the stills waiting on the user's notes
    save(f / "review.json", {"rounds": [{"stage": "cut", "round": 1, "at": at(190)}, {"stage": "edit", "round": 1, "at": at(400), "stills": True},
                                        {"stage": "edit", "round": 2, "at": at(700), "stills": True}, {"stage": "edit", "round": 3, "at": at(1300)}],
                             "events": [{"type": "approve", "stage": "cut", "round": 1, "at": at(300)},
                                        {"type": "send", "stage": "edit", "round": 1, "at": at(550)},
                                        {"type": "approve", "stage": "edit", "round": 2, "at": at(760), "stills": True}]})
    (f / "review").mkdir(exist_ok=True)
    (f / "review" / "asks.jsonl").write_text(json.dumps({"start": 1_800_000_800, "end": 1_800_001_280}) + "\n", encoding="utf-8")
    t = timings(f)
    assert t["stages"]["render"] == 60 and t["stages"]["edit"] == 250 and t["waits_s"] == 110 + 150 + 60 + 480, t["stages"]
    assert t["line"] == "Made in 8 min (cut 3:10, edit 4:10, render 1:00)", t["line"]
    assert mmss(70) == "1:10" and mmss(5) == "0:05"
    assert speculate(f, None) == "no renderer", "no renderer installed: nothing starts"
    os.environ["AI_EDITOR_NO_SPECULATE"] = "1"
    assert speculate(f, None).startswith("off")
    del os.environ["AI_EDITOR_NO_SPECULATE"]
    (f / "render.spec.json").write_text(json.dumps({"pid": 999999999}), encoding="utf-8")
    (f / "render.spec.mp4").write_bytes(b"x")
    drop_spec(f)
    assert not list(f.glob("render.spec*")), "drop_spec leaves nothing behind"


def demo_bake(tmp):
    """bake: the typed texts go into plan.json and the draft by a patch render (faked here), with no Claude."""
    f = tmp / "bake"
    (f / "review" / "snap-edit1").mkdir(parents=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=64x36:r=30:d=2", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", str(f / "render.mp4")], check=True)
    plan = {"fps": 30, "durationInFrames": 60, "width": 64, "height": 36, "texts": [{"kind": "title", "text": "T", "start": 0, "end": 1}]}
    for p in (f / "plan.json", f / "render.plan.json", f / "review" / "snap-edit1" / "plan.json"):
        p.write_text(json.dumps(plan), encoding="utf-8")
    clone(f / "render.mp4", f / "review" / "v-edit1.mp4")
    save(f / "review.json", {"stage": "edit", "round": 1, "sent": False, "stills": False, "events": [], "comments": [],
                             "plan": str(f / "plan.json"), "snap": "snap-edit1", "video": str(f / "review" / "v-edit1.mp4")})
    (f / "texts.json").write_text(json.dumps({"items": [{"id": "t1", "text": "hi", "style": "box", "start": 0.5, "end": 1.5,
                                                         "x_pct": 50, "y_pct": 30, "size_pct": 8}]}), encoding="utf-8")
    d = load(f / "review.json")
    stamp = lambda: (f / "render.stamp.json").write_text(json.dumps({"size": (f / "render.mp4").stat().st_size,
                                                                     "mtime_ns": (f / "render.mp4").stat().st_mtime_ns}), encoding="utf-8")
    assert bake_ready(f, d) == "the render was finished by hand", "no stamp: never patched over"
    assert bake(f) == "the render was finished by hand" and BAKE[str(f)]["state"] == "off"
    stamp()
    assert baked_texts(f, d) == [] and bake_ready(f, d) is None, bake_ready(f, d)
    ran = []

    def fake(cmd, **k):   # the patch render: blue frames
        ran.append(cmd[2:])
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:s=64x36:r=30:d=2", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", str(f / "render.mp4")], check=True)
        shutil.copy2(f / "plan.json", f / "render.plan.json")
        stamp()
        return subprocess.CompletedProcess(cmd, 0, "", "")
    (f / "overrides.json").write_text(json.dumps({"cards": {"repo@0.500": {"box": [5, 10, 40, 20], "start": 0.8, "end": 1.9}}}), encoding="utf-8")
    p = load(f / "plan.json")
    p["cards"] = [{"start": 0.5, "end": 1.5, "trigger_word": "repo", "box": [30, 60, 40, 20]}]
    (f / "plan.json").write_text(json.dumps(p), encoding="utf-8")
    assert bake(f, run=fake) is None and ran == [["patch", str(f), "--plan", "plan.json"]], ran
    c = load(f / "plan.json")["cards"][0]
    assert (c["box"], c["start"], c["end"]) == ([5, 10, 40, 20], 0.8, 1.9), "the moved and retimed card is baked in"
    p = load(f / "plan.json")
    assert [x["kind"] for x in p["texts"]] == ["title", "label"] and p["texts"][1]["size_pct"] == 8, p["texts"]
    d = load(f / "review.json")
    assert d["baked"] == 1 and baked_texts(f, d) == ["t1"] and BAKE[str(f)]["state"] == "done", d
    assert filecmp.cmp(f / "render.mp4", d["video"], shallow=False), "the round's video is the patched render"
    update(f / "review.json", lambda d: d.update(sent=True))
    assert bake(f, run=fake) == "Claude has this draft" and len(ran) == 1


def demo():
    import contextlib
    import io
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="review_demo_"))
    os.environ["AI_EDITOR_HOME"] = str(tmp / "home")   # start records the folder in the library index there
    demo_timings(tmp)
    demo_bake(tmp)
    # notes sent with no Claude on the edit: a new one opens in the library to carry on; never twice, never over a listener
    import launcher
    opened = []
    launcher.open_claude = lambda folder, prompt, session=None, resume=False: (
        opened.append((folder, prompt, resume)) or True, "claude '" + prompt + "'")
    typed, keep_type = [], launcher.type_into
    launcher.type_into = lambda tty, text: typed.append((tty, text)) or tty == "/dev/ttys-open"
    rf = tmp / "lib" / "edits" / "solo"
    (rf / "review").mkdir(parents=True)
    save(rf / "review.json", {})
    r0 = reopen(rf, rf / "review.json")
    assert r0["opened"] and r0["how"] == "new" and opened == [(tmp / "lib", "/ai-editor:start carry on edits/solo", False)]
    assert re.fullmatch(r"cd \S+ && claude --resume [0-9a-f-]{36}", r0["resume"]) and r0["session"] in r0["resume"], r0
    assert reopen(rf, rf / "review.json") is None and len(opened) == 1, "one per 15 min"
    (rf / "review" / ".listening").touch()
    assert reopen(rf, rf / "review.json", force=True) is None, "a listening Claude takes the notes"
    (rf / "review" / ".listening").unlink()
    (rf / "review" / ".claude").touch()
    update(rf / "review.json", lambda d: d.pop("claude"))
    assert reopen(rf, rf / "review.json") is None and reopen(rf, rf / "review.json", force=True) and len(opened) == 2, "busy: only the button"
    # the Claude that worked here goes first: open in a Terminal tab, the prompt is typed there; closed, it resumes
    me = {"pid": os.getpid(), "tty": "/dev/ttys-open", "app": "Terminal", "cwd": str(tmp), "session": "s-1"}
    keep_alive = globals()["claude_alive"]
    globals()["claude_alive"] = lambda w: w.get("pid") == os.getpid()
    (rf / "review" / ".claude").write_text(json.dumps(me), encoding="utf-8")
    r1 = reopen(rf, rf / "review.json", force=True)
    assert r1["how"] == "typed" and typed[-1] == ("/dev/ttys-open", "/ai-editor:start carry on edits/solo") and len(opened) == 2, r1
    assert r1["resume"] == f"cd {shlex.quote(str(tmp))} && claude --resume s-1", r1
    (rf / "review" / ".claude").write_text(json.dumps({**me, "pid": 999999999}), encoding="utf-8")
    r2 = reopen(rf, rf / "review.json", force=True)
    assert r2["how"] == "resumed" and opened[-1] == (tmp, "/ai-editor:start carry on edits/solo", True), (r2, opened[-1])
    (rf / "review" / ".claude").write_text(json.dumps({**me, "app": "Cursor"}), encoding="utf-8")
    assert reopen(rf, rf / "review.json", force=True)["how"] == "new", "open in an app that cannot be typed into: a new one"
    globals()["claude_alive"], launcher.type_into = keep_alive, keep_type
    w = who_claude()   # this demo's own process tree: a `claude` above it only when Claude Code runs it
    assert not w or (w["pid"] and "session" in w), w
    # a page no session owns takes only questions with no session: another project's Claude never asks there
    assert asker(rf, "")("sess-other") is None and asker(rf, "")("") == "solo"
    # the skills on a video: ran (the last one now while it is made), then the style's and chained ones still to run
    ve = tmp / "edits" / "sk"
    (ve / "review").mkdir(parents=True)
    (ve / "review" / "skills.jsonl").write_text("".join(json.dumps({"skill": k, "at": time.time()}) + "\n" for k in ("ai-editor:cut", "my-broll")), encoding="utf-8")
    sf = tmp / "home" / "home" / "state.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    old = sf.read_bytes() if sf.exists() else None
    sf.write_text(json.dumps({"jobs": [{"type": "video", "state": "taken", "args": {
        "edit": str(ve), "skill": "my-edit", "chain": "logo-pack,before:my-broll,after:my-thumbnail"}}]}), encoding="utf-8")
    assert video_skills(ve) == [{"skill": "ai-editor:cut", "state": "done"}, {"skill": "my-broll", "state": "now"},
                                {"skill": "my-edit", "state": "next"}, {"skill": "my-thumbnail", "state": "next"}], video_skills(ve)
    sf.write_bytes(old) if old is not None else sf.unlink()
    shutil.rmtree(tmp / "edits")
    vid = tmp / "v.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:duration=6",
                    "-f", "lavfi", "-i", "sine=duration=6", "-shortest", "-pix_fmt", "yuv420p", str(vid)], check=True)
    tr = tmp / "words.json"
    tr.write_text(json.dumps([{"text": "hello", "start": 1.0, "end": 1.4, "type": "word"},
                              {"text": " ", "start": 1.4, "end": 1.5, "type": "spacing"},
                              {"text": "world", "start": 1.5, "end": 2.0, "type": "word"},
                              {"text": "later", "start": 5.0, "end": 5.5, "type": "word"}]), encoding="utf-8")
    pl = tmp / "plan.json"
    pl.write_text(json.dumps({"cards": [{"src": "images/a.png", "start": 3.5, "end": 5.5, "trigger_word": "later"}]}), encoding="utf-8")
    folder = tmp / "edits" / "demo"
    ns = argparse.Namespace
    cmd_start(ns(video=str(vid), stage="cut", transcript=str(tr), plan=None, note=None, name=None), folder)
    assert str(folder.resolve()) in load(tmp / "home" / "library.json")["edits"], "start lists the edit in the library"
    end = tmp / "end.jpg"   # the playhead on the last frame: -ss there writes nothing, so grab seeks from the end
    grab(vid, duration(vid), end)
    assert end.exists() and end.stat().st_size > 1000, "no still at the last frame"
    assert "Move to playhead" not in HTML.read_text(encoding="utf-8") and 'id="homebtn"' in HTML.read_text(encoding="utf-8")
    assert load(folder / "review.json")["vertical"] is False
    os.environ["CLAUDE_CODE_SESSION_ID"] = "sess-review"
    srv, url = serve(folder, 0, open_browser=False)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base, tok = url.split("/?t=")

    def get(p, **h):
        return urllib.request.urlopen(urllib.request.Request(base + p + ("&" if "?" in p else "?") + "t=" + tok, headers=h))

    def post(p, b):
        return json.loads(urllib.request.urlopen(urllib.request.Request(
            base + p + "?t=" + tok, json.dumps(b).encode(), method="POST")).read())

    def waited():
        o = io.StringIO()
        with contextlib.redirect_stdout(o):
            cmd_wait(folder, poll=0.01)
        return o.getvalue()

    # no token: nothing reads or writes
    for p, data in (("/", None), ("/state", None), ("/video", None), ("/event", b'{"type":"send"}')):
        try:
            urllib.request.urlopen(urllib.request.Request(base + p, data, method="POST" if data else "GET"))
            raise AssertionError(f"{p} answered without the token")
        except urllib.error.HTTPError as e:
            assert e.code == 403, (p, e.code)
    assert not load(folder / "review.json")["events"]
    assert running(folder) == url and serve(folder, 0, open_browser=False) == (None, url)
    # a tab opens only when no home window is showing; with one, the home window goes there itself
    global OPEN
    opened, OPEN = [], (lambda u: opened.append(u))
    serve(folder, 0)
    assert opened == [url], opened
    hp = askhook.pages() / "1"
    hp.write_text(json.dumps({"url": "http://127.0.0.1:1/?t=x", "kind": "home", "session": ""}), encoding="utf-8")
    serve(folder, 0)
    assert opened == [url] * 2, "a home window busy with something else: this page still gets its tab"
    sf = tmp / "home" / "home" / "state.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    sf.write_text(json.dumps({"jobs": [{"type": "video", "state": "taken", "args": {"edit": str(folder)}}]}), encoding="utf-8")
    serve(folder, 0)
    assert opened == [url] * 2, "the home window holds this edit's job: it goes there itself, no second tab"
    hp.unlink()
    sf.unlink()
    OPEN = webbrowser.open
    r = get("/")
    assert b"review" in r.read() and "HttpOnly" in r.headers["Set-Cookie"]
    # Claude's question (askhook.py): posted, polled by the showing page, answered in its own words, cleared
    assert '<script src="/ask.js">' in HTML.read_text(encoding="utf-8") and b"askq" in get("/ask.js").read()
    qs = [{"question": "Keep the intro?", "header": "Intro", "options": [{"label": "Keep", "description": ""}], "multiSelect": False}]
    try:
        post("/ask", {"id": "q0", "questions": qs, "session": "sess-other"})
        raise AssertionError("took another session's question")
    except urllib.error.HTTPError as e:
        assert e.code == 409
    try:   # a POST from another site's page
        urllib.request.urlopen(urllib.request.Request(base + "/theme?t=" + tok, b'{"theme":"dark"}', {"Origin": "http://evil.example"}, method="POST"))
        raise AssertionError("took a cross-site POST")
    except urllib.error.HTTPError as e:
        assert e.code == 403
    os.environ.pop("CLAUDE_CODE_SESSION_ID")
    (folder / "review" / ".session").unlink(missing_ok=True)
    assert asker(folder, "")("") == "demo", "no session known (older Claude Code): a question with no session"
    assert asker(folder, "")("sess-anyone") is None, "a session that never touched this video: another project's"
    assert asker(folder, "sess-review")("sess-anyone") is None
    hs = Path(os.environ["AI_EDITOR_HOME"]) / "home" / "state.json"   # the home page's job for this video: its Claude asks here
    hs.parent.mkdir(parents=True, exist_ok=True)
    had = hs.read_bytes() if hs.exists() else None
    hs.write_text(json.dumps({"jobs": [{"type": "video", "state": "taken", "owner": "sess-job", "args": {"edit": str(folder)}}]}), encoding="utf-8")
    assert asker(folder, "sess-review")("sess-job") == "demo" and asker(folder, "sess-review")("sess-anyone") is None
    # a server the home window started (no session of its own): another video's Claude never asks here
    other = folder.parent / "demo-other"
    hs.write_text(json.dumps({"jobs": [{"type": "video", "state": "taken", "owner": "sess-job", "args": {"edit": str(folder)}},
                                       {"type": "video", "state": "taken", "owner": "sess-two", "args": {"edit": str(other)}}]}), encoding="utf-8")
    assert asker(folder, "")("sess-job") == "demo" and asker(folder, "")("sess-two") is None, "the job's own edit page only"
    (other / "review").mkdir(parents=True, exist_ok=True)
    (other / "review" / ".session").write_text("sess-three", encoding="utf-8")
    assert asker(folder, "")("sess-three") is None and asker(folder, "")("sess-old") is None, "working on another edit, or on none: not here"
    shutil.rmtree(other)
    hs.write_bytes(had) if had is not None else hs.unlink()
    os.environ["CLAUDE_CODE_SESSION_ID"] = "sess-review"
    post("/ask", {"id": "q1", "questions": qs, "session": "sess-review"})
    assert json.loads(get("/ask?v=1").read())["ask"] == {"id": "q1", "questions": qs, "about": "demo"} and askhook.live() == [url]
    post("/ask/answer", {"id": "q1", "answers": ["Cut it to 3 seconds"]})
    assert json.loads(get("/ask?id=q1").read())["result"] == {"answers": ["Cut it to 3 seconds"]}
    assert json.loads(get("/ask").read())["ask"] is None
    post("/ask/clear", {"id": "q1"})
    assert not srv.asks
    r = get("/download")   # the finished video, saved under its own name
    assert r.headers["Content-Disposition"] == "attachment; filename=\"demo.mp4\"; filename*=UTF-8''demo.mp4" and r.read()
    assert disposition("My take - Café edit.mp4").endswith("filename*=UTF-8''My%20take%20-%20Caf%C3%A9%20edit.mp4")
    r = get("/video?k=cut-1", Range="bytes=10-19")
    assert r.status == 206 and len(r.read()) == 10 and r.headers["Content-Range"].endswith(f"/{vid.stat().st_size}")
    # a note: its words, its frame still; an attached image (a non-image is dropped); delete
    c = post("/comment", {"t": 1.2, "t_end": None, "text": "cut the hello"})
    assert c["words"] == "hello world" and c["card"] is None and (folder / "review" / c["frame"]).stat().st_size > 0
    png = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJ"
           "RU5ErkJggg==")
    # edit in place, same id: the text; an image added then removed; moved to the playhead and back
    e = post("/edit", {"id": c["id"], "text": "cut the hello, please"})
    assert e["id"] == c["id"] and e["text"] == "cut the hello, please" and e["edited"] and e["t"] == 1.2, e
    e = post("/edit", {"id": c["id"], "images": [png]})
    assert e["images"] == [f"rcut1-c{c['id']}-img1.png"] and e["text"] == "cut the hello, please", e
    assert post("/edit", {"id": c["id"], "images": []})["images"] == []
    e = post("/edit", {"id": c["id"], "t": 5.1})
    assert e["t"] == 5.1 and e["words"] == "later" and e["frame"] != c["frame"] and (folder / "review" / e["frame"]).stat().st_size > 0, e
    c = post("/edit", {"id": c["id"], "t": 1.2})
    assert c["words"] == "hello world" and [x["text"] for x in load(folder / "review.json")["comments"]] == ["cut the hello, please"]
    for bad in ({"id": c["id"], "text": ""}, {"id": 999, "text": "x"}):
        try:
            post("/edit", bad)
            raise AssertionError(f"edit {bad}")
        except urllib.error.HTTPError as err:
            assert err.code in (400, 404), err.code
    ci = post("/comment", {"t": 1.5, "text": "", "images": [png, "data:text/html;base64,PGI+"]})
    assert ci["images"] == [f"rcut1-c{ci['id']}-img1.png"]
    assert get("/frames/" + ci["images"][0]).headers["Content-Type"] == "image/png"
    post("/delete", {"id": ci["id"]})
    assert [x["id"] for x in load(folder / "review.json")["comments"]] == [c["id"]]
    # "Anything to add?": images and links into assets.json (assets.py), shown on /state, a picture at /assets/<name>
    ad = post("/assets", {"add": [{"url": "https://x.com/a/status/1", "say": "the post"}, {"image": png, "name": "a.png"}]})["items"]
    assert [x["kind"] for x in ad] == ["link", "image"] and json.loads(get("/state").read())["assets"] == ad
    assert get("/" + ad[1]["src"]).headers["Content-Type"] == "image/png"
    assert post("/assets", {"remove": 1})["items"] == ad[:1] and not (folder / ad[1]["src"]).exists()
    up = lambda name, data: json.loads(urllib.request.urlopen(urllib.request.Request(
        f"{base}/assets/upload?name={quote(name)}&say=the%20demo&t={tok}", data, method="POST")).read())["items"]
    with tempfile.TemporaryDirectory() as vt:   # a video: streamed in, its picture at ?thumb=1
        clip = Path(vt, "clip.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=d=1:s=160x90:r=10", str(clip)], check=True)
        ad = up("demo clip.mp4", clip.read_bytes())
    assert ad[-1] == {"kind": "video", "src": "assets/asset-vid1.mp4", "name": "demo clip.mp4", "say": "the demo"}, ad[-1]
    assert get("/" + ad[-1]["src"] + "?thumb=1").headers["Content-Type"] == "image/jpeg"
    try:
        up("notes.txt", b"x")
        raise AssertionError("a text file was added")
    except urllib.error.HTTPError as err:
        assert err.code == 400 and "Add a video" in json.loads(err.read())["error"]
    post("/assets", {"remove": len(ad) - 1})
    st = json.loads(get("/state").read())
    assert not st["listening"] and f'"{folder.resolve()}" wait' in st["resume"], "Copy for Claude names this edit"
    # the first-edit notice: round 1 of the user's first videos, until dismissed; the theme keeps the count
    assert json.loads(get("/state").read())["intro"], "round 1 of the first video: the notice shows"
    set_theme("dark")
    assert ui()["videos"] == [str(folder)] and theme() == "dark"
    set_theme("system")
    post("/intro", {})
    assert not json.loads(get("/state").read())["intro"] and ui()["intro_off"]
    set_ui(intro_off=False)
    for i in range(4):
        seen(tmp / f"v{i}")
    assert len(ui()["videos"]) == INTRO_VIDEOS and intro(tmp / "v0", {"round": 1}), ui()
    assert not intro(tmp / "v2", {"round": 1}) and not intro(tmp / "v0", {"round": 2}), "after 3 videos, and after round 1: never"
    assert json.loads(get("/state").read())["home"] is None   # no home page running: the button says how to start it
    hs = ThreadingHTTPServer(("127.0.0.1", 0), type("H", (BaseHTTPRequestHandler,), {
        "do_GET": lambda self: (self.send_response(200), self.end_headers(), self.wfile.write(b"{}")), "log_message": lambda *a: None}))
    threading.Thread(target=hs.serve_forever, daemon=True).start()
    hurl = f"http://127.0.0.1:{hs.server_address[1]}/?t=abc"
    (tmp / "home" / "home").mkdir(parents=True, exist_ok=True)
    (tmp / "home" / "home" / ".server").write_text(hurl, encoding="utf-8")
    _HOME["at"] = 0
    assert json.loads(get("/state").read())["home"] == hurl, "the Home button reads home.py's fixed address"
    hsf = tmp / "home" / "home" / "state.json"
    keep_hs = hsf.read_text(encoding="utf-8") if hsf.exists() else None
    hsf.write_text(json.dumps({"jobs": [{"type": "video", "state": "taken"}, {"type": "video", "state": "queued"},
                                        {"type": "video", "state": "done"}, {"type": "teardown", "state": "taken"}]}), encoding="utf-8")
    assert json.loads(get("/state").read())["jobs"] == 2, "the rail's Making ring counts the home window's videos being made"
    mk = tmp / "edits" / "being-made"   # past its job: the preview approved, the video rendering (QA round 4 showed 0)
    mk.mkdir(parents=True)
    save(mk / "review.json", {"stage": "edit", "round": 1, "sent": True, "events": [{"type": "approve", "stills": True}], "rounds": []})
    import library
    library.record(mk)
    assert home_jobs() == 3, "an edit being made after its job counts in the Making ring"
    shutil.rmtree(mk)
    # round 0's checklist: every step of the cut from the job for this edit, by the scripts' own words
    j = {"type": "video", "state": "taken", "args": {"edit": str(folder)}, "steps": [{"text": "Writing down every word"},
                                                                                   {"text": "Finding retakes and pauses"}]}
    hsf.write_text(json.dumps({"jobs": [j]}), encoding="utf-8")
    cs = cut_steps(folder, {"rounds": []})
    assert [x["state"] for x in cs["steps"]] == ["done", "now", "todo", "todo", "todo", "todo"] and cs["steps"][0]["text"] == "Writing down every word", cs
    assert all(x["state"] == "done" for x in cut_steps(folder, {"rounds": [{"stage": "cut", "round": 1}]})["steps"])
    j.update(steps=[], state="queued", claude={"opened": True})
    hsf.write_text(json.dumps({"jobs": [j]}), encoding="utf-8")
    cs = cut_steps(folder, {})
    assert {x["state"] for x in cs["steps"]} == {"todo"} and cs["claude"]["opened"] and cut_steps(tmp, {}) is None, cs
    hsf.write_text(keep_hs, encoding="utf-8") if keep_hs is not None else hsf.unlink()
    hs.shutdown()
    hs.server_close()
    # the cut's transcript: kept words on the cut's timeline, the cut word struck, the removed pause a chip
    (folder / "words.raw.json").write_text(json.dumps([
        {"text": "hello", "start": 0.0, "end": 0.4, "type": "word"}, {"text": "um,", "start": 0.5, "end": 0.8, "type": "word"},
        {"text": "world.", "start": 2.0, "end": 2.5, "type": "word"}, {"text": "later", "start": 3.0, "end": 9.0, "type": "word"}]), encoding="utf-8")
    (folder / "decisions.json").write_text(json.dumps([{"start": 0.0, "end": 0.45}, {"start": 1.95, "end": 7.5}]), encoding="utf-8")
    tx = cut_transcript(folder, 6.0)
    toks = [x for ln in tx["lines"] for x in ln["tokens"]]
    assert toks[1]["k"] == "pause"   # cut with no spans.json entry: the pause trim took it
    assert [{k: x[k] for k in x if k not in ("s", "e", "k")} for x in toks] == [{"w": "hello", "t": 0.0}, {"w": "um,", "t": None}, {"p": 1.1},
                                                                          {"w": "world.", "t": 0.5}, {"w": "later", "t": 1.5}], toks
    assert toks[1]["s"] == 0.5 and toks[1]["e"] == 0.8 and tx["kept"] == [[0.0, 0.45], [1.95, 7.5]], tx
    assert [ln["t"] for ln in tx["lines"]] == [0.0, 1.5] and tx["points"] == [0.45] and tx["cuts"] == 2, tx
    assert cut_transcript(folder, 30.0) is None   # decisions that do not add up to this video: no transcript
    round_data(folder, vid, "cut", 1, None)
    assert json.loads(get("/data?k=cut-1").read())["transcript"]["cuts"] == 2
    assert json.loads(get("/data?k=nope").read()) == {}
    # stop does nothing until a send; after a send it opens the notes again and `status` tells Claude to stop
    post("/event", {"type": "stop"})
    assert not load(folder / "review.json")["sent"]
    post("/event", {"type": "send"})
    assert post("/claude", {})["opened"] and load(folder / "review.json")["claude"]["command"] == f"claude '/ai-editor:start carry on edits/{folder.name}'"
    cq = post("/comment", {"t": 2.0, "text": "queued then stopped"})   # with Claude: queued for the next round
    assert cq["queued"] and cq["round"] == 2, cq
    post("/event", {"type": "stop"})
    d = load(folder / "review.json")
    assert not d["sent"] and d["stopped"] and d["events"][-1]["type"] == "stop" and d["events"][-1]["handled"], d["events"]
    q = next(x for x in d["comments"] if x["id"] == cq["id"])
    assert q["round"] == 1 and "queued" not in q, q   # stop: the queued note joins the reopened round
    post("/delete", {"id": cq["id"]})
    d = load(folder / "review.json")
    try:
        with contextlib.redirect_stdout(io.StringIO()) as o:
            cmd_status(ns(text="rendering", log=None, done=False), folder)
        raise AssertionError("status after stop")
    except SystemExit as e:
        assert e.code == 3 and "STOPPED" in o.getvalue()
    # Undo approve: an approve, even one Claude already took, is taken back and the draft opens for notes again
    d["events"] = [{"type": "approve", "stage": d["stage"], "round": d["round"], "at": now(), "handled": True}]
    d["sent"] = False
    save(folder / "review.json", d)
    post("/event", {"type": "stop"})
    d = load(folder / "review.json")
    assert d["events"][-1]["type"] == "stop" and not d["sent"], d["events"]
    d["events"] = []
    save(folder / "review.json", d)
    # send: wait prints the note and its still; the page says the round is with Claude
    post("/event", {"type": "send"})
    out = waited()
    assert out.startswith("SEND: demo the cut, round 1, 1 note.") and "#1 0:01.2" in out and 'said: "hello world"' in out, out
    assert str(folder / "review" / c["frame"]) in out and not (folder / "review" / ".listening").exists()
    assert "): cut the hello, please" in out, out   # wait hands over the final text
    try:   # Claude has this round: its notes are read-only
        post("/edit", {"id": c["id"], "text": "too late"})
        raise AssertionError("edit after pick-up")
    except urllib.error.HTTPError as err:
        assert err.code == 409
    # a note while Claude works: queued for the next round, deletable, never in what `wait` hands over
    cx = post("/comment", {"t": 5.2, "text": "delete me"})
    post("/delete", {"id": cx["id"]})
    cn = post("/comment", {"t": 1.2, "text": "and the pause"})
    assert cn["queued"] and cn["round"] == 2 and cn["words"] == "hello world", cn
    cn = post("/edit", {"id": cn["id"], "text": "and the pause after it"})   # a queued note stays editable, and queued
    assert next(x for x in load(folder / "review.json")["comments"] if x["id"] == cn["id"])["queued"]
    assert [x["id"] for x in load(folder / "review.json")["comments"]] == [c["id"], cn["id"]]
    assert all(e["handled"] for e in load(folder / "review.json")["events"])   # nothing for `wait` to return on
    assert "LEARN:" in out.splitlines()[-2] and f"{folder} learn --none" in out, out
    # round 2 on the styled edit: the card under a note comes with it, Claude's answer shows.
    # The cut's note was never learned: round says so, then learn --none marks it one-off
    o = io.StringIO()
    with contextlib.redirect_stdout(o):
        cmd_round(ns(video=str(vid), stage="edit", transcript=None, plan=str(pl), note=None, name=None), folder)
    assert "notes not learned yet: 1." in o.getvalue(), o.getvalue()
    # the queued note is an open note of the new round, its words and a new frame still with it
    n = next(x for x in load(folder / "review.json")["comments"] if x["id"] == cn["id"])
    assert (n["stage"], n["round"], n["status"], n["words"]) == ("edit", 1, "open", "hello world") and "queued" not in n, n
    assert n["frame"] == f"redit1-c{cn['id']}.jpg" and (folder / "review" / n["frame"]).stat().st_size > 0, n
    # after a re-cut, a queued note moves to where its words are said (the word "world" moved 0.5 s later)
    otx = {"lines": [{"tokens": [{"w": "hello", "t": 0.0}, {"w": "um,", "t": 0.4}, {"w": "world", "t": 0.8}]}]}
    ntx = {"lines": [{"tokens": [{"w": "hello", "t": 0.0}, {"p": 0.3}, {"w": "um,", "t": None}, {"w": "world", "t": 0.4}]}]}
    assert remap(1.0, otx, ntx) == 0.6 and remap(0.5, otx, ntx) == 0.4 and remap(1.0, otx, None) is None
    learn = lambda **k: cmd_learn(ns(**{"scope": None, "rule": None, "none": False, "style": None, **k}), folder)
    with contextlib.redirect_stdout(io.StringIO()):
        learn(none=True)
    assert load(folder / "review.json")["comments"][0]["taste"] == "one-off"
    cmd_resolve(ns(id=1, status="fixed", reply="cut it", new_t=0.9), folder)
    c2 = post("/comment", {"t": 4.0, "t_end": 5.0, "text": "card smaller"})
    assert c2["card"]["trigger_word"] == "later" and c2["stage"] == "edit" and c2["round"] == 1, c2
    s = json.loads(get("/state").read())
    assert s["comments"][0]["status"] == "fixed" and not s["sent"] and [r["stage"] for r in s["rounds"]] == ["cut", "edit"]
    assert not s.get("stopped") and all(r["at"] for r in s["rounds"])
    trk = json.loads(get("/data?k=edit-1").read())
    assert trk["tracks"] == {"cards": [[3.5, 5.5]], "zooms": [], "captions": []} and "transcript" not in trk, trk
    # another video in the round: its own notes, notes on every video, scope switched and back
    cmd_alt(ns(name="wide", video=str(vid), transcript=str(tr)), folder)
    assert get("/video?k=edit-1&alt=wide").status == 200
    c3 = post("/comment", {"t": 5.1, "text": "louder here", "alt": "wide"})
    assert c3["alt"] == "wide" and c3["words"] == "later", c3
    c4 = post("/comment", {"t": 1.0, "text": "on all of them", "alt": "*"})
    c6 = post("/comment", {"t": 2.0, "text": "wait for it", "add_text": {"style": "box", "x_pct": 50, "y_pct": 140}})   # the Text tool
    assert c6["add_text"] == {"style": "box", "x_pct": 50.0, "y_pct": 100.0, "size_pct": TEXT_SIZE} and c6["t_end"] == 5.0, c6
    # the Text tab: a text not sent yet changes in place (words, look, place, time)
    c6 = post("/edit", {"id": c6["id"], "text": "wait for it!", "add_text": {"style": "outline", "x_pct": 40, "y_pct": 30}, "t": 2.5, "t_end": 6})
    assert (c6["text"], c6["add_text"]["style"], c6["add_text"]["x_pct"], c6["t"], c6["t_end"]) == ("wait for it!", "outline", 40.0, 2.5, 6.0), c6
    # a typed one (texts.json): Add, Edit and Delete change it on the spot, with no note (Claude does not have the round)
    (folder / "texts.json").write_text(json.dumps({"items": [{"id": "edit1-99", "text": "hi there", "style": "plain", "start": 1.0,
                                                              "end": 4.0, "x_pct": 50, "y_pct": 40, "size_pct": 6}]}), encoding="utf-8")
    assert [x["id"] for x in json.loads(get("/state").read())["texts"]] == ["edit1-99"]
    ch = post("/text/edit", {"id": "edit1-99", "text": "hello there", "style": "box", "x_pct": 30, "start": 2, "end": 5})
    row = load(folder / "texts.json")["items"][0]
    assert (row["text"], row["style"], row["x_pct"], row["y_pct"], row["start"], row["end"]) == ("hello there", "box", 30.0, 40.0, 2.0, 5.0), row
    assert ch == {"ok": True, "id": "edit1-99"} and not any("on-screen text" in c["text"] for c in load(folder / "review.json")["comments"]), ch
    nt = post("/text/add", {"text": "new one", "style": "plain", "x_pct": 50, "y_pct": 60, "size_pct": 9, "start": 3, "end": 4})
    row = load(folder / "texts.json")["items"][-1]
    assert row["id"] == nt["id"] and (row["text"], row["size_pct"], row["start"], row["end"]) == ("new one", 9.0, 3.0, 4.0), row
    st = json.loads(get("/state").read())
    assert st["bake"]["state"] in ("waiting", "working", "off") and st["texts_baked"] == [], st["bake"]
    # a font and a colour (Texts.tsx draws them); a drag on the timeline sends only the times and keeps them
    post("/text/edit", {"id": nt["id"], "font": "Anton", "color": "#ff3b30"})
    post("/text/edit", {"id": nt["id"], "start": 5, "end": 7.5})
    row = load(folder / "texts.json")["items"][-1]
    assert (row["font"], row["color"], row["start"], row["end"]) == ("Anton", "#FF3B30", 5.0, 7.5), row
    post("/text/edit", {"id": nt["id"], "font": "TikTok Sans", "color": "#FFFFFF"})   # back to the default: the keys go
    assert not {"font", "color"} & set(load(folder / "texts.json")["items"][-1]), load(folder / "texts.json")
    bad = urllib.request.Request(base + "/text/edit?t=" + tok, json.dumps({"id": nt["id"], "font": "Comic Sans"}).encode(), method="POST")
    try:
        urllib.request.urlopen(bad)
        raise AssertionError("a font not in TEXT_FONTS saved")
    except urllib.error.HTTPError as e:
        assert e.code == 400
    post("/text/delete", {"id": nt["id"]})
    # the timeline's Video row: split and cut pieces, merged, kept in overrides.json, one note that a put-back removes
    assert timeline_cuts({"splits": [3, 1, 1, 0], "gone": [[2, 3], [1, 2], [5, 5.01]]}) == {"splits": [1, 3], "gone": [[1, 3]]}
    r = post("/timeline/cut", {"splits": [1, 2], "gone": [[1, 2]]})
    note = [c for c in load(folder / "review.json")["comments"] if (c.get("on") or {}).get("k") == "cuts"]
    assert load(folder / "overrides.json")["cuts"] == {"splits": [1.0, 2.0], "gone": [[1.0, 2.0]]} and r["id"] and len(note) == 1 and "0:01.0-0:02.0" in note[0]["text"], note
    assert json.loads(get("/state").read())["cuts"]["gone"] == [[1.0, 2.0]]
    post("/timeline/cut", {"splits": [1, 2], "gone": []})
    assert not [c for c in load(folder / "review.json")["comments"] if (c.get("on") or {}).get("k") == "cuts"]
    # the Captions panel: words at a time and the look, saved for this video only, with a note each
    from ai_editor import taste as _taste
    cc1 = post("/captions", {"words": "sentence"})
    cc2 = post("/captions", {"look": "bold"})
    cap = (_taste.load_json(folder, count=False) or {}).get("captions") or {}
    assert cap.get("words_per_caption") == 12 and cap.get("preset") == "bold", cap
    cui = json.loads(get("/state").read())["captions_ui"]
    assert cui["words"] == "sentence" and cui["look"] == "bold" and "plain" in cui["looks"], cui
    assert cc1["text"].startswith("Captions: a sentence at a time, for this video"), cc1
    assert cc2["id"] == cc1["id"] and cc2["text"].startswith("Captions: a sentence at a time and the bold look"), cc2   # one note, kept current
    assert all(r["scope"] == f"video:{folder.name}" for r in _taste.load_rules() if r.get("setting", "").startswith("captions.")), "this video only"
    cc3 = post("/captions", {"size": 5.55, "y": 62, "color": "#ffd60a", "highlight": "#FF3B30"})
    cap = (_taste.load_json(folder, count=False) or {}).get("captions") or {}
    assert (cap.get("size_pct"), cap.get("y_pct"), cap.get("color"), cap.get("highlight_color")) == (5.5, 62.0, "#FFD60A", "#FF3B30"), cap
    cui = json.loads(get("/state").read())["captions_ui"]
    assert cui["mine"] == {"size_pct": 5.5, "y_pct": 62, "color": "#FFD60A", "highlight_color": "#FF3B30"} and "base" in cui, cui
    assert cc3["id"] == cc1["id"] and cc3["text"].startswith("Captions: a sentence at a time, the bold look, size 5.5, 62% down"), cc3
    for bad in ({"words": "7"}, {"look": "nope"}, {}, {"size": 40}, {"y": "high"}, {"color": "red"}, {"highlight": "#12"}):
        try:
            post("/captions", bad)
            raise AssertionError(bad)
        except urllib.error.HTTPError as e:
            assert e.code == 400, bad
    for x in (cc1, cc2):
        post("/delete", {"id": x["id"]})
    for r in [r for r in _taste.load_rules() if r.get("setting", "").startswith("captions.")]:
        with contextlib.redirect_stdout(io.StringIO()):
            _taste.forget(r["id"])   # the learn checks below count the session's own rules
    # the Sounds panel: picks for every video into the library (a temp one here), one note kept current, previews play
    keep_lib = os.environ.get("AI_EDITOR_LIBRARY")
    os.environ["AI_EDITOR_LIBRARY"] = str(tmp / "soundlib")
    try:
        su = json.loads(get("/state").read())["sounds_ui"]
        assert [x["cue"] for x in su["cues"]][:3] == ["whoosh-in", "pop", "zoom"] and su["own"] == [], su
        s1 = post("/sound", {"cue": "pop", "choice": "none"})
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=f=660:d=0.5", str(tmp / "ding.wav")], check=True)
        s2 = post("/sound/add", {"cue": "zoom", "name": "my ding!.wav", "data": "data:audio/wav;base64," +
                                 base64.b64encode((tmp / "ding.wav").read_bytes()).decode()})
        assert s2["id"] == s1["id"] and s2["text"].startswith("Sounds for every video: Logo pops in off; Zoom is my ding.wav."), s2
        su = json.loads(get("/state").read())["sounds_ui"]
        assert su["own"] == ["my ding.wav"] and {x["cue"]: x["choice"] for x in su["cues"]}["zoom"] == "my ding.wav", su
        assert get("/sound-preview?cue=zoom&c=my%20ding.wav").headers["Content-Type"] == "audio/wav"
        for bad in ({"cue": "pop", "choice": "nope.wav"}, {"cue": "nope", "choice": "default"}):
            try:
                post("/sound", bad)
                raise AssertionError(bad)
            except urllib.error.HTTPError as e:
                assert e.code == 400, bad
        try:
            get("/sound-preview?cue=zoom&c=..%2Freview.json")
            raise AssertionError("a preview of a file not in the library")
        except urllib.error.HTTPError as e:
            assert e.code == 404
        # the timeline's Sounds row: put a library sound at a moment, take it out, take out one the plan put there
        sa = post("/sfx/add", {"t": 2.0, "sound": "my ding.wav"})
        placed = json.loads(get("/state").read())["placed_sounds"]
        assert [x["sound"] for x in placed] == ["my ding.wav"] and placed[0]["t"] == 2.0, placed
        sr = post("/sfx/remove", {"t": 2.0, "placed": placed[0]["id"], "src": "my ding.wav"})
        sx = post("/sfx/remove", {"t": 3.5, "src": ".sfx/pop.wav"})
        assert sr["id"] == sa["id"] == sx["id"] and sx["lines"] == ["add my ding at 0:02.0", "remove my ding at 0:02.0",
                                                                      "remove pop at 0:03.5"], sx
        assert not json.loads(get("/state").read())["placed_sounds"] and json.loads(get("/state").read())["sfx_removed"] == [3.5]
        assert load(folder / "overrides.json")["sfx"]["3.500"] == {"deleted": True}
        for bad in ({"t": 1, "sound": "nope.wav"}, {"sound": "my ding.wav"}):
            try:
                post("/sfx/add", bad)
                raise AssertionError(bad)
            except urllib.error.HTTPError as e:
                assert e.code == 400, bad
        # an audio file dropped on the timeline: a clip as long as the file, then moved, trimmed and turned down
        import wave
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1), w.setsampwidth(2), w.setframerate(8000), w.writeframes(b"\x10\x20" * 8000 * 2)
        up = urllib.request.Request(base + "/audio/upload?name=my%20song.wav&at=1.5&t=" + tok, buf.getvalue(), method="POST")
        urllib.request.urlopen(up).read()
        clip = next(x for x in load(folder / "sounds.json")["items"] if x.get("kind") == "clip")
        assert (clip["sound"], clip["t"], clip["in"], clip["vol"]) == ("my song.wav", 1.5, 0.0, 1.0) and 0 < clip["dur"] <= 2.0, clip
        assert (folder / "audio" / "my song.wav").is_file() and get("/audio/my%20song.wav").read()[:4] == b"RIFF"
        post("/sfx/move", {"placed": clip["id"], "t": 3, "in": 0.5, "dur": 1, "vol": 0.4})
        clip = next(x for x in load(folder / "sounds.json")["items"] if x["id"] == clip["id"])
        assert (clip["t"], clip["in"], clip["dur"], clip["vol"]) == (3.0, 0.5, 1.0, 0.4), clip
        post("/sfx/remove", {"t": 3, "placed": clip["id"], "src": "my song.wav"})
        post("/delete", {"id": sa["id"]})   # the sounds note, so the next one starts clean
        (folder / "overrides.json").unlink()
        post("/delete", {"id": s1["id"]})
    finally:
        if keep_lib is None:
            os.environ.pop("AI_EDITOR_LIBRARY", None)
        else:
            os.environ["AI_EDITOR_LIBRARY"] = keep_lib
    # caption lines retyped: words one each, extra on the last word, missing ones blanked; one running note
    assert caption_words(["1.000", "1.300", "1.600"], "hello there") == {"1.000": "hello", "1.300": "there", "1.600": ""}
    assert caption_words(["1.000", "1.300"], "a b c") == {"1.000": "a", "1.300": "b c"}
    assert caption_words(["1.000"], "") == {"1.000": ""}
    k1 = post("/captions/text", {"s": 1.0, "w": [1.0, 1.3], "text": "hello world!", "old": "hello world"})
    k2 = post("/captions/text", {"s": 2.0, "w": [2.0], "text": "", "old": "later"})
    assert k2["id"] == k1["id"] and k2["text"].startswith('Captions retyped: "hello world" at 0:01.0 now "hello world!"; "later" at 0:02.0 taken out.'), k2
    assert json.loads(get("/state").read())["cap_words"] == {"1.000": "hello", "1.300": "world!", "2.000": ""}
    post("/captions/time", {"w": 1.0, "s": 0.9, "e": 1.8, "text": "hello world"})   # a page dragged on the Captions row
    assert json.loads(get("/state").read())["cap_times"] == {"1.000": [0.9, 1.8]} and load(folder / "overrides.json")["cap_times"]
    for bad in ({"w": 1, "s": 2, "e": 2.05}, {"w": "x", "s": 0, "e": 1}, {"s": 0, "e": 1}):
        try:
            post("/captions/time", bad)
            raise AssertionError(bad)
        except urllib.error.HTTPError as e:
            assert e.code == 400, bad
    try:
        post("/captions/text", {"s": 1.0, "w": [], "text": "x"})
        raise AssertionError("a line with no words")
    except urllib.error.HTTPError as e:
        assert e.code == 400
    (folder / "overrides.json").unlink()
    post("/delete", {"id": k1["id"]})
    # a card on the video: moved or resized, then deleted, into overrides.json with no note (Claude does not have the
    # round): the page draws it moved until the bake; its picture is served
    trk_items = json.loads(get("/data?k=edit-1").read())["items"]["cards"]
    assert trk_items[0]["key"].startswith("later@"), trk_items
    cm = post("/card/edit", {"key": trk_items[0]["key"], "label": "the picture", "t": 3.5, "t_end": 5.5, "box": [10, 12.34, 50, 30]})
    assert load(folder / "overrides.json")["cards"][trk_items[0]["key"]] == {"box": [10.0, 12.3, 50.0, 30.0]}
    assert cm == {"ok": True}, cm
    pend = json.loads(get("/state").read())["cards_pending"]
    assert pend == [{"key": trk_items[0]["key"], "box": [10.0, 12.3, 50.0, 30.0]}], pend
    cd = post("/card/edit", {"key": trk_items[0]["key"], "label": "the picture", "t": 3.5, "t_end": 5.5, "deleted": True})
    assert load(folder / "overrides.json")["cards"][trk_items[0]["key"]] == {"box": [10.0, 12.3, 50.0, 30.0], "deleted": True}
    for bad in ({"key": "x", "t": 1, "t_end": 2, "box": [0, 0, 10, 10]}, {"key": "a@1.0", "t": 1, "t_end": 2, "box": [0, 0, 1, 10]}):
        try:
            post("/card/edit", bad)
            raise AssertionError(bad)
        except urllib.error.HTTPError as e:
            assert e.code == 400, bad
    assert cd == {"ok": True} and json.loads(get("/state").read())["cards_pending"] == [{"key": trk_items[0]["key"], "deleted": True}]
    (folder / "overrides.json").unlink()
    # the timeline's Images row: a card moved or trimmed in time keeps its box, shows as pending, and bad times are refused
    k0, c0 = trk_items[0]["key"], trk_items[0]
    post("/card/edit", {"key": k0, "t": 4, "t_end": 6.5, "box": [10, 12, 50, 30]})
    ct = post("/card/edit", {"key": k0, "t": 4, "t_end": 6.5, "start": 4.004, "end": 6.5})
    assert ct == {"ok": True} and load(folder / "overrides.json")["cards"][k0] == {"box": [10.0, 12.0, 50.0, 30.0], "start": 4.0, "end": 6.5}
    pend = json.loads(get("/state").read())["cards_pending"]
    assert pend == [{"key": k0, "box": [10.0, 12.0, 50.0, 30.0], "start": 4.0, "end": 6.5}], pend
    post("/card/edit", {"key": k0, "t": 1, "t_end": 2, "box": c0["box"], "start": c0["s"], "end": c0["e"]})   # an undo: back where the video has it
    assert json.loads(get("/state").read())["cards_pending"] == [], "back in place is not pending"
    for bad in ({"start": -1, "end": 2}, {"start": 3, "end": 3.1}, {"start": 3}, {"start": "x", "end": 4}, {}):
        try:
            post("/card/edit", {"key": k0, "t": 1, "t_end": 2, **bad})
            raise AssertionError(bad)
        except urllib.error.HTTPError as e:
            assert e.code == 400, bad
    (folder / "overrides.json").unlink()
    for bad in ("/card-img/../review.json", "/card-img/review.json"):
        try:
            get(bad)
            raise AssertionError(bad)
        except urllib.error.HTTPError as e:
            assert e.code == 404, bad
    gone = post("/text/delete", {"id": "edit1-99"})
    assert not load(folder / "texts.json")["items"] and gone == {"ok": True, "id": "edit1-99"}, gone
    # a note that reads as a lasting preference is offered as a rule, ticked; the user can untick it
    assert looks_like_rule("Too many zooms") and looks_like_rule("I prefer bigger captions") and not looks_like_rule("cut the um at 0:12")
    c5 = post("/comment", {"t": 2.0, "text": "always use fewer zooms"})
    assert c5.get("keep") is True and not c4.get("keep"), (c5, c4)
    post("/keep", {"id": c5["id"], "keep": False})
    c5b = next(x for x in load(folder / "review.json")["comments"] if x["id"] == c5["id"])
    assert c5b["keep"] is False and c5b["keep_set"], c5b
    assert post("/edit", {"id": c5["id"], "text": "never zoom"}).get("keep") is False   # the user's choice stays
    assert json.loads(get("/state").read())["style_name"] == "My style"
    assert "keep as a rule for My style" in learn_hint(folder, [c5["id"]]) and "--scope style (no question)" in learn_hint(folder, [c5["id"]])
    assert "learn --none" in learn_hint(folder) and "Ask nothing" in learn_hint(folder), "nothing ticked: no rule, no question"
    post("/delete", {"id": c5["id"]})
    post("/scope", {"id": c3["id"], "alt": "*"})
    assert next(x for x in load(folder / "review.json")["comments"] if x["id"] == c3["id"])["alt"] == "*"
    post("/scope", {"id": c3["id"], "alt": "wide"})
    assert post("/edit", {"id": c3["id"], "alt": "*"})["alt"] == "*" and post("/edit", {"id": c3["id"], "alt": "wide"})["alt"] == "wide"
    # live progress from a render log
    lg = tmp / "r.log"
    lg.write_text("Rendered 10/40\nRendered 30/40\n", encoding="utf-8")
    cmd_status(ns(text="rendering", log=str(lg), done=False), folder)
    st = json.loads(get("/state").read())["activity"][-1]
    assert st["text"] == "rendering" and st["pct"] == 75 and not st["done"], st
    post("/event", {"type": "approve"})
    out = waited()
    assert out.startswith("APPROVE: demo the edit, round 1, 5 notes.") and f"also wide: {folder / 'review' / 'v-edit1-wide.mp4'}" in out, out
    assert f"assets: {folder / 'assets.json'} (1 video, image or link the user added." in out, out
    assert f"#{c4['id']} 0:01.0 (1.0s) [all videos]: on all of them" in out, out
    assert f": wait for it! [add text: outline]" in out and f"texts: {folder / 'texts.json'} (1 on-screen text the user typed" in out, out
    assert load(folder / "texts.json")["items"] == [{"id": f"edit1-{c6['id']}", "text": "wait for it!", "style": "outline", "x_pct": 40.0,
                                                       "y_pct": 30.0, "size_pct": TEXT_SIZE, "start": 2.5, "end": 6.0}]
    assert f"#{c3['id']} 0:05.1 (5.1s) [wide] [card 0 image 'later']: louder here" in out, out
    # the final approve: LEARN asks Claude for rules from every note of the session, the page waits for them
    assert "LEARN: the video is approved" in out and "#1 the cut r1: cut the hello, please -> reply: cut it" in out, out
    lr0 = json.loads(get("/state").read())["learn"]
    assert {k: lr0[k] for k in ("state", "style")} == {"state": "reading", "style": "My style"}, lr0
    assert lr0["styles"][0]["here"] and lr0["styles"][0]["name"] == "My style", lr0["styles"]   # Save to: this video's style first
    try:
        post("/comment", {"t": 2, "text": "after approve"})
        raise AssertionError("a note after approve")
    except urllib.error.HTTPError as e:
        assert e.code == 409
    # learn: the preference notes go to taste (scope asked once a batch), every note records what happened
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from ai_editor import taste
    taste.HOME = tmp / "home"
    old_skills = os.environ.get("AI_EDITOR_SKILLS")
    os.environ["AI_EDITOR_SKILLS"] = str(tmp / "skills")   # never the user's real skills folder
    o = io.StringIO()
    with contextlib.redirect_stdout(o):
        learn(scope="style", rule=[[str(c2["id"]), "visuals", "Cards fill the space they have"]])
        learn(scope="video", rule=[[str(c3["id"]), "sound", "Sound louder on this one", "sfx_db=-6"]])
        learn(scope="everyone", rule=[[str(c4["id"]), "captions", "Captions stay inside the safe zone"]])
    cs = {c["id"]: c for c in load(folder / "review.json")["comments"]}
    rid = next(r["id"] for r in taste.load_rules() if r["rule"] == "Cards fill the space they have")
    rc = {r["id"]: r for r in load(folder / "review.json")["receipts"]}   # the page shows one per saved rule
    assert rc[cs[c2["id"]]["receipt"]]["style"] == "My style" and rc[cs[c2["id"]]["receipt"]]["status"] == "added", rc
    assert "receipt" not in cs[c3["id"]] and rc[cs[c4["id"]]["receipt"]]["ref"] == next(
        r["id"] for r in taste.load_rules() if r["rule"] == "Captions stay inside the safe zone"), rc
    assert cs[c2["id"]]["taste"] == rid and cs[c3["id"]]["taste"] == "video-only", cs
    assert cs[c4["id"]]["taste"] == "suggested" and cs[c4["id"]]["rule"] == "Captions stay inside the safe zone", cs
    assert "Cards fill the space they have" in taste.load_md()["Visuals"] and "sfx_db" not in taste.read_json()
    sug = [json.loads(x) for x in (tmp / "home" / "suggestions.jsonl").read_text(encoding="utf-8").splitlines()]
    assert sug[-1]["note"] == taste.note_key(f"demo#{c4['id']}") and sug[-1]["what"] == "on all of them", sug
    assert "from a review note" in taste.report() and "3 came from review-page notes" in taste.report(), taste.report()
    # this-style: the edit used a creator's style, so LEARN offers it first; the setting goes to that style's
    # overrides and its skill, not to taste.json; without a creator style it refuses
    try:
        learn(scope="this-style", rule=[[str(c2["id"]), "captions", "Captions too big", "captions.size_pct=4.5"]])
        raise AssertionError("this-style with no creator style")
    except SystemExit as e:
        assert "no creator style" in str(e), e
    sp = tmp / "creator-teardowns" / "alice" / "style.json"
    sp.parent.mkdir(parents=True)
    sp.write_text('{"handle": "alice"}', encoding="utf-8")
    (folder / "style.json").write_text(json.dumps({"handle": "alice", "source": [str(sp)]}), encoding="utf-8")
    assert "learn --scope this-style" in learn_hint(folder, [c2["id"]]) and "@alice" in learn_hint(folder, [c2["id"]])
    with contextlib.redirect_stdout(o):
        learn(scope="this-style", rule=[[str(c2["id"]), "captions", "Captions too big", "captions.size_pct=4.5"]])
    assert "(this style, skill edit-like-alice)" in o.getvalue(), o.getvalue()
    r = next(r for r in taste.load_rules() if r["rule"] == "Captions too big")
    assert r["scope"] == "style:alice" and next(c for c in load(folder / "review.json")["comments"] if c["id"] == c2["id"])["taste"] == r["id"]
    assert json.loads((sp.parent / "style.overrides.json").read_text(encoding="utf-8")) == {"captions": {"size_pct": 4.5}}
    assert "size_pct" not in taste.read_json().get("captions", {})
    assert "- Captions too big." in (tmp / "skills" / "edit-like-alice" / "SKILL.md").read_text(encoding="utf-8")
    assert "Cards fill the space they have" in (tmp / "skills" / "my-style" / "SKILL.md").read_text(encoding="utf-8")
    # propose -> the page ticks two of three -> wait prints them -> done saves them into the edit's style
    props = [{"rule": "Captions one size smaller.", "section": "captions", "set": "captions.size_pct=4"},
             {"rule": "Fewer zooms in the first 5 s", "section": "visuals"}, {"rule": "Keep the pauses short", "section": "Cut"}]
    for bad in ("not json", '[{"rule": "x", "section": "colour"}]', '[{"rule": "x", "section": "cut", "set": "size"}]'):
        try:
            learn(propose=bad)
            raise AssertionError(f"propose {bad}")
        except SystemExit as e:
            assert e.code, bad
    with contextlib.redirect_stdout(io.StringIO()):
        learn(propose=json.dumps(props))
    lr = json.loads(get("/state").read())["learn"]
    assert lr["state"] == "proposed" and [r["rule"] for r in lr["rules"]][0] == "Captions one size smaller", lr
    try:
        learn(done="")
        raise AssertionError("done before the user ticked")
    except SystemExit as e:
        assert "nothing ticked" in str(e)
    for bad, code in (({"chosen": [0], "to": "/no/such/style.json"}, 400), ({"chosen": [0], "new": " "}, 409)):
        try:   # Save to takes only a listed style; a new style needs a name
            post("/learn", bad)
            raise AssertionError(bad)
        except urllib.error.HTTPError as e:
            assert e.code == code, (bad, e.code)
    post("/learn", {"chosen": [0, 2, 9], "to": lr["styles"][0]["id"]})
    out = waited()
    assert out.startswith("LEARN: the user ticked 2 rules for My style:") and "Captions one size smaller (captions.size_pct=4)" in out, out
    assert "Fewer zooms" not in out and "learn --done" in out, out
    with contextlib.redirect_stdout(io.StringIO()):
        learn(done="")
    lr = load(folder / "review.json")["learn"]
    assert lr["state"] == "done" and lr["summary"] == "Saved to @alice. Next video uses it.", lr
    sk = (tmp / "skills" / "edit-like-alice" / "SKILL.md").read_text(encoding="utf-8")
    assert "- Keep the pauses short." in sk and "Fewer zooms" not in sk, sk
    old_lib = os.environ.get("AI_EDITOR_LIBRARY")
    os.environ["AI_EDITOR_LIBRARY"] = str(tmp / "lib")   # New style from this video: a named copy of @alice
    try:
        ns_ = new_style_from(folder, "  Podcast   clips ")
        nsp = Path(ns_["id"])
        assert ns_["name"] == "Podcast clips" and ns_["new"] and nsp.is_file() and nsp.parent.name == "own-podcast-clips", ns_
        cp = json.loads(nsp.read_text(encoding="utf-8"))
        assert cp["own"] and cp["handle"] == "own-podcast-clips" and shown_style(nsp) == "Podcast clips", cp
        assert any(x["name"] == "Podcast clips" for x in style_choices(folder)), "the new style is listed next time"
        try:
            new_style_from(folder, "")
            raise AssertionError("a nameless style")
        except ValueError:
            pass
    finally:
        if old_lib is None:
            os.environ.pop("AI_EDITOR_LIBRARY", None)
        else:
            os.environ["AI_EDITOR_LIBRARY"] = old_lib
    assert json.loads((sp.parent / "style.overrides.json").read_text(encoding="utf-8"))["captions"]["size_pct"] == 4
    try:
        post("/learn", {"chosen": [1]})
        raise AssertionError("a second pick")
    except urllib.error.HTTPError as e:
        assert e.code == 409
    # the Trial reels tab: Claude's plan -> a question -> Claude's reply -> Make -> `wait` -> a render lands as a trial
    def trials(j):
        with contextlib.redirect_stdout(io.StringIO()):
            trials_propose(folder, json.dumps(j))
    for bad in ({"versions": []}, {"versions": [{"kinds": ["fast"]}]}, {"versions": [{"kinds": ["same", "rewind"]}]}):
        try:
            trials(bad)
            raise AssertionError(f"trials {bad}")
        except SystemExit as e:
            assert e.code, bad
    plan = {"message": "Make trial reels of this?", "hooks": [{"text": "I'm so hyped", "from": "your first take"}],
            "versions": [{"kinds": ["hooks"], "line": "Opens on the first take"}, {"kinds": "claude"}],
            "idea": {"kinds": ["animations"], "line": "New overlays"}}
    try:
        post("/trials", {"action": "skip"})
        raise AssertionError("a pick before any plan")
    except urllib.error.HTTPError as e:
        assert e.code == 409
    trials(plan)
    t = json.loads(get("/state").read())["trials"]
    assert t["state"] == "proposed" and t["versions"][1]["kinds"] == ["claude"] and t["idea"]["kinds"] == ["animations"], t
    for bad in ({"action": "make", "versions": []}, {"action": "ask"}, {"action": "make", "versions": [{"kinds": ["same", "rewind"]}]}):
        try:
            post("/trials", bad)
            raise AssertionError(f"post {bad}")
        except urllib.error.HTTPError as e:
            assert e.code == 400, bad
    post("/trials", {"action": "ask", "text": "make t2 the motion graphics bit"})
    try:
        post("/trials", {"action": "skip"})
        raise AssertionError("a pick while Claude reads the question")
    except urllib.error.HTTPError as e:
        assert e.code == 409
    out = waited()
    assert out.startswith("TRIALS ASK: make t2 the motion graphics bit") and "trials --propose" in out, out
    try:   # a note before anything is made: the tab's own Ask box is for that
        post("/trials", {"action": "note", "text": "x"})
        raise AssertionError("a note before Make")
    except urllib.error.HTTPError as e:
        assert e.code == 409
    trials({**plan, "versions": [plan["versions"][0], {"kinds": ["section"], "line": "0:06 to 0:15"}], "reply": "Done. t2 is 0:06 to 0:15."})
    t = load(folder / "review.json")["trials"]
    assert t["asks"][0]["reply"] == "Done. t2 is 0:06 to 0:15." and t["v"] == 2 and t["handled"] is None, t
    post("/trials", {"action": "make", "hooks": [0, 0], "versions": [{"kinds": ["rewind", "animations"]}, {"kinds": "claude"}, {"kinds": ["section"], "line": "0:06 to 0:15"}]})
    out = waited()
    assert out.startswith("TRIALS: make 3 trial reels.") and "t1: Rewind + New animations" in out and "t2: Claude decides" in out, out
    assert "t3: One section (0:06 to 0:15)" in out and 'spare hooks to use: "I\'m so hyped"' in out and "--trial" in out, out
    with contextlib.redirect_stdout(io.StringIO()):
        cmd_alt(ns(name="t1", video=str(vid), transcript=None, trial=True), folder)
    d = load(folder / "review.json")
    assert d["trials"]["state"] == "chosen" and next(a for a in d["alts"] if a["name"] == "t1")["trial"] is True, d["alts"]
    # feedback once they are made: notes for one version (with its time) or all, Claude's reply under them
    post("/trials", {"action": "note", "text": "the hook is too long", "for": "t1", "t": 2.34})
    post("/trials", {"action": "note", "text": "titles bigger", "for": "t9"})   # not a version: all of them
    out = waited()
    assert out.startswith("TRIALS NOTE:") and "t1 at 2.3s: the hook is too long" in out and "all of them: titles bigger" in out, out
    assert "trials --reply" in out and "alt t1 --video" in out, out
    with contextlib.redirect_stdout(io.StringIO()):
        trials_reply(folder, "t1 opens on the short hook now; titles are bigger on all three.")
    tn = load(folder / "review.json")["trials"]["notes"]
    assert [x["reply"] for x in tn] == ["", "t1 opens on the short hook now; titles are bigger on all three."], tn
    try:
        trials_reply(folder, "again")
        raise AssertionError("a reply with nothing to answer")
    except SystemExit as e:
        assert "no trial reel notes" in str(e)
    update(folder / "review.json", lambda d: (d.pop("trials"), d.update(alts=[a for a in d["alts"] if a["name"] != "t1"])))
    # a skill style ("skill" in its style.json): the ticked rules go into that skill's own SKILL.md (skillrules.py)
    sk_md = tmp / "skills" / "alice-edit" / "SKILL.md"
    sk_md.parent.mkdir(parents=True)
    sk_md.write_text("---\nname: alice-edit\ndescription: x\n---\n\n# Alice edit\n", encoding="utf-8")
    sp.write_text('{"handle": "alice", "skill": "alice-edit"}', encoding="utf-8")
    update(folder / "review.json", lambda d: d["learn"].update(state="reading"))
    with contextlib.redirect_stdout(io.StringIO()):
        learn(propose=json.dumps([{"rule": "Logos beside the head", "section": "visuals", "why": "one covered the chin"}]))
    assert "alice-edit skill" in learn_prompt(folder, load(folder / "review.json")), learn_prompt(folder, load(folder / "review.json"))
    update(folder / "review.json", lambda d: d["learn"].update(state="chosen", chosen=[0]))
    with contextlib.redirect_stdout(io.StringIO()):
        learn(done="")
    t = sk_md.read_text(encoding="utf-8")
    assert "## Learned rules\n\n- Logos beside the head. Why: one covered the chin. (" in t and "## Log" in t, t
    # the per-round learn at this-style on a skill style: the same SKILL.md, never the settings or edit-like skill
    with contextlib.redirect_stdout(io.StringIO()):
        learn(scope="this-style", rule=[[str(c2["id"]), "captions", "Captions two lines at most", "captions.size_pct=5"]])
    t = sk_md.read_text(encoding="utf-8")
    assert "- Captions two lines at most. Why: review note: " in t and t.count("\n- ") >= 3, t
    assert next(c for c in load(folder / "review.json")["comments"] if c["id"] == c2["id"])["taste"] == "skill"
    assert not any(r["rule"] == "Captions two lines at most" for r in taste.load_rules())
    assert json.loads((sp.parent / "style.overrides.json").read_text(encoding="utf-8"))["captions"]["size_pct"] == 4
    assert "Logos beside" not in (tmp / "skills" / "edit-like-alice" / "SKILL.md").read_text(encoding="utf-8")
    # Undo on a receipt: the rule comes out of the skill (or the style's rules) again, once
    d = load(folder / "review.json")
    sr = d["receipts"][next(c for c in d["comments"] if c["id"] == c2["id"])["receipt"] - 1]
    assert sr["kind"] == "skill" and sr["style"] == "@alice" and sr["rule"] == "Captions two lines at most", sr
    assert post("/undo", {"id": sr["id"]})["msg"] == "Removed from @alice."
    assert "Captions two lines at most" not in sk_md.read_text(encoding="utf-8").split("## Log")[0]
    try:
        post("/undo", {"id": sr["id"]})
        raise AssertionError("undo twice")
    except urllib.error.HTTPError as e:
        assert e.code == 409
    tr_ = next(x for x in d["receipts"] if x["from"] == "teach" and x["rule"] == "Keep the pauses short")
    assert tr_["kind"] == "settings" and tr_["style"] == "@alice", tr_
    post("/undo", {"id": tr_["id"]})
    assert not any(r["rule"] == "Keep the pauses short" for r in taste.load_rules())
    if old_skills is None:
        os.environ.pop("AI_EDITOR_SKILLS", None)
    else:
        os.environ["AI_EDITOR_SKILLS"] = old_skills
    # every round replays its own video: the next render overwriting the same file changes no earlier tab
    rs = load(folder / "review.json")["rounds"]
    assert [Path(r["video"]).name for r in rs] == ["v-cut1.mp4", "v-edit1.mp4"], rs
    size = vid.stat().st_size
    vid.write_bytes(b"the next render")
    assert len(get("/video?k=cut-1").read()) == size and len(get("/video?k=edit-1&alt=wide").read()) == size
    # the footer after a pick-up: an approve says approved, a send says Claude is working (node runs the page's own function)
    page = HTML.read_text(encoding="utf-8")
    js = re.search(r"^function listenText\(S\)\{.*?\n\}", page, re.M | re.S)
    alive = re.search(r"^function alive\(S\)\{.*?\}$", page, re.M)
    assert js and alive, "review.html has no listenText() or alive()"
    if shutil.which("node"):
        ev = lambda t, n: {"listening": False, "sent": True, "round": n, "comments": [],
                           "events": [{"type": t, "stage": "edit", "handled": True}]}
        mid = {"listening": False, "busy": True, "sent": False, "round": 1, "stage": "edit", "comments": [], "events": []}
        nc = re.search(r"^const newClaude=.*$", page, re.M).group(0)   # notes sent, a new Claude opened
        fresh = dict(ev("send", 1), events=[{"type": "send", "stage": "edit", "handled": False}], claude={"opened": True, "at": time.time()})
        o = subprocess.run(["node", "-e", nc + alive.group(0) + js.group(0) + "for(const s of " + json.dumps(
                            [ev("approve", 0), {**ev("send", 1), "busy": True}, mid, fresh, ev("send", 1)])
                            + ")console.log(listenText(s))"], capture_output=True, text=True, check=True).stdout
        assert o.splitlines() == ["Approved", "Claude is working on the next draft", "",   # mid-round: the Claude control says it
                                  "A new Claude is starting in its own Terminal window", "Claude stopped. Your notes are saved."], o
    # approve on the cut: the style-edit's scripts fill the page's "Making the edit" steps, in place, never twice
    sf = tmp / "edits" / "steps"
    sf.mkdir(parents=True)
    (sf / "review").mkdir()
    save(sf / "review.json", {"folder": str(sf), "name": "steps", "stage": "cut", "round": 1, "sent": False,
                              "comments": [], "events": []})
    assert not step(sf, "captions") and not step(tmp / "nowhere", "captions"), "no approve yet: nothing"
    update(sf / "review.json", lambda d: d.update(sent=True, events=[{"type": "approve", "stage": "cut", "round": 1,
                                                                      "at": now(), "handled": True}]))
    assert step(sf, "captions") and step(sf, "captions") and not step(sf, "nonsense")
    assert step(sf, "visuals") and step(sf, "plan") and step(sf, "plan", log=lg)
    with contextlib.redirect_stdout(io.StringIO()):
        cmd_status(ns(text="", log=str(lg), done=False, step="render"), sf)
    act = load(sf / "review.json")["activity"]
    assert [x.get("step") for x in act] == ["captions", "visuals", "plan", "render"], act
    assert [x["done"] for x in act] == [True, True, True, False] and act[-1]["text"] == "Making the video", act
    assert act[2]["log"] == str(lg.resolve()) and busy(sf)
    srv3, url3 = serve(sf, 0, open_browser=False)   # the page's Stop takes the approve back; `status` says STOPPED
    threading.Thread(target=srv3.serve_forever, daemon=True).start()
    b3, t3 = url3.split("/?t=")
    s3 = json.loads(urllib.request.urlopen(b3 + "/state?t=" + t3).read())
    assert s3["making"]["style"] is None and list(s3["making"]["steps"]) == list(EDIT_STEPS), s3.get("making")
    keep_d = load(sf / "review.json")
    update(sf / "review.json", lambda d: d["events"][-1].update(handled=False))   # Stop before `wait` took the approve
    urllib.request.urlopen(urllib.request.Request(b3 + "/event?t=" + t3, b'{"type":"stop"}', method="POST"))
    d = load(sf / "review.json")
    assert not d["sent"] and d["stopped"] and not making_edit(d) and not step(sf, "render"), d
    assert all(e["handled"] for e in d["events"]), "a stopped approve never reaches `wait`"
    try:   # and the edit cannot open on the stopped page
        with contextlib.redirect_stdout(io.StringIO()) as o:
            cmd_round(ns(video=str(folder / "review" / "v-cut1.mp4"), stage="edit", transcript=None, plan=None,
                         note=None, name=None), sf)
        raise AssertionError("an edit round after Stop")
    except SystemExit as e:
        assert e.code == 3 and "STOPPED" in o.getvalue()
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_status(ns(text="", log=None, done=False, step="render"), sf)
        raise AssertionError("status after a stop on the approve")
    except SystemExit as e:
        assert e.code == 3
    srv3.shutdown()
    save(sf / "review.json", keep_d)
    assert making_style(sf) is None and making_style(folder) == "@alice's style"
    with tempfile.TemporaryDirectory() as pd:   # the approve shows what visual-prep already made on this cut
        pd = Path(pd)
        for f in ("decisions.json", "prep-decisions.json", "captions.json", "visuals.json"):
            (pd / f).write_text("[]", encoding="utf-8")
        pdd = {"round": 1, "activity": []}
        assert prepared_steps(pd, pdd) == ["captions", "visuals"] and all(x["done"] for x in pdd["activity"]), pdd
        (pd / "decisions.json").write_text("[1]", encoding="utf-8")   # re-cut since: nothing is claimed
        assert prepared_steps(pd, {"round": 1, "activity": []}) == []
    from ai_editor import styleskill
    keep_names, styleskill.names = styleskill.names, lambda: {"alice": {"name": "Card edit"}}
    try:   # a named style shows its name, never the folder id ("@own-card-edit's style")
        assert making_style(folder) == "the Card edit style", making_style(folder)
    finally:
        styleskill.names = keep_names
    with contextlib.redirect_stdout(io.StringIO()):
        cmd_round(ns(video=str(folder / "review" / "v-cut1.mp4"), stage="edit", transcript=None, plan=None, note=None,
                     name=None), sf)
    d = load(sf / "review.json")
    assert not making_edit(d) and all(x["done"] for x in d["activity"]) and not step(sf, "render"), "the edit landed"
    d.update(sent=True, events=d["events"] + [{"type": "send", "stage": "edit", "round": 1, "at": now(), "handled": True}])
    save(sf / "review.json", d)
    assert step(sf, "render"), "a sent edit round is being redone: steps again"
    # "just the cut": final, so an approved cut makes no edit and takes no steps
    d.update(stage="cut", final=True, events=d["events"] + [{"type": "approve", "stage": "cut", "round": 1,
                                                             "at": now(), "handled": True}])
    save(sf / "review.json", d)
    assert not making_edit(load(sf / "review.json")) and not step(sf, "plan")
    # the lock: writers in many threads (and processes) never lose an update or share a tmp file
    cnt = tmp / "count.json"
    save(cnt, {"n": 0})
    ths = [threading.Thread(target=lambda: [update(cnt, lambda d: d.update(n=d["n"] + 1)) for _ in range(25)]) for _ in range(4)]
    [t.start() for t in ths]
    [t.join() for t in ths]
    sub = [subprocess.Popen([sys.executable, "-c", f"import sys; sys.path.insert(0, {str(Path(__file__).parent)!r}); "
                             f"import review; [review.update(review.Path({str(cnt)!r}), lambda d: d.update(n=d['n'] + 1)) "
                             f"for _ in range(25)]"]) for _ in range(2)]
    assert all(x.wait() == 0 for x in sub)
    assert load(cnt)["n"] == 150 and not list(tmp.glob("count*.tmp")) and not (tmp / "count.json.lock").exists()
    (tmp / "count.json.lock").touch()
    os.utime(tmp / "count.json.lock", (time.time() - 30, time.time() - 30))   # a writer that died holding it
    update(cnt, lambda d: d.update(n=0))
    # round 0: the raw clip opens before the cut. No approve or stop; a note waits for round 1, moved onto the cut
    vid.unlink()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:duration=6",
                    "-pix_fmt", "yuv420p", str(vid)], check=True)
    rf = tmp / "edits" / "raw"
    with contextlib.redirect_stdout(io.StringIO()):
        cmd_start(ns(video=str(vid), stage="cut", transcript=None, plan=None, note=None, name=None, raw=True), rf)
    d0 = load(rf / "review.json")
    assert (d0["round"], d0["raw"], d0["sent"]) == (0, True, True) and d0["events"][-1]["handled"], d0
    srv2, url2 = serve(rf, 0, open_browser=False)
    threading.Thread(target=srv2.serve_forever, daemon=True).start()
    urllib.request.urlopen(url2).read()   # a server that answered: its port sits in TIME_WAIT after it stops
    srv2.shutdown()
    srv2.server_close()
    srv2, again = serve(rf, 0, open_browser=False)   # a restart keeps the same address, so open tabs keep working
    assert again == url2, (again, url2)
    if os.name != "nt":
        assert (rf / "review" / ".server").stat().st_mode & 0o777 == 0o600
    threading.Thread(target=srv2.serve_forever, daemon=True).start()
    b2, t2 = url2.split("/?t=")
    p2 = lambda p, b: urllib.request.urlopen(urllib.request.Request(b2 + p + "?t=" + t2, json.dumps(b).encode(), method="POST"))
    for t in ("approve", "stop"):
        try:
            p2("/event", {"type": t})
            raise AssertionError(t + " on the raw clip")
        except urllib.error.HTTPError as e:
            assert e.code == 409, e
    n0 = json.loads(p2("/comment", {"t": 4.0, "text": "cut this bit"}).read())
    assert n0["queued"] and n0["round"] == 1, n0
    (rf / "decisions.json").write_text(json.dumps([{"start": 0.0, "end": 1.0}, {"start": 3.0, "end": 6.0}]), encoding="utf-8")
    cut = tmp / "rawcut.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(vid), "-t", "4", str(cut)], check=True)
    with contextlib.redirect_stdout(io.StringIO()):
        cmd_start(ns(video=str(cut), stage="cut", transcript=None, plan=None, note=None, name=None, raw=False), rf)
    d1 = load(rf / "review.json")
    c = next(c for c in d1["comments"] if c["id"] == n0["id"])
    assert (d1["round"], d1["sent"], "raw" in d1) == (1, False, False) and [r["round"] for r in d1["rounds"]] == [0, 1], d1
    assert (c["round"], c["t"], c["moved"], "queued" in c) == (1, 2.0, "words", False), c
    p2("/event", {"type": "approve"})
    assert "learn" not in load(rf / "review.json"), "the cut's approve is not the end: nothing to learn yet"
    # the final approve with no notes all session: the panel says so, LEARN asks nothing
    update(rf / "review.json", lambda d: d.update(final=True, sent=False, comments=[]))
    p2("/event", {"type": "approve"})
    assert load(rf / "review.json")["learn"]["state"] == "none"
    o = io.StringIO()
    with contextlib.redirect_stdout(o):
        cmd_wait(rf, poll=0.01)
    assert "LEARN: no notes this session" in o.getvalue(), o.getvalue()
    # the transcript editor: Apply turns restore/cut word ranges into spans.json, keeps spans.prev.json, and `wait`
    # exits with the EDITS line. Restoring part of a span splits it; a cut inside a word takes the whole word
    ef = tmp / "edits" / "tx"
    ws = "so the thing is the thing is we ship it today okay".split()
    (ef / "review").mkdir(parents=True)
    (ef / "words.raw.json").write_text(json.dumps([{"text": w, "start": i * 0.5, "end": i * 0.5 + 0.4, "type": "word"}
                                                    for i, w in enumerate(ws)] + [{"text": "untimed", "type": "word"}]), encoding="utf-8")
    sp0 = [{"text": "the thing is the thing is", "kind": "retake", "occurrence": 1, "note": "keeper after"},
           {"text": "okay", "kind": "filler"}]
    (ef / "spans.json").write_text(json.dumps(sp0), encoding="utf-8")
    (ef / "decisions.json").write_text(json.dumps([{"start": 0.0, "end": 0.45}, {"start": 3.45, "end": 6.0}]), encoding="utf-8")
    tv = tmp / "tx.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=30:duration=3",
                    "-pix_fmt", "yuv420p", str(tv)], check=True)
    with contextlib.redirect_stdout(io.StringIO()):
        cmd_start(ns(video=str(tv), stage="cut", transcript=None, plan=None, note=None, name=None, raw=False), ef)
    tx = load(ef / "review" / load(ef / "review.json")["data"])["transcript"]
    flat = [x for ln in tx["lines"] for x in ln["tokens"] if "w" in x]
    assert flat[1] == {"w": "the", "t": None, "s": 0.5, "e": 0.9, "k": "retake", "g": 0, "n": "keeper after"} and flat[-1] == {"w": "untimed", "t": None, "nt": 1}, flat
    assert tx["kept"] == [[0.0, 0.45], [3.45, 6.0]], tx
    srv3, url3 = serve(ef, 0, open_browser=False)
    threading.Thread(target=srv3.serve_forever, daemon=True).start()
    b3, t3 = url3.split("/?t=")
    p3 = lambda b: json.loads(urllib.request.urlopen(urllib.request.Request(b3 + "/edits?t=" + t3, json.dumps(b).encode(), method="POST")).read())
    # a data file from before words had raw times: /data rebuilds it, so the page can edit and follow the words
    dp = ef / "review" / load(ef / "review.json")["data"]
    old = load(dp)
    for ln in old["transcript"]["lines"]:
        ln["tokens"] = [{k: v for k, v in x.items() if k not in ("s", "e", "k", "g", "n")} for x in ln["tokens"] if not x.get("nt")]
    save(dp, old)
    got = json.loads(urllib.request.urlopen(b3 + "/data?k=cut-1&t=" + t3).read())
    assert got["transcript"]["lines"][0]["tokens"][1]["s"] == 0.5, got
    try:
        urllib.request.urlopen(urllib.request.Request(b3 + "/edits", b"{}", method="POST"))
        raise AssertionError("/edits without the token")
    except urllib.error.HTTPError as err:
        assert err.code == 403
    assert p3({"restore": [[6.0, 6.4]]})["event"] is False and not (ef / "spans.prev.json").exists()   # kept already: no change
    # restore "is the" (1.5-2.4 s): the retake span splits into two; cut "ship" by a range inside the word
    r = p3({"restore": [[1.5, 2.4]], "cut": [[4.05, 4.1]]})
    assert (r["restored"], r["cut"], r["event"]) == (2, 1, True), r
    sp1 = load(ef / "spans.json")
    assert sp1 == [{"kind": "retake", "note": "keeper after", "text": "the thing", "occurrence": 1},
                   {"kind": "retake", "note": "keeper after", "text": "thing is", "occurrence": 2},
                   {"kind": "manual", "note": "cut on the review page", "text": "ship"},
                   {"kind": "filler", "text": "okay"}], sp1
    assert load(ef / "spans.prev.json") == sp0
    try:   # Claude has the round now
        p3({"cut": [[0.0, 0.4]]})
        raise AssertionError("edits while Claude has the round")
    except urllib.error.HTTPError as err:
        assert err.code == 409
    o = io.StringIO()
    with contextlib.redirect_stdout(o):
        cmd_wait(ef, poll=0.01)
    o = o.getvalue()
    assert o.startswith("EDITS 2 transcript edits applied to spans.json: rebuild, render, verify, round"), o
    assert 'restore 1.50-2.40s: "is the"' in o and 'cut 4.05-4.10s: "ship"' in o and "build_timeline.py" in o and "\nSEND: tx the cut, round 1" in o, o
    # Stop while Claude applies them: spans.json goes back
    urllib.request.urlopen(urllib.request.Request(b3 + "/event?t=" + t3, b'{"type": "stop"}', method="POST"))
    assert load(ef / "spans.json") == sp0 and not load(ef / "review.json")["sent"]
    # a whole span restored: it goes; the next span keeps its fields
    assert p3({"restore": [[5.5, 5.9]]})["restored"] == 1 and load(ef / "spans.json") == sp0[:1]
    # the pause trim's words: Restore puts their time in keep.json (build_timeline.py leaves it in), a removed pause
    # comes back whole, Stop puts keep.json back, and a later cut takes its words out of keep.json again
    stop3 = lambda: urllib.request.urlopen(urllib.request.Request(b3 + "/event?t=" + t3, b'{"type": "stop"}', method="POST"))
    stop3()
    (ef / "decisions.json").write_text(json.dumps([{"start": 0.0, "end": 0.45}, {"start": 3.45, "end": 4.45}, {"start": 5.45, "end": 6.0}]),
                                       encoding="utf-8")   # "it today" (4.5-5.4 s) fall in a trimmed pause
    r = p3({"restore": [[4.5, 5.4]], "pause": [[0.4, 0.5]]})
    assert (r["restored"], r["pauses"], r["event"]) == (2, 1, True), r
    assert load(ef / "keep.json") == [{"start": 0.4, "end": 0.5}, {"start": 4.5, "end": 5.4}] and load(ef / "spans.json") == sp0
    assert load(ef / "keep.prev.json") == []
    o = edits_text(ef, load(ef / "review.json")["events"][-1])
    assert 'restore 4.50-5.40s: "it today"' in o and "pause back 0.40-0.50s" in o and "keep.json: 2 range(s)" in o, o
    stop3()
    assert load(ef / "keep.json") == [] and load(ef / "spans.json") == sp0
    assert apply_edits(ef, [[3.5, 3.9]], [])["restored"] == 0   # "we" plays already: nothing to keep
    assert apply_edits(ef, [[4.5, 5.4]], [])["keep"] == 1
    r = apply_edits(ef, [], [[5.0, 5.4]])
    assert r["cut"] == 1 and load(ef / "keep.json") == [{"start": 4.5, "end": 5.0}], r
    assert {"kind": "manual", "note": "cut on the review page", "text": "today"} in load(ef / "spans.json")
    # two Applies at once: one wins, the other is refused, and spans.prev.json is what was there before both
    before = load(ef / "spans.json")
    outs = []
    th = [threading.Thread(target=lambda c=c: outs.append(_post_code(b3 + "/edits?t=" + t3, {"cut": [c]}))) for c in ([0.0, 0.4], [3.5, 3.9])]
    [x.start() for x in th]
    [x.join() for x in th]
    assert sorted(outs) == [200, 409] and load(ef / "spans.prev.json") == before, outs
    # while Claude applies them: send and approve are refused (Stop first)
    assert _post_code(b3 + "/event?t=" + t3, {"type": "send"}) == 409 and _post_code(b3 + "/event?t=" + t3, {"type": "approve"}) == 409
    # Stop after Claude changed spans.json itself: nothing is put back over Claude's change; round refuses while stopped
    mine = load(ef / "spans.json") + [{"text": "so", "kind": "filler", "occurrence": 1}]
    save(ef / "spans.json", mine)
    stop3()
    assert load(ef / "spans.json") == mine
    try:
        cmd_round(ns(video=str(tv), stage=None, transcript=None, plan=None, note=None, name=None), ef)
        raise AssertionError("round while stopped")
    except SystemExit as err:
        assert "STOPPED" in str(err)
    # an Apply then a send in one `wait`: the EDITS block still prints
    def two(d):
        d["events"] += [{"type": "edits", "stage": "cut", "round": d["round"], "at": now(), "handled": False, "n": 1,
                         "restore": [], "cut": [[0.0, 0.4]], "pause": [], "counts": {"restored": 0, "cut": 1, "keep": 0}},
                        {"type": "send", "stage": "cut", "round": d["round"], "at": now(), "handled": False}]
    update(ef / "review.json", two)
    o = io.StringIO()
    with contextlib.redirect_stdout(o):
        cmd_wait(ef, poll=0.01)
    assert "EDITS 1 transcript edit applied" in o.getvalue() and "\nSEND: tx" in o.getvalue(), o.getvalue()
    # the reviewer's cases, straight on apply_edits: a restore never sweeps in a hidden (cough) span; a cut beside an
    # overlapping (laughs) merges into one span that builds; an untimed "the" counts in "occurrence" as build counts it
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills" / "cut" / "scripts"))
    import build_timeline

    def mk(words, spans):
        f = Path(tempfile.mkdtemp(dir=tmp))
        (f / "words.raw.json").write_text(json.dumps(words), encoding="utf-8")
        (f / "spans.json").write_text(json.dumps(spans), encoding="utf-8")
        return f
    W_ = lambda t, a, b, ty="word": {"text": t, "start": a, "end": b, "type": ty}
    f = mk([W_("a", 0, .4), W_("b", .5, .9), W_("(cough)", 1.0, 1.3, "audio_event"), W_("c", 1.4, 1.8)],
           [{"text": "b", "kind": "retake"}, {"text": "(cough)", "kind": "audio_event"}])
    apply_edits(f, [[0.5, 1.8]], [])
    assert load(f / "spans.json") == [{"text": "(cough)", "kind": "audio_event"}], load(f / "spans.json")
    f = mk([W_("so", 0, .5), W_("(laughs)", .45, .9, "audio_event"), W_("yes", 1.0, 1.3)], [{"text": "(laughs)", "kind": "audio_event"}])
    apply_edits(f, [], [[0, 0.5]])
    assert load(f / "spans.json") == [{"kind": "audio_event", "text": "so (laughs)"}], load(f / "spans.json")
    toks_ = [t for t in load(f / "words.raw.json") if t.get("type") in ("word", "audio_event")]
    assert len(build_timeline.resolve_spans(load(f / "spans.json"), toks_)) == 1
    f = mk([W_("the", 0, .2), {"text": "the", "type": "word"}, W_("the", 1, 1.2)], [])
    apply_edits(f, [], [[1, 1.2]])
    toks_ = [t for t in load(f / "words.raw.json") if t.get("type") in ("word", "audio_event")]
    assert load(f / "spans.json")[0]["occurrence"] == 3 and build_timeline.resolve_spans(load(f / "spans.json"), toks_)[0]["start"] == 1
    # what changed between two rounds: the plan's cards, zooms, captions, title and music; the cut's words
    A = {"cards": [{"src": "a.png", "trigger_word": "notion", "start": 1, "end": 2, "box": [10, 10, 40, 20]},
                   {"src": "b.png", "trigger_word": "github", "start": 3, "end": 4},
                   {"src": "c.png", "trigger_word": "react", "start": 5, "end": 6, "box": [0, 0, 50, 50]}],
         "zooms": [{"start": 0.5, "end": 1.5, "scale": 1.2}], "texts": [{"kind": "title", "text": "old", "start": 0, "end": 1}],
         "captions": {"style": {"size_pct": 4}, "chunks": [{"text": "hello wrold", "start": 0.2, "end": 0.8}]}, "music": {"src": "m"}}
    B = json.loads(json.dumps(A))
    B["cards"][0]["src"] = "a2.png"                       # swapped
    del B["cards"][1]                                      # removed
    B["cards"][1]["box"] = [0, 0, 80, 80]                  # bigger
    B["zooms"], B["texts"][0]["text"] = [], "new"
    B["captions"]["style"]["size_pct"], B["captions"]["chunks"][0]["text"] = 5, "hello world"
    got = [c["text"] for c in plan_changes(A, B, music=True)]
    for want in ('Swapped the card on "notion"', 'Removed the card on "github"', 'Made the card on "react" bigger',
                 "Removed the zoom at 0:00.5", 'Title now reads "new"', "Captions bigger", 'Caption now reads "world"',
                 "Changed the music"):
        assert want in got, (want, got)
    assert plan_changes(A, A) == [] and plan_changes(None, A) == []
    tok = lambda w, t: {"w": w, "t": t, "s": 0, "e": 0}
    o = {"lines": [{"t": 0, "tokens": [tok("a", 0), tok("b", 1), tok("c", None), tok("d", 2)]}]}
    n = {"lines": [{"t": 0, "tokens": [tok("a", 0), tok("b", None), tok("c", 1), tok("d", 2)]}]}
    assert cut_changes(o, n) == [{"t": 1, "text": 'Cut "b"'}, {"t": 1, "text": 'Put back "c"'}], cut_changes(o, n)
    it = screen_items(tmp, {"width": 1080, "height": 1920, "cards": A["cards"] + [{"anim": {"type": "notes"}, "start": 7, "end": 8, "layout": "split"}],
                            "captions": {"style": {"size_pct": 4, "y_pct": 66}, "chunks": A["captions"]["chunks"]}, "zooms": A["zooms"], "texts": A["texts"]})
    assert it["cards"][0]["label"] == 'the picture on "notion"' and it["cards"][1]["box"] == [0, 0, 100, 100], it["cards"]
    assert it["cards"][3]["label"] == "the notes animation" and it["cards"][3]["box"] == [0, 0, 100, 50]
    assert it["cap"]["y"] == 66 and it["captions"][0]["text"] == "hello wrold" and it["zooms"] == [{"s": 0.5, "e": 1.5}]
    # a note is tagged with what was clicked, else what is on screen at that exact time; the quote is one caption page
    tp = tmp / "tags.json"
    tp.write_text(json.dumps({"cards": [{"start": 0, "end": 9, "trigger_word": "tutorials"}], "zooms": [{"start": 2, "end": 6}],
                              "captions": {"chunks": [{"start": 2, "end": 3, "text": "steal these"}, {"start": 3, "end": 4.5, "text": "background songs"}]}}),
                  encoding="utf-8")
    assert note_tags(tp, None, "edit", 2.0, 6.0, {"k": "zooms"}) == ("steal these", None), "a zoom click: no card tag"
    assert note_tags(tp, None, "edit", 3.0, 4.5, {"k": "captions", "text": "background songs"}) == ("background songs", None)
    assert note_tags(tp, None, "edit", 3.2)[0] == "background songs" and note_tags(tp, None, "edit", 3.2)[1]["trigger_word"] == "tutorials"
    # go back: round 1's files and render return as round 3; the open note moves onto it
    gb = tmp / "edits" / "goback"
    gb.mkdir(parents=True)
    (gb / "plan.json").write_text(json.dumps(A), encoding="utf-8")
    (gb / "a.png").write_text("old", encoding="utf-8")
    shutil.copy(vid, gb / "render.mp4")
    with contextlib.redirect_stdout(io.StringIO()):
        cmd_start(ns(video=str(gb / "render.mp4"), stage="edit", transcript=None, plan=str(gb / "plan.json"), note=None, name=None), gb)
        (gb / "plan.json").write_text(json.dumps(B), encoding="utf-8")
        (gb / "overrides.json").write_text(json.dumps({"zooms": "none here"}), encoding="utf-8")   # a "no zoom here" fix
        cmd_round(ns(video=str(gb / "render.mp4"), stage=None, transcript=None, plan=None, note=None, name=None,
                     changed=["Captions one size bigger"]), gb)
    d2 = load(gb / "review.json")
    assert d2["rounds"][-1]["changed"] == ["Captions one size bigger"] and d2["rounds"][-1]["snap"] == "snap-edit2"
    assert 'Swapped the card on "notion"' in [c["text"] for c in data_of(gb, d2["data"])["changes"]]
    d2["comments"].append({"id": 1, "round": 2, "stage": "edit", "t": 1.0, "t_end": None, "alt": None, "text": "x", "words": "",
                           "card": None, "frame": "f.jpg", "images": [], "status": "open", "reply": None, "new_t": None, "at": now()})
    save(gb / "review.json", d2)
    for bad in (2, 9):
        try:
            go_back(gb, bad)
            raise AssertionError(f"went back to round {bad}")
        except ValueError:
            pass
    (gb / "a.png").write_text("new", encoding="utf-8")   # round 2 rebuilt round 1's picture in place
    d3 = go_back(gb, 1)
    assert (gb / "a.png").read_text(encoding="utf-8") == "old", "the picture round 1 showed is back"
    assert not (gb / "overrides.json").exists(), "a file made after round 1 goes: the next re-plan keeps round 1's zoom"
    assert d3["round"] == 3 and d3["back_to"] == 1 and load(gb / "plan.json") == A, "round 1's plan is back"
    assert d3["comments"][0]["round"] == 3 and "queued" not in d3["comments"][0], "the open note moved onto the restored round"
    assert 'Swapped the card on "notion"' in [c["text"] for c in data_of(gb, d3["data"])["changes"]], "round 3 shows the undo"
    assert d3["events"][-1]["type"] == "back" and Path(d3["video"]).name == "v-edit3.mp4" and Path(d3["video"]).exists()
    update(gb / "review.json", lambda d: d.update(sent=True))
    try:
        go_back(gb, 2)
        raise AssertionError("went back while Claude has the round")
    except ValueError:
        pass
    # a round whose sent notes nobody answered is refused, with the resolve lines; answered, it opens
    rnd = ns(video=str(gb / "render.mp4"), stage=None, transcript=None, plan=None, note=None, name=None, changed=None)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_round(rnd, gb)
        raise AssertionError("opened a round over an unanswered note")
    except SystemExit as e:
        assert "REFUSED" in str(e) and "resolve 1 fixed" in str(e), e
    with contextlib.redirect_stdout(io.StringIO()):
        cmd_resolve(ns(id=1, status="fixed", reply="did it", new_t=None), gb)
        cmd_round(rnd, gb)
    assert load(gb / "review.json")["round"] == 4
    srv3.shutdown()
    srv3.server_close()
    srv2.shutdown()
    srv2.server_close()
    srv.shutdown()
    srv.server_close()
    if os.name != "nt":   # the Claude control: a running `claude` here is working, Stop ends it, then it is off
        cf = tmp / "clc"
        (cf / "review").mkdir(parents=True)
        fake = tmp / "claude"
        fake.symlink_to(shutil.which("sleep") or "/bin/sleep")   # a copy of a system binary is killed on macOS: a link
        proc = subprocess.Popen([str(fake), "30"])
        try:
            assert claude_state(cf)["state"] == "off" and not stop_claude(cf), "no Claude ever ran here"
            (cf / "review" / ".claude").write_text(json.dumps({"pid": proc.pid, "tty": "/dev/ttys-x", "app": "Terminal", "session": "s1", "cwd": "/a b"}), encoding="utf-8")
            st = claude_state(cf)
            assert st["state"] == "working" and st["show"] and st["last"] and st["resume"] == "cd '/a b' && claude --resume s1", st
            (cf / "review" / ".listening").touch()
            assert claude_state(cf)["state"] == "waiting"
            assert stop_claude(cf) and proc.wait(5) is not None and not (cf / "review" / ".listening").exists()
            assert claude_state(cf) == {**st, "state": "off", "show": False}, claude_state(cf)
        finally:
            proc.kill()
    shutil.rmtree(tmp, ignore_errors=True)
    print("review demo ok")


def main():
    if sys.argv[1:2] == ["demo"]:
        return demo()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", help="the edit folder: edits/<name> (or product/<name>, clips/<name>)")
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("start")
    s.add_argument("--video", required=True)
    s.add_argument("--stage", choices=["cut", "edit"], default="edit")
    s.add_argument("--transcript", help="words timed to this video (edits/<name>/words.json)")
    s.add_argument("--plan", help="plan.json, so each note names the card on screen")
    s.add_argument("--name", help="what to call this video when the round has others (default main)")
    s.add_argument("--note")
    s.add_argument("--raw", action="store_true", help="round 0: the raw clip, shown while the cut is made")
    s.add_argument("--stills", action="store_true", help="the stills before the render (edit.py storyboard): approve renders")
    s = sp.add_parser("serve")
    s.add_argument("--port", type=int, default=0)
    s.add_argument("--no-open", action="store_true", help="do not open the browser (tests, headless checks)")
    sp.add_parser("wait")
    sp.add_parser("final", help="the cut is the finished video: no styled edit follows its approve")
    s = sp.add_parser("round")
    s.add_argument("--video", required=True)
    s.add_argument("--stage", choices=["cut", "edit"])
    s.add_argument("--stills", action="store_true", help="the stills before the render (edit.py storyboard): approve renders")
    s.add_argument("--transcript")
    s.add_argument("--plan")
    s.add_argument("--note")
    s.add_argument("--name")
    s.add_argument("--changed", action="append", metavar="TEXT",
                   help='anything changed beyond the notes, one line each: "Captions one size smaller" (repeat)')
    s = sp.add_parser("back", help="go back to an earlier round of this stage: its files and render return as a new round")
    s.add_argument("n", type=int, metavar="ROUND")
    s = sp.add_parser("status")
    s.add_argument("text", nargs="?", default="")
    s.add_argument("--log", help="a render log; the page shows the last N/M in it as progress")
    s.add_argument("--step", choices=list(EDIT_STEPS), help="one of the edit's steps: fills the page's Making the edit bar")
    s.add_argument("--done", action="store_true")
    s = sp.add_parser("alt")
    s.add_argument("name")
    s.add_argument("--video", required=True)
    s.add_argument("--transcript")
    s.add_argument("--trial", action="store_true", help="a trial reel: listed under Trial reels in the Version menu")
    s = sp.add_parser("resolve")
    s.add_argument("id", type=int)
    s.add_argument("status", choices=["fixed", "wontfix", "open"])
    s.add_argument("--reply")
    s.add_argument("--new-t", type=float, help="where the note's moment is in the new render")
    s = sp.add_parser("learn", help="save the round's preference notes to the user's taste")
    s.add_argument("--scope", choices=["this-style", "style", "video", "everyone"], help="asked once for the batch")
    s.add_argument("--style", help="this-style: the creator style.json (default: the one the edit used)")
    s.add_argument("--rule", nargs="+", action="append", metavar="ARG", help='<id> <section> "<rule>" [key=value]')
    s.add_argument("--none", action="store_true", help="no note in this round is a preference")
    s.add_argument("--propose", metavar="JSON", help="after the final approve: candidate rules for the page's learn panel")
    s.add_argument("--done", nargs="?", const="", metavar="SUMMARY", help="save the rules the user ticked into the style")
    s = sp.add_parser("trials", help="the Trial reels tab: Claude's plan for re-cuts of an approved reel")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--propose", metavar="JSON",
                   help='{"message", "hooks": [{"text", "from"}], "versions": [{"kinds", "line"}], "idea"?, "reply"?}')
    g.add_argument("--reply", metavar="TEXT", help="answer the notes on the made trial reels (TRIALS NOTE)")
    a = ap.parse_args()
    folder = Path(a.folder).resolve()
    if getattr(a, "stage", None) == "edit":  # an edit round reads the edit folder's own files
        for k, f in (("transcript", "words.json"), ("plan", "plan.json")):
            if getattr(a, k, 0) is None and (folder / f).exists():
                setattr(a, k, str(folder / f))
    if a.cmd != "start" and not (folder / "review.json").exists():
        sys.exit(f"no review in {folder}: run `start` first")
    if a.cmd != "serve":   # every Claude-side command marks Claude as working on this edit
        (folder / "review").mkdir(parents=True, exist_ok=True)
        w = who_claude()   # which Claude, and where: Send types into it, or resumes it, before opening a new one
        if w or not (folder / "review" / ".claude").exists():
            (folder / "review" / ".claude").write_text(json.dumps(w), encoding="utf-8")
        else:
            (folder / "review" / ".claude").touch()
        if askhook.session():   # this session's questions now go to this edit's page
            (folder / "review" / ".session").write_text(askhook.session(), encoding="utf-8")
    if a.cmd == "start":
        if not Path(a.video).exists():
            sys.exit(f"no such file: {a.video}")
        cmd_start(a, folder)
    elif a.cmd == "serve":
        srv, url = serve(folder, a.port, open_browser=not a.no_open)
        print(url, flush=True)
        if srv:
            threading.Thread(target=live.reexec_on_change, args=(srv,), daemon=True).start()   # newest code, same port
            try:
                srv.serve_forever()
            except KeyboardInterrupt:
                pass
        else:
            print("already serving this edit" + ("" if a.no_open else "; opened it"))
    elif a.cmd == "wait":
        cmd_wait(folder)
    elif a.cmd == "round":
        cmd_round(a, folder)
    elif a.cmd == "resolve":
        cmd_resolve(a, folder)
    elif a.cmd == "back":
        try:
            d = go_back(folder, a.n)
        except ValueError as e:
            sys.exit(str(e))
        print(f"{stage_name(d['stage'])}, round {d['round']}: round {a.n} again")
    elif a.cmd == "alt":
        cmd_alt(a, folder)
    elif a.cmd == "status":
        cmd_status(a, folder)
    elif a.cmd == "final":
        cmd_final(folder)
    elif a.cmd == "learn":
        cmd_learn(a, folder)
    elif a.cmd == "trials":
        trials_reply(folder, a.reply) if a.reply else trials_propose(folder, a.propose)


if __name__ == "__main__":
    main()
