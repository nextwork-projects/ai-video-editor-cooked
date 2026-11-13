#!/usr/bin/env python3
"""scene.json: every video is a scene of editable items (SCENE.md), drawn by the Remotion `Scene` composition
live in the review page and for the export.

    python3 scene.py from-plan <edit> [--plan plan.json]   a cooked. plan draft as a scene: the cut's kept pieces of the
                                                           raw take as clips, cards, texts, captions and sounds as items
    python3 scene.py from-video <edit> [--video render.mp4]   any other draft: its MP4 as a video clip
    python3 scene.py render <edit> [--out file.mp4] [--draft] the export (Remotion, the Scene composition)
    python3 scene.py stills <edit> <out_dir> name=frame ...   frames of the scene as PNGs (the same bundle)
    python3 scene.py show <edit> [--at t]                   the items (ids, times, boxes) and the words said, to target
    python3 scene.py ops <edit> '<json ops>'|ops.json [--why "<one line>"]   Claude's change: POST /scene/ops's ops
    python3 scene.py add <edit> text|image|video|shape|audio --start t [--end t] [--src file] [--text "..."]
                     [--x --y --w --h] [--track name] [--json '{...}'] [--why "..."]   one item, as an op
    python3 scene.py cards <edit> [--at t,t] [--plan plan.json] [--why "..."]   plan.json's new cards (overlays, motion) as items
    python3 scene.py demo                                   self-check
    show, ops, add, cards and render take --alt <version>: that version's scene (scene.<alt>.json, a trial reel's)

Skills write scenes with the helper: Scene(w, h, fps).video(src, start, end, ...), .image, .text, .shape, .audio,
.captions, then .save(edit). Stdlib + ffmpeg (numpy, when there, finds a cut's sideways framing).
"""
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parents[1]
EDIT_PY = PLUGIN / "skills" / "style-edit" / "scripts" / "edit.py"
NAME = "scene.json"
CHANGES = Path("review") / "claude.json"   # Claude's changes, each with the ops that undo and redo it (SCENE.md); a version's: changes_of
TYPES = {"video": "visual", "image": "visual", "text": "visual", "shape": "visual", "card": "visual", "audio": "audio", "captions": "captions"}
ANIMS = {"none", "cut", "fade", "pop", "slide-up"}
EASES = {"linear", "in", "out", "inout", "hold"}
KEY_PROPS = {"x", "y", "w", "h", "scale", "rotation", "opacity"}
TRACK_NAMES = {"video": "Video", "image": "Images", "card": "Cards", "shape": "Shapes", "text": "Text", "audio": "Sounds", "captions": "Captions"}
REASONS = {"retake": "retake", "redundant": "retake", "alt_hook": "retake", "false_start": "false start", "silence": "pause",
           "pause": "pause", "filler": "filler"}
EPS = 1e-6
AUDIO_EXT = (".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus")


class SceneError(ValueError):
    pass


def jload(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def jsave(p, d):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f".{p.name}.{os.getpid()}.{threading.get_ident()}.tmp")   # per thread: two saves at once never share a temp file
    tmp.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def probe(path):
    """{w, h, duration, kind, codec, adur (its sound's length), alpha (it has transparency)} of a media file, rotation applied."""
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height,duration,pix_fmt:stream_tags"
                          ":stream_side_data=rotation:format=duration", "-of", "json", str(path)], capture_output=True, text=True)
    if out.returncode:
        raise SceneError(f"ffprobe could not read {path}")
    d = json.loads(out.stdout)
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), None)
    dur = float((d.get("format") or {}).get("duration") or 0)
    if not v or Path(path).suffix.lower() in AUDIO_EXT:   # a song's cover art is no picture
        return {"kind": "audio", "duration": dur}
    w, h = v["width"], v["height"]
    if any(abs(sd.get("rotation", 0)) == 90 for sd in v.get("side_data_list", [])):
        w, h = h, w
    still = Path(path).suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
    au = next((float(s["duration"]) for s in d.get("streams", []) if s.get("codec_type") == "audio" and s.get("duration")), None)
    # a clip with transparency: VP9/VP8 WebM tags it (the decoder reports yuv420p), ProRes 4444 and PNG video say it in pix_fmt
    alpha = not still and (str({k.lower(): x for k, x in (v.get("tags") or {}).items()}.get("alpha_mode")) == "1"
                           or (v.get("pix_fmt") or "").startswith(("yuva", "rgba", "argb", "bgra", "abgr", "gbrap", "ya")))
    return {"kind": "image" if still else "video", "w": w, "h": h, "duration": 0 if still else dur, "codec": v.get("codec_name"), "adur": au,
            **({"alpha": True} if alpha else {})}


# ---------------------------------------------------------------- shape
def defaults(it, sc):
    """An item with every field its type has, at the plain look (SCENE.md)."""
    W, H, t = sc["width"], sc["height"], it.get("type")
    d = {"name": TRACK_NAMES.get(t, t)}
    if TYPES.get(t) == "visual":
        d.update(x=W / 2, y=H / 2, w=round(W * 0.84) if t == "text" else W, h=H, rotation=0, opacity=1, fit="cover", crop=None,
                 radius=0, shadow=None, border=None, anim=None, keys={})
    if t in ("video", "audio"):
        d.update({"in": 0, "speed": 1, "volume": 1, "fade_in": 0, "fade_out": 0})
    if t == "text":
        d.update(text="", font="TikTok Sans", weight=700, size=round(min(W, H) * 0.05), color="#FFFFFF", align="center",
                 line_height=1.2, box=None, outline=None)
    if t == "shape":
        d.update(fill="#FFFFFF", stroke=None)
    if t == "captions":
        d.update(words=[], style={}, asset=None)
    return {**d, **it}


def normalise(sc):
    """Defaults filled in, ids given, duration = the last item's end."""
    sc = {"version": 1, "fps": 30, "background": "#000000", "assets": {}, "tracks": [], **sc}
    ids = {it.get("id") for tr in sc["tracks"] for it in tr.get("items", [])}
    n = 0
    for i, tr in enumerate(sc["tracks"]):
        tr.setdefault("id", f"t{i + 1}")
        tr.setdefault("kind", "visual")
        tr.setdefault("name", tr["kind"].title())
        tr.setdefault("hidden", False)
        tr.setdefault("locked", False)
        tr.setdefault("items", [])
        if tr["kind"] == "audio":
            tr.setdefault("muted", tr.pop("hidden", False))
        for j, it in enumerate(tr["items"]):
            if not it.get("id"):
                while f"{(it.get('type') or 'x')[0]}{n}" in ids:
                    n += 1
                it["id"] = f"{(it.get('type') or 'x')[0]}{n}"
                ids.add(it["id"])
            tr["items"][j] = defaults(it, sc)
    ends = [it["end"] for tr in sc["tracks"] for it in tr["items"] if isinstance(it.get("end"), (int, float))]
    if ends:
        sc["duration"] = round(max(ends), 6)
    sc.setdefault("duration", 0)
    return sc


def magnet(sc, tr):
    """The magnet: on by default for the first visual track (the footage), off elsewhere."""
    first = next((t for t in sc["tracks"] if t["kind"] == "visual"), None)
    return tr.get("magnet", tr is first)


def validate(sc):
    """The scene, or SceneError naming every problem."""
    errs = []
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    for k in ("width", "height", "fps"):
        if not num(sc.get(k)) or sc[k] <= 0:
            errs.append(f"{k} must be a positive number (got {sc.get(k)!r})")
    for aid, a in (sc.get("assets") or {}).items():
        if not isinstance(a, dict) or not a.get("src"):
            errs.append(f"asset {aid}: needs a src")
    seen, tids = set(), set()
    for tr in sc.get("tracks") or []:
        tid = tr.get("id")
        if tid in tids:
            errs.append(f"track {tid}: two tracks have this id")
        tids.add(tid)
        if tr.get("kind") not in ("visual", "audio", "captions"):
            errs.append(f"track {tid}: kind must be visual, audio or captions (got {tr.get('kind')!r})")
        for it in tr.get("items") or []:
            iid, t = it.get("id"), it.get("type")
            where = f"item {iid} ({t}) on track {tid}"
            if iid in seen:
                errs.append(f"{where}: two items have this id")
            seen.add(iid)
            if t not in TYPES:
                errs.append(f"{where}: type must be one of {', '.join(sorted(TYPES))}")
                continue
            if TYPES[t] != tr.get("kind"):
                errs.append(f"{where}: a {t} goes on a {TYPES[t]} track, not a {tr.get('kind')} one")
            if not (num(it.get("start")) and num(it.get("end"))) or it["end"] <= it["start"]:
                errs.append(f"{where}: needs start < end (got {it.get('start')!r} to {it.get('end')!r})")
            if t in ("video", "image", "audio") and it.get("asset") not in (sc.get("assets") or {}):
                errs.append(f"{where}: asset {it.get('asset')!r} is not in assets")
            if t in ("video", "audio") and not (num(it.get("speed", 1)) and it.get("speed", 1) > 0):
                errs.append(f"{where}: speed must be above 0")
            if t == "captions" and not isinstance(it.get("words", []), list):
                errs.append(f"{where}: words must be a list")
            for k in ("box", "shadow"):   # a box's fill and a shadow's colour see-through, 0-1
                o = it[k].get("opacity") if isinstance(it.get(k), dict) else None
                if o is not None and not (num(o) and 0 <= o <= 1):
                    errs.append(f"{where}: {k}.opacity must be 0 to 1 (got {o!r})")
            sh = it.get("shadow") if isinstance(it.get("shadow"), dict) else {}
            for sub in ("blur", "y", "distance", "angle"):
                if sh.get(sub) is not None and not num(sh[sub]):
                    errs.append(f"{where}: shadow.{sub} must be a number (got {sh[sub]!r})")
            if sh.get("color") is not None and not (isinstance(sh["color"], str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", sh["color"])):
                errs.append(f"{where}: shadow.color must be #RRGGBB (got {sh['color']!r})")
            a = it.get("anim")
            if a and (a.get("in", "none") not in ANIMS or a.get("out", "none") not in ANIMS):
                errs.append(f"{where}: anim in and out must be one of {', '.join(sorted(ANIMS))}")
            for prop, ks in (it.get("keys") or {}).items():
                if prop not in KEY_PROPS:
                    errs.append(f"{where}: keys on {prop!r}: only {', '.join(sorted(KEY_PROPS))}")
                elif not isinstance(ks, list) or any(not isinstance(k, list) or len(k) < 2 or not num(k[0]) or not num(k[1])
                                                    or (len(k) > 2 and k[2] not in EASES) for k in ks):
                    errs.append(f"{where}: keys {prop} must be [[t, value, ease], ...] with ease one of {', '.join(sorted(EASES))}")
    if errs:
        raise SceneError("scene.json: " + "; ".join(errs))
    return sc


def name_of(alt=None):
    """The scene file of a version: scene.json for the round's main draft, scene.<alt>.json for another version (a
    name with other characters than letters, digits, - and _ as those and a short hash: "Trial t1: x" is
    scene.Trial-t1-x-1a2b3c4d.json)."""
    if not alt:
        return NAME
    import hashlib, re
    slug = re.sub(r"[^\w-]+", "-", str(alt)).strip("-")[:48] or "v"
    return f"scene.{slug}.json" if slug == alt else f"scene.{slug}-{hashlib.sha1(str(alt).encode()).hexdigest()[:8]}.json"


def changes_of(alt=None):
    """Claude's change log of a version: review/claude.json for the main draft, review/claude.<alt>.json beside its scene."""
    return CHANGES.with_name("claude" + name_of(alt)[len("scene"):])


def load(edit, name=NAME):
    return validate(normalise(jload(Path(edit) / name)))


def save(edit, sc, name=NAME):
    sc = validate(normalise(sc))
    jsave(Path(edit) / name, sc)
    return sc


# ---------------------------------------------------------------- ops
def find(sc, iid):
    for tr in sc["tracks"]:
        for i, it in enumerate(tr["items"]):
            if it["id"] == iid:
                return tr, i, it
    raise SceneError(f"no item {iid!r}")


def track_of(sc, tid):
    tr = next((t for t in sc["tracks"] if t["id"] == tid), None)
    if not tr:
        raise SceneError(f"no track {tid!r}")
    return tr


def editable(tr, it=None):
    if tr.get("locked") or (it or {}).get("locked"):
        raise SceneError(f"{'item ' + it['id'] if it and it.get('locked') else 'track ' + tr['id']} is locked")


def ripple(sc, at, delta, skip=None):
    """Every item at or after `at` moves by delta (an item across `at` grows or shrinks): the magnet."""
    fr = 1 / sc["fps"]
    for tr in sc["tracks"]:
        for it in tr["items"]:
            if it is skip:
                continue
            if it["start"] >= at - EPS:
                it["start"], it["end"] = round(it["start"] + delta, 6), round(it["end"] + delta, 6)
            elif it["end"] > at + EPS:
                it["end"] = round(max(it["start"] + fr, it["end"] + delta), 6)


def touch(it, by):
    """Who changed the item last: by "claude" marks it (the timeline's Claude mark), the page (None) clears the mark,
    "keep" (an undo or redo of Claude's change) leaves it."""
    if by == "claude":
        it["by"] = "claude"
    elif by is None:
        it.pop("by", None)


def apply(sc, ops, edit=None, by=None):
    """The scene after ops (SCENE.md), in order. SceneError on a bad op; the scene passed in is never changed.
    edit: the edit folder, so an added asset is probed (its size and length). by: touch()."""
    sc = normalise(copy.deepcopy(sc))
    fr = 1 / sc["fps"]
    if not isinstance(ops, list):
        raise SceneError("ops must be a list of ops")
    for op in ops:
        kind = op.get("op")
        if kind == "set":
            tr, _, it = find(sc, op.get("item"))
            props = dict(op.get("props") or {})
            if set(props) - {"locked"}:
                editable(tr, it)
            for k in ("id", "type"):
                props.pop(k, None)
            it.update(props)
            touch(it, by)
        elif kind == "add":
            tr = track_of(sc, op.get("track"))
            editable(tr)
            it = dict(op.get("item") or {})
            if it.get("id") and any(x["id"] == it["id"] for t in sc["tracks"] for x in t["items"]):
                raise SceneError(f"item {it['id']} already exists")
            touch(it, by)
            tr["items"].insert(op.get("index", len(tr["items"])), it)
            sc = normalise(sc)
        elif kind == "remove":
            tr, i, it = find(sc, op.get("item"))
            editable(tr, it)
            del tr["items"][i]
            if magnet(sc, tr) and it["type"] == "video":
                ripple(sc, it["end"], -(it["end"] - it["start"]))
        elif kind == "move":
            tr, i, it = find(sc, op.get("item"))
            to = track_of(sc, op.get("track"))
            editable(tr, it)
            editable(to)
            if TYPES[it["type"]] != to["kind"]:
                raise SceneError(f"a {it['type']} cannot go on {to['kind']} track {to['id']}")
            del tr["items"][i]
            touch(it, by)
            to["items"].insert(op.get("index", len(to["items"])), it)
        elif kind == "track":
            tr = track_of(sc, op.get("track"))
            tr.update({k: v for k, v in (op.get("props") or {}).items() if k not in ("id", "items", "kind")})
        elif kind == "add_track":
            t = {"items": [], **(op.get("track") or {})}
            if any(x["id"] == t.get("id") for x in sc["tracks"]):
                raise SceneError(f"track {t['id']} already exists")
            t.setdefault("id", next(f"t{n}" for n in range(1, 999) if all(x["id"] != f"t{n}" for x in sc["tracks"])))
            sc["tracks"].insert(op.get("index", len(sc["tracks"])), t)
            sc = normalise(sc)
        elif kind == "remove_track":
            tr = track_of(sc, op.get("track"))
            editable(tr)
            sc["tracks"].remove(tr)
        elif kind == "split":
            tr, i, it = find(sc, op.get("item"))
            editable(tr, it)
            t = float(op.get("t", -1))
            if not it["start"] + fr - EPS <= t <= it["end"] - fr + EPS:
                raise SceneError(f"split at {t}: outside item {it['id']} ({it['start']} to {it['end']})")
            touch(it, by)
            b = copy.deepcopy(it)
            b["id"] = None
            it["end"], b["start"] = round(t, 6), round(t, 6)
            if "in" in it:
                b["in"] = round(it["in"] + (t - it["start"]) * it.get("speed", 1), 6)
            b.pop("cut", None)
            for k in ("keys",):   # keys run from each part's own start
                b[k] = {p: [[round(k_[0] - (t - it["start"]), 6), *k_[1:]] for k_ in ks] for p, ks in (it.get(k) or {}).items()}
            tr["items"].insert(i + 1, {k: v for k, v in b.items() if k != "id"})
            sc = normalise(sc)
        elif kind == "trim":
            tr, _, it = find(sc, op.get("item"))
            editable(tr, it)
            by, edge = float(op.get("by", 0)), op.get("edge")
            if edge not in ("start", "end"):
                raise SceneError("trim takes edge start or end")
            if it["end"] - it["start"] - by * (1 if edge == "start" else -1) < fr - EPS:
                raise SceneError(f"trim by {by}: item {it['id']} would be shorter than a frame")
            sp, old_end = it.get("speed", 1), it["end"]
            touch(it, by)
            if edge == "start":
                if "in" in it and it["in"] + by * sp < -EPS:
                    raise SceneError(f"trim by {by}: item {it['id']} would start before its source")
                if "in" in it:
                    it["in"] = round(it["in"] + by * sp, 6)
                if magnet(sc, tr):   # the clip stays where it is, shorter or longer; everything after closes up or opens
                    it["end"] = round(it["end"] - by, 6)
                    ripple(sc, old_end, -by, skip=it)
                else:
                    it["start"] = round(it["start"] + by, 6)
                for p, ks in (it.get("keys") or {}).items():
                    it["keys"][p] = [[round(k[0] - by, 6), *k[1:]] for k in ks]
            else:
                it["end"] = round(it["end"] + by, 6)
                if magnet(sc, tr):
                    ripple(sc, old_end, by, skip=it)
        elif kind == "asset" and op.get("asset") is None:   # an asset no item uses any more (the undo of an add)
            aid = str(op.get("id") or "")
            if any(it.get("asset") == aid for tr in sc["tracks"] for it in tr["items"]):
                raise SceneError(f"asset {aid} is still on the timeline")
            sc["assets"].pop(aid, None)
        elif kind == "asset":
            a, aid = dict(op.get("asset") or {}), str(op.get("id") or "")
            src = Path(str(a.get("src") or ""))
            if not aid or src.is_absolute() or ".." in src.parts or not src.parts:
                raise SceneError("asset takes an id and a src inside the edit folder")
            if edit and not a.get("kind"):
                if not (Path(edit) / src).is_file():
                    raise SceneError(f"asset {aid}: {src} is not in the edit")
                a.update({k: v for k, v in probe(Path(edit) / src).items() if k not in ("codec", "adur")})
                if needs_proxy({**a, "src": src.as_posix()}, sc["width"], sc["height"]):   # a seekable copy, alpha kept
                    a["proxy"] = f".scene/{aid}.{'webm' if a.get('alpha') else 'mp4'}"
            sc["assets"][aid] = {**a, "src": src.as_posix()}
        else:
            raise SceneError(f"unknown op {kind!r}: set, add, remove, move, track, add_track, remove_track, split, trim or asset")
    return validate(normalise(sc))


# ---------------------------------------------------------------- the helper skills call
class Scene:
    """Scene(1080, 1920, 30).video("cut.mp4", 0, 12).text("Hi", 0, 2, y=400).save(edit). Each adder returns the item
    (a dict: change any field); `track` names the track (made on first use, in order: the first one is the bottom)."""

    def __init__(self, w, h, fps=30, background="#000000", edit=None):
        self.sc = {"version": 1, "width": w, "height": h, "fps": fps, "duration": 0, "background": background, "assets": {}, "tracks": []}
        self.edit = Path(edit) if edit else None

    def track(self, name, kind="visual", **kw):
        tr = next((t for t in self.sc["tracks"] if t["name"] == name or t["id"] == name), None)
        if not tr:
            tr = {"id": f"{kind[0]}{1 + sum(t['kind'] == kind for t in self.sc['tracks'])}", "kind": kind, "name": name, "items": [], **kw}
            self.sc["tracks"].append(tr)
        return tr

    def asset(self, src, aid=None, **kw):
        """The asset id for a file (src relative to the edit, or absolute), probed once."""
        for k, a in self.sc["assets"].items():
            if a["src"] == str(src):
                return k
        aid = aid or "".join(c if c.isalnum() else "-" for c in Path(str(src)).stem.lower())[:24] or "a"
        base, n = aid, 2
        while aid in self.sc["assets"]:
            aid, n = f"{base}-{n}", n + 1
        p = Path(src) if Path(src).is_absolute() or not self.edit else self.edit / src
        info = probe(p) if p.exists() else {}
        self.sc["assets"][aid] = {"src": str(src), **{k: v for k, v in info.items() if k not in ("codec", "adur")}, **kw}
        return aid

    def _add(self, typ, start, end, track=None, **kw):
        kind = TYPES[typ]
        it = {"type": typ, "start": round(start, 6), "end": round(end, 6), **kw}
        self.track(track or TRACK_NAMES[typ], kind)["items"].append(it)
        return it

    def _fit(self, aid, kw):
        a, W, H = self.sc["assets"][aid], self.sc["width"], self.sc["height"]
        if "w" not in kw and a.get("w"):   # the whole picture, as big as the frame allows
            f = min(W / a["w"], H / a["h"])
            kw.setdefault("w", round(a["w"] * f, 2))
            kw.setdefault("h", round(a["h"] * f, 2))
        return kw

    def video(self, src, start=0, end=None, track=None, **kw):
        aid = self.asset(src)
        end = end if end is not None else start + (self.sc["assets"][aid].get("duration") or 1) / kw.get("speed", 1) - kw.get("in", 0)
        return self._add("video", start, end, track, asset=aid, **self._fit(aid, kw))

    def image(self, src, start, end, track=None, **kw):
        aid = self.asset(src)
        return self._add("image", start, end, track, asset=aid, **self._fit(aid, kw))

    def text(self, text, start, end, track=None, **kw):
        return self._add("text", start, end, track, text=text, **kw)

    def shape(self, start, end, track=None, **kw):
        return self._add("shape", start, end, track, **kw)

    def audio(self, src, start=0, end=None, track=None, **kw):
        aid = self.asset(src)
        end = end if end is not None else start + (self.sc["assets"][aid].get("duration") or 1) / kw.get("speed", 1) - kw.get("in", 0)
        return self._add("audio", start, end, track, asset=aid, **kw)

    def captions(self, words, style=None, start=0, end=None, track=None, **kw):
        end = end if end is not None else max([w["end"] for w in words] or [start + 1])
        return self._add("captions", start, end, track, words=words, style=style or {}, **kw)

    def done(self):
        return validate(normalise(copy.deepcopy(self.sc)))

    def save(self, edit=None):
        return save(edit or self.edit, self.sc)


# ---------------------------------------------------------------- migration
def rel(edit, p):
    p = Path(p)
    try:
        return p.resolve().relative_to(Path(edit).resolve()).as_posix()
    except ValueError:
        return str(p)


EASE_F = {"linear": lambda u: u, "in": lambda u: u * u, "out": lambda u: 1 - (1 - u) ** 2,
          "inout": lambda u: (1 - __import__("math").cos(__import__("math").pi * u)) / 2, "hold": lambda u: 0}


def key_at(ks, t):
    """A keyed value at t: the last key at or before t, eased toward the next (Scene.tsx keyAt)."""
    i = max([j for j, k in enumerate(ks) if k[0] <= t + EPS] or [0])
    k = ks[i]
    if i + 1 >= len(ks) or t < k[0]:
        return k[1]
    n = ks[i + 1]
    u = (t - k[0]) / max(EPS, n[0] - k[0])
    return k[1] + (n[1] - k[1]) * EASE_F[k[2] if len(k) > 2 else "linear"](min(1, u))


ZOOM_ORIGIN = (50, 30)   # StyleEdit.tsx's, % of the frame, for a zoom with no origin of its own


def zoom_keys(zooms, a, b):
    """Scale keys on a clip from scene a to b: StyleEdit.tsx zoomAt's punches (held, or eased in PUNCH_S) and pushes
    (sine in and out), from the clip's start. And each key's zoom origin, % of the frame (zoomAt scales each zoom about
    its own origin)."""
    zs = sorted(zooms, key=lambda z: z["start"])
    pts = []
    for i, z in enumerate(zs):
        k, nxt, o = z["scale"], zs[i + 1]["start"] if i + 1 < len(zs) else float("inf"), tuple(z.get("origin") or ZOOM_ORIGIN)
        if z.get("kind") == "push" and z.get("ease_s", 0) > 0:
            e = min(max(0.8, z["ease_s"]), (z["end"] - z["start"]) / 2)
            pts += [[z["start"], 1, "inout", o], [z["start"] + e, k, "hold", o], [z["end"] - e, k, "inout", o], [z["end"], 1, "hold", o]]
            continue
        tr = z.get("travel_s", 0.16)
        tail = min(tr, max(0, nxt - z["end"]))
        if tr < 0.02:
            pts += [[z["start"], k, "hold", o]] + ([[z["end"], 1, "hold", o]] if tail > 0 else [])
        else:
            pts += [[z["start"], 1, "out", o], [z["start"] + tr, k, "hold", o]] + ([[z["end"], k, "out", o], [z["end"] + tail, 1, "hold", o]] if tail > 0 else [])
    pts = sorted(pts, key=lambda p: p[0])
    if not pts:
        return {}, None
    o_at = lambda t: max((p for p in pts if p[0] <= t + EPS), key=lambda p: p[0], default=pts[0])[3]
    keys = [[0, round(key_at(pts, a) if pts[0][0] <= a else 1, 6), "hold"]]
    orgs = [o_at(a)]
    for p in pts:
        if a + EPS < p[0] < b - EPS:
            keys.append([round(p[0] - a, 6), p[1], p[2]])
            orgs.append(p[3])
    if all(k[1] == 1 for k in keys):
        return {}, None
    return {"scale": keys}, orgs


def pos_keys(keys, origins, base, W, H):
    """x and y keys that hold each key's zoom origin in place while scale changes (scale about a point, not the centre).
    origins: one per scale key (zoom_keys), or one for all."""
    if not keys or not origins:
        return {}
    ks = keys["scale"]
    os_ = [origins] * len(ks) if isinstance(origins[0], (int, float)) else origins
    cx, cy = base
    return {"x": [[t, round(o[0] / 100 * W + k * (cx - o[0] / 100 * W), 3), e] for (t, k, e), o in zip(ks, os_)],
            "y": [[t, round(o[1] / 100 * H + k * (cy - o[1] / 100 * H), 3), e] for (t, k, e), o in zip(ks, os_)]}


def framing(edit, plan, src, spans):
    """How the cut sits on the raw take after the cut was rendered (a house step slid it sideways or down): (dx, dy) in
    canvas px, from one frame of each. (0, 0) without numpy or when nothing moved."""
    try:
        import numpy as np
    except ImportError:
        return 0, 0
    W, H = plan["width"], plan["height"]
    sw, sh = 135, round(135 * H / W)
    s = max(spans, key=lambda x: x["end"] - x["start"])
    t_cut = sum(x["end"] - x["start"] for x in spans[:spans.index(s)]) + (s["end"] - s["start"]) / 2

    def grab(p, t):
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(p), "-frames:v", "1", "-vf",
                            f"scale={sw}:{sh}:flags=area", "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True)
        return np.frombuffer(r.stdout, np.uint8).reshape(sh, sw).astype(float) if len(r.stdout) == sw * sh else None
    def search(a, b, m, c=(0, 0)):
        h_, w_ = a.shape
        best = (float("inf"), 0, 0)
        for dy in range(c[1] - m, c[1] + m + 1):
            for dx in range(c[0] - m, c[0] + m + 1):
                ys, xs = slice(max(0, dy), h_ + min(0, dy)), slice(max(0, dx), w_ + min(0, dx))
                yb, xb = slice(max(0, -dy), h_ + min(0, -dy)), slice(max(0, -dx), w_ + min(0, -dx))
                d = abs(a[ys, xs] - b[yb, xb]).mean()
                if d < best[0] - 0.01 or (d < best[0] + 0.01 and abs(dx) + abs(dy) < abs(best[1]) + abs(best[2])):
                    best = (min(d, best[0]), dx, dy)
        return best
    tc, ts = s["start"] + (s["end"] - s["start"]) / 2, t_cut
    a, b = grab(Path(edit) / plan["video"], ts), grab(src, tc)
    if a is None or b is None:
        return 0, 0
    _, cx, cy = search(a, b, sw // 8)   # coarse, then at full size around it
    sw, sh = W // 2, H // 2
    a, b = grab(Path(edit) / plan["video"], ts), grab(src, tc)
    k = sw // 135
    _, dx, dy = search(a, b, k + 1, (cx * k, cy * k))
    return dx * 2, dy * 2


def cover(sc):
    """The footage zoomed just enough to cover the frame edge to edge: a cut the house centre step slid sideways
    (framing's dx, dy) otherwise leaves a black strip where the step mirrored the picture in. Each zoom key that falls
    short is raised about the clip's centre (so the zooms that already cover keep their framing exactly), and a clip
    still short anywhere (no zoom keys) grows, keeping its shape. Only video clips on the first visual track that fill
    most of the frame (a picture-in-picture is left alone). The ids it changed; the scene is marked `covered` so a later
    move of the user's is never undone."""
    W, H = sc["width"], sc["height"]
    first = next((t for t in sc["tracks"] if t["kind"] == "visual"), None)
    out = []
    for it in (first or {}).get("items", []):
        if it.get("type") != "video" or it.get("fit", "cover") != "cover" or it.get("rotation") or not it.get("w") or not it.get("h"):
            continue
        ks, d = it.get("keys") or {}, it["end"] - it["start"]
        at = lambda p, t, v: key_at(ks[p], t) if ks.get(p) else it.get(p, v)

        def need(t):   # how much bigger the picture must be at t, about its centre; None: not footage that fills the frame
            s, x, y = at("scale", t, 1), at("x", t, W / 2), at("y", t, H / 2)
            w, h = it["w"] * s, it["h"] * s
            return None if w < W * 0.8 or h < H * 0.8 else max(1.0, 2 * x / w, 2 * (W - x) / w, 2 * y / h, 2 * (H - y) / h)
        ts = sorted({0.0, d, *(k[0] for p in ("x", "y", "scale") for k in ks.get(p) or [] if 0 <= k[0] <= d)})
        if any(need(t) is None for t in ts):
            continue
        changed = False
        for k in ks.get("scale") or []:
            f = need(k[0])
            if f > 1 + 1e-4:
                k[1], changed = round(k[1] * f + 1e-4, 4), True
        f = max(need(t) for t in ts)
        if f > 1 + 1e-4:
            it["w"], it["h"], changed = round(it["w"] * f + 0.01, 2), round(it["h"] * f + 0.01, 2), True
        if changed:
            out.append(it["id"])
    sc["covered"] = True
    return out


def cut_before(report, words, prev_end, start):
    """What the cut took out between two kept pieces: {reason, words, dur}."""
    if start - prev_end < 0.02:
        return None
    over = [(min(c["end"], start) - max(c["start"], prev_end), c) for c in report.get("cuts") or []
            if c.get("end", 0) > prev_end and c.get("start", 0) < start]
    kind = max(over, key=lambda x: x[0])[1].get("kind") if over else None
    said = " ".join(w["text"].strip() for w in words if w.get("type", "word") == "word" and prev_end - EPS <= w["start"] < start)
    return {"reason": REASONS.get(kind, "by hand") if kind else "pause", "words": said, "dur": round(start - prev_end, 3)}


def raw_take(edit):
    """(the raw take, kept spans in its seconds) the cut was made from, or None."""
    e = Path(edit)
    try:
        src, spans = Path(jload(e / "report.json")["source"]), jload(e / "decisions.json")
    except (OSError, ValueError, KeyError):
        return None
    if not src.is_absolute():
        src = e / src
    spans = [s for s in spans if isinstance(s, dict) and s.get("end", 0) > s.get("start", 0)]
    return (src, spans) if src.is_file() and spans else None


def card_item(c, W, H, sizes):
    """One plan card as a scene item: a plain clip or picture as a video or image item at its box, any other card
    (a built overlay, a framed shot) as a card item drawn by the composition's CardView."""
    bx, by, bw, bh = (v / 100 * s for v, s in zip(c["box"], (W, H, W, H)))
    a = c.get("anim") or {}
    p = a.get("props") or {}
    common = {"x": round(bx + bw / 2, 2), "y": round(by + bh / 2, 2), "rotation": c.get("rotation", 0), "opacity": c.get("opacity", 1)}
    cut = lambda f: not f or f.get("kind") == "cut" or not f.get("dur")
    if a.get("type") == "video_card" and p.get("bare") and p.get("src") and cut(p.get("enter")) and cut(p.get("exit")) and not c.get("layout") == "scene":
        size = p.get("size") or sizes(p["src"])
        r = size[0] / size[1] if size else 16 / 9
        cw, ch = (bw, bw / r) if r > bw / bh else (bh * r, bh)
        land = p.get("word_at", 0.17)
        return {"type": "video", "src": p["src"], "start": round(c["start"] + land, 6), "end": c["end"], "w": round(cw, 2), "h": round(ch, 2),
                "in": round(float(p.get("start_s", 0)) + land * float(p.get("rate", 1)), 6), "speed": float(p.get("rate", 1)), "volume": 0, **common}
    if c.get("src") and c.get("format") == "plain" and not c["src"].endswith(".json"):
        return {"type": "image", "src": c["src"], "start": c["start"], "end": c["end"], "w": round(bw, 2), "h": round(bh, 2), "fit": "contain", **common}
    card = {k: v for k, v in c.items() if k not in ("start", "end", "box", "rotation", "opacity", "override", "_key", "z", "lane")}
    return {"type": "card", "card": card, "start": c["start"], "end": c["end"], "w": round(bw, 2), "h": round(bh, 2), **common}


def text_items(x, W, H):
    """A plan text (Texts.tsx) as text items."""
    k, s = x.get("kind"), min(W, H)
    emoji = lambda f: f
    if k == "label":
        fs = x.get("size_pct", 5) / 100 * s
        style = x.get("style", "plain")
        c = x.get("color", "#FFFFFF")
        dark = lambda h: 0.299 * int(h[1:3], 16) + 0.587 * int(h[3:5], 16) + 0.114 * int(h[5:7], 16) > 150
        on = x.get("text_color") or ("#000000" if dark(c) else "#FFFFFF")
        it = {"type": "text", "text": x["text"], "start": x["start"], "end": x["end"], "x": x["x_pct"] / 100 * W, "y": x["y_pct"] / 100 * H,
              "w": x.get("width_pct", 84) / 100 * W, "size": round(fs, 2), "font": emoji(x.get("font") or "TikTok Sans"), "weight": 700,
              "align": x.get("align", "center"), "color": on if style in ("box", "block") else c, "rotation": x.get("rotation", 0),
              "opacity": x.get("opacity", 1), "line_height": 1.32 if style == "box" else 1.15}
        if style == "box":
            it["box"] = {"color": c, "pad": [round(fs * 0.24, 2), round(fs * 0.06, 2)], "radius": round(fs * 0.18, 2)}
        if style == "block":
            it["box"] = {"color": c, "pad": [round(fs * 0.4, 2), round(fs * 0.22, 2)], "radius": round(fs * 0.28, 2), "block": True}
        if style == "outline":
            it["outline"] = {"color": "#000000", "width": round(fs * 0.14, 2)}
        if x.get("anim"):
            it["anim"] = {"in": {"slide": "slide-up"}.get(x["anim"], x["anim"]), "out": "fade", "dur": 0.18}
        return [it]
    if k in ("title", "cta"):
        fs = x["size_pct"] / 100 * H
        cta = k == "cta"
        return [{"type": "text", "text": (f"{x['label']}\n" if cta and x.get("label") else "") + x["text"], "start": x["start"], "end": x["end"],
                 "x": W / 2, "y": x["y_pct"] / 100 * H, "w": 0.74 * W, "size": round(fs, 2), "weight": 800, "line_height": 1.15,
                 "color": "#FFFFFF" if cta else "#000000", "box": {"color": "#0B0B0C" if cta else "#FFFFFF", "block": True,
                 "pad": [round(fs * (0.34 if cta else 0.3), 2), round(fs * (0.12 if cta else 0.25), 2)], "radius": round(fs * (0.26 if cta else 0.16), 2)},
                 "anim": {"in": "pop", "out": "fade", "dur": 0.18}}]
    if k == "onscreen":
        fs = x["size_pct"] / 100 * H
        bx, by, bw, bh = x["box"]
        it = {"type": "text", "text": x["text"], "start": x["start"], "end": x["end"], "x": (bx + bw / 2) / 100 * W, "y": (by + bh / 2) / 100 * H,
              "w": 0.9 * W, "size": round(fs, 2), "color": x.get("color", "#FFFFFF"), "line_height": 1.2}
        it.update({"box": {"color": x["box_color"], "pad": [round(fs * 0.35, 2), round(fs * 0.2, 2)], "radius": round(fs * 0.25, 2), "block": True}}
                  if x.get("box_color") else {"outline": {"color": "#000000", "width": round(fs * 0.08, 2)}})
        return [it]
    if k == "list":
        fs = x["size_pct"] / 100 * H
        return [{"type": "text", "text": f"{j + 1}. {i['text']}", "start": i["at"], "end": x["end"], "x": x["x_pct"] / 100 * W + 0.3 * W,
                 "y": x["y_pct"] / 100 * H + (j + 0.5) * 1.3 * fs, "w": 0.6 * W, "size": round(fs, 2), "align": "left", "line_height": 1.3,
                 "outline": {"color": "#000000", "width": round(fs * 0.06, 2)}, "anim": {"in": "fade", "out": "none", "dur": 0.18}}
                for j, i in enumerate(x.get("items") or [])]
    print(f"scene: a {k} text is not a scene item yet; left out", file=sys.stderr)
    return []


def from_plan(edit, plan=None, sounds=None, library=None, proxies=True, frame_it=True):
    """A plan draft as a scene (SCENE.md Migration). plan: the plan dict (default <edit>/plan.json); sounds: the timeline's
    placed sounds (sounds.json items), library: the sound library folder they name."""
    e = Path(edit)
    p = plan or jload(e / "plan.json")
    W, H, fps = p["width"], p["height"], p["fps"]
    lay = p.get("layout") or {}
    if lay.get("mode") in ("split", "board") or p.get("cover") or p.get("cutouts"):
        raise SceneError(f"a {lay.get('mode') or 'cover' if not p.get('cutouts') else 'cutout'} plan is not a scene yet: use from-video")
    S = Scene(W, H, fps, edit=e)
    dur = p["durationInFrames"] / fps
    take = raw_take(e)
    if take and abs(sum(s["end"] - s["start"] for s in take[1]) - dur) > 3 / fps:
        print(f"scene: decisions.json ({sum(s['end'] - s['start'] for s in take[1]):.2f} s) is not this cut ({dur:.2f} s): "
              "the footage is the cut as one clip", file=sys.stderr)
        take = None
    if take and not (e / p["video"]).is_file():
        take = None
    box = [0, 0, W, H]
    if lay.get("mode") == "letterbox":
        bx, by, bw, bh = (v / 100 * s for v, s in zip(lay["band"], (W, H, W, H)))
        box = [bx, by, bw, bh]
    grade = p.get("grade")
    cam_track = S.track("Video", "visual", magnet=True)
    words_raw, report = [], {}
    if take:
        src, spans = take
        dx, dy = framing(e, p, src, spans) if frame_it and lay.get("mode") != "letterbox" else (0, 0)
        aid = S.asset(rel(e, src), "cam")
        a = S.sc["assets"][aid]
        if proxies and needs_proxy(a, W, H):
            a["proxy"] = f".scene/{aid}.mp4"
        try:
            words_raw, report = jload(e / "words.raw.json"), jload(e / "report.json")
        except (OSError, ValueError):
            pass
        t, prev = 0.0, None
        clips = []
        for s in spans:
            d = s["end"] - s["start"]
            clips.append((t, t + d, s))
            t += d
    else:
        aid = S.asset(p["video"], "cam")
        dx = dy = 0
        clips = [(0.0, dur, {"start": 0.0, "end": dur})]
    base = (box[0] + box[2] / 2 + dx, box[1] + box[3] / 2 + dy)
    # a slid cut (the house centre step) mirrored a dx-wide strip in at the edge; a scene has no mirror, so cover()
    # grows each clip about its centre until it fills the frame (the face stays within a few px of where the step put it)
    prev = None
    for a_, b_, s in clips:
        it = {"type": "video", "asset": aid, "start": round(a_, 6), "end": round(b_, 6), "in": round(s["start"], 6),
              "x": base[0], "y": base[1], "w": box[2], "h": box[3], "name": "Footage"}
        if grade:
            it["grade"] = {"brightness": grade["brightness"], "saturate": grade["saturate"]}
        if take and prev is not None:
            cb = cut_before(report, words_raw, prev, s["start"])
            if cb:
                it["cut"] = {"before": cb}
        prev = s["end"]
        if lay.get("mode") != "letterbox":   # the letterbox draws its band plain, no zoom
            keys, org = zoom_keys(p.get("zooms") or [], a_, b_)
            if keys:
                it["keys"] = {**keys, **pos_keys(keys, org, base, W, H)}
        cam_track["items"].append(it)
    to_raw = lambda tt: next((s["start"] + tt - a_ for a_, b_, s in clips if a_ - EPS <= tt < b_ + EPS), None)
    # cards, a track per lane (overrides.json lanes: card.z); a later lane draws on top
    sizes_c = {}

    def sizes(src):
        if src not in sizes_c:
            try:
                i = probe(e / src)
                sizes_c[src] = [i["w"], i["h"]]
            except SceneError:
                sizes_c[src] = None
        return sizes_c[src]
    lanes = sorted({(c.get("lane") or "", c.get("z") or 0) for c in p.get("cards") or []}, key=lambda x: (x[1], x[0]))
    for n, ln in enumerate(lanes):
        name = "Cards" if not n else f"Cards {n + 1}"
        for c in sorted((c for c in p["cards"] if (c.get("lane") or "", c.get("z") or 0) == ln), key=lambda c: c["start"]):
            it = card_item(c, W, H, sizes)
            if "src" in it:
                it["asset"] = S.asset(it.pop("src"))
            it["name"] = c.get("trigger_word") or it["type"]
            if it["type"] == "card":
                it.update(look=p.get("look"), motion=p.get("motion"))
            S.track(name, "visual")["items"].append(it)
    if lay.get("mode") == "letterbox":
        if lay.get("card"):
            cbx, cby, cbw, cbh = (v / 100 * s for v, s in zip(lay["card"]["box"], (W, H, W, H)))
            S.image(lay["card"]["src"], 0, lay["card"]["to"], track="Cards", x=cbx + cbw / 2, y=cby + cbh / 2, w=cbw, h=cbh, fit="cover")
        tb = [v / 100 * s for v, s in zip(lay["title_box"], (W, H, W, H))]
        S.text(lay["title"], 0, dur, x=tb[0] + tb[2] / 2, y=tb[1] + tb[3] - lay["title_px"] / 1920 * H * 0.55, w=tb[2],
               size=round(lay["title_px"] / 1920 * H, 2), weight=400, line_height=1.1, font=(p.get("captions") or {}).get("style", {}).get("font_match") or "TikTok Sans")
    for x in p.get("texts") or []:
        for it in text_items(x, W, H):
            S.track("Text", "visual")["items"].append(it)
    cap = p.get("captions") or {}
    if cap.get("chunks"):
        words, pages = [], []
        for i, ch in enumerate(cap["chunks"]):
            mp = to_raw if take else (lambda tt: tt)
            pg = {k: ch[k] for k in ("treat", "treat_color", "face", "big", "lines") if k in ch}
            ps, pe = mp(ch["start"]), mp(max(ch["start"], ch["end"] - 1e-3))
            if ps is None:
                continue
            pages.append({"start": round(ps, 4), "end": round((pe if pe is not None else ps) + (1e-3 if pe is not None else 0), 4), **pg})
            for w in ch.get("words") or []:
                ws, we = mp(w["start"]), mp(max(w["start"], w["end"] - 1e-3))
                if ws is None:
                    continue
                words.append({"w": w["text"], "start": round(ws, 4), "end": round((we if we is not None else ws) + 1e-3, 4), "p": len(pages) - 1,
                              **{k: w[k] for k in ("emph", "big") if w.get(k)}})
        S.captions(words, cap.get("style") or {}, 0, dur, asset=aid if take else None, pages=pages, motion=p.get("motion"))
    if p.get("music"):
        S.audio(p["music"]["src"], 0, dur, track="Music")
    for c in p.get("sfx") or []:
        if c.get("placed") or str(c["src"]).startswith("/"):
            continue
        aid_ = S.asset(c["src"])
        d = S.sc["assets"][aid_].get("duration") or 1
        S.audio(c["src"], c["t"], c["t"] + d, name=Path(c["src"]).stem)
    placed(S, e, sounds, library)
    sc = S.done()
    if lay.get("mode") != "letterbox":   # the band is meant to leave the frame
        cover(sc)
    sc["duration"] = round(max(sc["duration"], dur), 6)
    return sc


def lane_name(name, n):
    return name if not n else f"{name} {n + 1}"


def placed(S, e, sounds, library):
    """The timeline's placed sounds (sounds.json items) as audio items, a track per lane (`lane`, `lane_off`: its lane is
    muted)."""
    for x in sorted((x for x in sounds or [] if isinstance(x, dict) and "sound" in x and not x.get("muted")), key=lambda x: x.get("lane", 0)):
        f = e / "audio" / x["sound"] if x.get("kind") == "clip" else Path(library or "") / x["sound"]
        if not f.is_file():
            continue
        aid_ = S.asset(rel(e, f))
        d = x.get("dur") or S.sc["assets"][aid_].get("duration") or 1
        S.track(lane_name("Placed sounds", x.get("lane", 0)), "audio", **({"muted": True} if x.get("lane_off") else {}))
        S.audio(rel(e, f), x["t"], x["t"] + d, track=lane_name("Placed sounds", x.get("lane", 0)), name=Path(x["sound"]).stem,
                volume=x.get("vol", 1), fade_in=x.get("fade_in", 0), fade_out=x.get("fade_out", 0), **{"in": x.get("in") or 0})


def from_video(edit, video, gone=(), texts=(), sounds=(), library=None):
    """Any other draft (SCENE.md Migration): its MP4 as clips on the bottom track, the Video row's cut pieces (`gone`,
    [a, b] on the MP4's clock) the gaps between them, and the hand edits already made on it as items, on the cut's
    clock: texts (plan label texts, `lane`, `lane_off`: its lane is hidden) and placed sounds (sounds.json items)."""
    e = Path(edit)
    f = Path(video) if Path(video).is_absolute() else e / video
    i = probe(f)
    W, H, end = i["w"], i["h"], min(i["duration"], i.get("adur") or i["duration"])   # ends with its sound, so the export's picture and sound end together
    S = Scene(W, H, 30, edit=e)
    aid = S.asset(rel(e, f), "draft")
    if needs_proxy(S.sc["assets"][aid], W, H):
        S.sc["assets"][aid]["proxy"] = f".scene/{aid}.mp4"
    tr = S.track("Video", "visual", magnet=True)
    t, at = 0.0, 0.0
    for a, b in [*sorted(gone), (end, end)]:
        if a - at > EPS:
            it = {"type": "video", "asset": aid, "start": round(t, 6), "end": round(t + a - at, 6), "in": round(at, 6), "x": W / 2, "y": H / 2,
                  "w": W, "h": H, "name": "Draft"}
            if at > EPS:
                it["cut"] = {"before": {"reason": "by hand", "words": "", "dur": round(at - prev, 3)}}
            tr["items"].append(it)
            t += a - at
        prev, at = a, max(at, b)
    for x in sorted(texts, key=lambda x: x.get("lane", 0)):
        S.track(lane_name("Text", x.get("lane", 0)), "visual", **({"hidden": True} if x.get("lane_off") else {}))["items"] += text_items(x, W, H)
    placed(S, e, sounds, library)
    return S.done()


# ---------------------------------------------------------------- media and render
def needs_proxy(a, W, H):
    """A take the browser cannot seek smoothly (HEVC, 4K, an iPhone's long GOP): a copy at the scene's size."""
    return a.get("kind") == "video" and (max(a.get("w", 0), a.get("h", 0)) > max(W, H) * 1.05 or Path(a["src"]).suffix.lower() == ".mov")


def proxy_cmd(src, out, a, W, H):
    f = min(1, max(W, H) / max(a["w"], a["h"]))
    w, h = round(a["w"] * f / 2) * 2, round(a["h"] * f / 2) * 2
    hw = ["-hwaccel", "videotoolbox"] if sys.platform == "darwin" else []
    if a.get("alpha"):   # VP9 with alpha: the one transparent video Chrome plays (ProRes 4444 it does not)
        dec = ["-c:v", "libvpx-vp9"] if Path(src).suffix.lower() == ".webm" else []   # ffmpeg's own VP9 decoder drops the alpha
        return ["ffmpeg", "-v", "error", "-y", *dec, "-i", str(src), "-map", "0:v:0", "-map", "0:a:0?", "-vf", f"scale={w}:{h}:flags=lanczos",
                "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0", "-crf", "24", "-row-mt", "1", "-g", "15", "-c:a", "libopus",
                "-f", "webm", str(out)]
    return ["ffmpeg", "-v", "error", "-y", *hw, "-i", str(src), "-map", "0:v:0", "-map", "0:a:0?", "-vf",
            f"scale={w}:{h}:flags=lanczos,setsar=1", "-c:v", "libx264", "-crf", "17", "-preset", "veryfast", "-g", "15",
            "-keyint_min", "15", "-sc_threshold", "0", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)]


def path_of(edit, a, playable=True):
    """The file an asset plays from: its proxy once made (playable), else its src."""
    if playable and a.get("proxy") and (Path(edit) / a["proxy"]).is_file():
        return Path(edit) / a["proxy"]
    p = Path(a["src"])
    return p if p.is_absolute() else Path(edit) / p


PROXY_LOCK = threading.Lock()   # one proxy made at a time: an export pressed while the page's copy is still being made waits for it


def ensure_proxies(edit, sc):
    """Make every proxy the scene names that is not there yet (the export waits for them)."""
    with PROXY_LOCK:
        for aid, a in sc["assets"].items():
            if not a.get("proxy") or (Path(edit) / a["proxy"]).is_file():
                continue
            out = Path(edit) / a["proxy"]
            out.parent.mkdir(parents=True, exist_ok=True)
            tmp = out.with_name(f"{out.stem}.part{os.getpid()}{out.suffix}")   # the page's server and a CLI may both make it
            print(f"preparing a {aid} copy the editor can seek: {out.name}", flush=True)
            subprocess.run(proxy_cmd(path_of(edit, a, False), tmp, a, sc["width"], sc["height"]), check=True)
            tmp.replace(out)


def stage(edit, sc, tag="render"):
    """The renderer's public folder: a hard link per asset (render.mjs links the folder into the bundle), and the props."""
    e = Path(edit)
    pub = e / ".scene" / "pub"
    if pub.exists():
        shutil.rmtree(pub)
    (pub / "a").mkdir(parents=True)
    props = copy.deepcopy(sc)
    for aid, a in props["assets"].items():
        f = path_of(e, a)
        if not f.is_file():
            raise SceneError(f"asset {aid}: {f} is missing")
        link = pub / "a" / f"{aid}{f.suffix.lower()}"
        try:   # a hard link: the renderer serves no symlinks, and a copy of a long take is slow
            os.link(f.resolve(), link)
        except OSError:
            shutil.copy2(f, link)
        a["url"] = f"a/{link.name}"
    files = {f: e / f for tr in sc["tracks"] for it in tr["items"] if it["type"] == "card"   # a card names its files itself
             for f in __import__("re").findall(r'"([^"/][^"]*\.[A-Za-z0-9]{2,5})"', json.dumps(it["card"])) if (e / f).is_file()}
    for f, src in files.items():
        (pub / f).parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(src.resolve(), pub / f)
        except OSError:
            shutil.copy2(src, pub / f)
    props["composition"] = "Scene"
    pf = e / ".scene" / f"{tag}.props.json"
    jsave(pf, props)
    return pub, pf


def renderer():
    sys.path.insert(0, str(EDIT_PY.parent))
    import edit as edit_py
    edit_py.sync_renderer()
    return edit_py.REMOTION


def render(edit, out=None, draft=False, log=None, name=NAME):
    """The export: the scene (name: a version's scene file) through the Scene composition to out (default
    <edit>/exports/<edit name>.mp4)."""
    e = Path(edit)
    sc = load(e, name)
    ensure_proxies(e, sc)
    out = Path(out) if out else e / "exports" / f"{e.name}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    pub, pf = stage(e, sc)
    rem = renderer()
    cmd = ["node", str(rem / "render.mjs"), "local", str(pub), str(pf), str(out), *(["--draft"] if draft else [])]
    with open(log or os.devnull, "w", encoding="utf-8") as lf:
        r = subprocess.run(cmd, cwd=rem, stdout=lf if log else None, stderr=subprocess.STDOUT if log else None)
    if r.returncode:
        raise SceneError(f"the render failed ({r.returncode})" + (f": see {log}" if log else ""))
    return out


def stills(edit, outdir, pairs):
    e = Path(edit)
    sc = load(e)
    ensure_proxies(e, sc)
    pub, pf = stage(e, sc, "stills")
    rem = renderer()
    subprocess.run(["node", str(rem / "render.mjs"), "stills", str(pub), str(pf), str(outdir), *pairs], cwd=rem, check=True)


# ---------------------------------------------------------------- Claude's changes (SCENE.md, Claude edits the scene)
def diff(a, b):
    """The ops that turn scene a into scene b: what Undo and Redo of one change send."""
    loc = lambda sc: {it["id"]: (tr["id"], i, it) for tr in sc["tracks"] for i, it in enumerate(tr["items"])}
    A, B, ta, tb = loc(a), loc(b), {t["id"]: t for t in a["tracks"]}, {t["id"]: t for t in b["tracks"]}
    ops = [{"op": "add_track", "track": {k: v for k, v in t.items() if k != "items"}, "index": i}
           for i, t in enumerate(b["tracks"]) if t["id"] not in ta]
    ops += [{"op": "asset", "id": k, "asset": v} for k, v in b["assets"].items() if a["assets"].get(k) != v]
    ops += [{"op": "remove", "item": i} for i in A if i not in B]
    for iid, (tid, i, it) in B.items():
        if iid not in A:
            ops.append({"op": "add", "track": tid, "item": it, "index": i})
            continue
        if A[iid][0] != tid:
            ops.append({"op": "move", "item": iid, "track": tid, "index": i})
        props = {k: it.get(k) for k in set(it) | set(A[iid][2]) if it.get(k) != A[iid][2].get(k)}
        if props:
            ops.append({"op": "set", "item": iid, "props": props})
    for tid, t in tb.items():
        props = {k: t.get(k) for k in set(t) | set(ta.get(tid, t)) if k != "items" and t.get(k) != ta.get(tid, t).get(k)}
        if tid in ta and props:
            ops.append({"op": "track", "track": tid, "props": props})
    ops += [{"op": "remove_track", "track": t} for t in ta if t not in tb]
    ops += [{"op": "asset", "id": k, "asset": None} for k in a["assets"] if k not in b["assets"]]   # after the items that used it
    held = [t["id"] for t in a["tracks"] if magnet(a, t) and t["id"] in tb and any(A[i][0] == t["id"] for i in A if i not in B)]
    return [{"op": "track", "track": t, "props": {"magnet": False}} for t in held] + ops + \
        [{"op": "track", "track": t, "props": {"magnet": magnet(b, tb[t])}} for t in held]   # a remove here closes no gap


def describe(ops, sc):
    """A change in a few words, when Claude gave no --why: "added text 'Link in bio'"."""
    out = []
    for o in ops:
        it = o.get("item") if isinstance(o.get("item"), dict) else next((x for t in sc["tracks"] for x in t["items"] if x["id"] == o.get("item")), {})
        what = f"{it.get('type', 'item')} '{it.get('text') or it.get('name') or it.get('id')}'"
        if o["op"] in ("add", "set", "remove", "trim", "split", "move"):
            out.append({"add": "added", "remove": "removed"}.get(o["op"], "changed") + " " + what)
    return ", ".join(dict.fromkeys(out)) or "changed the scene"


def log_change(edit, before, after, why=None, alt=None):
    """Claude's change, kept in review/claude.json (a version's: changes_of(alt)) with the round it was made on and the ops that undo (back) and redo
    (fwd) it, so the page lists it under Claude's changes and Undo takes it off as one step. None when nothing changed."""
    e = Path(edit)
    fwd = diff(before, after)
    if not fwd:
        return None
    try:
        r = jload(e / "review.json")
        at = [r.get("stage"), r.get("round")]
    except (OSError, ValueError):
        at = None
    cf = e / changes_of(alt)
    log = jload(cf) if cf.is_file() else []
    ids = [o["item"]["id"] if isinstance(o.get("item"), dict) else o.get("item") for o in fwd if o.get("item")]
    starts = [it["start"] for sc in (after, before) for t in sc["tracks"] for it in t["items"] if it["id"] in ids]
    entry = {"n": 1 + max([x["n"] for x in log] or [0]), "why": why or describe(fwd, after), "at": at, "t": min(starts) if starts else None,
             "items": list(dict.fromkeys(ids)), "fwd": fwd, "back": diff(after, before), "undone": False, "when": time.strftime("%Y-%m-%dT%H:%M:%S")}
    jsave(cf, log + [entry])
    return entry


def undo_change(edit, n, undo=True, alt=None):
    """Undo (or redo) Claude's change n (on version alt) by its own ops: the user's edits since stay. The scene after."""
    e, cf, name = Path(edit), Path(edit) / changes_of(alt), name_of(alt)
    log = jload(cf) if cf.is_file() else []
    x = next((x for x in log if x["n"] == n), None)
    if not x:
        raise SceneError(f"no Claude change {n}")
    sc = load(e, name)
    if x["undone"] != bool(undo):
        new = save(e, apply(sc, x["back" if undo else "fwd"], e, by="keep"), name)
        x["fwd" if undo else "back"] = diff(new, sc)   # its opposite puts back exactly what this took (the user's moves since too)
        x["undone"], sc = bool(undo), new
        jsave(cf, log)
    return sc


def server(edit):
    """The open page's server for this edit (review.py running), or None."""
    try:
        url = (Path(edit) / "review" / ".server").read_text(encoding="utf-8").strip()
        st = json.loads(urllib.request.urlopen(url.replace("/?t=", "/state?t="), timeout=2).read())
        return url if st.get("folder") == str(Path(edit).resolve()) else None
    except (OSError, ValueError):
        return None


def claude_ops(edit, ops, why=None, alt=None):
    """Claude's change to the scene (alt: that version's, scene.<alt>.json): through the open page's server when it runs
    (one undo there, drawn on the page's next poll), else straight into the scene file. (scene, change)."""
    url = server(edit)
    if url:
        base, tok = url.split("/?t=", 1)
        req = urllib.request.Request(f"{base}/scene/ops?t={tok}", json.dumps({"ops": ops, "by": "claude", "why": why, "alt": alt}).encode(),
                                     {"Content-Type": "application/json"}, method="POST")
        try:
            r = json.loads(urllib.request.urlopen(req, timeout=120).read())
        except urllib.error.HTTPError as x:
            raise SceneError(json.loads(x.read() or b"{}").get("error") or f"the page answered {x.code}")
        return r["scene"], r.get("change")
    before = load(edit, name_of(alt))
    after = save(edit, apply(before, ops, edit, by="claude"), name_of(alt))
    ensure_proxies(edit, after)
    return after, log_change(edit, before, after, why, alt)


def scene_of(edit, alt=None):
    """scene.json (alt: the version's scene.<alt>.json), made by the open page when it is not there yet (the page's live
    plan goes in)."""
    name = name_of(alt)
    if not (Path(edit) / name).is_file():
        url = server(edit)
        if url:
            try:
                q = f"&alt={urllib.parse.quote(alt)}" if alt else ""
                urllib.request.urlopen(url.replace("/?t=", "/scene?t=") + q, timeout=120).read()
            except OSError:
                pass
    if not (Path(edit) / name).is_file():
        raise SceneError(f"no {name} in {edit}: this draft is not a scene (open it on the page, or scene.py from-plan)")
    return load(edit, name)


def to_scene(sc, asset, t):
    """A time on an asset's clock (a raw take's word) as scene seconds, through the footage clips that show it."""
    for tr in sc["tracks"]:
        for it in tr["items"]:
            if it["type"] == "video" and it.get("asset") == asset and it["in"] - EPS <= t < it["in"] + (it["end"] - it["start"]) * it.get("speed", 1):
                return it["start"] + (t - it["in"]) / it.get("speed", 1)
    return None


def show(sc, at=None, name=NAME):
    """What is on the scene (at a time): tracks bottom to top, each item's id, times and box, then the words said."""
    out = [f"{name}: {sc['width']}x{sc['height']}, {sc['fps']} fps, {sc['duration']:.2f} s. Tracks, bottom to top:"]
    box = lambda it: f"  x {it['x']:.0f} y {it['y']:.0f} w {it['w']:.0f}" + (f" h {it['h']:.0f}" if it["type"] != "text" else "") if "x" in it else ""
    for tr in sc["tracks"]:
        flags = [f for f in ("hidden", "muted", "locked") if tr.get(f)] + (["magnet"] if tr["kind"] == "visual" and magnet(sc, tr) else [])
        its = [it for it in tr["items"] if at is None or it["start"] - EPS <= at < it["end"]]
        out.append(f"  track {tr['id']} {tr['name']!r} ({tr['kind']}{', ' + ', '.join(flags) if flags else ''}): {len(tr['items'])} items"
                   + (f", {len(its)} at {at:.2f} s" if at is not None else ""))
        foot = tr.get("magnet", magnet(sc, tr)) and all(it["type"] == "video" for it in tr["items"]) and at is None and len(its) > 3
        for it in its if not foot else []:
            a = sc["assets"].get(it.get("asset") or "") or {}
            what = it.get("text") or (Path(a["src"]).name if a.get("src") else "") or it.get("name") or ""
            if it["type"] == "captions":
                what = f"{len(it.get('words') or [])} words"
            extra = (f"  in {it['in']:.2f}" if it["type"] in ("video", "audio") else "") + (" [locked]" if it.get("locked") else "") + \
                    (" [by claude]" if it.get("by") == "claude" else "") + (f"  keys {', '.join(it['keys'])}" if it.get("keys") else "")
            out.append(f"    {it['id']}  {it['type']} {what!r}  {it['start']:.2f}-{it['end']:.2f}{box(it)}{extra}")
        if foot:
            out.append(f"    footage clips {tr['items'][0]['id']}..{tr['items'][-1]['id']}, 0.00-{tr['items'][-1]['end']:.2f} (show --at t names the one then)")
    cap = next((it for tr in sc["tracks"] for it in tr["items"] if it["type"] == "captions"), None)
    if cap:
        ws = [(to_scene(sc, cap["asset"], w["start"]) if cap.get("asset") else w["start"], w["w"]) for w in cap.get("words") or []]
        ws = [(t, w) for t, w in ws if t is not None and (at is None or abs(t - at) <= 3)]
        out.append(("Said around %.2f s:" % at if at is not None else "Said (scene seconds):") + " " + " ".join(f"[{t:.2f}] {w}" for t, w in ws))
    return "\n".join(out)


def cards_ops(edit, sc, plan, at=()):
    """scene.py cards: plan.json's cards (the overlays skill, template-filler, a placed motion clip) that the scene does not
    show yet, as items on its Cards track: the card on screen at each `at` time, or every new one."""
    e, W, H = Path(edit), sc["width"], sc["height"]
    have = {(round(it["card"].get("start", it["start"]), 2), it["card"].get("trigger_word")) for t in sc["tracks"] for it in t["items"]
            if it["type"] == "card"} | {(round(it["start"], 2), it["name"]) for t in sc["tracks"] for it in t["items"]}
    sizes = lambda src: (lambda i: [i["w"], i["h"]] if i.get("w") else None)(probe(e / src)) if (e / src).is_file() else None
    ops, assets = [], dict(sc["assets"])
    for c in plan.get("cards") or []:
        if at and not any(c["start"] - EPS <= t < c["end"] for t in at) or (round(c["start"], 2), c.get("trigger_word")) in have:
            continue
        it = card_item(c, W, H, sizes)
        if "src" in it:
            src = it.pop("src")
            aid = next((k for k, a in assets.items() if a.get("src") == src), None)
            if not aid:
                aid = "".join(ch if ch.isalnum() else "-" for ch in Path(src).stem.lower())[:24] or "a"
                aid = next(f"{aid}-{n}" if n else aid for n in range(99) if (f"{aid}-{n}" if n else aid) not in assets)
                assets[aid] = {"src": src}
                ops.append({"op": "asset", "id": aid, "asset": {"src": src}})
            it["asset"] = aid
        it["name"] = c.get("trigger_word") or it["type"]
        if it["type"] == "card":
            it.update(look=plan.get("look"), motion=plan.get("motion"))
        tr = next((t for t in sc["tracks"] if t["kind"] == "visual" and t["name"] == "Cards"), None)
        if not tr:
            kinds = [t["kind"] for t in sc["tracks"]]
            tr = {"id": next(f"v{n}" for n in range(1, 999) if all(t["id"] != f"v{n}" for t in sc["tracks"]))}
            ops.append({"op": "add_track", "track": {"id": tr["id"], "kind": "visual", "name": "Cards"}, "index": kinds.index("visual") + 1})
            sc = {**sc, "tracks": sc["tracks"] + [{**tr, "kind": "visual", "name": "Cards", "items": []}]}
        ops.append({"op": "add", "track": tr["id"], "item": it})
    return ops


def bring_in(edit, f):
    """A file outside the edit copied into its media/ (an APFS clone on a Mac; the same file there already is used as
    it is), so the scene plays and exports anywhere. Returns its src (relative to the edit)."""
    e, f = Path(edit), Path(f).expanduser().resolve()
    if e.resolve() in f.parents:
        return f.relative_to(e.resolve()).as_posix()
    (e / "media").mkdir(exist_ok=True)
    dst, n = e / "media" / f.name, 2
    while dst.exists() and dst.stat().st_size != f.stat().st_size:   # a different file of that name: never over it
        dst, n = e / "media" / f"{f.stem}-{n}{f.suffix}", n + 1
    if not dst.exists() and (sys.platform != "darwin" or subprocess.run(["cp", "-c", str(f), str(dst)], capture_output=True).returncode):
        shutil.copyfile(f, dst)
    return dst.relative_to(e).as_posix()


PEAKS_RATE = 50   # waveform values a second of source


def peaks(edit, aid, a):
    """An asset's sound as a waveform for its timeline clips: {"rate", "peaks"} (0-1, PEAKS_RATE a second of the source,
    the loudest 20 ms each, scaled to the file's loudest). Cached in .scene/<aid>.peaks.json by the file it reads."""
    from array import array
    f = path_of(edit, a, False)
    st = f.stat()
    sig = f"{a.get('src')}|{st.st_size}|{st.st_mtime_ns}"
    cache = Path(edit) / ".scene" / f"{aid}.peaks.json"
    try:
        d = jload(cache)
        if d.get("sig") == sig:
            return d
    except (OSError, ValueError):
        pass
    sr = 8000
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(f), "-map", "0:a:0", "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
                         capture_output=True).stdout
    x = array("h")
    x.frombytes(raw[:len(raw) // 2 * 2])
    step = sr // PEAKS_RATE
    p = [max(map(abs, x[i:i + step]), default=0) for i in range(0, len(x), step)]
    top = max(p, default=0) or 1
    d = {"sig": sig, "rate": PEAKS_RATE, "peaks": [round(v / top, 2) for v in p]}
    jsave(cache, d)
    return d


STRIP_H = 72         # a filmstrip frame's height in pixels (the timeline shows it at about half, sharp on a Retina screen)
STRIP_MAX = 240      # frames at most in one strip: a long take samples further apart


def strip(edit, aid, a):
    """A video asset's frames for its timeline clips, CapCut's filmstrip: one JPEG of frames side by side, a frame every
    "step" seconds of the source from 0. {"step", "n", "w", "h", "file"}; cached in .scene/<aid>.strip.jpg by the file it reads."""
    f = path_of(edit, a, False)
    st = f.stat()
    sig = f"{a.get('src')}|{st.st_size}|{st.st_mtime_ns}"
    meta, img = Path(edit) / ".scene" / f"{aid}.strip.json", Path(edit) / ".scene" / f"{aid}.strip.jpg"
    try:
        d = jload(meta)
        if d.get("sig") == sig and img.is_file():
            return {**d, "file": img}
    except (OSError, ValueError):
        pass
    pr = probe(f)
    if pr["kind"] != "video" or not pr.get("duration"):
        raise SceneError(f"{aid} has no frames to show")
    dur, step = pr["duration"], max(1.0, round(pr["duration"] / STRIP_MAX, 2))
    n = max(1, min(STRIP_MAX, int(dur // step) + 1))
    w = max(2, round(STRIP_H * pr["w"] / pr["h"] / 2) * 2)
    img.parent.mkdir(parents=True, exist_ok=True)
    tmp = img.with_suffix(".part.jpg")
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(f), "-an", "-vf", f"fps=1/{step},scale={w}:{STRIP_H},tile={n}x1",
                        "-frames:v", "1", "-q:v", "5", str(tmp)], capture_output=True, text=True)
    if r.returncode or not tmp.is_file():
        raise SceneError(f"could not draw the frames of {aid}: {r.stderr.strip()[-200:]}")
    tmp.replace(img)
    d = {"sig": sig, "step": step, "n": n, "w": w, "h": STRIP_H}
    jsave(meta, d)
    return {**d, "file": img}


def lane_kind(typ):
    """What shares a track: texts with texts, sounds with sounds, pictures and clips (and shapes, cards) with each other."""
    return "text" if typ == "text" else "audio" if typ == "audio" else "captions" if typ == "captions" else "media"


def lane(sc, typ, a, b, track=None):
    """Where a new item goes (the page's scPlace): the named track when it holds this kind and is free from a to b, else the
    first track of this kind that is unlocked, shown and free then (top first), else a new track of this kind just above the
    others of its kind. Never the footage track (the magnet one), never over a clip. Returns (track id, ops making it)."""
    k, kind = lane_kind(typ), TYPES[typ]
    def fits(t):
        return (t["kind"] == kind and not t.get("locked") and not t.get("muted" if kind == "audio" else "hidden")
                and not (kind == "visual" and magnet(sc, t)) and all(lane_kind(i.get("type")) == k for i in t["items"])
                and not any(i["start"] < b - 1e-3 and i["end"] > a + 1e-3 for i in t["items"]))
    pool = [t for t in sc["tracks"] if track in (t["id"], t.get("name"))] if track else list(reversed(sc["tracks"]))
    for t in pool:
        if fits(t):
            return t["id"], []
    ids, kinds = {t["id"] for t in sc["tracks"]}, [t["kind"] for t in sc["tracks"]]
    tid = next(f"{kind[0]}{n}" for n in range(1, 999) if f"{kind[0]}{n}" not in ids)
    mine = [i for i, t in enumerate(sc["tracks"]) if t["kind"] == kind and t["items"] and all(lane_kind(x.get("type")) == k for x in t["items"])
            and not (kind == "visual" and magnet(sc, t))]
    idx = mine[-1] + 1 if mine else (len(kinds) - kinds[::-1].index("visual") if kind == "visual" and "visual" in kinds else len(kinds))
    base = track or {"text": "Text", "audio": "Sounds", "media": "Images" if typ == "image" else "Motion" if typ == "video" else "Shapes"}[k]
    names = {t.get("name") for t in sc["tracks"]}
    name = base if base not in names else next(f"{base} {n}" for n in range(2, 999) if f"{base} {n}" not in names)
    return tid, [{"op": "add_track", "track": {"id": tid, "kind": kind, "name": name}, "index": idx}]


def add_op(edit, sc, typ, start, end=None, src=None, text=None, track=None, geo=None, extra=None):
    """scene.py add: the ops that put one item on the scene (its file copied into the edit's media/ when it is outside)."""
    e, W, H = Path(edit), sc["width"], sc["height"]
    if typ not in TYPES or typ == "captions" or (typ in ("video", "image", "audio")) != bool(src):
        raise SceneError("add takes text (--text), shape, or image, video or audio with --src")
    ops, it = [], {"type": typ, "start": round(float(start), 6), **{k: v for k, v in (geo or {}).items() if v is not None}, **(extra or {})}
    if text is not None:
        it["text"] = text
    if src:
        f = Path(src).expanduser().resolve()
        if not f.is_file():
            raise SceneError(f"no file {src}")
        rel_ = bring_in(e, f)   # outside the edit: a copy in media/ (an APFS clone on a Mac)
        f = e / rel_
        aid = next((k for k, a in sc["assets"].items() if a.get("src") == rel_), None)
        if not aid:
            base = "".join(c if c.isalnum() else "-" for c in f.stem.lower())[:24] or "a"
            aid, n = base, 2
            while aid in sc["assets"]:
                aid, n = f"{base}-{n}", n + 1
            ops.append({"op": "asset", "id": aid, "asset": {"src": rel_}})
        info = probe(f)
        it["asset"] = aid
        if typ in ("image", "video") and "w" not in it and info.get("w"):   # as the page drops a picture: 70% wide or 40% high at most
            k = min(W * 0.7 / info["w"], H * 0.4 / info["h"])
            it.update(w=round(info["w"] * k, 2), h=round(info["h"] * k, 2))
        elif typ in ("image", "video") and "h" not in it and info.get("w"):
            it["h"] = round(it["w"] * info["h"] / info["w"], 2)
        if end is None and info.get("duration"):
            end = float(start) + info["duration"] / it.get("speed", 1) - it.get("in", 0)
    if typ == "shape":
        it.setdefault("w", round(W * 0.3))
        it.setdefault("h", round(W * 0.3))
    it["end"] = round(float(end) if end is not None else float(start) + 3, 6)
    tid, more = lane(sc, typ, it["start"], it["end"], track)
    ops += more
    tr = {"id": tid}
    ops.append({"op": "add", "track": tr["id"], "item": it})
    return ops


# ---------------------------------------------------------------- self-check
def demo():
    with tempfile.TemporaryDirectory() as d:
        e = Path(d)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=s=320x568:r=30:d=6", "-f", "lavfi", "-i", "sine=d=6",
                        "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(e / "take.mp4")], check=True)
        S = Scene(1080, 1920, 30, edit=e)
        S.video("take.mp4", 0, 2, **{"in": 1})
        S.video("take.mp4", 2, 4, **{"in": 4})
        S.text("Hi", 1, 3, y=400, box={"color": "#FFFFFF", "pad": 10, "radius": 8})
        S.captions([{"w": "one", "start": 1.2, "end": 1.6}], {"y_pct": 70}, asset="take")
        sc = S.save(e)
        assert sc["duration"] == 4 and sc["assets"]["take"]["w"] == 320 and sc["tracks"][0]["items"][0]["fit"] == "cover"
        v1, v2 = (it["id"] for it in sc["tracks"][0]["items"])
        txt = sc["tracks"][1]["items"][0]["id"]
        # trim the first clip's end out by 0.5 s: the magnet moves the second clip and the text, the captions grow
        s2 = apply(sc, [{"op": "trim", "item": v1, "edge": "end", "by": 0.5}])
        assert [(i["start"], i["end"]) for i in s2["tracks"][0]["items"]] == [(0, 2.5), (2.5, 4.5)], s2["tracks"][0]["items"]
        assert s2["tracks"][1]["items"][0]["start"] == 1 and s2["tracks"][1]["items"][0]["end"] == 3.5 and s2["duration"] == 4.5
        assert sc["tracks"][0]["items"][0]["end"] == 2, "apply never changes the scene passed in"
        s3 = apply(sc, [{"op": "trim", "item": v2, "edge": "start", "by": -1}])   # bring back a second before it
        assert s3["tracks"][0]["items"][1]["in"] == 3 and s3["tracks"][0]["items"][1]["end"] == 5
        s4 = apply(sc, [{"op": "split", "item": v1, "t": 0.5}, {"op": "set", "item": txt, "props": {"x": 100, "box": None}},
                        {"op": "track", "track": "c1", "props": {"hidden": True}}, {"op": "remove", "item": v2}])
        a, b = s4["tracks"][0]["items"]
        assert (a["end"], b["start"], b["in"]) == (0.5, 0.5, 1.5) and s4["tracks"][1]["items"][0]["x"] == 100
        assert s4["tracks"][2]["hidden"] and s4["duration"] == 3, s4["duration"]
        for bad, why in (([{"op": "set", "item": "nope", "props": {}}], "no item"), ([{"op": "trim", "item": v1, "edge": "end", "by": -5}], "shorter"),
                         ([{"op": "split", "item": v1, "t": 9}], "outside"), ([{"op": "wat"}], "unknown op")):
            try:
                apply(sc, bad)
                raise AssertionError(bad)
            except SceneError as x:
                assert why in str(x), x
        locked = apply(sc, [{"op": "track", "track": "v1", "props": {"locked": True}}])
        try:
            apply(locked, [{"op": "set", "item": v1, "props": {"x": 0}}])
            raise AssertionError("locked")
        except SceneError as x:
            assert "locked" in str(x)
        try:
            validate(normalise({**sc, "tracks": [{"id": "x", "kind": "audio", "items": [{"type": "text", "start": 1, "end": 0}]}]}))
            raise AssertionError("invalid")
        except SceneError as x:
            assert "goes on a visual track" in str(x) and "start < end" in str(x), x
        # zoom keys: a held punch inside a clip, scale about the origin
        keys, org = zoom_keys([{"start": 1, "end": 2, "scale": 1.2, "kind": "punch", "travel_s": 0.001, "origin": [50, 30]}], 0, 4)
        assert keys["scale"] == [[0, 1, "hold"], [1, 1.2, "hold"], [2, 1, "hold"]], keys
        assert pos_keys(keys, org, (540, 960), 1080, 1920)["y"][1][1] == round(576 + 1.2 * 384, 3)
        assert cut_before({"cuts": [{"start": 1, "end": 3, "kind": "retake"}]}, [{"text": "uh", "start": 1.5, "end": 1.7}], 1, 3) == \
            {"reason": "retake", "words": "uh", "dur": 2}
        assert name_of() == NAME and name_of("t1") == "scene.t1.json" and name_of("Trial t1: big").startswith("scene.Trial-t1-big-")
        assert name_of("../x") != name_of("x") and "/" not in name_of("../x")
        v = from_video(e, "take.mp4", gone=[[1, 2], [4, 4.5]], texts=[{"kind": "label", "text": "Yo", "start": 0.5, "end": 2, "x_pct": 50,
                       "y_pct": 30}, {"kind": "label", "text": "Hid", "start": 0, "end": 1, "x_pct": 50, "y_pct": 60, "lane": 1, "lane_off": True}])
        vt = v["tracks"][0]["items"]
        assert v["width"] == 320 and [(x["start"], x["end"], x["in"]) for x in vt] == [(0, 1, 0), (1, 3, 2), (3, 4.5, 4.5)], vt
        assert "cut" not in vt[0] and vt[1]["cut"]["before"] == {"reason": "by hand", "words": "", "dur": 1} and vt[2]["cut"]["before"]["dur"] == 0.5
        assert not vt[0].get("locked") and v["duration"] == 4.5 and [t["name"] for t in v["tracks"]] == ["Video", "Text", "Text 2"]
        assert v["tracks"][2]["hidden"] and v["tracks"][1]["items"][0]["text"] == "Yo", v["tracks"]
        # Claude's changes: marked by "claude", the page's touch clears it; diff undoes and redoes any change
        back = apply(s4, diff(s4, sc), e)
        assert [[{k: i.get(k) for k in ("id", "start", "end", "x", "in")} for i in t["items"]] for t in back["tracks"]] == \
            [[{k: i.get(k) for k in ("id", "start", "end", "x", "in")} for i in t["items"]] for t in sc["tracks"]] and not back["tracks"][2]["hidden"]
        assert [t["items"] for t in apply(sc, diff(sc, s4), e)["tracks"]] == [t["items"] for t in s4["tracks"]]
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=64x32", "-frames:v", "1", str(e.parent / "ce-shot.png")], check=True)
        ops = add_op(e, sc, "image", 1, 2, src=e.parent / "ce-shot.png") + add_op(e, sc, "text", 3, 4, text="Link in bio", extra={"box": {"color": "#FFFFFF"}})
        assert (e / "media" / "ce-shot.png").is_file() and ops[0] == {"op": "asset", "id": "ce-shot", "asset": {"src": "media/ce-shot.png"}}, ops
        # a sound from outside: copied into media/, an audio asset (cover art is no picture), its waveform; undo drops the asset
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=440:d=2", "-i", str(e.parent / "ce-shot.png"),
                        "-map", "0:a", "-map", "1:v", "-c:v", "mjpeg", "-disposition:v", "attached_pic", str(e.parent / "ce-song.mp3")], check=True)
        so = add_op(e, sc, "audio", 1, src=e.parent / "ce-song.mp3")
        assert bring_in(e, e.parent / "ce-song.mp3") == "media/ce-song.mp3" and so[0]["asset"] == {"src": "media/ce-song.mp3"}, so
        sa = apply(sc, so, e)
        assert sa["assets"]["ce-song"]["kind"] == "audio" and abs(so[-1]["item"]["end"] - 3) < 0.1, (sa["assets"]["ce-song"], so[-1])
        pk = peaks(e, "ce-song", sa["assets"]["ce-song"])
        assert pk["rate"] == PEAKS_RATE and abs(len(pk["peaks"]) - 2 * PEAKS_RATE) <= 2 and max(pk["peaks"]) == 1 and peaks(e, "ce-song", sa["assets"]["ce-song"]) == pk
        un = apply(sa, diff(sa, sc), e)
        assert "ce-song" not in un["assets"] and json.dumps(un, sort_keys=True) == json.dumps(normalise(copy.deepcopy(sc)), sort_keys=True)
        try:
            apply(sa, [{"op": "asset", "id": "ce-song", "asset": None}], e)
            raise AssertionError("an asset on the timeline is never dropped")
        except SceneError:
            pass
        c1 = save(e, apply(sc, ops, e, by="claude"))
        mine = [i for t in c1["tracks"] for i in t["items"] if i.get("by") == "claude"]
        mine = sorted(mine, key=lambda i: i["type"])
        assert [i["type"] for i in mine] == ["image", "text"] and mine[0]["w"] == 756, mine
        assert [t["name"] for t in c1["tracks"]] == ["Video", "Text", "Images", "Captions"], "a new track on top of the pictures, under the captions"
        ch = log_change(e, sc, c1, "Link in bio at the end")
        assert ch["n"] == 1 and ch["why"] == "Link in bio at the end" and ch["t"] == 1 and set(ch["items"]) == {i["id"] for i in mine}
        assert "[by claude]" in show(c1, 3.5) and "[0.20] one" in show(c1, 1)
        moved = save(e, apply(c1, [{"op": "set", "item": mine[0]["id"], "props": {"y": 100}}], e))   # the user drags Claude's image
        assert "by" not in next(i for t in moved["tracks"] for i in t["items"] if i["id"] == mine[0]["id"]), "the page's touch clears the mark"
        u = undo_change(e, 1)
        assert not any(i["id"] in ch["items"] for t in u["tracks"] for i in t["items"]) and jload(e / CHANGES)[0]["undone"]
        r = undo_change(e, 1, undo=False)
        img = next(i for t in r["tracks"] for i in t["items"] if i["id"] == mine[0]["id"])
        assert img["y"] == 100, "redo puts back what undo took, the user's move too"
        assert changes_of() == CHANGES and changes_of("t1").as_posix() == "review/claude.t1.json"
        t1 = save(e, apply(sc, add_op(e, sc, "text", 5, 6, text="t1"), e, by="claude"), name_of("t1"))
        ct = log_change(e, sc, t1, "t1 only", alt="t1")
        assert ct["n"] == 1 and len(jload(e / CHANGES)) == 1 and (e / changes_of("t1")).is_file(), "a version keeps its own change log"
        assert undo_change(e, 1, alt="t1") == load(e, name_of("t1")) and jload(e / changes_of("t1"))[0]["undone"]
        assert not any(i.get("by") for t in load(e, name_of("t1"))["tracks"] for i in t["items"]) and not jload(e / CHANGES)[0]["undone"]
        assert describe([{"op": "add", "item": {"type": "text", "text": "Hi"}}], sc) == "added text 'Hi'"
        plan = {"width": 1080, "height": 1920, "cards": [{"start": 1, "end": 2, "box": [10, 10, 50, 20], "src": "media/ce-shot.png", "format": "plain",
                                                          "trigger_word": "red"}]}
        co = cards_ops(e, r, plan)
        assert [o["op"] for o in co] == ["add_track", "add"] and co[1]["item"]["type"] == "image" and co[1]["item"]["name"] == "red", co
        assert cards_ops(e, apply(r, co, e), plan) == [], "a card already on the scene is not added again"
        assert probe(e / "take.mp4").get("alpha") is None
        # a slid cut (x 640, a 100 px black strip on the left, zoomed to 1.12 later) grows until it covers the frame
        sl = normalise({"width": 1080, "height": 1920, "fps": 30, "assets": {"c": {"src": "take.mp4"}}, "tracks": [{"id": "v", "kind": "visual", "items": [
            {"id": "a", "type": "video", "asset": "c", "start": 0, "end": 2, "x": 640, "w": 1080, "h": 1920,
             "keys": {"scale": [[0, 1, "hold"], [1, 1.12, "hold"]], "x": [[0, 640, "hold"], [1, 651.87, "hold"]]}},
            {"id": "b", "type": "video", "asset": "c", "start": 2, "end": 3, "x": 540, "w": 1080, "h": 1920},
            {"id": "p", "type": "video", "asset": "c", "start": 3, "end": 4, "x": 900, "w": 300, "h": 533}]}]})
        assert cover(sl) == ["a"] and sl["covered"], "only the slid clip; a full one and a picture-in-picture stay"
        a = sl["tracks"][0]["items"][0]
        assert a["w"] == 1080 and [k[1] for k in a["keys"]["scale"]] == [1.1853, 1.2073], a["keys"]   # each short key raised, just enough
        assert all(key_at(a["keys"]["x"], t) - 540 * key_at(a["keys"]["scale"], t) <= 0 for t in (0, 0.5, 1, 1.5)), "the left edge is covered"
        plain = normalise({**sl, "covered": False, "tracks": [{"id": "v", "kind": "visual", "items": [{**sl["tracks"][0]["items"][1], "x": 600}]}]})
        assert cover(plain) == ["b"] and plain["tracks"][0]["items"][0]["w"] >= 1200, "no keys: the clip grows"
        # a new item: a free track of its own kind, else a new one above its kind; never the footage, never over a clip
        ln = normalise({"width": 1080, "height": 1920, "fps": 30, "assets": {"c": {"src": "take.mp4"}}, "tracks": [
            {"id": "v", "kind": "visual", "items": [{"id": "a", "type": "video", "asset": "c", "start": 0, "end": 9}]},
            {"id": "x", "kind": "visual", "name": "Text", "items": [{"id": "t", "type": "text", "text": "hi", "start": 1, "end": 3}]}]})
        assert lane(ln, "text", 4, 5) == ("x", []), "a free text track"
        tid, op = lane(ln, "text", 2, 4)
        assert tid == "v1" and op[0]["index"] == 2 and op[0]["track"]["name"] == "Text 2", op   # busy: a new one above it
        tid, op = lane(ln, "image", 1, 2)
        assert tid == "v1" and op[0]["track"]["name"] == "Images", "a picture never goes on the text track or the footage"
        assert validate(normalise({**ln, "tracks": [{"id": "x", "kind": "visual", "items": [{"type": "text", "start": 0, "end": 1,
                        "box": {"color": "#FFFFFF", "opacity": 0.5}, "shadow": {"color": "#FF0000", "distance": 8, "angle": 45}}]}]}))
        try:
            validate(normalise({**ln, "tracks": [{"id": "x", "kind": "visual", "items": [{"type": "text", "start": 0, "end": 1, "box": {"color": "#FFFFFF", "opacity": 2}}]}]}))
            raise AssertionError("box opacity 2 passed")
        except SceneError as e:
            assert "box.opacity" in str(e), e
    print("scene demo ok")


def main(a):
    if a[:1] == ["demo"]:
        return demo()
    if len(a) < 2:
        return print(__doc__)
    alt = a[a.index("--alt") + 1] if "--alt" in a[:-1] else None   # a version (a trial reel): its own scene.<alt>.json
    a = [x for i, x in enumerate(a) if "--alt" not in (x, a[i - 1] if i else None)] if alt else a
    cmd, e = a[0], Path(a[1])
    opt = lambda k, d=None: a[a.index(k) + 1] if k in a else d
    if cmd == "from-plan":
        sc = from_plan(e, jload(e / opt("--plan", "plan.json")))
        ensure_proxies(e, sc)
        save(e, sc)
        print(f"{e / NAME}: {sum(len(t['items']) for t in sc['tracks'])} items on {len(sc['tracks'])} tracks, {sc['duration']:.2f} s")
    elif cmd == "from-video":
        save(e, from_video(e, opt("--video", "render.mp4")))
        print(e / NAME)
    elif cmd == "render":
        print(render(e, opt("--out"), "--draft" in a, name=name_of(alt)))
    elif cmd == "stills":
        stills(e, a[2], a[3:])
    elif cmd == "show":
        print(show(scene_of(e, alt), float(opt("--at")) if opt("--at") else None, name_of(alt)))
    elif cmd in ("ops", "add", "cards"):
        sc = scene_of(e, alt)
        if cmd == "cards":
            ops = cards_ops(e, sc, jload(e / opt("--plan", "plan.json")), [float(x) for x in opt("--at", "").split(",") if x])
        elif cmd == "ops":
            arg = a[2] if len(a) > 2 else ""
            try:
                ops = json.loads(Path(arg).read_text(encoding="utf-8") if arg and Path(arg).is_file() else arg)
            except ValueError as x:
                raise SceneError(f"ops: not JSON ({x})")
            ops = ops.get("ops") if isinstance(ops, dict) else ops
        else:
            num = lambda k: float(opt(k)) if opt(k) is not None else None
            try:
                extra = json.loads(opt("--json", "{}"))
            except ValueError as x:
                raise SceneError(f"--json: not JSON ({x})")
            if opt("--start") is None:
                raise SceneError("add takes --start (scene seconds)")
            ops = add_op(e, sc, a[2] if len(a) > 2 else "", num("--start"), num("--end"), opt("--src"), opt("--text"), opt("--track"),
                         {k: num("--" + k) for k in ("x", "y", "w", "h")}, extra)
        before = {it["id"] for t in sc["tracks"] for it in t["items"]}
        after, ch = claude_ops(e, ops, opt("--why"), alt)
        try:   # this Claude session worked on the edit: the page's notes go to it (review.py note_session)
            import review
            review.note_session(e.resolve(), "scene")
        except Exception:
            pass
        new = [f"{it['id']} ({it['type']})" for t in after["tracks"] for it in t["items"] if it["id"] not in before]
        print(f"Claude change {ch['n']}: {ch['why']}" if ch else "nothing changed",
              f"; added {', '.join(new)}" if new else "", "; the open page shows it on its next poll" if server(e) else "", sep="")
    else:
        print(__doc__)


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except SceneError as x:
        sys.exit(f"ERROR: {x}")
