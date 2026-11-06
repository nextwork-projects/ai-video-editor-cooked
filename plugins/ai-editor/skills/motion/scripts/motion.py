#!/usr/bin/env python3
"""Bespoke motion clips for a style-edit: one HyperFrames + GSAP composition per beat that needs motion.

    python3 motion.py pick edits/NAME [--max 8]   visuals.json -> edits/NAME/motion/<id>/ (template + brief.md)
    python3 motion.py check edits/NAME/motion/ID  every gate, the render, the sheets -> ID/gates.json
    python3 motion.py place edits/NAME            passed clips -> visuals.json video_card beats; failed: the template
    python3 motion.py status edits/NAME           one line per clip
    python3 motion.py strips VIDEO --at 3.2,9.1 --out strips.png [--safe]   10 fps strips round each time
    python3 motion.py demo                        self-check (offline)

pick: the beats route.py's picks sent to a moving template (a count, a list of notes, a flow, a before and
after, a run, a mechanism: MOTION_TYPES) become clips, and so does a beat routed elsewhere whose sentence is a
list, a number, steps or a before and after (promote_type). Each gets the template filled with its size, duration,
id, look and the said words' times in clip seconds (clip t=0 is the card's first frame, CARD_LEAD_S before
its word), and a brief for one clip-builder agent. Beats with under MIN_S of room keep their template.
check: check_clip.py, `hyperframes lint`, `check --at-transitions`, render, check_motion.py, measure_ink.py,
check_composition.py (advisory), a 1 fps contact sheet and a 10 fps strip of the first 1.2 s.
place: a clip whose last check passed replaces its beat with a video_card of the render, `start_s` set from
clip_motion.py so the motion finishes 0.25 s before the card leaves; the template beat is kept under "fallback"
and comes back for a clip that did not pass. Never edits anything but visuals.json and images/motion-*.mp4.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
PLUGIN = SKILL.parents[1]
sys.path.insert(0, str(HERE))

HF_VERSION = "0.8.155"     # setup.py installs exactly this (MOTION_PKGS); 0.7.x had other flags
GSAP_VERSION = "3.14.2"
MOTION_TYPES = ("likes", "progress", "curve", "notes", "terminal", "chat", "toasts", "side_by_side", "flow", "logo_cluster")
# style.json "motion": {"engine": "clips"|"templates", "amount": 0-1, "kinds": {kind: bool}, "look": "default"}.
# A kind names what the sentence is doing; each maps to the template formats a clip replaces.
KINDS = {"counter": ("likes",), "list": ("notes",), "flow": ("flow",), "before_after": ("side_by_side",),
         "ui_demo": ("progress", "terminal", "chat", "toasts"), "curve": ("curve",), "logo": ("logo_cluster",)}
CARD_LEAD_S = 0.1          # plan.py: a card lands this long before its word
MIN_S = 1.0                # less room than this and the beat keeps its template
HOLD_S = 2.5               # a beat with no hold_s
SIZE = {"9:16": (1200, 630), "16:9": (1280, 720)}   # card canvas: shown at about 800 px wide, so 1.5x sharp
FINISH_S = 0.25            # motion ends this long before the card leaves (visual-system.md "Watch the animation FINISH")
ROUNDS = 3                 # check rounds a clip-builder gets before the beat falls back to its template

# The default look (references/looks.md): the house look, neutral. A style overrides ground, ink, accent, font.
DEFAULT_LOOK = {"name": "default", "ground": "#FFFFFF", "paper": "#FDF8EC", "ink": "#171614", "muted": "#6B6862",
                "accent": None, "stop": "#FF3040", "ok": "#3DDC84", "font": "TikTok Sans", "radius": 28,
                "stroke": {"container": 6, "connector": 3, "texture": 1.2}}
PRESETS = {  # remotion/src/look.tsx, the parts a clip uses; "paper" is the 50/50 style's ground, "board" Motion design's
    "paper": {"ground": "#FDF8EC", "ink": "#171614"},
    "board": {"ground": "#0B0B0D", "ink": "#F4F6FA"},   # the Motion design style's canvas: near-black, silver-white ink
    "editorial": {"ground": "#F2EEE6", "ink": "#141414", "accent": "#E5482C"},
    "editorial-dark": {"ground": "#151413", "ink": "#F2EEE6", "accent": "#FF5A36"},
    "mono": {"ground": "#FFFFFF", "ink": "#0A0A0A", "font": "IBM Plex Sans"},
    "poster-red": {"ground": "#E2321B", "ink": "#111111", "accent": "#F7D23B"},
    "poster-green": {"ground": "#1E4A2C", "ink": "#F4EFE2", "accent": "#F5D63D"},
    "poster-blue": {"ground": "#1F3FD1", "ink": "#F4EFE2", "accent": "#FF7A59"},
}


def home():
    return Path(os.environ.get("AI_EDITOR_HOME", "").strip() or Path.home() / ".ai-video-editor")


def hf_bin():
    """The pinned HyperFrames CLI setup installed, or None."""
    b = home() / "motion" / "node_modules" / ".bin" / ("hyperframes.cmd" if os.name == "nt" else "hyperframes")
    return b if b.exists() else None


SETUP_PY = PLUGIN / "skills" / "setup" / "scripts" / "setup.py"
FELL_BACK = ("Animations fell back: the motion tools did not install ({why}), so the animated beats stay visual "
             "templates and a beat with nothing visual gets no card. For animations: python3 \"{setup}\" motion, then pick again.")


def ensure_tools(install=None):
    """The pinned motion tools, installed now when they are missing (setup.py motion: a few seconds to a minute, once).
    An install from before the motion step existed has none, and every clip fell back to a words-only template.
    (ok, why). install: the installer, swapped by the demo."""
    if hf_bin():
        return True, ""
    print("installing the motion tools (once, under a minute)", flush=True)
    r = (install or (lambda: subprocess.run([sys.executable, str(SETUP_PY), "motion"], capture_output=True, text=True)))()
    if hf_bin() and not r.returncode:
        return True, ""
    why = last((r.stdout or "") + (r.stderr or ""), 1).strip().removeprefix("ERROR: ").replace("; its output is above.", "")
    return False, why or "setup.py motion failed"


def clean(t):
    return re.sub(r"[^\w'’-]+", "", t).lower()


def slug(t):
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:24] or "beat"


def word_time(words, word, nth=1, after=-1.0):
    """Start of the nth time `word` is said (the next one after `after` without nth), like plan.py _place."""
    hits = [w for w in words if clean(w["text"]) == clean(word)]
    hits = hits[nth - 1:nth] if nth else [w for w in hits if w["start"] > after]
    return hits[0]["start"] if hits else None


def sentences(words):
    out, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        if nxt is None or w["text"].rstrip().endswith((".", "?", "!")) or nxt["start"] - w["end"] > 0.8:
            out.append({"text": " ".join(x["text"] for x in cur).strip(), "start": cur[0]["start"], "end": cur[-1]["end"]})
            cur = []
    return out


def look_for(style, profile=None):
    """The clip look: DEFAULT_LOOK, then the style's look preset, then the brand kit's or creator's ink, accent, font."""
    look = json.loads(json.dumps(DEFAULT_LOOK))
    sl = (style or {}).get("look") or {}
    pick_ = ((style or {}).get("motion") or {}).get("look") if isinstance((style or {}).get("motion"), dict) else None
    if pick_ in PRESETS:   # the style page's Motion look wins over the style's card look
        look.update(PRESETS[pick_], name=pick_)
    elif sl.get("preset") in PRESETS:
        look.update(PRESETS[sl["preset"]], name=sl["preset"])
    brand = ((profile or {}).get("brand") or {})
    for k, src in (("ink", "ink"), ("accent", "accent"), ("font", "font"), ("ground", "ground")):
        v = sl.get(src) or brand.get(src)
        if v:
            look[k] = v
            look["name"] = look["name"] if look["name"] != "default" else "default + style"
    return look


def motion_cfg(style):
    """style.json "motion" with defaults: clips on, every kind, look "default". amount: the share of moving beats
    built as clips (0 none, 0.5 some, 1 lots); with none set, a measured style's animation share
    (creator-teardown graphics.kinds "animation", in percent) decides, else 1."""
    m = (style or {}).get("motion") or {}
    m = m if isinstance(m, dict) else {}
    kinds = {k: bool((m.get("kinds") or {}).get(k, True)) for k in KINDS}
    share = (((style or {}).get("graphics") or {}).get("kinds") or {}).get("animation")
    amount = m.get("amount", round(min(1.0, share / 100), 2) if isinstance(share, (int, float)) else 1.0)
    return {"engine": m.get("engine", "clips"), "amount": float(amount), "kinds": kinds, "look": m.get("look", "default")}


def allowed_types(cfg):
    return tuple(t for k, ts in KINDS.items() if cfg["kinds"][k] for t in ts) if cfg["engine"] == "clips" else ()


def promote_type(line):
    """The moving template a sentence asks for, whatever visual-prep routed there: a before and after, a number,
    steps (first... then...) or a natural list (four or more items said in a row: "a, b, c and d"). None: no motion."""
    sys.path.insert(0, str(SKILL.parent / "style-edit" / "scripts"))
    import route
    if route.VERSUS.search(line):
        return "side_by_side"
    if route.NUM.search(line):
        return "likes"
    if len(route.STEPS.findall(line)) >= 2:
        return "flow"
    if line.count(",") >= 3 or (line.count(",") >= 2 and re.search(r",? (?:and|or) ", line)):
        return "notes"
    return None


def beats_for(visuals, words, aspect="9:16", max_n=8, images=(), types=MOTION_TYPES, amount=1.0, face=None):
    """The visuals.json beats that become clips: [{id, i, word, nth, start, dur, words, line, ...}].
    types: the template formats clips may replace (style.json motion kinds); amount: the share of them built.
    A beat routed to anything else (a card, a capture, a sticker) whose sentence is a list, a number, steps or a
    before and after becomes a clip too (promote_type), one per sentence, when no animation is there already."""
    times, after = [], -1.0
    for v in list(visuals) + list(images):
        t = word_time(words, v["word"], v.get("nth"), after) if v.get("word") else None
        if t is not None:
            times.append(t)
    times.sort()
    sents = sentences(words)
    sent_of = lambda t: next((k for k, s in enumerate(sents) if s["start"] <= t <= s["end"] + 0.05), None)   # noqa: E731
    animated = {sent_of(t) for v in visuals if v.get("kind") == "anim" and v.get("word")
                for t in [word_time(words, v["word"], v.get("nth", 1))] if t is not None}
    out = []
    for i, v in enumerate(visuals):
        if not v.get("word"):
            continue
        t = word_time(words, v["word"], v.get("nth", 1))
        if t is None:
            continue
        if v.get("kind") != "anim":   # routed elsewhere: a clip only when the sentence itself moves
            si = sent_of(t)
            pt = promote_type(sents[si]["text"]) if si is not None and si not in animated else None
            if pt not in types:
                continue
            animated.add(si)
            v = {**v, "type": pt, "props": {}, "promoted": v.get("kind")}
        elif v.get("type") not in types:
            continue
        start = round(max(0.0, t - CARD_LEAD_S), 3)
        nxt = next((x - CARD_LEAD_S for x in times if x > t + 1e-6), words[-1]["end"] + 0.5)
        dur = round(min(nxt, start + max(v.get("hold_s") or HOLD_S, MIN_S)) - start, 2)
        if dur < MIN_S:
            continue
        si = next((k for k, s in enumerate(sents) if s["start"] <= t <= s["end"] + 0.05), None)
        said = [{"w": w["text"], "t": round(w["start"] - start, 2)} for w in words if start <= w["start"] < start + dur]
        out.append({"id": f"{len(out) + 1:02d}-{slug(v['word'])}", "i": i, "word": v["word"], "nth": v.get("nth", 1),
                    "type": v["type"], "props": v.get("props") or {}, "start": start, "dur": dur, "clock": "cut",
                    "size": card_size(face, start, start + dur, aspect), "words": said,
                    "line": sents[si]["text"] if si is not None else "", **({"promoted": v["promoted"]} if v.get("promoted") else {}),
                    "before": sents[si - 1]["text"] if si else "", "after": sents[si + 1]["text"] if si is not None and si + 1 < len(sents) else ""})
    n = min(max_n, int(len(out) * max(0.0, min(1.0, amount)) + 0.5))   # half up: 1 beat at "some" is 1 clip, not 0
    if len(out) > n:   # keep the longest windows: a bespoke clip pays off most where it holds longest
        keep = {b["id"] for b in sorted(out, key=lambda b: -b["dur"])[:n]}
        out = [b for b in out if b["id"] in keep]
    return out


def card_size(face, start, end, aspect="9:16"):
    """The card canvas for a clip up from start to end: 1200 wide, as tall as the band above the head lets a
    800 px card be (plan.py: the band runs from the safe top, 13.1%, to 2% over the head, and a card may tuck its
    bottom fifth behind the hair). No head found or a wide frame: SIZE."""
    if aspect != "9:16" or not face or not face.get("heads"):
        return list(SIZE.get(aspect, SIZE["9:16"]))
    tops = [h["box"][1] for h in face["heads"] if h.get("box") and start - 0.5 <= h["t"] <= end]
    if not tops:
        return list(SIZE["9:16"])
    band = max(8.0, (min(tops) - 13.1 - 2.0) / 0.8) / 100 * 1920 * 0.92   # px the picture gets (FILL)
    ar = max(1.6, min(3.0, 0.74 * 1080 * 0.96 / band))
    return [1200, int(round(1200 / ar / 2)) * 2]


def panel_size(style):
    """The 50/50 (split layout) panel's art box as a clip canvas, or None for an overlay style. plan.py
    split_art_box: x 13-87%, y 13.1% to 2% above the seam. The clip fills it edge to edge on the panel's ground."""
    lay = (style or {}).get("layout") or {}
    if lay.get("mode") != "split":
        return None
    seam = float(lay.get("seam", 50))
    w_px, h_px = 0.74 * 1080, (seam - 2 - 13.1) / 100 * 1920
    return [1200, int(round(1200 * h_px / w_px / 2)) * 2]


def board_size(style):
    """A board-layout style (Motion design): the clip is an overlay beside the speaker, in plan.py BOARD_OVERLAY_BOX
    (42% x 60% of a 16:9 frame, 806 x 648 px), so its canvas is that shape. None for any other layout."""
    if ((style or {}).get("layout") or {}).get("mode") != "board":
        return None
    return [1200, int(round(1200 * 648 / 806 / 2)) * 2]


def fill_template(beat, look, gsap=None):
    w, h = beat["size"]
    html = (SKILL / "template" / "index.html").read_text(encoding="utf-8")
    for k, v in {"__ID__": beat["id"], "__W__": w, "__H__": h, "__CX__": w // 2, "__CY__": h // 2,
                 "__DUR__": f"{beat['dur']:.2f}", "__GROUND__": look["ground"], "__INK__": look["ink"],
                 "__WORDS__": json.dumps(beat["words"])}.items():
        html = html.replace(k, str(v))
    return html


BRIEF = """# Clip {id}

Read `{card}` first (every gate and approved value), then build this one clip. Do not read the check
scripts' source. First render within about 10 minutes, then iterate on `check` output.

- Folder (yours alone): `{dir}`. Edit `index.html` only, plus files you add under `assets/`.
- Canvas {w}x{h}, {dur} s, 30 fps. It plays as a card about {cw} px wide in the band above the speaker's head,
  {placement}
- The look: {look}
- The line: "{line}"
  Before it: "{before}"  After it: "{after}"
- When each word lands (clip seconds, already in `WORDS` in index.html): {words}
- What this beat was going to be (the template's content, use its real words and pictures): `{type}` {props}
- The edit's real pictures you may use (copy into `assets/`): {images}

{start}Build: `{env}python3 "{run}" "{motion}" check "{dir}"` (the editor's own Python, which has Pillow and OpenCV) runs every gate and the render, writes `gates.json`, `renders/clip.mp4`,
`renders/sheet.png` (1 fps) and `renders/strip.png` (10 fps, first 1.2 s). Look at both sheets after every
render. At most {rounds} checks; then stop and report.
"""


def effective(edit):
    """style.json as plan.py uses it (the style page's settings and the user's corrections over it), else the raw file."""
    sp = Path(edit) / "style.json"
    try:
        sys.path[:0] = [str(SKILL.parent / "style-edit" / "scripts"), str(PLUGIN / "lib")]
        import contextlib
        import io
        import plan
        from ai_editor import profile as prof_mod
        with contextlib.redirect_stderr(io.StringIO()):
            return plan.effective_style(sp, prof_mod.load(), str(edit), count=False)
    except Exception:   # noqa: BLE001  outside the plugin's venv: the raw style.json
        return json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {}


def pick(edit, max_n=8):
    edit = Path(edit)
    visuals = json.loads((edit / "visuals.json").read_text(encoding="utf-8"))
    words = [w for w in json.loads((edit / "captions.json").read_text(encoding="utf-8")) if w.get("type", "word") == "word"]
    style = effective(edit)
    images = json.loads((edit / "images.json").read_text(encoding="utf-8")) if (edit / "images.json").exists() else []
    try:
        sys.path.insert(0, str(PLUGIN / "lib"))
        from ai_editor import profile as prof_mod
        profile = prof_mod.load() if hasattr(prof_mod, "load") else {}
    except Exception:   # noqa: BLE001  a missing or broken profile means the default look
        profile = {}
    look = look_for(style, profile)
    aspect = style.get("aspect", "9:16")
    cfg = motion_cfg(style)
    face = json.loads((edit / "face.json").read_text(encoding="utf-8")) if (edit / "face.json").exists() else None
    types = allowed_types(cfg)
    if board_size(style):   # Motion design: logos and flows land as tiles on the canvas, never as clips
        types = tuple(t for t in types if t not in ("logo_cluster", "flow"))
    beats = beats_for([v.get("fallback") or v for v in visuals], words, aspect, max_n, images, types, cfg["amount"], face)
    pj = edit / "plan.json"
    if pj.exists() and pj.stat().st_mtime >= (edit / "visuals.json").stat().st_mtime:   # the plan dropped some beats
        kept = {(c.get("trigger_word") or "").lower() for c in json.loads(pj.read_text(encoding="utf-8")).get("cards", [])}
        gone = [b for b in beats if b["word"].lower() not in kept]
        if gone:
            print("not in the plan, no clip: " + ", ".join(f"'{b['word']}'" for b in gone))
        beats = [b for b in beats if b["word"].lower() in kept]
    panel = panel_size(style)
    if panel:   # the 50/50 panel: every clip is the panel's own shape, on the panel's ground
        look = {**look, "ground": (style.get("layout") or {}).get("ground") or look["ground"]}
        for b in beats:
            b.update(size=panel, panel=True)
    if board_size(style):   # Motion design: an overlay on one side of the wide frame, the speaker moved to the other
        for b in beats:
            b.update(size=board_size(style), board=True)
    if cfg["engine"] != "clips":
        print("style.json motion.engine is \"templates\": no clips, the template formats stay")
    elif beats:
        ok, why = ensure_tools()
        if not ok:   # said once; no clip folders, so no clip-builder is started for a clip that cannot render
            print(FELL_BACK.format(why=why, setup=SETUP_PY))
            return []
    gsap = home() / "motion" / "node_modules" / "gsap" / "dist" / "gsap.min.js"
    root = edit / "motion"
    root.mkdir(exist_ok=True)
    pics = sorted(p.name for p in (edit / "images").glob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".svg", ".webp")) \
        if (edit / "images").is_dir() else []
    for b in beats:
        d = root / b["id"]
        (d / "assets").mkdir(parents=True, exist_ok=True)
        if b["type"] == "notes":   # real UI, never words alone: the speaker's avatar and the take's frames in assets/
            sys.path.insert(0, str(SKILL.parent / "style-edit" / "scripts"))
            import plan
            card = {"start": b["start"], "anim": {"type": "notes", "props": json.loads(json.dumps(b["props"]))}}
            for ln in card["anim"]["props"].get("lines") or []:   # each frame where its line is said
                t = next((w["t"] for w in b["words"] if isinstance(ln, dict) and clean(w["w"]) == clean(ln.get("word") or "")), None)
                if t is not None and "at" not in ln:
                    ln["at"] = t
            plan.take_frames([card], d, edit / "cut.mp4", face, "assets")
            b["props"] = card["anim"]["props"]
        if not (d / "index.html").exists():   # never clobber a clip being built
            (d / "index.html").write_text(fill_template(b, look), encoding="utf-8")
            sp = starting_point(b["type"])
            if sp and (library_dir() / sp["id"] / "index.html").exists():
                shutil.copy(library_dir() / sp["id"] / "index.html", d / "start.html")
                for a in (library_dir() / sp["id"] / "assets").glob("*"):
                    if not (d / "assets" / a.name).exists():
                        shutil.copy(a, d / "assets" / a.name)
                b["start_from"] = sp["id"]
                if sp.get("use_next"):
                    lib_set(sp["id"], use=False)
        shutil.copy(SKILL / "template" / "hyperframes.json", d / "hyperframes.json")
        if gsap.exists():
            shutil.copy(gsap, d / "assets" / "gsap.min.js")
        (d / "beat.json").write_text(json.dumps(b, indent=1), encoding="utf-8")
        w, h = b["size"]
        (d / "brief.md").write_text(BRIEF.format(
            id=b["id"], card=SKILL / "references" / "clip-brief-card.md", dir=d.resolve(), w=w, h=h, dur=b["dur"],
            cw=800 if aspect == "9:16" else 760, lead=CARD_LEAD_S,
            placement=("over the footage, popping in {lead} s before its word. Fill the card edge to edge: no inner margin of "
                       "ground.\n  Its bottom fifth may sit behind the speaker's hair: nothing that must be read goes there."
                       ).format(lead=CARD_LEAD_S) if not b.get("panel") and not b.get("board") else
                      ("beside the speaker, on one side of a 16:9 frame (the speaker is moved to the other side), popping in "
                       f"{CARD_LEAD_S} s before its word. Its ground is the canvas's own near-black ({look['ground']}): dark "
                       "silver-rimmed tiles, real logos, lowercase labels in the speaker's words, 2 px dashed connectors. "
                       "Fill it edge to edge.") if b.get("board") else
                      ("in the 50/50 panel: the top of the frame, above the speaker, the whole panel. Its ground is the panel's own "
                       f"({look['ground']}), so it has no edge: no card, border or shadow round the exhibit. Fill at least 55% of it."), look=json.dumps(look), line=b["line"],
            before=b["before"], after=b["after"], words=json.dumps(b["words"]), type=b["type"], props=json.dumps(b["props"]),
            images=", ".join(str((edit / "images" / p).resolve()) for p in pics) or "none", motion=Path(__file__).resolve(), run=PLUGIN / "lib" / "ai_editor" / "run.py", rounds=ROUNDS,
            env=f'AI_EDITOR_HOME="{os.environ["AI_EDITOR_HOME"]}" ' if os.environ.get("AI_EDITOR_HOME") else "",
            start="- A clip the user approved before is in `start.html` (same kind of beat). You may start from its design, "
                  "but re-time every part to this clip's `WORDS` and change it for this line: an unchanged copy fails "
                  "`check`.\n- Notes on this clip, if any: `notes.md` beside this brief. Do what they say.\n\n"
                  if b.get("start_from") else "- Notes on this clip, if any: `notes.md` beside this brief. Do what they say.\n\n"),
            encoding="utf-8")
    (root / "beats.json").write_text(json.dumps({"clock": "cut", "look": look, "beats": beats}, indent=1), encoding="utf-8")
    for b in beats:
        print(f"{b['id']:<22} {b['type']:<13} {b['start']:6.2f}s +{b['dur']:.2f}s  \"{b['line'][:60]}\"")
    print(f"{len(beats)} clip(s) in {root}. One clip-builder agent per clip, all in one message, "
          f"each given {root}/<id>/brief.md.")
    return beats


def run(cmd, cwd=None, timeout=900):
    try:
        p = subprocess.run([str(c) for c in cmd], cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)


def last(text, n=6):
    return "\n".join([ln for ln in text.strip().splitlines() if ln.strip() and not ln.startswith("[hyperframes]")][-n:])


def sheets(video, out_dir, dur):
    """renders/sheet.png: one frame a second; renders/strip.png: 10 fps over the first 1.2 s (motion, not stills)."""
    n = max(1, int(dur))
    run(["ffmpeg", "-v", "error", "-y", "-i", video, "-vf", f"fps=1,scale=360:-1,tile={min(n, 6)}x{(n + 5) // 6}",
         "-frames:v", "1", out_dir / "sheet.png"])
    run(["ffmpeg", "-v", "error", "-y", "-i", video, "-t", "1.2", "-vf", "fps=10,scale=300:-1,tile=6x2",
         "-frames:v", "1", out_dir / "strip.png"])


def cream(rgb):
    """style-edit ai_tells.is_cream: a warm off-white ground, the banned "cream-paper-ground" tell in a card."""
    import colorsys
    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
    return 20 <= h * 360 <= 60 and 0.04 <= s <= 0.3 and v >= 0.78


def ground_of(video, w, h):
    """(rgb, share) of the dominant colour of the clip's frame at 3/4 of its length, quantised like ai_tells.cream_ground."""
    import numpy as np
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                               capture_output=True, text=True).stdout.strip() or 1)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{dur * 0.75:.3f}", "-i", str(video), "-frames:v", "1", "-vf",
                          f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    q = (np.frombuffer(raw[:w * h * 3], np.uint8).reshape(-1, 3) >> 4).astype(np.int32)
    keys, counts = np.unique(q[:, 0] * 256 + q[:, 1] * 16 + q[:, 2], return_counts=True)
    k = int(keys[counts.argmax()])
    return (((k >> 8) & 15) * 16 + 8, ((k >> 4) & 15) * 16 + 8, (k & 15) * 16 + 8), counts.max() / len(q)


def panel_fill(video, ground, tol=10, min_fill=0.55):
    """The 50/50 PANEL gate (the house check_clip_ground.py, panel mode): the corners are the panel's ground (no edge
    for a mismatch to draw) and the ink band covers at least min_fill of the panel, sampled at 3/4 of the clip."""
    import numpy as np
    w, h = 240, 200
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                               capture_output=True, text=True).stdout.strip() or 1)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{dur * 0.75:.3f}", "-i", str(video), "-frames:v", "1", "-vf",
                          f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    f = np.frombuffer(raw[:w * h * 3], np.uint8).reshape(h, w, 3).astype(int)
    off = [tuple(int(v) for v in f[y, x]) for y, x in ((1, 1), (1, w - 2), (h - 2, 1), (h - 2, w - 2))
           if max(abs(int(a) - b) for a, b in zip(f[y, x], ground)) > tol]
    ink = np.abs(f - np.array(ground)).max(axis=2) > 24
    rows, cols = np.where(ink.any(axis=1))[0], np.where(ink.any(axis=0))[0]
    fill = ((rows[-1] - rows[0] + 1) * (cols[-1] - cols[0] + 1) / (w * h)) if len(rows) and len(cols) else 0.0
    cx = ((cols[0] + cols[-1]) / 2 / w) if len(cols) else 0.5
    msgs = ([f"the drawing's centre is {abs(cx - 0.5):.0%} of the width off the panel's centre (the render check fails 2%)"]
            if abs(cx - 0.5) > 0.02 else []) + ([f"{len(off)} corner(s) are not the panel's ground #{''.join(f'{c:02x}' for c in ground)}: the exhibit draws an edge"]
            if off else []) + ([f"the ink band fills {fill:.0%} of the panel (under {min_fill:.0%})"] if fill < min_fill else [])
    return not msgs, "; ".join(msgs) or f"corners on the ground, ink band {fill:.0%} of the panel"


def check(clip_dir):
    """Every gate on one clip, the render, the sheets. gates.json: {"pass", "round", "gates": {name: [ok, detail]}}."""
    d = Path(clip_dir).resolve()
    hf = hf_bin()
    if not hf:
        sys.exit("ERROR: the motion tools are not installed. Run the setup skill's motion step: python3 setup.py motion")
    prev = json.loads((d / "gates.json").read_text(encoding="utf-8")) if (d / "gates.json").exists() else {}
    beat = json.loads((d / "beat.json").read_text(encoding="utf-8")) if (d / "beat.json").exists() else {}
    g, render = {}, d / "renders" / "clip.mp4"
    import check_clip
    err, warn = check_clip.check((d / "index.html").read_text(encoding="utf-8"), clip_id=d.name)
    g["check_clip"] = [not err, "; ".join(m for _, m in err)[:600] or f"{len(warn)} warning(s)"]
    if same_as_start(d):
        g["reuse"] = [False, "index.html is the library clip in start.html unchanged: re-time it to WORDS and change it for this line"]
    if g["check_clip"][0]:
        rc, out = run([hf, "lint", str(d)])
        g["lint"] = [rc == 0, last(out, 4)]
        rc, out = run([hf, "check", str(d), "--at-transitions", "--samples", "24", "--no-contrast"])
        g["layout"] = [rc == 0, last(out, 6)]
        if g["lint"][0]:
            (d / "renders").mkdir(exist_ok=True)
            rc, out = run([hf, "render", str(d), "-o", str(render), "--quality", "looks", "--quiet"], timeout=1800)
            g["render"] = [rc == 0 and render.exists(), last(out, 3) if rc else str(render)]
    if g.get("render", [False])[0]:
        rc, out = run([sys.executable, HERE / "check_motion.py", render, d / "index.html"])
        g["motion"] = [rc == 0, last(out, 8)]
        rc, out = run([sys.executable, HERE / "check_composition.py", render, d / "index.html"])
        g["composition (advisory)"] = [True, last(out, 5)]
        rgb, share = ground_of(render, 120, 64)
        look = json.loads((d.parent / "beats.json").read_text(encoding="utf-8")).get("look", {}) if (d.parent / "beats.json").exists() else {}
        lg = (look.get("ground") or "#FFFFFF").lstrip("#")
        own = cream(tuple(int(lg[i:i + 2], 16) for i in (0, 2, 4))) if len(lg) == 6 else False
        bad = share > 0.5 and cream(rgb) and not own
        g["ground"] = [not bad, f"{share:.0%} of the frame at 3/4 is #{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}" +
                       (": a cream paper ground, banned in a card; use the look's ground or the real surface" if bad else "")]
        node = shutil.which("node")
        if node:   # the four proofs (verify.mjs): blocking in the 50/50 panel, advisory on a card (a 1 s card is not read whole)
            rc, out = run([node, HERE / "verify.mjs", d] + (["--rails"] if beat.get("size") == [1080, 1920] else []), timeout=600)
            try:
                pr = json.loads(out.strip().splitlines()[-1])
                detail = f"clipped {pr['clipped']}, rails {pr['rails']}, neighbour {pr['neighbour']}, reading {pr['reading']}" + \
                         (": " + "; ".join(pr["notes"][:3]) if pr["notes"] else "")
                g["proofs" if beat.get("panel") else "proofs (advisory)"] = [pr["pass"] or not beat.get("panel"), detail]
            except (ValueError, IndexError, KeyError):
                g["proofs (advisory)"] = [True, "not run: " + last(out, 1)]
        png = d / "renders" / "tells.png"   # the editor's generated-look tells on a settled frame (style-edit ai_tells.py)
        run(["ffmpeg", "-v", "error", "-y", "-ss", f"{beat.get('dur', 2) * 0.75:.2f}", "-i", render, "-frames:v", "1", png])
        allow = "cream-paper-ground" if own else ""
        rc, out = run([sys.executable, PLUGIN / "lib" / "ai_editor" / "run.py", SKILL.parent / "style-edit" / "scripts" / "ai_tells.py",
                       "still", png] + (["--allow", allow] if allow else []))
        if "No module named" in out or "cannot read" in out:
            g["tells (advisory)"] = [True, "not run: " + last(out, 1)]
        else:
            bans = [ln.split(None, 2)[1] for ln in out.splitlines() if ln.startswith("BAN")]
            g["tells"] = [not bans, ("banned look: " + ", ".join(bans) + " (style-edit references/ai-tells.md)") if bans else "none"]
        if beat.get("panel"):
            ok, msg = panel_fill(render, tuple(int(lg[i:i + 2], 16) for i in (0, 2, 4)) if len(lg) == 6 else (255, 255, 255))
            g["panel"] = [ok, msg]
        import measure_ink
        top, bot = measure_ink.ink_band(str(render))
        g["ink"] = [True, f"ink band {top:.2f}-{bot:.2f} of the height"]
        sheets(render, d / "renders", beat.get("dur", 3))
    ok = all(v[0] for v in g.values()) and "render" in g
    res = {"pass": ok, "round": prev.get("round", 0) + 1, "gates": g,
           "render": str(render) if render.exists() else "", "sheet": str(d / "renders" / "sheet.png"),
           "strip": str(d / "renders" / "strip.png")}
    (d / "gates.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    for k, (o, detail) in g.items():
        print(f"{'ok  ' if o else 'FAIL'} {k}: {detail.splitlines()[-1] if detail else ''}")
    print(f"{'PASS' if ok else 'FAIL'} check {res['round']} ({ROUNDS} to build, 2 more per note). Look at {res['sheet']} and {res['strip']}.")
    return 0 if ok else 1


def motion_window(video):
    import clip_motion
    m = clip_motion.motion(video)
    return m or (0.0, 0.0, 0.0)


def placed_beat(orig, beat, src, first, last_):
    """The video_card beat for a passed clip: motion finishes FINISH_S before the card leaves (clip_motion.py)."""
    hold = beat["dur"]
    start_s = round(max(0.0, min(first, last_ + FINISH_S - hold)), 2) if last_ else 0.0
    return {"word": beat["word"], "nth": beat["nth"], "kind": "anim", "type": "video_card", "hold_s": hold,
            "props": {"src": src, "size": beat["size"], "start_s": start_s, "motion": beat["id"],
                      **({"bare": True} if beat.get("panel") else {})}, "motion": beat["id"],
            "fallback": orig}


def place(edit):
    edit = Path(edit)
    vf = edit / "visuals.json"
    visuals = json.loads(vf.read_text(encoding="utf-8"))
    doc = json.loads((edit / "motion" / "beats.json").read_text(encoding="utf-8"))
    by_id = {v.get("motion"): i for i, v in enumerate(visuals) if v.get("motion")}
    placed, back = [], []
    for b in doc["beats"]:
        d = edit / "motion" / b["id"]
        gates = json.loads((d / "gates.json").read_text(encoding="utf-8")) if (d / "gates.json").exists() else {}
        i = by_id.get(b["id"])
        if i is None:   # still the template beat: find it by word and type
            i = next((k for k, v in enumerate(visuals) if v.get("word") == b["word"] and v.get("nth", 1) == b["nth"]
                      and v.get("type") == b["type"]), None)
        if i is None:
            continue
        orig = visuals[i].get("fallback") or visuals[i]
        render = d / "renders" / "clip.mp4"
        if gates.get("pass") and render.exists() and not gates.get("rejected"):
            (edit / "images").mkdir(exist_ok=True)
            import hashlib   # the name changes with the render, so edit.py patch re-renders only this clip's span
            tag = hashlib.sha256(render.read_bytes()).hexdigest()[:8]
            for old in (edit / "images").glob(f"motion-{b['id']}-*.mp4"):
                old.unlink()
            dst = edit / "images" / f"motion-{b['id']}-{tag}.mp4"
            shutil.copy(render, dst)
            _, first, last_ = motion_window(dst)
            visuals[i] = placed_beat(orig, b, f"images/{dst.name}", first, last_)
            placed.append(f"{b['id']} (motion {first:.2f}-{last_:.2f} s, from {visuals[i]['props']['start_s']} s)")
        else:
            visuals[i] = orig
            back.append(f"{b['id']} -> {b['type']} template ({'not built' if not gates else 'did not pass'})")
    vf.write_text(json.dumps(visuals, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"placed {len(placed)}: " + "; ".join(placed))
    if back:
        print(f"template {len(back)}: " + "; ".join(back))
    return placed, back


def status(edit):
    root = Path(edit) / "motion"
    doc = json.loads((root / "beats.json").read_text(encoding="utf-8"))
    for b in doc["beats"]:
        g = root / b["id"] / "gates.json"
        s = json.loads(g.read_text(encoding="utf-8")) if g.exists() else {}
        st = "passed" if s.get("pass") else (f"failed round {s['round']}" if s else "building")
        print(f"{b['id']:<22} {st}")


def strips(video, times, out, before=0.4, after=1.1, fps=10, safe=False, width=240):
    """One row per time: consecutive frames at `fps` from t-before to t+after. With safe, the reels safe zone
    (x 30-1010, y 150-1640 of 1080x1920) is drawn on every frame."""
    tmp = Path(tempfile.mkdtemp(prefix="strips-"))
    try:
        rows = []
        n = int(round((before + after) * fps)) + 1
        box = ",drawbox=x=iw*60/1080:y=ih*250/1920:w=iw*880/1080:h=ih*1190/1920:color=red@0.9:t=3" if safe else ""
        for k, t in enumerate(times):
            row = tmp / f"row{k}.png"
            run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(0.0, t - before):.3f}", "-t", f"{before + after + 0.5 / fps:.3f}",
                 "-i", video, "-vf", f"fps={fps}{box},scale={width}:-2,tile={n}x1:padding=2", "-frames:v", "1", row])
            if row.exists():
                rows.append(row)
        if not rows:
            sys.exit("ERROR: no frames read from " + str(video))
        args = ["ffmpeg", "-v", "error", "-y"]
        for r in rows:
            args += ["-i", r]
        args += ["-filter_complex", f"vstack=inputs={len(rows)}" if len(rows) > 1 else "null", out]
        rc, msg = run(args)
        if rc:
            sys.exit("ERROR: " + last(msg, 2))
        print(f"wrote {out}: one row per time ({', '.join(f'{t:.2f}' for t in times)} s), {n} frames each at {fps} fps, "
              f"from {before} s before to {after} s after")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---- the motion library: clips the user approved, kept per user to start a matching beat from (never reused unchanged)
def library_dir():
    return home() / "motion-library"


def lib_entries():
    """Every saved clip's meta.json, newest first; archived ones included (flag "archived")."""
    out = []
    for m in library_dir().glob("*/meta.json"):
        try:
            out.append(json.loads(m.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return sorted(out, key=lambda e: -e.get("made", 0))


def save(edit, clip=None):
    """Copy each placed clip (composition, brief, beat, small assets, a thumbnail) into the library. Run when the user
    approves the render. Returns the saved ids; a clip already saved (same composition) is skipped."""
    import hashlib
    import time
    edit = Path(edit)
    visuals = json.loads((edit / "visuals.json").read_text(encoding="utf-8"))
    style = json.loads((edit / "style.json").read_text(encoding="utf-8")) if (edit / "style.json").exists() else {}
    doc = json.loads((edit / "motion" / "beats.json").read_text(encoding="utf-8"))
    placed = {v.get("motion") for v in visuals if v.get("motion")}
    saved = []
    for b in doc["beats"]:
        d = edit / "motion" / b["id"]
        if b["id"] not in placed or (clip and clip != b["id"]) or not (d / "index.html").exists():
            continue
        html = (d / "index.html").read_text(encoding="utf-8")
        lid = f"{b['type']}-{hashlib.sha256(html.encode()).hexdigest()[:10]}"
        dst = library_dir() / lid
        if dst.exists():
            continue
        (dst / "assets").mkdir(parents=True)
        for f in ("index.html", "brief.md", "beat.json", "hyperframes.json"):
            if (d / f).exists():
                shutil.copy(d / f, dst / f)
        for a in (d / "assets").glob("*"):
            if a.is_file() and a.stat().st_size < 20e6:
                shutil.copy(a, dst / "assets" / a.name)
        render = d / "renders" / "clip.mp4"
        if render.exists():
            run(["ffmpeg", "-v", "error", "-y", "-ss", f"{b['dur'] * 0.6:.2f}", "-i", render, "-frames:v", "1",
                 "-vf", "scale=480:-2", dst / "thumb.jpg"])
        kind = next((k for k, ts in KINDS.items() if b["type"] in ts), b["type"])
        meta = {"id": lid, "type": b["type"], "kind": kind, "line": b["line"], "size": b["size"], "dur": b["dur"],
                "style": style.get("handle") or "", "look": doc.get("look", {}).get("name", "default"),
                "made": time.time(), "archived": False, "use_next": False}
        (dst / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
        saved.append(lid)
    print(f"saved {len(saved)} clip(s) to {library_dir()}" + (": " + ", ".join(saved) if saved else ""))
    return saved


def lib_set(lid, archived=None, use=None):
    """Archive (never used again) or bring back; "use again" marks it the first starting point for its kind."""
    f = library_dir() / lid / "meta.json"
    if not re.fullmatch(r"[a-z_]+-[0-9a-f]{10}", lid or "") or not f.exists():
        raise KeyError(lid)
    m = json.loads(f.read_text(encoding="utf-8"))
    if archived is not None:
        m["archived"] = bool(archived)
        m["use_next"] = False if archived else m.get("use_next", False)
    if use is not None:
        m["use_next"] = bool(use) and not m.get("archived")
    f.write_text(json.dumps(m, indent=1), encoding="utf-8")
    return m


def starting_point(kind_type):
    """The library clip a new beat of this template type starts from: "use again" first, then the newest. Archived
    clips never."""
    c = [e for e in lib_entries() if e.get("type") == kind_type and not e.get("archived")]
    c.sort(key=lambda e: (not e.get("use_next"), -e.get("made", 0)))
    return c[0] if c else None


def same_as_start(d):
    """True when index.html is the library starting point with only its id swapped: a straight copy."""
    st, ix = d / "start.html", d / "index.html"
    if not (st.exists() and ix.exists()):
        return False
    a, b = st.read_text(encoding="utf-8"), ix.read_text(encoding="utf-8")
    old = re.search(r'data-composition-id="([^"]+)"', a)
    if old:
        a = a.replace(old[1], d.name)
    norm = lambda t: re.sub(r"\s+", "", t)
    return norm(a) == norm(b)


def note(edit, text, at=None, clip=None):
    """A note on one clip (the review page note's time, or the clip id): appended to that clip's notes.md, so only it
    is rebuilt. Prints what to run next and the span edit.py patch re-renders."""
    edit = Path(edit)
    doc = json.loads((edit / "motion" / "beats.json").read_text(encoding="utf-8"))
    b = next((x for x in doc["beats"] if x["id"] == clip or (at is not None and x["start"] <= at <= x["start"] + x["dur"])), None)
    if not b:
        sys.exit(f"no motion clip {'named ' + clip if clip else f'up at {at} s'}: a note for another card goes to the overlays skill")
    d = edit / "motion" / b["id"]
    with open(d / "notes.md", "a", encoding="utf-8") as fh:
        fh.write(f"- {text.strip()}" + (f" (said at {at:.2f} s)" if at is not None else "") + "\n")
    print(f"note on {b['id']}: give one clip-builder {d / 'brief.md'} and this note (up to 2 checks), then "
          f"motion.py place, plan.py, and edit.py patch (re-renders {b['start']:.2f}-{b['start'] + b['dur']:.2f} s only)")
    return b["id"]


def demo():
    words = [{"text": w, "start": i * 0.5, "end": i * 0.5 + 0.4, "type": "word"}
             for i, w in enumerate("over ten thousand people asked. it renders every frame. then it learns.".split())]
    visuals = [{"word": "over", "nth": 1, "kind": "anim", "type": "likes", "hold_s": 2.0, "props": {"counts": [{"n": 0}]}},
               {"word": "renders", "nth": 1, "kind": "anim", "type": "progress", "hold_s": 0.6},
               {"word": "every", "nth": 1, "kind": "logo", "brand": "x"},
               {"word": "learns", "nth": 1, "kind": "anim", "type": "notes", "hold_s": 3.0}]
    with tempfile.TemporaryDirectory() as t:   # tools missing: pick installs them; a failed install says why, once
        keep = os.environ.get("AI_EDITOR_HOME")
        os.environ["AI_EDITOR_HOME"] = t
        try:
            fail = lambda: subprocess.CompletedProcess([], 1, "", "npm missing. Install Node first\n")   # noqa: E731
            assert ensure_tools(fail) == (False, "npm missing. Install Node first")

            def ok():
                b = Path(t) / "motion" / "node_modules" / ".bin" / ("hyperframes.cmd" if os.name == "nt" else "hyperframes")
                b.parent.mkdir(parents=True)
                b.write_text("", encoding="utf-8")
                return subprocess.CompletedProcess([], 0, "Motion clip tools installed", "")
            assert ensure_tools(ok) == (True, "") and ensure_tools(fail) == (True, "")   # installed: never runs again
        finally:
            os.environ.pop("AI_EDITOR_HOME") if keep is None else os.environ.update(AI_EDITOR_HOME=keep)
    bs = beats_for(visuals, words)
    assert [b["type"] for b in bs] == ["likes", "notes"], bs   # progress: room for 0.6 s only, keeps its template
    assert bs[0]["start"] == 0.0 and bs[0]["dur"] == 2.0 and bs[0]["clock"] == "cut", bs[0]
    assert bs[0]["words"][0] == {"w": "over", "t": 0.0} and bs[0]["line"].startswith("over ten"), bs[0]
    assert bs[1]["start"] == 5.4 and bs[1]["dur"] == 1.0, bs[1]   # to the end of the take
    assert beats_for(visuals, words, max_n=1)[0]["type"] == "likes"   # the longest window wins
    cfg = motion_cfg({"motion": {"kinds": {"counter": False}}})
    assert [b["type"] for b in beats_for(visuals, words, types=allowed_types(cfg))] == ["notes"]
    assert beats_for(visuals, words, amount=0.5)[0]["type"] == "likes" and len(beats_for(visuals, words, amount=0.5)) == 1
    assert allowed_types(motion_cfg({"motion": {"engine": "templates"}})) == ()
    # promoted: a 4-item list visual-prep sent to a card becomes a notes clip; amount 0 or the kind off promotes nothing
    lw = [{"text": w, "start": i * 0.5, "end": i * 0.5 + 0.4, "type": "word"}
          for i, w in enumerate("you need captions, zooms, music and cards. it is red, blue and green. follow me now.".split())]
    lv = [{"word": "need", "nth": 1, "kind": "card", "text": "captions"}, {"word": "cards.", "nth": 1, "kind": "logo", "brand": "x"},
          {"word": "red,", "nth": 1, "kind": "card", "text": "red"}, {"word": "follow", "nth": 1, "kind": "card", "text": "follow"}]
    pb = beats_for(lv, lw)
    assert [(b["type"], b["word"], b.get("promoted")) for b in pb] == [("notes", "need", "card")], pb   # one per sentence, three items is no list
    assert beats_for(lv, lw, amount=0) == []
    assert beats_for(lv, lw, types=allowed_types(motion_cfg({"motion": {"kinds": {"list": False}}}))) == []
    assert promote_type("first cut it, then render it") == "flow" and promote_type("before it took a week") == "side_by_side"
    assert promote_type("it is red, blue and green") is None and promote_type("over 10,000 people") == "likes"
    assert [b["type"] for b in beats_for(visuals, words)] == ["likes", "notes"], "a sentence with an animation gets no second"
    assert card_size({"heads": [{"t": 1.0, "box": [30, 31, 40, 40]}]}, 0.5, 2) == [1200, 550], card_size(
        {"heads": [{"t": 1.0, "box": [30, 31, 40, 40]}]}, 0.5, 2)   # head top at 31%: a 2.2:1 card
    assert card_size(None, 0, 1) == [1200, 630] and card_size({"heads": [{"t": 1, "box": [0, 60, 9, 9]}]}, 0, 2)[1] == 750
    html = fill_template(bs[0], DEFAULT_LOOK)
    assert "__" not in re.sub(r"__timelines", "", html) and 'data-duration="2.00"' in html and "var DURATION = 2.00" in html
    import check_clip
    err, _ = check_clip.check(html, clip_id=bs[0]["id"])
    assert not err, err
    assert look_for({})["ground"] == "#FFFFFF" and look_for({"look": {"preset": "mono"}})["font"] == "IBM Plex Sans"
    assert look_for({}, {"brand": {"accent": "#FF0000"}})["accent"] == "#FF0000"
    p = placed_beat(visuals[0], bs[0], "images/motion-01-over.mp4", 0.1, 2.1)
    assert p["props"]["start_s"] == 0.1 and p["fallback"] is visuals[0] and p["type"] == "video_card", p   # skips to finish
    assert placed_beat(visuals[0], bs[0], "x", 0.2, 1.0)["props"]["start_s"] == 0.0
    with tempfile.TemporaryDirectory() as t:   # place: a passed clip in, a failed one back to its template
        e = Path(t)
        (e / "visuals.json").write_text(json.dumps(visuals), encoding="utf-8")
        (e / "motion").mkdir()
        (e / "motion" / "beats.json").write_text(json.dumps({"beats": bs}), encoding="utf-8")
        for b, ok in zip(bs, (True, False)):
            (e / "motion" / b["id"] / "renders").mkdir(parents=True)
            (e / "motion" / b["id"] / "gates.json").write_text(json.dumps({"pass": ok}), encoding="utf-8")
        clip = e / "motion" / bs[0]["id"] / "renders" / "clip.mp4"
        rc, _ = run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=120x64:r=30:d=2", "-pix_fmt", "yuv420p", clip])
        if rc == 0:
            placed, back = place(e)
            v = json.loads((e / "visuals.json").read_text(encoding="utf-8"))
            assert v[0]["type"] == "video_card" and v[0]["fallback"]["type"] == "likes" and list((e / "images").glob(f"motion-{bs[0]['id']}-*.mp4")), v[0]
            assert v[3]["type"] == "notes" and len(back) == 1, (v[3], back)
            (e / "motion" / bs[0]["id"] / "gates.json").write_text(json.dumps({"pass": False}), encoding="utf-8")
            place(e)
            assert json.loads((e / "visuals.json").read_text(encoding="utf-8"))[0]["type"] == "likes"   # failed later: the template again
            v = e / "frame.mp4"   # strips: 16 consecutive frames a row, the safe box drawn
            run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=108x192:r=30:d=3", "-pix_fmt", "yuv420p", v])
            strips(v, [1.0, 2.0], e / "s.png", width=60, safe=True)
            rc, wh = run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0", e / "s.png"])
            assert wh.strip().split(",")[0] == str(16 * 60 + 15 * 2), wh
    assert cream((253, 248, 236)) and not cream((255, 255, 255)) and not cream((23, 22, 20))
    assert panel_size({}) is None and panel_size({"layout": {"mode": "split", "seam": 50}}) == [1200, 1006]
    assert board_size({}) is None and board_size({"layout": {"mode": "board"}}) == [1200, 964]
    assert look_for({"motion": {"look": "board"}})["ground"] == "#0B0B0D"
    with tempfile.TemporaryDirectory() as t:   # the panel gate: a full-bleed drawing passes, a small one on white fails
        for name, vf, want in (("ok", "drawbox=x=20:y=20:w=200:h=160:color=black:t=fill", True),
                               ("small", "drawbox=x=100:y=90:w=30:h=20:color=black:t=fill", False)):
            v = Path(t) / f"{name}.mp4"
            run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=0xFDF8EC:s=240x200:d=1:r=30", "-vf", vf, "-pix_fmt", "yuv444p", v])
            assert panel_fill(v, (0xFD, 0xF8, 0xEC))[0] is want, (name, panel_fill(v, (0xFD, 0xF8, 0xEC)))
    assert motion_cfg({"graphics": {"kinds": {"animation": 55}}})["amount"] == 0.55   # a measured style's share
    assert motion_cfg({"motion": {"amount": 0}, "graphics": {"kinds": {"animation": 55}}})["amount"] == 0.0
    assert look_for({"motion": {"look": "mono"}, "look": {"preset": "editorial"}})["name"] == "mono"
    with tempfile.TemporaryDirectory() as t:   # library: save, reuse as a starting point, archive, no straight copy
        keep = os.environ.get("AI_EDITOR_HOME")
        os.environ["AI_EDITOR_HOME"] = str(Path(t) / "home")
        try:
            e = Path(t) / "ed"
            b = dict(bs[0])
            (e / "motion" / b["id"] / "renders").mkdir(parents=True)
            (e / "motion" / b["id"] / "index.html").write_text(fill_template(b, DEFAULT_LOOK).replace("// 4.", "// built\n// 4."), encoding="utf-8")
            (e / "motion" / "beats.json").write_text(json.dumps({"look": DEFAULT_LOOK, "beats": [b]}), encoding="utf-8")
            (e / "visuals.json").write_text(json.dumps([placed_beat(visuals[0], b, "x", 0, 1)]), encoding="utf-8")
            lid = save(e)[0]
            assert save(e) == [] and lib_entries()[0]["kind"] == "counter" and starting_point("likes")["id"] == lid
            d = e / "motion" / "x-new"
            d.mkdir()
            shutil.copy(library_dir() / lid / "index.html", d / "start.html")
            (d / "index.html").write_text((d / "start.html").read_text(encoding="utf-8").replace(b["id"], "x-new"), encoding="utf-8")
            assert same_as_start(d)
            (d / "index.html").write_text((d / "index.html").read_text(encoding="utf-8").replace("// built", "// re-timed"), encoding="utf-8")
            assert not same_as_start(d)
            lib_set(lid, use=True)
            assert starting_point("likes")["use_next"]
            lib_set(lid, archived=True)
            assert starting_point("likes") is None   # archived: never used
            assert note(e, "make the counter bigger", at=b["start"] + 0.5) == b["id"]
            assert "bigger" in (e / "motion" / b["id"] / "notes.md").read_text(encoding="utf-8")
        finally:
            if keep is None:
                os.environ.pop("AI_EDITOR_HOME", None)
            else:
                os.environ["AI_EDITOR_HOME"] = keep
    print("demo ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pick")
    p.add_argument("edit")
    p.add_argument("--max", type=int, default=8)
    sub.add_parser("check").add_argument("clip")
    sub.add_parser("place").add_argument("edit")
    sub.add_parser("status").add_argument("edit")
    s = sub.add_parser("strips")
    s.add_argument("video")
    s.add_argument("--at", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--fps", type=float, default=10)
    s.add_argument("--before", type=float, default=0.4)
    s.add_argument("--after", type=float, default=1.1)
    s.add_argument("--safe", action="store_true")
    n = sub.add_parser("note")
    n.add_argument("edit")
    n.add_argument("text")
    n.add_argument("--at", type=float)
    n.add_argument("--clip")
    sv = sub.add_parser("save")
    sv.add_argument("edit")
    sv.add_argument("--clip")
    lb = sub.add_parser("library")
    lb.add_argument("action", nargs="?", default="list", choices=["list", "archive", "unarchive", "use"])
    lb.add_argument("id", nargs="?")
    sub.add_parser("demo")
    a = ap.parse_args()
    if a.cmd == "pick":
        pick(a.edit, a.max)
    elif a.cmd == "check":
        sys.exit(check(a.clip))
    elif a.cmd == "place":
        place(a.edit)
    elif a.cmd == "status":
        status(a.edit)
    elif a.cmd == "note":
        note(a.edit, a.text, a.at, a.clip)
    elif a.cmd == "save":
        save(a.edit, a.clip)
    elif a.cmd == "library":
        if a.action == "list":
            for e in lib_entries():
                print(f"{e['id']:<26} {e['kind']:<12} {'archived' if e.get('archived') else 'use again' if e.get('use_next') else '':<9} \"{e['line'][:60]}\"")
        else:
            lib_set(a.id, archived={"archive": True, "unarchive": False}.get(a.action), use=True if a.action == "use" else None)
    elif a.cmd == "strips":
        strips(a.video, [float(x) for x in a.at.split(",")], a.out, a.before, a.after, a.fps, a.safe)
    else:
        demo()


if __name__ == "__main__":
    main()
