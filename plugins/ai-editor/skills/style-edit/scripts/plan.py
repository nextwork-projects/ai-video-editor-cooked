#!/usr/bin/env python3
"""Turn a creator's style.json + a cut's words.json into plan.json for the Remotion render.

    python3 plan.py <style.json> <edits/NAME/captions.json> [--images images.json (default: next to it)]
                    [--aspect auto|9:16|16:9] [--layout overlay|split|letterbox|board] [--title T]
                    [--out edits/NAME/plan.json]
    python3 plan.py cards edits/NAME [--plan plan.json]   every card, its time, box and the beat it came from
    python3 plan.py beat  edits/NAME card:3|0:15|word@2 key=value ... | --drop   change one beat (visuals.json, images.json)
    python3 plan.py beat  edits/NAME --add beats.json   new beats into visuals.json in spoken order
    python3 plan.py demo      self-check

cut.mp4 is read from the words' folder (ffprobe gives its size, fps and length). A missing or empty
style.json plans with the default style (profile.py DEFAULT_STYLE) and says so.
images.json, optional: [{"src": "images/a.png", "word": "notion"}, ...]. src is relative
to the edit folder. Optional per image: "nth" (which time the word is said, default the
next one after the previous card), "box" [x, y, w, h] in percent, "entrance", "hold_s".
visuals.json next to words.json, optional: its "anim" beats become animated cards
(its "capture" beats arrive through images.json once capture.mjs has run).
Every card gets a "layout" (references/motion.md "Layout per template"): explaining templates are
full-frame scenes (a cut-away with a designed transition), pile/icon_burst and vertical captures sit in
the split panel (the speaker in a window under it, framed from face.json; the panel opens only when a
card needs it), and only logos, lower thirds, arrow callouts and caption pages stay boxes over the
footage. A beat's "layout" overrides, except that an explaining card on vertical is never a box.
--layout overlay never opens the panel: split cards become scenes. --layout letterbox (a landscape take only):
a black 9:16 frame, the take as a centred band, a lowercase title above it, one word at a time in the band and
the first image in images.json beside the head over the opening line; nothing else.
--layout board (16:9, the Motion design sample style): one dark canvas a camera drags across; logo cards become
tiles landing on their words under a heading in the speaker's words, a question becomes a heading that rises as the
camera pans down, every other card an overlay on the speaker's footage, sides alternating (board_layout).
Also writes "look" (profile brand kit > creator style.json > editorial; references/motion.md) and
"motion" (the personality, from the creator's pace). The anti-generic rules (visuals.md) run first.
The user's profile (~/.ai-video-editor/profile.json, the start skill) supplies brand, avoid and sound.
The style page's presets (lib/ai_editor/presets.py): captions.preset names a caption style (custom/captions/ or the
built-in presets/captions/), zoom.preset none | smooth | punchy, "cards": {"on", "per_min"} how many cards may land,
"look": {"preset"} the card look, "music": false drops the bed. custom/templates/<type>.json holds default props
for that motion template (<library>/custom/, custom.py).
Shapes: references/contracts.md, references/motion.md. Stdlib only, deterministic.
"""
import argparse
import inspect
import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SIZES = {"9:16": (1080, 1920), "16:9": (1920, 1080)}
PAUSE_S = 0.3          # a gap this long starts a new caption chunk
MAX_WORD_S = 0.8       # longest a single spoken word is believed to last
HOLD_TAIL_S = 0.3      # a caption stays up this long after its last word
CARD_LEAD_S = 0.1      # a card lands this long before its word
ENTRANCES = ("pop", "slide", "fade", "scale")
# Entrance per overlay format, so cards do not all arrive the same way (ai-tells.md "same-entrance"):
# a capture lifts, a post or a chat slides, a sticker or a logo pops, a terminal fades up.
FORMAT_ENTRANCE = {"shot": "scale", "browser": "slide", "sticker": "pop", "plain": "scale", "social_post": "slide", "chat": "slide",
                   "terminal": "fade", "toasts": "slide", "logo_cluster": "pop", "side_by_side": "slide", "video_card": "scale",
                   "logo": "pop", "logo_sting": "pop", "likes": "pop", "progress": "scale", "curve": "scale", "notes": "slide"}
# Above the head in a vertical frame, the right side in a wide one.
DEFAULT_BOX = {"9:16": [10, 15, 74, 20], "16:9": [54, 10, 40, 48]}
# Where the app's own UI sits, in percent: left, top, right, bottom. Vertical: the
# TikTok/Reels/Shorts top bar, the like/comment/share rail on the right and the
# caption/username block at the bottom. Wide: YouTube's progress bar.
# Vertical is the reels safe zone, x 60-940 and y 250-1440 of 1080x1920 (rounded inwards): nothing a plan draws
# (cards, overlays, logos, captions, scene content) goes outside it. Cards centred on the frame keep the wider
# side margin on both sides (x 140-940).
SAFE = {"9:16": (5.6, 13.1, 13.0, 25.0), "16:9": (3, 5, 3, 10)}
# Vertical overlays beside the head (free_regions) may reach the safe zone's left edge; the band above the head
# is centred, so it keeps the wider margin. check.py plan allows the same.
OVERLAY_TOP, OVERLAY_EDGE = SAFE["9:16"][1], SAFE["9:16"][0]
LOGO_S = 1.2           # a logo stays up this long
LOGO_BOX_H = 11        # logo tile height, % of the frame
LOGO_CARD_BOX = (18, 13.1, 64, 18)   # a card edit's logo card on white: centred in the band above the head, the logo 200+ px
# logo_cluster on vertical (Overlays.tsx reads props.band and props.size): the logos' outer edges span this
# band of the width, centred, each this % of the width wide. check.py plan FAILs a vertical cluster whose
# ink is under INK_MIN_W of the width or off centre, the same as check.py render measures it.
LOGO_BAND, LOGO_SIZE = (17, 83), 20
INK_MIN_W = 60
TOP_CARD_MAX_H = {"9:16": 22, "16:9": 80}   # a top card taller than this reaches the head
SCENES = ("flow",)   # picture scenes: parts land on their own words
# Every template in remotion/src/Templates.tsx (references/motion.md), plus the two original names that remain.
TEMPLATES = ("flow", "logo_sting", "social_post", "arrow_callout", "icon_burst", "caption_page")
# The overlay formats (remotion/src/Overlays.tsx): real pictures floating over the footage. The default.
OVERLAYS = ("shot", "browser", "sticker", "chat", "terminal", "toasts", "logo_cluster", "side_by_side", "video_card",
            "likes", "progress", "curve", "notes")
# The moving ones: a card edit leans on these over static captures (references/shapes.md "Card edit").
MOVING = ("chat", "terminal", "toasts", "logo_cluster", "side_by_side", "video_card", "likes", "progress", "curve", "notes", "flow")
FORMATS = ("shot", "browser", "sticker", "plain")    # how an image card is drawn
# Type cards (words on a ground) were removed from the product (2026-10-06): an old visuals.json naming one
# is skipped with a pointer to the overlay format that shows the real source instead.
TYPE_ONLY = ("slam", "title", "counter", "bar_chart", "line_chart", "checklist", "phrase_mark", "keyword", "steps", "race",
             "versus", "lower_third", "pile")
INSTEAD = {"counter": "a capture (sticker) of the page that published the number, the number highlighted",
           "bar_chart": "side_by_side of the two real pages, or a sticker of the sentence with the figures",
           "line_chart": "a capture of the real chart, ringed where the speaker points",
           "versus": "side_by_side with the two real screenshots", "lower_third": "the person's real post (post) or page (capture)",
           "pile": "a logo_cluster of the real logos"}
# Content aspect (width / height) of each overlay, to pick the free region around the head it fills best.
ASPECT = {"browser": 1.45, "chat": 1.9, "terminal": 1.8, "toasts": 3.2, "social_post": 2.2, "side_by_side": 2.6,
          "video_card": 16 / 9, "flow": 2.4, "icon_burst": 1.6, "likes": 2.6, "progress": 2.2, "curve": 2.0, "notes": 2.2}
FIXED_BOX = ("logo", "logo_sting", "arrow_callout", "caption_page")   # keep their own box
LEGACY = ("logo", "flow")
ANIMS = tuple(dict.fromkeys(TEMPLATES + OVERLAYS + LEGACY))
# Where each card sits (references/motion.md "Layout per template"). "scene": a full-frame cut-away on
# the look's ground. "split": the split layout's top panel. "box": a card over the footage, only for these.
BOX_OK = ("logo", "logo_sting", "arrow_callout", "caption_page")
SPLIT_FIRST = ("icon_burst",)    # scene or split: split keeps the speaker in shot
LAYOUTS = ("scene", "split", "box")
SCENE_BOX = [0, 0, 100, 100]            # "use the scene box" (the renderer's, clear of the app's UI)
SCENE_TYPE_BOX = {True: [14, 14, 72, 52], False: [6, 9, 88, 70]}   # Scene.tsx sceneBox, vertical / wide: where it draws
TRANSITIONS = ("match", "iris")         # renderer defaults: in, out
# A scene's transition in takes about 0.62 s x the personality's k (Scene.tsx). The scene starts this
# much earlier than a box card, so the ground has mostly grown by the word. A "cut" in has nothing to grow:
# it is whole on its first frame, so it starts where a box card does (CARD_LEAD_S before its word).
SCENE_LEAD_S = 0.3
# An overlay's entrance (motion.ts dropIn: expo.out over 0.62 s x k) carries half its ink, what quality.py counts as
# landed (LAND_SHARE), this long x k after it starts: 0.06 and 0.08 s on the sample take's captures. plan.py starts
# the card this much (x k) before CARD_LEAD_S ahead of its word, the renderer starts the drop-in there (motion.ts
# reads the same two numbers; the demo checks they match) and quality.py's word model reads it (scene_land).
OVERLAY_LEAD_S = 0.07
MOTION_K = {"punchy": 0.7, "snappy": 0.8, "smooth": 1.0, "calm": 1.35}
# Personality from the copied creator's median shot length (references/motion.md "Personalities").
PERSONALITY = ((1.4, "punchy"), (2.4, "snappy"), (4.0, "smooth"), (1e9, "calm"))
STOCK = ("unsplash.com", "pexels.com", "shutterstock.com", "istockphoto.com", "gettyimages.", "pixabay.com",
         "freepik.com", "stock.adobe.com", "depositphotos.com", "dreamstime.com", "123rf.com")
EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]")
READ_XH = 28           # px: a capture's x-height on a 1080-wide frame under this is too small to read on a phone
MIN_CARD_S = 0.5       # a card cut shorter than this by the next one is dropped
MIN_SHOW_S = 1.2       # no card is on screen for less: one shorter grows into the free time round it, else goes
# Pacing (SKILL.md step 3, one rule): a card where a sentence names something real, never two at once. The
# longest stretch with no card is 2 x the copied creator's measured mean gap (120 / graphics.per_min), else
# GAP_S; inside a longer one the frame still changes (a zoom) at least every QUIET_HOLD_S. check.py plan WARNs
# a longer gap that holds a named thing or a stretch with no change.
GAP_S = 10.0
QUIET_HOLD_S = 5.0


def clean(text):
    return re.sub(r"[^\w'’-]+", "", text)


def cased(text, mode):
    text = clean(text)
    return text.lower() if mode == "lower" else text.upper() if mode == "upper" else text


def ends_sentence(text):
    return text.rstrip().endswith((".", "?", "!"))


def ends_clause(text):
    return text.rstrip().endswith((".", "?", "!", ",", ";", ":"))


def join_hyphens(words):
    """Whisper splits "one-for-one" into "one", "-for", "-one": a token starting with "-" joins the word before."""
    out = []
    for w in words:
        if out and w["text"].strip().startswith("-") and len(w["text"].strip()) > 1:
            out[-1] = {**out[-1], "text": out[-1]["text"].rstrip() + w["text"].strip(), "end": w["end"]}
        else:
            out.append(w)
    return out


def chunk_captions(words, n, mode):
    chunks, cur = [], []
    words = join_hyphens(words)
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        if nxt is None or len(cur) >= n or ends_clause(w["text"]) or nxt["start"] - w["end"] > PAUSE_S:
            chunks.append(cur)
            cur = []
    out = []
    for i, c in enumerate(chunks):
        nxt = chunks[i + 1][0]["start"] if i + 1 < len(chunks) else None
        # A transcriber can stretch one word over a pause or a misheard run; never hold past
        # a plausible spoken length plus a short tail.
        last = c[-1]
        end = min(last["end"], last["start"] + MAX_WORD_S) + HOLD_TAIL_S
        if nxt is not None:
            end = min(end, nxt)
        ws = [{"text": cased(w["text"], mode), "start": w["start"], "end": w["end"]} for w in c]
        ws = [w for w in ws if w["text"]]
        if ws:
            out.append({"text": " ".join(w["text"] for w in ws), "start": c[0]["start"],
                        "end": round(end, 3), "words": ws})
    return out


def zoom_times(words, on, cuts):
    """Candidate moments for a zoom, in seconds."""
    if on == "every_cut" and cuts:
        return cuts
    starts = [w["start"] for i, w in enumerate(words)
              if i == 0 or ends_sentence(words[i - 1]["text"]) or w["start"] - words[i - 1]["end"] > 0.5]
    if on != "emphasis":
        return starts
    # Emphasis: the longest-held word of each phrase (people stretch the word they stress).
    out, phrase = [], []
    for i, w in enumerate(words):
        phrase.append(w)
        if i + 1 == len(words) or words[i + 1]["start"] - w["end"] > 0.2:
            out.append(max(phrase, key=lambda x: x["end"] - x["start"])["start"])
            phrase = []
    return out


# An audio-only clip (clips.py trim): the renderer draws the show's cover and moves it, so the frame never holds still.
COVER_PUSH, COVER_GROUND, COVER_PULSE = 1.12, 1.06, 1.02   # cover's end scale, ground's start scale, punch on a sentence


def audio_cover(edit_dir, words):
    """plan "cover" for an audio-only clip with artwork (clip.json from clips.py trim), else None. Pulses: sentence
    starts, never in the opening half second and at least a second apart."""
    cj = edit_dir and Path(edit_dir) / "clip.json"
    meta = json.loads(cj.read_text(encoding="utf-8")) if cj and cj.exists() else {}
    if not (meta.get("audio_only") and meta.get("cover") and meta.get("cover_box")
            and (Path(edit_dir) / meta["cover"]).exists()):
        return None
    pulses = []
    for t in zoom_times(words, "sentence_start", ()):
        if t >= 0.5 and (not pulses or t - pulses[-1] >= 1.0):
            pulses.append(round(t, 3))
    return {"src": meta["cover"], "box": meta["cover_box"], "push": COVER_PUSH, "ground_push": COVER_GROUND,
            "pulse": COVER_PULSE, "pulses": pulses}


def card_gap_s(style):
    """The longest stretch with no card: 2 x the creator's measured mean gap between cards, else GAP_S."""
    pm = graphics(style, "graphics").get("per_min")
    return round(120 / pm, 1) if pm else GAP_S


def named_beats(edit_dir):
    """route.py's beats.json sentences that name one of the profile's things ([] when there is none)."""
    bj = edit_dir and Path(edit_dir) / "beats.json"
    return [x for x in json.loads(bj.read_text(encoding="utf-8")) if x.get("names")] if bj and bj.exists() else []


def card_gaps(cards, duration):
    """[(start, end)] stretches of the video with no card up, the opening and the end included."""
    out, t = [], 0.0
    for c in sorted(cards, key=lambda c: c["start"]):
        if c["start"] > t:
            out.append((round(t, 3), round(c["start"], 3)))
        t = max(t, c["end"])
    if duration > t:
        out.append((round(t, 3), round(duration, 3)))
    return out


def place_zooms(zoom, words, duration, cuts, cut_kinds=None, quiet=(), shot_s=None):
    """quiet: stretches with no card longer than card_gap_s; inside them a zoom change comes at least every
    QUIET_HOLD_S, so the frame keeps changing while the speaker carries the line.
    shot_s (pace.median_shot_s): a punch holds about one of her shots, then goes back to 1x, as a punch on a cut
    does in hers; without it, until the next zoom change (a 2x punch once held 16 s)."""
    per_min = zoom.get("per_min") or 0
    if not per_min or not words:
        return []
    if zoom.get("fill_quiet") is False:   # user_rate: the user's own zoom rate, no extra changes in quiet stretches
        quiet = ()
    if zoom.get("kind", "punch") == "punch" and shot_s:
        per_min /= 2   # each punch comes back out by itself: in and out are two of her measured zooms
    gap = 60 / per_min * 0.8
    picked = []
    cands = zoom_times(words, zoom.get("on", "sentence_start"), cuts)
    mix = cut_kinds or {}
    if mix.get("zoom-punch") and zoom.get("on") == "every_cut" and cuts:
        # pace.cut_kinds: her share of cuts that punch in; the rest are hard holds (no zoom)
        z = mix["zoom-punch"] / sum(mix.values())
        cands = [t for t, k in zip(cands, deal({"zoom": z, "hold": 1 - z}, len(cands))) if k == "zoom"]
    for t in cands:
        if not picked or t - picked[-1] >= gap:
            picked.append(t)
    # Her rate, not her cut count: a take with fewer cuts than hers (one long shot) still gets per_min zooms, the
    # rest on sentence starts (her every_cut punches were 5 a minute over 35 cuts; ours has 12).
    want = round(per_min * duration / 60)
    for t in zoom_times(words, "sentence_start", ()) if len(picked) < want else ():
        if len(picked) >= want:
            break
        if all(abs(t - p) >= gap for p in picked):
            picked = sorted(picked + [t])
    hold = zoom.get("max_hold_s")
    starts = [w["start"] for w in words]
    longest = lambda a, b: min(hold or 1e9, QUIET_HOLD_S if any(qa < (a + b) / 2 < qb for qa, qb in quiet) else 1e9)
    while (hold or quiet) and picked:
        # the default style (and any stretch with no card): a long sentence still gets a zoom change, on the
        # word start nearest its middle
        add = {min(mids, key=lambda t: abs(t - (a + b) / 2))
               for a, b in zip(picked, picked[1:] + [duration]) if b - a > longest(a, b)
               for mids in [[t for t in starts if a + 1 < t < b - 1]] if mids}
        if not add:
            break
        picked = sorted(set(picked) | add)
    kind = zoom.get("kind", "punch")
    ease = 0.0 if kind == "punch" else (zoom.get("duration_s") or 0.4)
    # Alternate in / out so the frame never creeps tighter: every other change goes back to 1x.
    ends = picked[1:] + [duration]
    named = {"ease": zoom["ease"]} if kind != "punch" and zoom.get("ease") not in (None, "none") else {}
    capped = kind == "punch" and shot_s
    if capped:   # her punch is a step on one frame: ours travels 3 frames, not the house 0.16 s (StyleEdit.tsx PUNCH_S)
        named["travel_s"] = CREATOR_PUNCH_S
    if capped:   # every change is a punch in that comes back out by itself
        ends = [min(e, s + max(1.0, shot_s)) for s, e in zip(picked, ends)]
    return [{"start": round(s, 3), "end": round(e, 3), "scale": zoom.get("scale", 1.15),
             "kind": kind, "ease_s": ease, **named}
            for i, (s, e) in enumerate(zip(picked, ends)) if (capped or i % 2 == 0) and e > s]


ENTER_S = (0.15, 0.75)   # a card's entrance window: from just before its start to when it has settled
PUNCH_S = 0.16           # StyleEdit.tsx PUNCH_S: how long a punch zoom takes to travel
CREATOR_PUNCH_S = 0.1    # a copied creator's punch (measured as a one-frame step): 3 frames, under quality.py's snap line


def clear_entrances(zooms, cards):
    """A zoom change never lands while a card is entering: it moves to finish just before the card starts, or,
    for a full-frame scene, to its middle, hidden under it (the footage comes back at the new zoom, like a cut).
    Two zooms closer than a punch's travel join into one (the out move would be cut short: a one-frame snap);
    a zoom that gets shorter than 0.5 s is dropped. Two moves at once compete for the eye, and the render check
    cannot time a card's landing while the footage under it jumps. A punch that would start and end under a scene
    starts as the scene leaves instead (the footage comes back punched in), so the scene does not eat it."""
    orig = {id(z): (z["start"], z["end"]) for z in zooms}
    for c in cards:
        a, b = c["start"] - ENTER_S[0] - PUNCH_S, c["start"] + ENTER_S[1]
        to = round((c["start"] + c["end"]) / 2, 3) if c.get("layout") == "scene" else round(max(0.0, a), 3)
        for z in zooms:
            for k in ("start", "end"):
                if a < z[k] < b:
                    z[k] = to
    out = []
    for z in sorted(zooms, key=lambda z: z["start"]):
        if z["end"] - z["start"] < 0.5:
            a0, b0 = orig[id(z)]
            sc = next((c for c in cards if c.get("layout") == "scene" and c["start"] - ENTER_S[0] - PUNCH_S < a0 < c["end"]), None)
            if not sc:
                continue
            z["start"], z["end"] = round(sc["end"] + ENTER_S[1], 3), round(sc["end"] + ENTER_S[1] + b0 - a0, 3)
        if out and z["start"] < out[-1]["end"] + PUNCH_S:
            out[-1]["end"] = max(out[-1]["end"], z["end"])
        else:
            out.append(z)
    return out


def card_defaults(style):
    cats = style.get("cats") or (style["events"] if isinstance(style.get("events"), dict) else {})
    top = next(iter(cats.values()), {}) if cats else {}
    ent = next((e[0] for e in top.get("entrance") or [] if e[0] in ENTRANCES), None)   # None: per format (FORMAT_ENTRANCE)
    return top.get("hold_s") or 2.5, ent, top.get("box") or (graphics(style, "layout").get("layout") or {}).get("median_box")


# ---------- the creator's measured fields (creator-teardown style.json; references/visuals.md "From the teardown") ----------
# Each is used only when present and only when the blend took its part (editplan.py --take strips the rest).
# Absent: the defaults above, unchanged.

def took(style, part):
    """A teardown part ("graphics", "entrances", "layout", "pace", "sound") counts only when the blend took it.
    No blend.take (a single creator, or an older file): every part present counts."""
    take = (style.get("blend") or {}).get("take")
    return take is None or part in take


MUSIC_PCT = 50   # the creator runs a bed under this share of her videos or more: the edit gets one too


def music_wanted(style, prof):
    """A music bed for this edit? The style page's switch ("music" in the effective style), else the user's
    profile sound.music, else the creator's measure: a bed in MUSIC_PCT% of her videos or more."""
    if "music" in style:
        return bool(style["music"])
    pm = ((prof or {}).get("sound") or {}).get("music")
    if pm is not None:
        return bool(pm)
    m = ((style.get("sound") or {}).get("music") or {}) if took(style, "sound") else {}
    return (m.get("present_pct") or 0) >= MUSIC_PCT


def graphics(style, part):
    """style.json "graphics" when `part` was taken, else {}."""
    return (style.get("graphics") or {}) if took(style, part) else {}


def deal(shares, n):
    """n picks that follow shares {name: weight}, spread out (smooth weighted round robin). Deterministic."""
    shares = {k: v for k, v in shares.items() if v and v > 0}
    if not shares:
        return [None] * n
    cur, tot, out = dict.fromkeys(shares, 0.0), sum(shares.values()), []
    for _ in range(n):
        for k in cur:
            cur[k] += shares[k]
        k = max(cur, key=cur.get)
        cur[k] -= tot
        out.append(k)
    return out


def fit_of(e, aspect, out=False):
    """One graphics.entrances[] / exits[] row -> the renderer's fit (motion.ts Fit): kind, GSAP ease, dur (s),
    dir, dist (% of the frame's short side), fade, scale. distance_pct is % of the frame along the move."""
    W, H = SIZES[aspect]
    side = e.get("to" if out else "from")
    f = {"kind": e.get("kind") or "cut", "ease": e.get("ease") or "none", "dur": round(e.get("duration_s") or 0, 3)}
    if f["kind"] in ("slide", "mask") and side:
        f["dir"] = side
    if f["kind"] == "slide":
        f["dist"] = round((e.get("distance_pct") or 0) * (H if side in ("top", "bottom") else W) / min(W, H), 1)
    if e.get("fade"):
        f["fade"] = True
    sc = e.get("scale_to" if out else "scale_from")
    if f["kind"] == "scale" and sc:
        f["scale"] = sc
    return f


# A measured entrance kind -> the card's "entrance" (sfx.py cues and ai_tells read it)
FIT_ENTRANCE = {"cut": "cut", "slide": "slide", "fade": "fade", "scale": "scale", "mask": "slide"}
# graphics.kinds -> the capture format that shows it with a real source. A text card is never built
# (type cards were removed): it becomes a sticker of the real sentence.
KIND_FORMAT = {"real screenshot": "shot", "photo": "shot", "meme": "shot", "UI recording": "browser",
               "text card": "sticker", "chart": "sticker"}
# graphics.secondary_motion -> the ambient move a card makes while up (motion.ts camera). "video": the picture
# itself moves in hers; a still capture stands in with the default push and drift.
AMBIENT = {"still": "still", "push": "push", "drift": "drift", "video": "video"}


def creator_motion(cards, style, aspect):
    """Deals the creator's measured entrances, exits and ambient moves over the box cards, in her shares
    (props.enter / props.exit / props.ambient; motion.ts plays them in place of dropIn / exitUp / the camera)."""
    g = graphics(style, "entrances")
    # logo_cluster keeps its own pop round the head: a measured slide carries its logos across the face
    box = [c for c in cards if c.get("layout") != "scene" and (c.get("anim") or {}).get("type") != "logo_cluster"]
    for key, out in (("entrances", False), ("exits", True)):
        rows = g.get(key) or []
        if not rows:
            continue
        for c, i in zip(box, deal({i: r.get("share_pct") or r.get("n") or 0 for i, r in enumerate(rows)}, len(box))):
            if i is None:
                continue
            f = fit_of(rows[i], aspect, out)
            props(c)["exit" if out else "enter"] = f
            if not out:
                c["entrance"] = FIT_ENTRANCE.get(f["kind"], c.get("entrance"))
    sec = g.get("secondary_motion") or {}
    for c, a in zip(box, deal({AMBIENT[k]: v for k, v in sec.items() if k in AMBIENT}, len(box))):
        if a:
            props(c)["ambient"] = a
    return cards


def props(c):
    """The props the renderer reads for a card: the anim's, or (an image card) the card's own, copied so the
    images.json item they came from is never written into."""
    if c.get("anim"):
        c["anim"] = {**c["anim"], "props": dict(c["anim"].get("props") or {})}
        return c["anim"]["props"]
    c["props"] = dict(c.get("props") or {})
    return c["props"]


def kind_formats(images, style):
    """Captures with no format take one from the creator's graphics.kinds mix, dealt in her shares."""
    mix = {}
    for k, v in (graphics(style, "graphics").get("kinds") or {}).items():
        if k in KIND_FORMAT:
            f = "shot" if pictures_only(style) and KIND_FORMAT[k] == "sticker" else KIND_FORMAT[k]
            mix[f] = mix.get(f, 0) + v
    free = [i for i, im in enumerate(images) if not im.get("format") and str(im.get("src", "")).startswith("images/capture-")]
    images = [dict(im) for im in images]
    for i, f in zip(free, deal(mix, len(free))):
        if f:
            images[i]["format"] = f
    return images


def place_pans(cam, duration):
    """camera.pan_per_min -> slow sideways drifts of the footage: each 1.5 s, PAN_PCT of the width, alternating
    out and back so the frame never walks off. [] without a measured camera."""
    n = round(duration / 60 * (cam.get("pan_per_min") or 0))
    out = []
    for i in range(n):
        s = (i + 0.5) * duration / n - PAN_S / 2
        a, b = (0, PAN_PCT) if i % 2 == 0 else (PAN_PCT, 0)
        out.append({"start": round(max(0.0, s), 3), "end": round(min(duration, s + PAN_S), 3), "from": a, "to": b})
    return out


PAN_S, PAN_PCT = 1.5, 2.5    # visual.py counts a pan at 2% of the width a second for 1 s


def safe_box(box, aspect):
    """Move then shrink a card box so none of it sits under the app's UI."""
    l, t, r, b = SAFE[aspect]
    x, y, w, h = box
    if aspect == "9:16":    # vertical cards are centred on the frame, not on the gap between the UI
        l = r = max(l, r)
    # ponytail: fixed height cap, not a head measurement; measure the head if framings vary a lot
    w, h = min(w, 100 - l - r), min(h, 100 - t - b, TOP_CARD_MAX_H[aspect] if y < 50 else 100)
    x = (100 - w) / 2 if aspect == "9:16" else min(max(x, l), 100 - r - w)
    y = min(max(y, t), 100 - b - h)
    return [x, y, w, h]


def logo_items(visuals, edit_dir, cap_y, aspect, card=False):
    """logo beats -> small logo cards just above the captions. They run in their own lane,
    so a logo can land while a bigger card is up. capture.mjs fetches the files. card (a card edit, vertical): the
    logo is a card of its own on white in the band above the head, in the main lane, held like any card."""
    out = []
    for v in visuals:
        if v.get("kind") != "logo":
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", (v.get("brand") or v["word"]).lower()).strip("-")
        src = next((f"images/logo-{slug}.{e}" for e in ("svg", "png")
                    if edit_dir and (edit_dir / f"images/logo-{slug}.{e}").exists()), None)
        if not src:
            print(f"warning: no logo file for '{slug}', run capture.mjs first; skipped", file=sys.stderr)
            continue
        w = LOGO_BOX_H * (16 / 9 if aspect == "9:16" else 9 / 16)   # a square tile
        item = {k: v[k] for k in ("word", "nth", "entrance", "heading") if k in v}
        if card and aspect == "9:16":
            item.update({"anim": {"type": "logo", "props": {"src": src, "card": True}}, "box": v.get("box") or list(LOGO_CARD_BOX)})
            item.update({"hold_s": v["hold_s"]} if v.get("hold_s") else {})
            out.append(item)
            continue
        item.update({"anim": {"type": "logo", "props": {"src": src}}, "hold_s": v.get("hold_s", LOGO_S),
                     "box": v.get("box") or [50 - w / 2, cap_y - LOGO_BOX_H - 5, w, LOGO_BOX_H], "lane": "logo"})
        out.append(item)
    return out


def strip_emoji(node, where, warn):
    """Emoji never reach the screen: removed from every text prop, with a warning."""
    if isinstance(node, list):
        return [strip_emoji(x, where, warn) for x in node]
    if isinstance(node, dict):
        return {k: strip_emoji(v, where, warn) for k, v in node.items()}
    if isinstance(node, str) and EMOJI.search(node):
        warn(f"anti-generic: emoji removed from '{where}': {node!r}")
        return EMOJI.sub("", node).strip()
    return node


def icon_only(props):
    """True when a card's pictures are all stock icons (Lucide) and nothing real: no logo, image or capture."""
    icons, real = [], []

    def walk(n):
        if isinstance(n, list):
            for x in n:
                walk(x)
        elif isinstance(n, dict):
            if "icon" in n:
                icons.append(n["icon"])
            if "logo" in n or ("src" in n and not str(n["src"]).startswith("images/icon-")):
                real.append(1)
            for v in n.values():
                walk(v)
    walk(props)
    return bool(icons) and not real


def anti_generic(visuals, profile=None, warn=None):
    """The visuals.md anti-generic rules on visuals.json, before anything is placed. Returns the beats
    that pass. Dropped: captures of stock-photo sites, anim cards whose only pictures are stock icons
    (a beat may set "allow_icons": true when nothing real exists and the icon sits in a type layout).
    Emoji are stripped from every text."""
    warn = warn or (lambda m: print(f"warning: {m}", file=sys.stderr))
    avoid = (profile or {}).get("avoid") or {}
    out = []
    for v in visuals:
        where = v.get("word", "?")
        url = (v.get("url") or "").lower()
        if avoid.get("stock", True) and any(d in url for d in STOCK):
            warn(f"anti-generic: '{where}' captures a stock-photo site ({url}); capture the named thing instead. Skipped")
            continue
        if v.get("kind") == "anim" and avoid.get("icons", True) and not v.get("allow_icons") \
                and icon_only(v.get("props") or {}):
            warn(f"anti-generic: the '{where}' {v.get('type')} card is only stock icons; use a logo, a capture, the "
                 f"user's own image or a type-led template (or set \"allow_icons\": true). Skipped")
            continue
        # the title card keeps its emoji: it is the user's own hook line, set as they wrote it
        out.append(strip_emoji(v, where, warn) if avoid.get("emoji", True) and v.get("kind") != "title" else v)
    return out


def type_only(v):
    """A removed words-on-a-ground card."""
    return v.get("type") in TYPE_ONLY


# Formats that are lines of words unless they carry a picture. A card edit never shows one bare.
WORDY = ("notes", "terminal", "chat")
PICTURE_KEYS = ("src", "logo_src", "avatar", "a_src", "b_src", "thumbs", "logo", "icon")


def has_picture(node):
    """True when a props tree names a picture anywhere: an image, a logo, an icon, an avatar, a frame."""
    if isinstance(node, list):
        return any(has_picture(x) for x in node)
    if not isinstance(node, dict):
        return False
    return any(node.get(k) for k in PICTURE_KEYS) or any(has_picture(v) for v in node.values())


def words_only(kind, props):
    """True when a card of this anim type would show only lines of words. notes needs the speaker's avatar and a
    frame of the take beside a line, progress the take's frames lighting up (take_frames fills them); terminal and
    chat need a logo or picture."""
    if kind in TYPE_ONLY:
        return True
    props = props or {}
    if kind == "progress":   # a label over an empty bar reads as words
        return not props.get("thumbs")
    if kind == "notes":
        return not (props.get("avatar") and any(isinstance(ln, dict) and ln.get("src") for ln in props.get("lines") or []))
    return kind in WORDY and not has_picture(props)


def frame_at(video, t, out, crop=None):
    """One frame of the take at t seconds as a small jpg (out, never overwritten). crop: a head box [x, y, w, h] in %,
    cut square round its centre (the avatar). None when ffmpeg cannot read it."""
    out = Path(out)
    if not out.exists():
        vf = "scale=360:-2"
        if crop:
            x, y, w, h = (v / 100 for v in crop)
            side = f"min(min(iw\\,ih)\\,max(iw*{w:.4f}\\,ih*{h:.4f}))"
            vf = (f"crop={side}:{side}:clip(iw*{x + w / 2:.4f}-ow/2\\,0\\,iw-ow):clip(ih*{y + h / 2:.4f}-oh/2\\,0\\,ih-oh),"
                  "scale=200:200")
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-n", "-ss", f"{max(0.0, t):.3f}", "-i", str(video), "-frames:v", "1",
                        "-vf", vf, "-q:v", "4", str(out)], capture_output=True)
    return out if out.exists() else None


def take_frames(cards, edit_dir, video, face=None, folder="images"):
    """A notes card is real UI, not words: the speaker's avatar (their head from the take, face.json) in its header
    and, beside each line, the frame of the take where that line is said. A progress card: four frames of the take
    from while it is up, lighting up as the bar passes them. Written to images/ once; a card that
    already names them keeps its own. folder: under edit_dir (a motion clip's own "assets")."""
    if not edit_dir or not video or not Path(video).exists():
        return cards
    for c in cards:
        a = c.get("anim") or {}
        if a.get("type") == "progress" and not (a.get("props") or {}).get("thumbs"):
            span = max(0.4, c["end"] - c["start"])
            fs = [frame_at(video, c["start"] + span * (k + 0.5) / 4, Path(edit_dir) / folder / f"frame-{round((c['start'] + span * (k + 0.5) / 4) * 1000)}.jpg")
                  for k in range(4)]
            if all(fs):
                a.setdefault("props", {})["thumbs"] = [f"{folder}/{f.name}" for f in fs]
            continue
        if a.get("type") != "notes":
            continue
        p = a.setdefault("props", {})
        if not p.get("avatar"):
            hd = face and head_during(face["heads"], face.get("step_s", 0.5), c["start"], c["start"] + 0.5)
            box = [hd[0], hd[1], hd[2] - hd[0], hd[3] - hd[1]] if hd else [25, 10, 50, 40]
            f = frame_at(video, c["start"], Path(edit_dir) / folder / f"avatar-{round(c['start'] * 1000)}.jpg", box)
            if f:
                p["avatar"] = f"{folder}/{f.name}"
        for i, ln in enumerate(p.get("lines") or []):
            if isinstance(ln, dict) and not ln.get("src"):
                t = c["start"] + (ln.get("at") if isinstance(ln.get("at"), (int, float)) else 0.35 + 0.6 * i) + 0.2
                f = frame_at(video, t, Path(edit_dir) / folder / f"frame-{round(t * 1000)}.jpg")
                if f:
                    ln["src"] = f"{folder}/{f.name}"
    return cards


def drop_words_only(cards, style):
    """A card edit (pictures only) shows no card made of words alone: such a beat gets no card."""
    if not pictures_only(style):
        return cards
    out = []
    for c in cards:
        a = c.get("anim") or {}
        if a and words_only(a.get("type"), a.get("props")):
            print(f"warning: no card on '{c.get('trigger_word')}': its {a.get('type')} shows only words, and this style "
                  "shows only screenshots, logos, photos and animations. Give the beat the user's image, a capture, a "
                  "logo or a motion clip, or leave it without a card", file=sys.stderr)
            continue
        out.append(c)
    return out


def with_presets(style, mine):
    """The style page's presets (lib/ai_editor/presets.py): captions.preset names a caption style (the user's
    <library>/custom/captions/<name>.json, else a built-in plugins/ai-editor/presets/captions/<name>.json) laid
    over the creator's captions; zoom.preset (none | smooth | punchy) over the creator's zooms. taste.json's own
    keys still win (they are merged after this)."""
    from ai_editor import presets
    return presets.apply(style, mine)


def pictures_only(style):
    """True when style.json "card_kinds" (a card edit: ["capture", "logo", "photo", "animation"]) leaves out "text":
    every card is a real screenshot, logo, photo or animation. No sticker of a re-set sentence, and a capture whose
    text reads small stays a picture (the shot pushes into its mark) instead of being cut to a line of words."""
    ks = style.get("card_kinds")
    return bool(ks) and "text" not in ks


def text_labels(cards, style):
    """A pictures-only style draws a sticker whose capture is the page itself as a shot, and drops a capture.mjs
    sticker (a sentence re-set alone on white, images.json "xh"): a text label, not a screenshot. capture.mjs shoots
    the page instead once style.json is current."""
    if not pictures_only(style):
        return cards
    out = []
    for c in cards:
        if c.get("format") == "sticker" and not c.get("xh"):   # the page itself: drawn whole as the picture
            c = {**c, "format": "shot", "props": {k: v for k, v in (c.get("props") or {}).items() if k != "crop"}}
            c["props"] or c.pop("props")
        if c.get("format") == "sticker":
            print(f"warning: '{c.get('word')}' {c.get('src')}: a sentence set alone on white is a text card, and this style "
                  "shows only screenshots, logos, photos and animations. Dropped: give the beat \"format\": \"shot\" "
                  "and run capture.mjs again", file=sys.stderr)
            continue
        out.append(c)
    return out


# A card edit's words besides the captions (visuals.json "title", "cta", "list", "stamp" beats; remotion Texts.tsx). % of the frame.
# The title: one plain white box, black bold type, tight to the words, on the lower chest with its bottom on the safe
# zone's bottom line (y 1440); captions wait while it is up. The cta: a black pill with white type in the band above the head.
TITLE_SIZE, TITLE_HOLD_S = 3.0, 3.8
TITLE_BOTTOM = 100 - SAFE["9:16"][3] - 0.5
CTA_Y, CTA_SIZE, CTA_HOLD_S = SAFE["9:16"][1] + 3, 5.2, 2.4
LIST_X, LIST_SIZE = SAFE["9:16"][0] + 1, 1.8
TEXT_KINDS = ("title", "list", "stamp")


def text_items(visuals, words, duration, cards, face=None, cap_y=66.0, cap_size=None):
    """plan.json "texts" from visuals.json: a "title" (text, "\\n" between lines, emoji kept; on its word, else from 0 s,
    for hold_s), a "cta" (text, label?; on its word, for hold_s), a running numbered "list" (items: [{text, word, nth}], each on its word, all held to the list's word
    "until" or the end; its type never smaller than the captions', cap_size), a "stamp" (a red X over the card up on its
    word). Every box inside the reels safe zone."""
    def at(word, nth=None):
        hits = [w["start"] for w in words if clean(w["text"]).lower() == clean(word or "").lower()]
        return hits[(nth or 1) - 1] if len(hits) >= (nth or 1) else None
    out = []
    for v in visuals:
        k = v.get("kind")
        if k == "title" and v.get("text"):
            t = at(v["word"], v.get("nth")) if v.get("word") else 0.0
            if t is None:
                print(f"warning: title '{v['text']}': '{v['word']}' is never said, skipped", file=sys.stderr)
                continue
            start = max(0.0, t - CARD_LEAD_S) if t else 0.0
            x = {"kind": "title", "text": v["text"], "start": round(start, 3), "end": round(min(duration, start + (v.get("hold_s") or TITLE_HOLD_S)), 3),
                 "y_pct": 0, "size_pct": v.get("size_pct") or TITLE_SIZE}
            x["y_pct"] = round(TITLE_BOTTOM - title_bottom(x), 1)
            out.append(x)
        elif k == "cta" and v.get("text") and v.get("word"):
            t = at(v["word"], v.get("nth"))
            if t is None:
                print(f"warning: cta '{v['text']}': '{v['word']}' is never said, skipped", file=sys.stderr)
                continue
            start = max(0.0, t - CARD_LEAD_S)
            out.append({"kind": "cta", "text": v["text"], "label": v.get("label") or "", "start": round(start, 3),
                        "end": round(min(duration, start + (v.get("hold_s") or CTA_HOLD_S)), 3), "y_pct": CTA_Y, "size_pct": CTA_SIZE})
        elif k == "list":
            items = [{"text": it["text"], "at": at(it.get("word"), it.get("nth"))} for it in v.get("items") or [] if it.get("text")]
            items = [{**it, "at": round(max(0.0, it["at"] - CARD_LEAD_S), 3)} for it in items if it["at"] is not None]
            if not items:
                continue
            until = at(v["until"], v.get("until_nth")) if v.get("until") else None
            start, end = items[0]["at"], min(duration, until if until else duration)
            # at the left: under the chin, else just above or below the captions; never over the head or the captions
            hd = face and head_during(face["heads"], face.get("step_s", 0.5), start, end)
            size = max(LIST_SIZE, float(cap_size or 0))   # QA round 4: 1.8% type under 4.4% captions read as specks
            h = len(items) * size * 1.3
            w = (3 + max(len(it["text"]) for it in items)) * 0.55 * size * 16 / 9   # % of the width, about
            cap = (cap_y - 3, cap_y + 3)
            up = [c["box"] for c in cards if c.get("box") and c["start"] < end and start < c["end"]]
            free = lambda y: (SAFE["9:16"][1] <= y and y + h <= 100 - SAFE["9:16"][3] and (y + h <= cap[0] or y >= cap[1])
                              and not (hd and LIST_X < hd[2] and LIST_X + w > hd[0] and y < hd[3] and y + h > hd[1])
                              and not any(LIST_X < b[0] + b[2] and LIST_X + w > b[0] and y < b[1] + b[3] and y + h > b[1] for b in up))
            y = next((y for y in ([hd[3] + 1] if hd else [47.0]) + [cap[0] - 0.5 - h, cap[1] + 0.5] if free(y)), None)
            if y is None:
                print(f"warning: the list ('{items[0]['text']}', ...) has no room clear of the head, the captions and the "
                      "cards up with it, skipped", file=sys.stderr)
                continue
            out.append({"kind": "list", "items": items, "start": start, "end": round(end, 3), "x_pct": LIST_X, "y_pct": round(y, 1), "size_pct": size})
        elif k == "stamp":
            t = at(v.get("word"), v.get("nth"))
            card = t is not None and next((c for c in cards if c.get("lane") != "logo" and c.get("layout") != "scene" and c["start"] <= t < c["end"]), None)
            if not card:
                print(f"warning: stamp on '{v.get('word')}': no card is up then, skipped", file=sys.stderr)
                continue
            out.append({"kind": "stamp", "start": round(t, 3), "end": card["end"], "box": card["box"]})
    return out


def title_bottom(x):
    """Where a title's box ends, % of the frame: its lines as Texts.tsx wraps them (74% wide, bold, about 0.55 em a
    character) at 1.15 em each, plus the box's 0.5 em of padding."""
    per = max(8, int(74 * 1080 / 100 / (0.55 * x["size_pct"] / 100 * 1920)))
    n = sum(max(1, math.ceil(len(ln) / per)) for ln in x["text"].split("\n"))
    return x["y_pct"] + (n * 1.15 + 0.5) * x["size_pct"]


def placed_sounds(plan, edit_dir):
    """The sounds the user put on the timeline on the review page (<edit>/sounds.json, review.py /sfx/add): each one
    from the sound library, at its moment, levelled like the kit (sfx.py own_cue). A missing file is skipped."""
    f = edit_dir and Path(edit_dir) / "sounds.json"
    if not f or not f.exists():
        return plan
    import sfx
    fps = plan.get("fps") or 30
    for x in json.loads(f.read_text(encoding="utf-8")).get("items") or []:
        try:   # a dropped audio file plays from its moment; a library sound lands its hit there
            src, att = (sfx.clip_cue(edit_dir, x), 0.0) if x.get("kind") == "clip" else sfx.own_cue(edit_dir, x["sound"])
        except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as e:
            print(f"warning: a placed sound was skipped: {e}", file=sys.stderr)
            continue
        t = float(x["t"])
        plan.setdefault("sfx", []).append({"t": round(round(max(0.0, t - att) * fps) / fps, 4), "src": src, "event": round(t, 3),
                                           "placed": x.get("id")})
    plan["sfx"] = sorted(plan.get("sfx") or [], key=lambda c: c["t"])
    return plan


def typed_texts(edit_dir):
    """The text the user typed on the review page's Text tool (<edit>/texts.json, review.py writes it when the round
    goes to Claude): plan.json "texts" kind "label" exactly as typed, styled and placed. Never reworded or moved."""
    f = edit_dir and Path(edit_dir) / "texts.json"
    if not f or not f.exists():
        return []
    keep = ("text", "style", "start", "end", "x_pct", "y_pct", "size_pct")
    extra = ("font", "color", "width_pct")   # set only when the user picked them (review.py text_look)
    return [{"kind": "label", **{k: x[k] for k in keep}, **{k: x[k] for k in extra if x.get(k) is not None}} for x in json.loads(f.read_text(encoding="utf-8")).get("items") or []]


def under_titles(cards, texts):
    """A card up with a cta gives way: it ends as the cta lands, or starts when it ends (the pill owns the band above
    the head). A card up with a title that overlaps its box moves below the title (keeping its bottom edge); one that
    would lose over 40% of its height starts when the title ends instead. Returns the cards kept."""
    for x in (x for x in texts if x["kind"] == "cta"):
        for c in cards:
            if c.get("layout") == "scene" or c["end"] <= x["start"] or c["start"] >= x["end"]:
                continue
            if c["start"] < x["start"]:
                c["end"] = x["start"]
            else:
                c["start"] = x["end"]
    cards[:] = [c for c in cards if c["end"] - c["start"] >= MIN_CARD_S]
    for x in (x for x in texts if x["kind"] == "title"):
        tb = title_bottom(x)
        for c in cards:
            if c.get("layout") == "scene" or c["end"] <= x["start"] or c["start"] >= x["end"] or c["box"][1] >= tb \
                    or c["box"][1] + c["box"][3] <= x["y_pct"]:
                continue
            bx, by, bw, bh = c["box"]
            if by + bh - tb >= max(MIN_CARD_H, 0.6 * bh):   # still most of its size: shrink it under the title
                c["box"] = [bx, round(tb, 1), bw, round(by + bh - tb, 1)]
            elif x["end"] < c["end"] - MIN_CARD_S:
                c["start"] = x["end"]


def image_size(path):
    """[w, h] of a PNG, JPEG, GIF or WebP from its header (stdlib), or None. An image card without "size" (the
    user's own photo, added on the page) was fitted as 16:10: a portrait sat in a grey box wider than itself."""
    import struct
    try:
        b = Path(path).read_bytes()
    except OSError:
        return None
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return list(struct.unpack(">II", b[16:24]))
    if b[:6] in (b"GIF87a", b"GIF89a"):
        return list(struct.unpack("<HH", b[6:10]))
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        if b[12:16] == b"VP8X":
            return [int.from_bytes(b[24:27], "little") + 1, int.from_bytes(b[27:30], "little") + 1]
        if b[12:16] == b"VP8 ":
            return [struct.unpack("<H", b[26:28])[0] & 0x3FFF, struct.unpack("<H", b[28:30])[0] & 0x3FFF]
        if b[12:16] == b"VP8L":
            v = int.from_bytes(b[21:25], "little")
            return [(v & 0x3FFF) + 1, ((v >> 14) & 0x3FFF) + 1]
    if b[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(b):
            if b[i] != 0xFF:
                i += 1
                continue
            m = b[i + 1]
            if m in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack(">HH", b[i + 5:i + 9])
                return [w, h]
            if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7:
                i += 2
                continue
            i += 2 + struct.unpack(">H", b[i + 2:i + 4])[0]
    return None


def min_show(cards, duration):
    """Every card on screen for MIN_SHOW_S at least (QA round 4: a capture flashed for 0.6 s at the very end): a shorter
    one runs on into the free time after it, then starts earlier into the free time before it, then takes time from
    the card before, then the card after, each down to MIN_SHOW_S; still short, it goes."""
    out = []
    order = sorted(cards, key=lambda c: c["start"])
    for i, c in enumerate(order):
        if c["end"] - c["start"] < MIN_SHOW_S - 1e-6:
            nxt = min([x["start"] for x in order[i + 1:] if x["start"] >= c["start"]] + [duration])
            c["end"] = round(min(nxt, max(c["end"], c["start"] + MIN_SHOW_S)), 3)
            prev = max([x["end"] for x in out] + [0.0])
            c["start"] = round(max(prev, min(c["start"], c["end"] - MIN_SHOW_S)), 3)
            p = out[-1] if out else None
            if c["end"] - c["start"] < MIN_SHOW_S - 1e-6 and p and p["end"] - p["start"] > MIN_SHOW_S:
                p["end"] = round(max(p["start"] + MIN_SHOW_S, c["end"] - MIN_SHOW_S), 3)   # the card before gives some up
                c["start"] = round(max(p["end"], min(c["start"], c["end"] - MIN_SHOW_S)), 3)
            n = order[i + 1] if i + 1 < len(order) else None
            if c["end"] - c["start"] < MIN_SHOW_S - 1e-6 and n and n["end"] - n["start"] > MIN_SHOW_S and n["start"] <= c["end"] + 1e-6:
                n["start"] = round(min(c["start"] + MIN_SHOW_S, n["end"] - MIN_SHOW_S), 3)   # the card after starts later
                c["end"] = max(c["end"], n["start"])
            if c["end"] - c["start"] < MIN_SHOW_S - 1e-6:
                print(f"warning: the '{c.get('trigger_word')}' card has no room for {MIN_SHOW_S} s on screen, dropped",
                      file=sys.stderr)
                continue
        out.append(c)
    return out


def card_rate(style):
    """Cards a minute the edit aims at: the copied creator's measured graphics.per_min (when the blend took it), held
    under the user's own cards.per_min, or 0 with cards.on false (the style page's Cards, saved to taste.json; a
    creator's style has no "cards" until the user picks one). The default style's 4 a minute is a cap, not a rate:
    with no creator rate this is None. route.py want() and style_check.py read it."""
    pm = graphics(style, "graphics").get("per_min")
    cfg = style.get("cards") or {}
    if not pm:
        return None
    if cfg.get("on") is False:
        return 0
    return min(pm, cfg["per_min"]) if cfg.get("per_min") is not None else pm


def thin_cards(cards, duration, cards_cfg):
    """style.json "cards" (the style page's Cards and graphics; the default style has per_min 4): on=false plans none;
    per_min keeps at most that many cards a minute, spread through the video in spoken order (0: none). Unset (a
    creator's style the user has not changed): every card stays. Each card left out is named on stderr."""
    cfg = cards_cfg or {}
    pm = cfg.get("per_min")
    cap = 0 if cfg.get("on") is False else None if pm is None else max(0, math.ceil(duration / 60 * pm)) if pm > 0 else 0
    if cap is None or len(cards) <= cap:
        return cards
    # ponytail: an even pick by order; rank by beat strength if a weak card wins a slot
    order = sorted(cards, key=lambda c: c["start"])
    keep = set() if cap == 0 else {id(order[round(i * (len(order) - 1) / max(1, cap - 1))]) for i in range(cap)} if cap > 1 else {id(order[0])}
    gone = [c for c in order if id(c) not in keep]
    why = "cards are off" if cfg.get("on") is False else f"at most {pm:g} cards a minute"
    print(f"note: {len(gone)} card{'s' if len(gone) != 1 else ''} left out ({why}; the style page's Cards and graphics): " +
          ", ".join(f"{c.get('trigger_word') or (c.get('anim') or {}).get('type') or c.get('src')}@{c['start']:.1f}s" for c in gone),
          file=sys.stderr)
    return [c for c in cards if id(c) in keep]


def template_props(kind, props):
    """A beat's props over the user's defaults for that template (<library>/custom/templates/<kind>.json)."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
    from ai_editor import custom
    return {**custom.load_json("templates", kind), **(props or {})}


def anim_items(visuals, edit_dir=None, style=None):
    """The built-animation beats of visuals.json as card items. Capture beats reach the
    plan through images.json (capture.mjs writes them there). "post" beats become social_post
    cards from the real post capture.mjs fetched (images/post-<id>.json)."""
    out = []
    for v in visuals:
        if v.get("kind") == "post":
            pid = v.get("id") or (re.search(r"status(?:es)?/(\d+)", v.get("url", "")) or [None, None])[1]
            f = edit_dir and pid and Path(edit_dir) / f"images/post-{pid}.json"
            if not f or not f.exists():
                print(f"warning: no images/post-{pid}.json for '{v.get('word')}', run capture.mjs first; skipped", file=sys.stderr)
                continue
            props = {k: x for k, x in json.loads(f.read_text(encoding="utf-8")).items() if k != "url"}
            props.update(v.get("props") or {})
            v = {**v, "kind": "anim", "type": "social_post", "props": props}
        if v.get("kind") != "anim":
            continue
        if type_only(v):
            print(f"warning: '{v.get('word')}' {v['type']} is a type card (words on a ground); type cards were removed. "
                  f"Use {INSTEAD.get(v['type'], 'a capture of the real source with the words marked (sticker, shot or browser)')}. Skipped",
                  file=sys.stderr)
            continue
        if v.get("type") not in ANIMS:
            print(f"warning: unknown anim type {v.get('type')!r} on '{v.get('word')}', skipped", file=sys.stderr)
            continue
        if v["type"] not in ("notes", "progress") and not drop_words_only([{"trigger_word": v.get("word"), "anim": v}], style or {}):
            continue   # notes and progress wait: take_frames gives them the take's frames once their times are known
        item = {k: v[k] for k in ("word", "nth", "box", "entrance", "hold_s", "layout", "transition_in", "transition_out", "focus", "heading") if k in v}
        if "box" in v:
            item["_own_box"] = True
        item["anim"] = {"type": v["type"], "props": template_props(v["type"], v.get("props"))}
        out.append(item)
    return out


def resolve_src(node, edit_dir):
    """{"icon": name} / {"logo": brand} -> the file capture.mjs fetched, or None."""
    slug = lambda x: re.sub(r"[^a-z0-9]+", "-", x.lower()).strip("-")
    if "icon" in node:
        return f"images/icon-{slug(node['icon'])}.svg"
    s = slug(node["logo"])
    src = next((f"images/logo-{s}.{e}" for e in ("svg", "png")
                if edit_dir and (Path(edit_dir) / f"images/logo-{s}.{e}").exists()), None)
    if not src:
        print(f"warning: no logo file for '{s}', run capture.mjs first", file=sys.stderr)
    return src


def word_at(words, card, node, key):
    """Seconds after the card lands that node[key] is said ("nth" picks a later time), or None."""
    target = clean(node[key]).lower()
    hits = [w for w in words if clean(w["text"]).lower() == target and w["start"] >= card["start"]]
    n = node.get("nth", 1)
    if len(hits) < n:
        print(f"warning: '{node[key]}' is not said during the '{card['trigger_word']}' card", file=sys.stderr)
        return None
    at = round(hits[n - 1]["start"] - card["start"], 3)
    if card["start"] + at > card["end"]:
        print(f"warning: '{node[key]}' lands after the '{card['trigger_word']}' card ends; raise hold_s", file=sys.stderr)
    return at


def scene_parts(cards, words, edit_dir):
    """Fill in every anim card's props, anywhere they nest: "icon" / "logo" -> "src" (the file capture.mjs
    fetched), "word" / "off_word" -> "at" / "off_at", seconds after the card lands. A word is the
    first time it is said once the card is up ("nth" picks a later time). No word: the template staggers.
    A prop that wants a file path ("avatar", "logo_src", "src", "a_src", "b_src") may be given as
    {"logo": ...} and becomes the path. caption_page with no "words" gets the words said while it is up.
    Capture cards: each mark's "at_word" -> "at" (an "at_s" is kept as "at"; neither: 0.8 s)."""
    def walk(node, card):
        if isinstance(node, list):
            for x in node:
                walk(x, card)
            return
        if not isinstance(node, dict):
            return
        if (isinstance(node.get("icon"), str) or isinstance(node.get("logo"), str)) and "src" not in node:
            src = resolve_src(node, edit_dir)
            if src:
                node["src"] = src
        for key, out in (("word", "at"), ("off_word", "off_at")):
            if key in node:
                at = word_at(words, card, node, key)
                if at is not None:
                    node[out] = at
        for k, v in list(node.items()):
            if k in ("avatar", "logo_src", "src", "a_src", "b_src", "logo") and isinstance(v, dict) and ("logo" in v or "icon" in v):
                node[k] = resolve_src(v, edit_dir)
            else:
                walk(v, card)

    for c in cards:
        if c.get("anim"):
            c["anim"] = json.loads(json.dumps(c["anim"]))   # never write back into visuals
            walk(c["anim"]["props"], c)
            if c["anim"]["type"] == "caption_page" and not c["anim"]["props"].get("words"):
                c["anim"]["props"]["words"] = [
                    {"text": w["text"], "start": round(max(0.0, w["start"] - c["start"]), 3),
                     "end": round(min(c["end"], w["end"]) - c["start"], 3)}
                    for w in words if c["start"] <= w["start"] < c["end"]]
        wt = c.pop("_word_t", None)
        if wt is not None and c.get("layout") != "scene":
            # seconds from the card's start to its own word: motion.ts landAt lands the entrance there
            props(c)["word_at"] = round(max(0.0, wt - c["start"]), 3)
        for mk in c.get("marks") or []:
            if "at_word" in mk:
                at = word_at(words, c, {"word": mk["at_word"], "nth": mk.get("nth", 1)}, "word")
                mk["at"] = at if at is not None else 0.8
            elif "at_s" in mk:
                mk["at"] = mk["at_s"]
            mk.setdefault("at", 0.8)
            for k in ("at_word", "at_s", "nth"):   # "find" stays: check.py plan reads it (a capture on the hook)
                mk.pop(k, None)
    return cards


def place_cards(images, words, duration, style, aspect):
    """images: image items and anim items (anim_items). Each group without "nth" takes the
    next time its word is said after that group's previous card."""
    hold, ent, box = card_defaults(style)
    out = []
    logos = [i for i in images if i.get("lane") == "logo"]
    images = [i for i in images if i.get("lane") != "logo"]
    for lane in ([i for i in images if "anim" not in i] + [i for i in images if "anim" in i], logos):
        cards = []
        for group in ([i for i in lane if "anim" not in i], [i for i in lane if "anim" in i]):
            cards += _place(group, words, duration, hold, ent, box, aspect)
        cards.sort(key=lambda c: c["start"])
        for a, b in zip(cards, cards[1:]):     # never two cards at once in a lane
            a["end"] = min(a["end"], b["start"])
        for c in cards:
            if c["end"] - c["start"] < MIN_CARD_S:
                print(f"warning: '{c['trigger_word']}' card cut to {c['end'] - c['start']:.2f} s by the next one, dropped",
                      file=sys.stderr)
        out += [c for c in cards if c["end"] - c["start"] >= MIN_CARD_S]
    return sorted(out, key=lambda c: c["start"])


def _place(images, words, duration, hold, ent, box, aspect):
    cards, after = [], -1.0
    for im in images:
        target = clean(im["word"]).lower()
        hits = [w for w in words if clean(w["text"]).lower() == target]
        if im.get("nth"):
            hits = hits[im["nth"] - 1:im["nth"]]
        else:
            hits = [w for w in hits if w["start"] > after]
        if not hits:
            print(f"warning: '{im['word']}' is never said after the previous card, "
                  f"skipped {im.get('src') or im['anim']['type']}", file=sys.stderr)
            continue
        start = round(max(0.0, hits[0]["start"] - CARD_LEAD_S), 3)
        card = {"src": im["src"]} if "src" in im else {"anim": im["anim"]}
        if im.get("lane"):
            card["lane"] = im["lane"]
        for k in ("highlight", "size", "layout", "transition_in", "transition_out", "focus", "format", "props", "_own_box", "xh", "lines", "pics",
                  "heading"):
            if im.get(k):
                card[k] = im[k]
        if im.get("marks"):
            card["marks"] = json.loads(json.dumps(im["marks"]))
        kind = im.get("format") or (im.get("anim") or {}).get("type") or ("shot" if "src" in im else None)
        end = min(duration, start + (im.get("hold_s") or hold))
        if im.get("lane") == "logo":    # a logo in passing leaves when its sentence does
            i = words.index(hits[0])
            nxt = next((words[j + 1]["start"] for j in range(i, len(words) - 1) if ends_sentence(words[j]["text"])), None)
            end = min(end, nxt) if nxt is not None else end
        card.update({"start": start, "end": round(end, 3),
                     "_word_t": hits[0]["start"], "trigger_word": im["word"], "entrance": im.get("entrance") or ent or FORMAT_ENTRANCE.get(kind, "pop"),
                     "box": safe_box(im.get("box") or box or DEFAULT_BOX[aspect], aspect)})
        cards.append(card)
        after = start
    return cards


HEAD_GAP = 2           # % kept between a card and the head (a zoom punch grows the head a little)
MIN_CARD_H = 9         # a card squeezed shorter than this above the head is dropped instead


def head_during(heads, step, start, end):
    """Union of the head boxes sampled while a card is up, as (left, top, right, bottom)."""
    bs = [h["box"] for h in heads if h["box"] and start - step <= h["t"] <= end]
    if not bs:
        return None
    return (min(b[0] for b in bs), min(b[1] for b in bs),
            max(b[0] + b[2] for b in bs), max(b[1] + b[3] for b in bs))


def avoid_heads(cards, face, cap_y, aspect):
    """Keep every card off the speaker's head (face.json from face.py). A top card shrinks to
    the band above the head; a logo drops below the chin or moves beside or above the head. A card
    that cannot fit is dropped: covering the face is worse than losing the visual."""
    if not face:
        return cards
    l_safe, t_safe, r_safe, _ = SAFE[aspect]
    if aspect == "9:16":    # vertical cards keep the wider side margin on both sides, as check.py plan does
        l_safe = r_safe = max(l_safe, r_safe)
    out = []
    for c in cards:
        if (c.get("anim") or {}).get("type") == "logo_cluster":   # the whole frame, its logos placed round the head
            out.append(c)
            continue
        hd = head_during(face["heads"], face.get("step_s", 0.5), c["start"], c["end"])
        x, y, w, h = c["box"]
        if hd is None or not (x < hd[2] and x + w > hd[0] and y < hd[3] and y + h > hd[1]):
            out.append(c)
            continue
        left, top, right, bottom = hd
        new = None
        if (c.get("anim") or {}).get("type") == "logo" and h < 20 and not (c["anim"].get("props") or {}).get("card"):
            if bottom + HEAD_GAP + h <= cap_y - 1:
                new = [x, bottom + HEAD_GAP, w, h]
            elif max(bottom + HEAD_GAP, cap_y + 5) + h <= 100 - SAFE[aspect][3]:    # under the captions
                new = [x, max(bottom + HEAD_GAP, cap_y + 5), w, h]
            elif 100 - r_safe - (right + HEAD_GAP) >= w:
                new = [right + HEAD_GAP, (top + bottom - h) / 2, w, h]
            elif left - HEAD_GAP - l_safe >= w:
                new = [left - HEAD_GAP - w, (top + bottom - h) / 2, w, h]
            elif top - HEAD_GAP - h >= t_safe:
                new = [(left + right - w) / 2, top - HEAD_GAP - h, w, h]
        elif top - HEAD_GAP - y >= MIN_CARD_H:
            new = [x, y, w, top - HEAD_GAP - y]
        if new is None:
            print(f"warning: no room off the head for the '{c['trigger_word']}' card, dropped", file=sys.stderr)
            continue
        c["box"] = [round(v, 1) for v in new]
        out.append(c)
    return out


def clear_caption_paths(cards, cap_y, aspect):
    """A card that slides in (or out) from the top or bottom never crosses the caption band on the way: a card
    under the captions comes from and leaves to the bottom, one above them the top. The measured move is kept,
    only its side is turned (a slide down through the captions read as the card covering them)."""
    W, H = SIZES[aspect]
    lo, hi = cap_y - 5, cap_y + 5
    for c in cards:
        x, y, w, h = c.get("box") or (0, 0, 0, 0)
        p = (c.get("anim") or {}).get("props") if c.get("anim") else c.get("props")
        for key in ("enter", "exit"):
            f = (p or {}).get(key)
            if not f or f.get("kind") != "slide" or f.get("dir") not in ("top", "bottom"):
                continue
            d = (f.get("dist") or 5) * min(W, H) / H     # % of the frame's height
            top, bot = (y - d, y + h) if f["dir"] == "top" else (y, y + h + d)
            if top < hi and bot > lo and not (y < hi and y + h > lo):
                props(c)[key] = {**f, "dir": "bottom" if y >= hi else "top"}
    return cards


def free_regions(hd, cap_y, aspect):
    """The frame around the head, as boxes clear of the app's UI and the captions: above, left, right."""
    l, t, r, b = SAFE[aspect]
    top = OVERLAY_TOP if aspect == "9:16" else t       # overlays may use the top bar's margin: it holds only small text
    left, htop, right, hbot = hd
    floor = min(cap_y - 5, 100 - b) if aspect == "9:16" else 100 - b
    side = max(l, r) if aspect == "9:16" else 4      # vertical: the centred band inside the safe zone
    out = [[side, top, 100 - 2 * side, htop - HEAD_GAP - top]]
    if aspect == "9:16":
        out += [[OVERLAY_EDGE, htop, left - HEAD_GAP - OVERLAY_EDGE, floor - htop], [right + HEAD_GAP, htop, 100 - r - (right + HEAD_GAP), floor - htop]]
        # below the chin, over the body: where most talking-head creators put a photo when the face fills the top.
        # Two bands, never over the captions: chin to the captions, and the captions to the app's bottom UI.
        # Kept inside the side margins check.py plan holds: the right edge is under the like and comment buttons.
        side, chin = max(l, r), hbot + HEAD_GAP
        out += [[side, y0, 100 - 2 * side, y1 - y0] for y0, y1 in ((chin, cap_y - 5), (max(chin, cap_y + 5), 100 - b))]
    else:
        out += [[l, top, left - HEAD_GAP - l, floor - top], [right + HEAD_GAP, top, 100 - r - (right + HEAD_GAP), floor - top]]
    return [[round(v, 1) for v in bx] for bx in out if bx[2] >= 12 and bx[3] >= 9]


def content_aspect(c):
    a = c.get("anim") or {}
    p = {**(a.get("props") or {}), **(c.get("props") or {})}
    size = c.get("size") or p.get("size")
    if c.get("format") == "sticker" and p.get("crop"):
        return p["crop"][2] / p["crop"][3]
    if size:
        return size[0] / size[1] * (1.25 if c.get("format") == "browser" else 1)
    return ASPECT.get(a.get("type"), 1.6)


def sticker_area(c, aspect):
    """(w, h) frame px a sticker's picture may fill, as Overlays.tsx Sticker draws it: 98% of the box less its
    white edge each side, and less the source row when the card has a label or logo (sourceRow)."""
    W, H = SIZES[aspect]
    s = min(W, H) / 1080
    w, h = c["box"][2] / 100 * W, c["box"][3] / 100 * H
    p = c.get("props") or {}
    head = bool(p.get("label") or p.get("logo_src"))
    e = 22 * s if head else max(12 * s, min(w, h) / 100 * 1.6)
    return w * 0.98 - 2 * e, h * 0.98 - 2 * e - (60 * s if head else 0)


def sticker_xh(c, aspect):
    """The rendered x-height (px) of a sticker's text, from capture.mjs's "xh" (PNG px) and the fit
    Overlays.tsx Sticker uses: its crop (sticker_crop) in sticker_area."""
    aw, ah = sticker_area(c, aspect)
    iw, ih = sticker_crop(c)[2:]
    return c["xh"] * min(aw / iw, ah / ih)


XH_PER_LINE = 0.42     # a DOM line box is about 1.2 em tall and a Latin x-height about 0.5 em
CAPTION_LEADING = 1.14  # em, Captions.tsx lineHeight: a sticker cut from a page never sets its lines tighter
LINE_BOX_EM = 1.2
# ponytail: a crop cut to the evidence may show the capture up to 2 frame px per PNG px (a 2x capture's body text
# needs about 1.8 to read); soft but legible. Upgrade: re-shoot the crop at a higher deviceScaleFactor instead.
MAX_UP = 2.0


def evidence_lines(c, said=False):
    """The text lines (image px) a capture is shown for: those under its marks or highlight, else its largest
    type (the headline; [] with said=True: only words the speaker says count). Inside a sticker's crop only."""
    lines = [ln[:4] for ln in c.get("lines") or []]
    if c.get("format") == "sticker":
        x, y, w, h = sticker_crop(c)
        lines = [ln for ln in lines if ln[0] >= x - 1 and ln[1] >= y - 1 and ln[0] + ln[2] <= x + w + 1 and ln[1] + ln[3] <= y + h + 1]
    if not lines:
        return []
    iw, ih = c["size"]
    rects = [r for mk in c.get("marks") or [] for r in (mk.get("rects") or ([mk["rect"]] if mk.get("rect") else []))]
    rects += [[a * iw, b * ih, cw * iw, ch * ih] for a, b, cw, ch in (c.get("highlight") or {}).get("rects") or []]
    hit = [ln for ln in lines if any(r[0] - 4 <= ln[0] + ln[2] / 2 <= r[0] + r[2] + 4 and r[1] - 4 <= ln[1] + ln[3] / 2 <= r[1] + r[3] + 4
                                     for r in rects)]
    if hit or said:
        return hit
    top = max(ln[3] for ln in lines)
    return [ln for ln in lines if ln[3] >= 0.85 * top]


def capture_scale(c, aspect):
    """Frame px per image px of a capture card as Overlays.tsx draws it in its box (no push-in counted)."""
    W, H = SIZES[aspect]
    w, h = c["box"][2] / 100 * W, c["box"][3] / 100 * H
    iw, ih = c["size"]
    f = c.get("format") or "shot"
    if f == "sticker":
        aw, ah = sticker_area(c, aspect)
        cw, ch = sticker_crop(c)[2:]
        return min(aw / cw, ah / ch)
    if f == "browser":
        bar = max(28, h * 0.09)
        bw, vh = min(w * 0.96, (h * 0.94 - bar) * 1.7), h * 0.94 - bar
        follows = c.get("marks") or c.get("highlight") or ih / iw > vh / bw * 1.6
        return bw / iw if follows else min(bw / iw, vh / ih)
    return min(w * 0.96 / iw, h * 0.92 / ih)


PICTURE_SHARE = 0.5   # a capture this much picture (a book cover, a product photo) is shown for the picture


def picture_share(c):
    """The share of a capture's PNG that its pictures cover (capture.mjs "pics", overlaps counted once per row
    of 10 px), 0-1."""
    iw, ih = c.get("size") or (0, 0)
    if not c.get("pics") or not iw or not ih:
        return 0.0
    covered = 0
    for y in range(0, int(ih), 10):
        spans = sorted((p[0], p[0] + p[2]) for p in c["pics"] if p[1] <= y < p[1] + p[3])
        end = 0
        for a, b in spans:
            covered += max(0, b - max(a, end)) * 10
            end = max(end, b)
    return min(1.0, covered / (iw * ih))


def capture_xh(c, aspect):
    """The rendered x-height (px on a 1080-wide frame) of a capture card's evidence text, from its DOM line
    boxes; None when it has none. A capture.mjs sticker's own measured "xh" wins."""
    if c.get("format") == "sticker" and c.get("xh") and c.get("size"):
        return sticker_xh(c, aspect) * 1080 / min(SIZES[aspect])
    if not c.get("size") or c.get("format") == "plain" or picture_share(c) >= PICTURE_SHARE:
        return None
    ev = evidence_lines(c)
    if not ev:
        return None
    hl = sorted(ln[3] for ln in ev)[len(ev) // 2]
    return XH_PER_LINE * hl * capture_scale(c, aspect) * 1080 / min(SIZES[aspect])


def small_lines(c, aspect):
    """The text lines inside a sticker's crop (one cut from a shot: capture.mjs's own stickers carry "xh") that
    render under READ_XH x-height: a kicker or footnote too small to read beside the evidence."""
    if c.get("format") != "sticker" or c.get("xh") or not c.get("lines") or not c.get("size") or not c.get("box"):
        return []
    x, y, w, h = sticker_crop(c)
    k = capture_scale(c, aspect) * 1080 / min(SIZES[aspect])
    return [ln[:4] for ln in c["lines"] if ln[0] >= x - 1 and ln[1] >= y - 1 and ln[0] + ln[2] <= x + w + 1
            and ln[1] + ln[3] <= y + h + 1 and XH_PER_LINE * ln[3] * k < READ_XH]


def tight(ln, lines):
    """Whether a text line (image px) has a neighbour above or below it closer than the captions' leading."""
    return any(o[:4] != ln[:4] and o[0] < ln[0] + ln[2] and ln[0] < o[0] + o[2]
               and 0 < abs(o[1] - ln[1]) < CAPTION_LEADING / LINE_BOX_EM * max(o[3], ln[3]) for o in lines)


def readable_captures(cards, aspect, pictures=False):
    """On vertical a capture whose evidence would render under READ_XH becomes a sticker cropped to that
    evidence: the crop takes the band's shape around the evidence's first lines (as many as still read) at the
    largest size that holds them (at most MAX_UP frame px per picture px), every line whole. The evidence is the
    words the speaker says, marked on the page ("find" / "highlight"): with none marked, or marked words set
    tighter than the captions, the card is dropped (never a sticker of the page's own headline, never lines that
    touch). One that still reads small is left for check.py to FAIL."""
    if aspect != "9:16" or pictures:   # pictures_only: a screenshot stays a screenshot
        return cards
    W, H = SIZES[aspect]
    keep = []
    for c in cards:
        keep.append(c)
        if c.get("layout") == "scene" or not c.get("src") or c.get("format") in ("sticker", "plain") or not c.get("lines"):
            continue
        xh = capture_xh(c, aspect)
        if xh is None or xh >= READ_XH:
            continue
        ev = sorted(evidence_lines(c, said=True), key=lambda ln: (ln[1], ln[0]))
        if not ev:
            keep.pop()
            print(f"warning: '{c['trigger_word']}' {c['src']}: dropped. Its text would read at {xh:.0f} px x-height "
                  f"(under {READ_XH}) and no words the speaker says are marked on the page to cut it to. To keep it, "
                  "give the capture beat \"format\": \"sticker\" and a mark whose \"find\" is a phrase said there, re-run capture.mjs and plan.py",
                  file=sys.stderr)
            continue
        aw, ah = sticker_area(c, aspect)   # the crop becomes a sticker: drawn in that area
        unit = 1080 / min(W, H)

        def fit(group):
            gx0, gy0 = min(ln[0] for ln in group), min(ln[1] for ln in group)
            gx1, gy1 = max(ln[0] + ln[2] for ln in group), max(ln[1] + ln[3] for ln in group)
            pad = 0.25 * min(ln[3] for ln in group)
            f = min(MAX_UP, aw / (gx1 - gx0 + 2 * pad), ah / (gy1 - gy0 + 2 * pad))
            return f, (gx0, gy0, gx1, gy1), XH_PER_LINE * sorted(ln[3] for ln in group)[len(group) // 2] * f * unit

        # a headline set tighter than the captions has its letters touch once it stands alone on a card, and a
        # crop of the picture cannot open its lines up: only a sticker beat re-sets the sentence (capture.mjs)
        if tight(ev[0], c["lines"]):
            keep.pop()
            print(f"warning: '{c['trigger_word']}' {c['src']}: dropped. Its text would read at {xh:.0f} px x-height "
                  f"(under {READ_XH}) and the marked words are set tighter than the captions ({CAPTION_LEADING} line height), "
                  "so a crop would show their lines touching. To keep it, give the beat \"format\": \"sticker\" (capture.mjs "
                  "re-sets the sentence with open lines), re-run capture.mjs and plan.py", file=sys.stderr)
            continue
        # the evidence from its first line on, as many lines as still read at READ_XH
        group = ev[:1]
        for ln in ev[1:]:
            if fit(group + [ln])[2] < READ_XH:
                break
            group.append(ln)
        f, (x0, y0, x1, y1), _ = fit(group)
        iw, ih = c["size"]
        cw, ch = min(iw, aw / f), min(ih, ah / f)
        cx = min(max((x0 + x1) / 2, cw / 2), iw - cw / 2)
        cy = min(max((y0 + y1) / 2, ch / 2), ih - ch / 2)
        new = {**c, "format": "sticker", "props": {k: v for k, v in (c.get("props") or {}).items() if k != "url"}}
        new["props"]["crop"] = whole_lines([cx - cw / 2, cy - ch / 2, cw, ch], c["lines"], c["size"])
        # a kicker or footnote above or below the evidence that would read under READ_XH is left out of the
        # crop (the card hugs it), never shown too small to read
        ours = [ln[:4] for ln in group]
        for ln in small_lines(new, aspect):
            x, y, w, h = new["props"]["crop"]
            if ln in ours:
                continue
            top, bot = (max(y, ln[1] + ln[3]), y + h) if ln[1] + ln[3] <= y0 else (y, min(y + h, ln[1]))
            new["props"]["crop"] = [x, round(top), w, round(bot - top)]
        got = capture_xh(new, aspect)
        if got and got > xh:
            print(f"'{c['trigger_word']}' {c['src']}: its {c.get('format') or 'shot'} text would read at {xh:.0f} px x-height, "
                  f"so plan.py cut it to the marked words ({len(group)} line(s)) as a sticker: {got:.0f} px", file=sys.stderr)
            c.clear()
            c.update(new)
    return keep


def heat(gl, bx):
    """How much the creator's graphics sat in box bx (% of the frame), 0-1: the mean of her layout grid over
    it (graphics.layout.grid, seconds of cover per cell, 0-100), else her zone share (zones_pct)."""
    grid = gl.get("grid")
    if grid:
        gh, gw = len(grid), len(grid[0])
        r0, c0 = int(bx[1] / 100 * gh), int(bx[0] / 100 * gw)
        r1, c1 = max(r0 + 1, math.ceil((bx[1] + bx[3]) / 100 * gh)), max(c0 + 1, math.ceil((bx[0] + bx[2]) / 100 * gw))
        cells = [grid[r][c] for r in range(r0, min(r1, gh)) for c in range(c0, min(c1, gw))]
        return sum(cells) / len(cells) / 100 if cells else 0
    cy = bx[1] + bx[3] / 2
    z = "full" if bx[2] * bx[3] >= 6000 else "top" if cy < 38 else "bottom" if cy > 62 else "middle"
    return (gl.get("zones_pct") or {}).get(z, 0) / 100


HEAT_FLOOR = 0.25      # a region she never used still scores this much of its area: her heat leans, never forbids


def place_overlays(cards, face, cap_y, aspect, prefer=None):
    """Overlay cards (captures, overlay formats, social posts) go to the free region around the head that
    their picture fills best. logo_cluster takes the whole frame and is told where the head is. A card with
    its own box, and the small fixed ones (logo tile, lower third, arrow, caption page), keep their box.
    prefer: the creator's graphics.layout; each region's area is weighted by where her graphics sat (heat).
    The regions are the same free ones either way: never the head, never under the app's UI."""
    W, H = SIZES[aspect]
    out = []
    for c in cards:
        t = (c.get("anim") or {}).get("type")
        hd = face and head_during(face["heads"], face.get("step_s", 0.5), c["start"], c["end"])
        if t == "logo_cluster":
            c["box"] = [0, 0, 100, 100]
            if hd:
                c["anim"]["props"]["head"] = [round(hd[0], 1), round(hd[1], 1), round(hd[2] - hd[0], 1), round(hd[3] - hd[1], 1)]
            if aspect == "9:16":    # readable logos spread over a band centred on the frame, not round the head
                c["anim"]["props"].setdefault("band", list(LOGO_BAND))
                c["anim"]["props"].setdefault("size", LOGO_SIZE)
            out.append(c)
            continue
        if c.get("lane") == "logo" or t in FIXED_BOX or c.get("_own_box") or not hd:
            if not hd and aspect == "9:16" and c.get("src") and not c.get("_own_box") and c.get("lane") != "logo":
                m = max(SAFE[aspect][0], SAFE[aspect][2])   # no head found: a capture takes the band above where it would be
                c["box"] = [m, OVERLAY_TOP, 100 - 2 * m, c["box"][3]]
            out.append(c)
            continue
        ar = content_aspect(c)

        def area(bx):
            bw, bh = bx[2] / 100 * W, bx[3] / 100 * H
            a = min(bw, bh * ar) * min(bh, bw / ar)
            return a * (HEAT_FLOOR + heat(prefer, bx)) if prefer else a
        regions = free_regions(hd, cap_y, aspect)
        if aspect == "9:16":   # check.py plan FAILs a vertical card off centre: the band above the head first
            regions = [r for r in regions if abs(r[0] + r[2] / 2 - 50) <= 1.5] or regions
        if not regions:
            print(f"warning: no room around the head for the '{c['trigger_word']}' card, dropped", file=sys.stderr)
            continue
        c["box"] = max(regions, key=area)
        out.append(c)
    return out


# Cards behind the speaker (references/motion.md "Behind the speaker"): these formats sit above the
# footage and under the speaker's cutout (matte.py), so a card may tuck behind the hair and grow.
# the moving cards tuck behind the hair too, so they fill the band down to the hairline (references/motion-design.md)
BEHIND = ("shot", "sticker", "logo_cluster", "social_post", "browser", "chat", "terminal", "toasts", "side_by_side",
          "likes", "progress", "curve", "notes")
BEHIND_TUCK = 0.4      # a behind card reaches at most this far down the head (share of the head's height)
FILL = 0.92            # an overlay's picture fills about this much of its box (Overlays.tsx fitBox)


def kind_of(c):
    return c.get("format") or (c.get("anim") or {}).get("type") or ("shot" if c.get("src") else None)


def content_rect(c, box, aspect):
    """Where the picture lands in the box, % of the frame: fitted at its aspect, centred."""
    W, H = SIZES[aspect]
    x, y, w, h = box
    bw, bh, ar = w / 100 * W * FILL, h / 100 * H * FILL, content_aspect(c)
    cw, ch = (bw, bw / ar) if ar > bw / bh else (bh * ar, bh)
    return [x + (w - cw / W * 100) / 2, y + (h - ch / H * 100) / 2, cw / W * 100, ch / H * 100]


def key_rect(c, content):
    """What must stay in view, % of the frame: the marks (grown by the shot's push-in), else the
    picture less its bottom fifth (a post's stats row, a page's foot), or for a screenshot with no mark its top
    three fifths (an app window reads from its top; the hair may cross the rest, as the band is filled)."""
    x, y, w, h = content
    p = {**((c.get("anim") or {}).get("props") or {}), **(c.get("props") or {})}
    marks = c.get("marks") or p.get("marks") or []
    size = c.get("size") or p.get("size")
    if not (marks and size):
        return [x, y, w, h * (0.6 if kind_of(c) == "shot" else 0.8)]
    ox, oy, iw, ih = p.get("crop") or [0, 0, *size]
    z = (p.get("zoom") or 1.45) if kind_of(c) == "shot" else 1
    rs = [r for mk in marks for r in [mk["rect"]] + (mk.get("rects") or [])]
    l, t = min(r[0] for r in rs), min(r[1] for r in rs)
    r_, b = max(r[0] + r[2] for r in rs), max(r[1] + r[3] for r in rs)
    cx, cy, hw, hh = (l + r_) / 2, (t + b) / 2, (r_ - l) / 2 * z, (b - t) / 2 * z
    fx = lambda v: x + max(0, min(1, (v - ox) / iw)) * w
    fy = lambda v: y + max(0, min(1, (v - oy) / ih)) * h
    return [fx(cx - hw), fy(cy - hh), fx(cx + hw) - fx(cx - hw), fy(cy + hh) - fy(cy - hh)]


def tuck_behind(cards, face, aspect):
    """Behind formats get "layer": "behind". A card above the head grows down behind the hair, as far
    as BEHIND_TUCK of the head, keeping its key region (marks, or the post's text) clear of the head;
    "key" is written for matte.py to check against the real cutout."""
    hit = lambda a, hd: a[0] < hd[2] + HEAD_GAP and a[0] + a[2] > hd[0] - HEAD_GAP and a[1] < hd[3] + HEAD_GAP and a[1] + a[3] > hd[1] - HEAD_GAP
    for c in cards:
        clip = ((c.get("anim") or {}).get("props") or {}).get("motion")   # a motion skill clip tucks like a card
        if (kind_of(c) not in BEHIND and not clip) or c.get("layout") == "scene":
            continue
        c["layer"] = "behind"
        hd = face and head_during(face["heads"], face.get("step_s", 0.5), c["start"], c["end"])
        if kind_of(c) == "logo_cluster" or not hd:
            continue
        x, y, w, h = c["box"]
        if y + h > hd[1]:       # beside the head, not above it: stays as placed
            c["key"] = [round(v, 1) for v in key_rect(c, content_rect(c, c["box"], aspect))]
            continue
        best = c["box"]
        steps = 20
        for i in range(steps, -1, -1):
            box = [x, y, w, hd[1] + BEHIND_TUCK * (hd[3] - hd[1]) * i / steps - y]
            if not hit(key_rect(c, content_rect(c, box, aspect)), hd):
                best = box
                break
        c["box"] = [round(v, 1) for v in best]
        c["key"] = [round(v, 1) for v in key_rect(c, content_rect(c, c["box"], aspect))]
    return cards


SFX_GAP_S = 0.25       # never two cues closer than this
SFX_EVERY_S = 5.0      # at most one cue per this many seconds, on average: most cards land silent (ai-tells.md)
SFX_RANK = ("impact", "hit", "whoosh-in", "whoosh-out", "pop", "zoom")   # who keeps its slot when cues crowd


# sound.kinds (sound.py) -> the kit's cues that sound like them
SOUND_CUES = {"whoosh": ("whoosh-in", "whoosh-out"), "pop": ("pop",), "click": ("pop",), "ding": ("pop",),
              "impact": ("impact",), "riser": ("hit",), "other": SFX_RANK[1:]}


def place_sfx(plan, words, kit, sound=None):
    """Sound cues for a few of the plan's visual events, about one per SFX_EVERY_S: a card that slides
    in gets whoosh-in, one that pops (a logo, a sticker) a pop, a scene's tag the soft hit,
    a card that scales or fades in lands silent; a scene part lands on its word (pop), a zoom starts
    (zoom). No exit whooshes, and never the same cue twice in a row. A cue starts its attack early so
    its hit is heard on the event. kit: sfx.py's kit.json.
    sound: the creator's measured style.json "sound". Its sfx_per_min sets the budget (0 is allowed: she
    uses none), its kinds keep only the cues that sound like hers, on_graphic_pct / on_cut_pct 0 drop the
    card / zoom cues."""
    words = [w for w in words if w.get("type", "word") == "word" and w["text"].strip()]
    ev = []

    def parts(node, key, start):
        if isinstance(node, list):
            for x in node:
                parts(x, key, start)
        elif isinstance(node, dict):
            if "at" in node and key != "label":   # a label swapping its text stays quiet
                ev.append((start + node["at"], "hit" if key == "tag" else "pop"))
            for k, v in node.items():
                parts(v, k, start)

    def mid_sentence(t):
        before = [w for w in words if w["end"] <= t + 0.05]
        return bool(before) and t - before[-1]["end"] < PAUSE_S and not ends_sentence(before[-1]["text"]) \
            and any(0 <= w["start"] - t < PAUSE_S for w in words)

    ev += [(t, n) for t, n in (plan.get("layout") or {}).get("cues", [])]   # the board's camera moves and tile landings
    for c in plan["cards"]:
        kind = (c.get("anim") or {}).get("type")
        lands = c["start"] + CARD_LEAD_S
        logo = kind in ("logo", "logo_sting")
        ent = c.get("entrance", "slide")
        cue = "pop" if logo or ent == "pop" else "whoosh-in" if ent == "slide" else None
        if c.get("scene_by") == "creator":
            cue = "hit"   # her cut-away is a cut: her cues sit on cuts (sound.on_cut_pct)
        if cue:
            ev.append((lands, cue))
        parts((c.get("anim") or {}).get("props"), None, c["start"])
    ev += [(z["start"], "zoom") for z in plan["zooms"]]

    duration = plan["durationInFrames"] / plan["fps"]
    budget = max(1, int(duration / SFX_EVERY_S))
    sound = sound or {}
    if sound.get("sfx_per_min") is not None:
        budget = round(duration / 60 * sound["sfx_per_min"])
    if (sound.get("kinds") or {}).get("impact", 0) >= max((sound.get("kinds") or {"": 1}).values()):
        # her cues are mostly impacts (a low boom on a cut): the scene cut and the zoom take the kit's impact
        ev = [(t, "impact" if n in ("hit", "zoom") else n) for t, n in ev]
    if sound.get("kinds"):
        ok = {c for k, v in sound["kinds"].items() if v > 0 for c in SOUND_CUES.get(k, ())}
        ev = [e for e in ev if e[1] in ok]
    if sound.get("on_graphic_pct") == 0 and sound.get("on_cut_pct") == 0:
        ev = []   # all of hers sit inside the voice, on nothing the edit draws
    elif sound.get("on_graphic_pct") == 0:
        ev = [e for e in ev if e[1] == "zoom"]
    elif sound.get("on_cut_pct") == 0:
        ev = [e for e in ev if e[1] != "zoom"]
    kept = []
    # ponytail: rank-then-time greedy, so a crowded video loses its LATER low-rank cues first;
    # spread the budget over time if that ever reads lopsided.
    for t, name in sorted(ev, key=lambda e: (SFX_RANK.index(e[1]), e[0])):
        if name in kit["cues"] and len(kept) < budget and 0 <= t < duration \
                and all(abs(t - k) >= SFX_GAP_S for k, _ in kept):
            kept.append((t, name))
    if not sound.get("kinds"):   # never the same cue twice running, unless her measured mix repeats them itself
        kept = [k for i, k in enumerate(sorted(kept)) if i == 0 or k[1] != sorted(kept)[i - 1][1]]
    # on the frame Sfx.tsx starts it on (round(t x fps)): the plan's t is when the cue really plays
    fps = plan["fps"]
    return [{"t": round(round(max(0.0, t - kit["cues"][n]["attack_s"]) * fps) / fps, 4), "src": f".sfx/{n}.wav", "event": round(t, 3)}
            for t, n in kept]


def with_sfx(build):
    """Adds plan["sfx"] (place_sfx) to build()'s plan. Off when style.json has "sfx": false or
    there is no edit folder (sfx.py level-matches the kit to the folder's cut.mp4)."""
    sig = inspect.signature(build)

    def wrap(*a, **k):
        plan = build(*a, **k)
        v = sig.bind(*a, **k)
        v.apply_defaults()
        style, edit_dir = v.arguments["style"], v.arguments["edit_dir"]
        if style.get("sfx", True) is False or not edit_dir:
            plan["sfx"] = []
            return plan
        import sfx
        plan["sfx"] = place_sfx(plan, v.arguments["words"], sfx.kit(edit_dir), style.get("sound") if took(style, "sound") else None)
        return plan
    return wrap


# Split layout: the visual owns a top panel, the speaker a window under the seam. In percent of the frame.
SPLIT = {"seam": 50, "ground": "#F4F4F2"}
CUTOUT_BREAKOUT = 10.6  # 50/50 cutout: the speaker's head rises this far (% of the frame) above the window's top edge
SPLIT_GAP = 2          # art stops this far above the seam
SPLIT_CAP_BELOW = 4.5  # captions sit this far under the seam, over the top of the speaker's window
HEAD_ROOM = 4          # the top of the head (hair included) sits this far into the window
MIN_HEAD = 22          # a head shorter than this is scaled up to it, so a face is never tiny
MAX_SPEAKER_SCALE = 1.6
PANEL_T = 0.3          # the panel opens this long before a card lands (StyleEdit.tsx PANEL_T)
SPLIT_LOGO_S = 1.5     # a logo alone in the panel stays at least this long


def split_art_box(seam):
    """The part of the top panel clear of the app's UI and the seam: every split card fills it."""
    l, t, r, _ = SAFE["9:16"]
    m = max(l, r)       # equal side margins: the art is centred on the frame
    return [m, t, 100 - 2 * m, seam - SPLIT_GAP - t]


def speaker_frame(face, seam, head_room=HEAD_ROOM):
    """How the cut sits in the window under the seam: scaled so the head is at least MIN_HEAD tall,
    moved so the hair sits HEAD_ROOM below the window's top and the head is centred left to right.
    x, y: how far the scaled video's top-left is pulled left and up, in % of the frame. origin: the
    head's centre on the video, for zooms."""
    win = 100 - seam
    bs = sorted((h["box"] for h in (face or {}).get("heads", []) if h["box"]), key=lambda b: b[1])
    if not bs:
        return {"scale": 1, "x": 0, "y": round(seam / 2, 1), "origin": [50, 40]}
    q = lambda xs, f: sorted(xs)[min(len(xs) - 1, int(f * len(xs)))]
    top = q([b[1] for b in bs], 0.1)                  # the highest the head goes, near enough
    bottom = q([b[1] + b[3] for b in bs], 0.9)
    cx = q([b[0] + b[2] / 2 for b in bs], 0.5)
    k = min(max(1, MIN_HEAD / max(1, bottom - top)), MAX_SPEAKER_SCALE)
    y = min(max(0, k * top - head_room), k * 100 - win)
    x = min(max(0, k * cx - 50), k * 100 - 100)
    if k * bottom - y > win:
        print("warning: the head is taller than the split window; the chin is cut off", file=sys.stderr)
    return {"scale": round(k, 3), "x": round(x, 1), "y": round(y, 1), "origin": [round(cx, 1), round((top + bottom) / 2, 1)]}


FACE_GAP_S = 1.5      # a face beat between two panel runs: long enough for the panel to close and open (2 x PANEL_T + a hold)
BRIDGE_S = 1.2        # StyleEdit.tsx: the panel stays open across a gap this short


def face_every(cards, max_run):
    """The 50/50 rule (layout.face_every_s): the speaker's face has the whole frame again within max_run seconds of the
    panel opening. A card that would keep the panel open past it starts FACE_GAP_S after the run ends instead, or is
    dropped when that leaves it under MIN_CARD_S."""
    out, run0, run1 = [], None, None
    for c in sorted(cards, key=lambda c: c["start"]):
        if run1 is not None and c["start"] - run1 < BRIDGE_S and c["end"] - run0 > max_run:
            start = round(run1 + FACE_GAP_S, 3)
            if c["end"] - start < MIN_CARD_S:
                print(f"warning: '{c.get('trigger_word')}' card dropped: the face comes back within {max_run:g} s "
                      "(layout.face_every_s)", file=sys.stderr)
                continue
            c = {**c, "start": start}
        if run1 is None or c["start"] - run1 >= BRIDGE_S:
            run0 = c["start"]
        run1 = max(run1 or 0, c["end"])
        out.append(c)
    for a, b in zip(out, out[1:]):   # the panel is never open and empty: a card holds until the next lands
        if 0 < b["start"] - a["end"] < BRIDGE_S:
            a["end"] = b["start"]
    return out


# Board layout (the Motion design sample style, 16:9): one dark canvas a camera drags across. Logos become tiles
# landing on their words under a heading in the speaker's words; a question asked becomes a heading that first sits
# centred and then rises as the camera pans down; every other card is an overlay on the speaker's footage, the
# sides alternating and the speaker reframed to the other side. Units: px of a 1920x1080 frame.
BOARD_GAP_S = 4.0      # a tile this long after the last one starts a new board
BOARD_MAX_TILES = 4    # one idea in view: a fifth tile starts a new board
BOARD_HOLD_S = 2.5     # a board stays this long after its last tile lands
BOARD_LEAD_S = 3.0     # a board starts on the sentence that names it, at most this long before its first tile
BOARD_BRIDGE_S = 1.5   # boards closer than this: the camera drags straight across, no speaker in between
BOARD_DRAG_S = 1.0     # one camera move
BOARD_FADE_S = 0.6     # speaker <-> canvas crossfade (Board.tsx); the camera never flies over the speaker
BOARD_HEAD_WORDS = 6   # a heading is one line of their words
BOARD_Q_WORDS = 14     # a question keeps every word (Board.tsx shrinks it to fit one line)
BOARD_Q_LEAD_S = 2.5   # a board whose first tile is said this soon after a question rises into it (one said inside it: no rise)
BOARD_Q_GAP_S = 6.0    # a question with no board this soon after the last one shown stays with the speaker
Q_WORDS = {"what", "why", "how", "when", "where", "which", "who", "can", "could", "should", "would", "will", "do",
           "does", "did", "is", "are", "was", "have", "has"}   # a question starts with one of these
BOARD_Q_RISE = 402     # the question sits this far below the heading spot (the frame's middle), then rises
BOARD_STEP = (2400, 1350)   # board i sits at (STEP x (i % 2), STEP y x i) on the canvas: right, down, left, down
BOARD_OVERLAY_BOX = ([5, 14, 42, 60], [53, 14, 42, 60])   # % of the frame, left and right, off the frame edge
BOARD_REFRAME_S = 5.0  # the speaker's framing changes at least this often while they hold the frame
BOARD_FACE = {"rest": 1.1, "push": 1.18, "side": 1.3, "max": 1.5}   # the speaker's zoom: between beats, a slow push, beside an overlay


def board_heading(ws, t0):
    """Heading words -> [[word, time it types on]]: its own time, or arrival + 0.1 s a word when said before the board."""
    return [[clean(w["text"]).lower(), round(max(w["start"], t0 + 0.1 * i), 3)] for i, w in enumerate(ws)]


def board_words(words, first, phrase=None):
    """The words a board's heading is made of: the beat's own "heading" (their words, found in order around the first
    tile), else the BOARD_HEAD_WORDS of the sentence that end on the first tile's word."""
    if phrase:
        want, out = [clean(x).lower() for x in phrase.split() if clean(x)], []
        for w in words:
            if len(out) < len(want) and first - 8 <= w["start"] < first + 4 and clean(w["text"]).lower() == want[len(out)]:
                out.append(w)
        if len(out) == len(want):
            return out
        print(f"warning: heading '{phrase}' is not said in that order near {first:.1f} s; using the sentence instead", file=sys.stderr)
    a = board_sentence(words, first + CARD_LEAD_S)[0]
    ws = [w for w in words if a - 0.05 <= w["start"] <= first + CARD_LEAD_S + 0.05 and clean(w["text"])]
    return ws[-BOARD_HEAD_WORDS:]


def board_sentence(words, t):
    """[start, end, words] of the sentence being said at t."""
    i = max((k for k, w in enumerate(words) if w["start"] <= t + 0.05), default=0)
    a = i
    while a > 0 and not ends_sentence(words[a - 1]["text"]):
        a -= 1
    b = i
    while b < len(words) - 1 and not ends_sentence(words[b]["text"]):
        b += 1
    return words[a]["start"], words[b]["end"], words[a:b + 1]


def board_tiles(c, words, edit_dir):
    """The logo tiles a card turns into: [{src, label, at}], or [] for a card that stays an overlay. A logo is one
    tile; a logo_cluster or a flow one per logo, each on its own word."""
    a = c.get("anim") or {}
    p = a.get("props") or {}
    if a.get("type") == "logo" and p.get("src"):
        return [{"src": p["src"], "label": clean(c.get("trigger_word") or "").lower(), "at": round(c["start"], 3),
                 **({"heading": c["heading"]} if c.get("heading") else {})}]
    nodes = p.get("logos") if a.get("type") == "logo_cluster" else p.get("nodes") if a.get("type") == "flow" else None
    out = []
    for i, n in enumerate(nodes or []):
        if not isinstance(n, dict):
            continue
        src = n.get("src") or (resolve_src(n, edit_dir) if n.get("logo") else None)
        if not src:
            continue
        said = clean(n.get("word") or n.get("label") or n.get("logo") or "").lower()
        hit = next((w for w in words if clean(w["text"]).lower() == said and w["start"] >= c["start"] - 0.3), None)
        at = hit["start"] - CARD_LEAD_S if hit else c["start"] + 0.4 * i
        out.append({"src": src, "label": clean(n.get("label") or n.get("word") or n.get("logo") or "").lower(), "at": round(at, 3),
                    **({"heading": c["heading"]} if c.get("heading") else {})})
    return out


def board_layout(cards, words, duration, face, edit_dir=None):
    """The board layout (references/contracts.md "board"): logos -> tiles on boards, questions -> headings that rise or
    centred lines over the speaker, the rest -> overlays on alternating sides. Returns (overlay cards, layout)."""
    tiles, rest = [], []
    for c in sorted(cards, key=lambda c: c["start"]):
        ts = board_tiles(c, words, edit_dir)
        (tiles.extend(sorted(ts, key=lambda x: x["at"])) if ts else rest.append(c))
    groups = []
    for t in sorted(tiles, key=lambda x: x["at"]):
        g = groups[-1] if groups else None
        if g and t["at"] - g[-1]["at"] < BOARD_GAP_S and len(g) < BOARD_MAX_TILES:
            if t["src"] not in [x["src"] for x in g]:   # one tile a brand on a board
                g.append(t)
        else:
            groups.append([t])
    sents, cur = [], []
    for w in words:
        cur.append(w)
        if ends_sentence(w["text"]):
            sents, cur = sents + [cur], []
    qs = []   # a question: the clause that ends in "?" ("so now you know, but when should you ...?" -> "when should ...?")
    for st in sents + [cur]:
        if st and st[-1]["text"].rstrip().endswith("?"):
            cut = max((i + 1 for i, w in enumerate(st[:-1]) if ends_clause(w["text"]) and len(st) - i - 1 >= 3), default=0)
            st = [w for w in st[cut:] if clean(w["text"])]
            while st and clean(st[0]["text"]).lower() in DANGLING:   # "but when should you ..." -> "when should you ..."
                st = st[1:]
            if len(st) > BOARD_Q_WORDS:   # "... to decide is can you write down every answer?" -> "can you write down ..."
                st = st[next((i for i in range(len(st) - BOARD_Q_WORDS, len(st) - 2) if clean(st[i]["text"]).lower() in Q_WORDS), 0):]
            if 3 <= len(st) <= BOARD_Q_WORDS and clean(st[0]["text"]).lower() in Q_WORDS:   # "yes or no?" is not one
                qs.append({"start": st[0]["start"], "end": st[-1]["end"], "words": st})
    boards, prev_end = [], 0.0
    for k, g in enumerate(groups):
        first = g[0]["at"]
        q = None if g[0].get("heading") else \
            next((q for q in qs if q["end"] - 0.5 <= first <= q["end"] + BOARD_Q_LEAD_S and q["start"] >= prev_end), None)
        if q:   # the whole question is the heading, never cut
            start = max(prev_end, q["start"] - 0.2)
            heading = board_heading([w for w in q["words"] if clean(w["text"])][:BOARD_Q_WORDS], start)
            qs.remove(q)
        else:   # the board arrives on its heading's first word: never an empty board
            inq = next((q for q in qs if q["start"] <= first < q["end"] - 0.5), None)   # named inside a question: its heading
            hw = inq["words"] if inq and not g[0].get("heading") else board_words(words, first, g[0].get("heading"))
            start = max(prev_end, first - BOARD_LEAD_S, min(first - 0.3, hw[0]["start"] if hw else first))
            heading = board_heading(hw, start)
        nxt = min([groups[k + 1][0]["at"] if k + 1 < len(groups) else duration] +   # the next board, or an overlay after it
                  [c["start"] for c in rest if c["start"] > g[-1]["at"] + 0.5])
        end = min(max(g[-1]["at"] + BOARD_HOLD_S, start + 3.0), nxt - 0.5, duration)
        start = max(start, min(first - 0.3, max([c["end"] + 0.3 for c in rest if c["start"] < first], default=0)))   # after an overlay
        bd = {"start": round(start, 3), "end": round(end, 3), "x": BOARD_STEP[0] * (k % 2), "y": BOARD_STEP[1] * k,
              "heading": heading, "tiles": g, **({"question": True, "rise": round(max(start + 0.6, first - 0.9), 3)} if q else {})}
        boards.append(bd)
        prev_end = end
    # the camera: [at, centre x, centre y, zoom, move seconds]; views: when the canvas has the frame
    cam, views, cues = [], [], []
    for k, bd in enumerate(boards):
        cx, cy = bd["x"] + 960, bd["y"] + 540
        y0 = cy - BOARD_Q_RISE if bd.get("question") else cy
        if views and bd["start"] - views[-1][1] < BOARD_BRIDGE_S:   # drag straight across from the last board
            views[-1][1] = bd["end"]
            cam.append([bd["start"], cx, y0, 1, BOARD_DRAG_S])
        else:   # the canvas fades in over the speaker while the camera is already dragging in from the side
            views.append([bd["start"], bd["end"]])
            cam += [[bd["start"], cx + 350, y0, 1, 0.01], [bd["start"], cx, y0, 1, BOARD_DRAG_S]]
        if not any(n == "whoosh-in" and bd["start"] - t < 30 for t, n in cues):   # two whooshes a minute at most
            cues.append([bd["start"], "whoosh-in"])
        if bd.get("question"):
            cam.append([bd["rise"], cx, cy, 1, max(0.4, min(0.9, bd["tiles"][0]["at"] - bd["rise"]))])
            cues.append([bd["rise"], "zoom"])   # the pan down: a short rise into a soft thump
        cues += [[t["at"] + CARD_LEAD_S, "pop"] for t in bd["tiles"]]
    up = lambda a, b: any(v[0] - 0.3 < b and a < v[1] for v in views)   # noqa: E731
    over, side = [], 0
    for c in rest:
        if up(c["start"], c["end"]):
            print(f"warning: the '{c.get('trigger_word')}' card falls while a board is up, dropped: the board is the "
                  "visual there", file=sys.stderr)
            continue
        c = {**c, "box": list(BOARD_OVERLAY_BOX[side]), "lane": None, "side": "left" if side == 0 else "right"}
        c.pop("layout", None)   # a full-frame scene becomes an overlay: the canvas is the only full-frame visual
        over.append(c)
        side = 1 - side
    lone, last = [], -99.0   # questions with no board after them: centred over the speaker, never over an overlay
    for q in qs:
        if up(q["start"], q["end"]) or q["start"] - last < BOARD_Q_GAP_S or \
                any(o["start"] - 0.3 < q["end"] and q["start"] < o["end"] + 0.3 for o in over):
            continue
        last = min([q["end"] + 1.0, duration] + [o["start"] - 0.1 for o in over if o["start"] > q["end"]])
        lone.append({"start": round(q["start"], 3), "end": round(last, 3),
                     "words": [[clean(w["text"]).lower(), round(w["start"], 3)] for w in q["words"] if clean(w["text"])]})
    heads = [h["box"] for h in (face or {}).get("heads", []) if h.get("box")]
    head_x = sorted(b[0] + b[2] / 2 for b in heads)[len(heads) // 2] if heads else 50
    # the speaker's framing: [at, zoom, side (-1 on the left, 0 centred, +1 on the right), move seconds], top-anchored
    fkf = [[0, 1.0, 0, 0.01], [0.3, BOARD_FACE["push"], 0, 2.5]]
    for a, b in views:   # back from the canvas: a slow push in, unless an overlay is about to want the speaker aside
        if not any(c["start"] - 1.6 <= b + 0.4 <= c["end"] for c in over):
            fkf += [[b, BOARD_FACE["rest"], 0, 0.01], [b + 0.4, BOARD_FACE["push"], 0, 2.5]]
    for c in over:   # the speaker moves to the side the overlay is not on, zoomed in until the head clears its half
        hd = head_during(face["heads"], face.get("step_s", 0.5), c["start"], c["end"]) if face else None
        left = c["side"] == "left"
        z = BOARD_FACE["side"]
        if hd:   # Board.tsx faceRect: him on the right shows the source's left edge, on the left its right edge
            z = min(BOARD_FACE["max"], max(z, 51 / max(1, hd[0]) if left else 49 / max(1, 100 - hd[2])))
            edge = hd[0] * z if left else hd[2] * z - 100 * (z - 1)   # the head's near edge on screen, %
            bx = c["box"]
            if left and bx[0] + bx[2] > edge - 2:
                bx[2] = max(30, round(edge - 2 - bx[0], 1))
            elif not left and bx[0] < edge + 2:
                bx[2], bx[0] = max(30, round(bx[0] + bx[2] - edge - 2, 1)), round(max(bx[0], min(edge + 2, 65)), 1)
        fkf += [[max(0, c["start"] - 1.6), round(z, 3), 1 if left else -1, 1.0], [c["end"], BOARD_FACE["rest"], 0, 1.0]]
    fkf.sort(key=lambda k: k[0])
    ends = sorted([k[0] for k in fkf] + [duration])
    for a, b in zip(ends, ends[1:]):   # a long stretch on the speaker eases in or back out every BOARD_REFRAME_S
        t = a + BOARD_REFRAME_S
        while b - t > 2.0:
            if not any(v[0] - 0.5 < t < v[1] for v in views) and not any(c["start"] - 1.6 < t < c["end"] for c in over):
                z = next(k[1] for k in sorted(fkf, key=lambda k: k[0], reverse=True) if k[0] <= t)
                fkf.append([round(t, 3), 1.06 if z > 1.12 else BOARD_FACE["push"] + 0.06, 0, 2.2])
                fkf.sort(key=lambda k: k[0])
            t += BOARD_REFRAME_S
    return over, {"mode": "board", "ground": "#0B0B0D", "boards": boards, "camera": cam, "views": views,
                  "questions": lone, "face": fkf, "head_x": round(head_x, 1), "fade": BOARD_FADE_S, "cues": cues}


def split_cards(cards, art):
    """Every card fills the top panel's art box. A logo tile gets the panel to itself for a moment,
    unless a bigger card is up then (the panel is already showing the visual): that logo is dropped."""
    main = [c for c in cards if c.get("lane") != "logo"]
    out = []
    for c in cards:
        if c.get("lane") == "logo":
            if any(m["start"] - 2 * PANEL_T < c["end"] and c["start"] < m["end"] + 2 * PANEL_T for m in main):
                continue
            c = {k: v for k, v in c.items() if k != "lane"}
            nxt = min((m["start"] for m in main if m["start"] > c["start"]), default=c["end"] + 9)
            c["end"] = round(max(c["end"], min(c["start"] + SPLIT_LOGO_S, nxt - 2 * PANEL_T)), 3)
        out.append({**c, "box": list(art)})
    return sorted(out, key=lambda c: c["start"])


# Letterbox layout: a black 9:16 frame, the landscape take as a centred band, one lowercase title above it,
# one word at a time inside the bottom of the band, and one real photo beside the head over the opening line.
# Pixels of the 1080 x 1920 frame. LB_SAFE: the reels safe zone (x 60-940, y 250-1440): nothing outside it.
LB_SAFE = (60, 250, 940, 1440)
LB_TITLE_X = 140        # title and word side margins: centred, the right edge inside the safe zone
LB_TITLE_GAP = 24       # the title's last line ends this far above the band
LB_TITLE_PX = 58
LB_TITLE_EM = 0.46      # a regular lowercase title's width per character, in em (measured 0.42 on a render)
LB_TITLE_MIN_PX = 40    # a title that needs smaller than this to sit on one line wraps at LB_TITLE_PX instead
LB_WORD_PX = 46
LB_WORD_Y = 0.18        # the word's centre sits this share of the band's height above its bottom
LB_CARD = (0.41, 0.25)  # the photo: side and top inset, as shares of the band's height
LB_HIGHLIGHT = "#F7D21C"
LB_TITLE_WORDS = 8
LB_OPEN_MAX_S = 6.0     # the photo leaves at the end of the first sentence, or by this


DANGLING = {"and", "or", "but", "so", "the", "a", "an", "to", "of", "if", "with", "for", "that", "because", "like"}


def letterbox_title(words):
    """The fallback when Claude wrote no --title: the first sentence or clause, lowercase, at most LB_TITLE_WORDS
    words, never ending on a joining word ("... horrible mindset and"); a question keeps its mark."""
    out = []
    for w in words:
        out.append(w["text"].strip())
        if w["text"].rstrip().endswith((".", "?", "!", ",")) or len(out) >= LB_TITLE_WORDS:
            break
    while len(out) > 1 and clean(out[-1]).lower() in DANGLING:
        out.pop()
    q = out and out[-1].endswith("?")
    return " ".join(clean(x) for x in out if clean(x)).lower() + ("?" if q else "")


def letterbox_plan(head, style, words, meta, images, face, lay):
    """plan.json for the letterbox layout (references/contracts.md). Light by design: no zooms, no cards but
    the opening photo, which is the first image in images.json (the user's own photo or a capture) or none."""
    if meta["height"] >= meta["width"]:
        sys.exit("ERROR: letterbox needs a landscape (16:9) take; this cut is vertical. Use --layout overlay or split")
    W, H = SIZES["9:16"]
    bh = W * meta["height"] / meta["width"]
    by = (H - bh) / 2
    pct = lambda v, d: round(100 * v / d, 2)
    title = (lay.get("title") or letterbox_title(words)).strip().lower()
    if len(title) > 90:
        print(f"warning: the title is {len(title)} characters; over about 90 it no longer fits above the band", file=sys.stderr)
    # one line when it fits: the largest size from LB_TITLE_PX down to LB_TITLE_MIN_PX that holds it, else wrap at full size
    tpx = next((px for px in range(LB_TITLE_PX, LB_TITLE_MIN_PX - 1, -2) if len(title) * px * LB_TITLE_EM <= W - 2 * LB_TITLE_X), LB_TITLE_PX)
    cs = style.get("captions") or {}
    # the creator's highlight when she has one (not her fill colour), else yellow; layout.highlight wins
    hi = lay.get("highlight") or (cs.get("highlight_color") if cs.get("highlight_color") not in (None, cs.get("color", "#FFFFFF")) else LB_HIGHLIGHT)
    cap = {"present": cs.get("present", True), "font_match": cs.get("font_match"), "weight": 500, "case": "lower",
           "color": hi, "highlight_color": hi, "effect": "none", "active_scale": 1, "size_pct": pct(LB_WORD_PX, H),
           "width_pct": pct(W - 2 * LB_TITLE_X, W), "y_pct": pct(by + bh * (1 - LB_WORD_Y), H)}
    cap = {k: v for k, v in cap.items() if v is not None}
    chunks = chunk_captions(words, 1, "lower") if cap["present"] else []
    out = {**head, "width": W, "height": H, "durationInFrames": round(meta["duration"] * head["fps"]),
           "layout": {"mode": "letterbox", "band": [0, pct(by, H), 100, pct(bh, H)], "title": title,
                      "title_box": [pct(LB_TITLE_X, W), pct(LB_SAFE[1], H), pct(W - 2 * LB_TITLE_X, W),
                                    pct(by - LB_TITLE_GAP - LB_SAFE[1], H)], "title_px": tpx},
           "captions": {"style": cap, "chunks": chunks}, "zooms": [], "cards": []}
    img = next((i for i in images if i.get("src")), None)
    if not img:
        print("note: letterbox has no opening photo: add one of your own photos or a capture to images.json "
              "(never a generated image), or leave it out", file=sys.stderr)
        return out
    end = next((w["end"] for w in words if w["text"].rstrip().endswith((".", "?", "!"))), words[-1]["end"] if words else 3)
    side, top = LB_CARD[0] * bh, by + LB_CARD[1] * bh
    heads = [h["box"] for h in (face or {}).get("heads", []) if h.get("box")]
    cx = sorted(b[0] + b[2] / 2 for b in heads)[len(heads) // 2] if heads else 40
    x = LB_SAFE[2] - side if cx < 50 else LB_SAFE[0]    # beside the head, on the side it is not
    out["layout"]["card"] = {"src": img["src"], "to": round(min(end, LB_OPEN_MAX_S), 3),
                             "box": [pct(x, W), pct(top, H), pct(side, W), pct(side, H)]}
    return out


def mark_emph(chunks):
    """The stressed word of a caption line: in a line of 3+ words, the one held clearly longest
    (people stretch the word they stress). Marked "emph": true for the renderer."""
    for c in chunks:
        ws = c["words"]
        if len(ws) < 3:
            continue
        d = sorted(w["end"] - w["start"] for w in ws)
        top = max(ws, key=lambda w: w["end"] - w["start"])
        if top["end"] - top["start"] > 1.4 * d[len(d) // 2] and len(top["text"]) > 3:
            top["emph"] = True
    return chunks


STOP = set("a an the and or but so to of in on at for with from by as is are was were be been it its i i'm i'd you "
           "your we our they their he she his her this that these those there here what when how if not no do does did "
           "can could will would just than then me my mine us them now also gonna wanna".split())   # look.py STOP
LIGHT_FONT = {"serif": "Instrument Serif"}   # look.py light_face -> the Google face that sets it (a sans keeps font_match)


def keywords(c):
    return [w for w in c["words"] if clean(w["text"]).lower() not in STOP and len(clean(w["text"])) > 2]


def spread(cands, n):
    """n items of cands, evenly spaced."""
    if n <= 0 or not cands:
        return []
    step = len(cands) / n
    return [cands[int(k * step)] for k in range(min(n, len(cands)))]


def type_pages(chunks, cap):
    """The creator's caption typography on the pages (look.py line_types): accent_pct of the pages get their
    keyword in the accent colour ("emph"); light_pct are set in her second, lighter face ("face": "light"); about a
    tenth jump to her big keyword size ("big": big_ratio); stack_pct of the pages of 2+ words sit
    on two lines ("lines": 2). Pages are picked spread over the video; keyword pages first when hers are keywords."""
    n = len(chunks)
    if not n:
        return chunks
    kw = [c for c in chunks if keywords(c)]
    for c in spread(kw if (cap.get("accent_keyword_pct") or 0) >= 50 else chunks, round(n * (cap.get("accent_pct") or 0) / 100)):
        for w in c["words"]:   # her accent colours the whole line ("having heard", "she can"), not one word
            w["emph"] = True
    plain = [c for c in chunks if not any(w.get("emph") for w in c["words"])]
    pool = [c for c in plain if keywords(c)] if (cap.get("light_keyword_pct") or 0) >= 50 else [c for c in plain if not keywords(c)]
    for c in spread(pool or plain, round(n * (cap.get("light_pct") or 0) / 100)):
        c["face"] = "light"
    if (cap.get("big_ratio") or 0) >= 1.4:   # under that it is the spread of one size
        word = lambda c: max(keywords(c), key=lambda w: len(clean(w["text"])))
        solo = [c for c in kw if len(clean(word(c)["text"])) >= 5 and c.get("face") != "light"]   # a real word, not "has"
        for c in spread(solo, round(n / 7)):   # enough that her big size is in the top tenth of the lines measured
            c["big"] = cap["big_ratio"]
            word(c)["big"] = cap["big_ratio"]   # the keyword on its own line at her big size (Captions.tsx)
    two = [c for c in chunks if len(c["words"]) >= 2 and not c.get("big")]
    for c in spread(two, round(n * (cap.get("stack_pct") or 0) / 100)):
        c["lines"] = 2
    return chunks


def pick_motion(style):
    """plan.json "motion": style.json motion (a name, or motion.personality), else from the creator's
    median shot length (references/motion.md "Personalities"), else smooth."""
    m = style.get("motion")
    if isinstance(m, str):
        return m
    if isinstance(m, dict) and m.get("personality"):
        return m["personality"]
    shot = (style.get("pace") or {}).get("median_shot_s")
    return next(name for top, name in PERSONALITY if shot < top) if shot else "smooth"


def frame_of(card, aspect):
    """"scene", "split" or "box" for one card (references/motion.md "Layout per template"). A visuals.json
    beat's "layout" wins, except that an explaining card on vertical is never a box over the face.
    Captures: split on vertical (a screen needs the room), a box on wide. Split is vertical only."""
    # Overlay first: every card floats over the footage beside or above the head, the speaker stays on screen.
    # A full-frame scene only when the beat asks for one ("layout": "scene"); the split panel when asked, or
    # for an icon_burst on vertical when the split layout is on (lay_out keeps it a box otherwise).
    want = card.get("layout")
    got = want if want in LAYOUTS else "box"
    t = (card.get("anim") or {}).get("type")
    if aspect == "9:16" and got == "box" and not want and t in SPLIT_FIRST:
        got = "split"
    return "box" if got == "split" and aspect != "9:16" else got


def head_centre(face, t):
    hd = face and head_during(face["heads"], face.get("step_s", 0.5), t, t + 0.01)
    return [round((hd[0] + hd[2]) / 2, 1), round((hd[1] + hd[3]) / 2, 1)] if hd else [50, 31]


def as_scene(card, face, style, n):
    """A full-frame cut-away: the scene box, the transitions (style.json "transitions" cycled; an empty
    list, a creator who only cuts, gives hard cuts; no list gives match in / iris out; a beat's own win)
    and the focus they grow from (the head at the card's start)."""
    cyc = scene_cycle(style)
    card.update({"layout": "scene", "box": list(SCENE_BOX), "focus": card.get("focus") or head_centre(face, card["start"])})
    card.setdefault("transition_in", cyc[n % len(cyc)] if cyc else TRANSITIONS[0])
    card.setdefault("transition_out", cyc[n % len(cyc)] if cyc else TRANSITIONS[1])
    return card


def scene_cycle(style):
    """The transitions scene cards cycle through: style.json "transitions", ["cut"] when it is []."""
    return ["cut"] if style.get("transitions") == [] else style.get("transitions") or []


def _tw(text, fs, wt=700):
    """A bold sans line's width in px, about. ponytail: a per-character average, not measureText; the
    FAIL line (INK_MIN_W) sits well clear of the error."""
    return len(text or " ") * fs * (0.58 if wt >= 800 else 0.55)


def _label(lab):
    return lab if isinstance(lab, str) or not lab else max((x.get("text", "") for x in lab), key=len, default="")


def flow_ink(c, W, H):
    """[x0, x1] in % of the frame: where Diagrams.tsx draws a flow's cards (nodes and branches; the task chips
    are swallowed by the time it settles). The same layout as the renderer: shrink to fit, spread the spare
    width into the wires, centre the cards (a portrait box stacks the chips over the source, no side lane)."""
    p = (c.get("anim") or {}).get("props") or {}
    bx, _, bw, bh = SCENE_TYPE_BOX[H > W] if c.get("layout") == "scene" else c["box"]
    w, h = bw / 100 * W, bh / 100 * H
    s = min(W, H) / 100 / 10.8
    lab_min = 40 * s
    chain = (p.get("nodes") or [])[:6]
    if not chain:
        return None
    n = len(chain)
    branches = (p.get("split") or [])[:max(0, min(4, 6 - n))]
    k = len(branches)
    tasks = [x for x in (p.get("tasks") or []) if (x or {}).get("text")][:4]
    pad = min(w, h) * 0.03
    chip_fs = max(lab_min, min(44 * s, h * 0.11))
    lane = max((_tw(x["text"], chip_fs, 800) + chip_fs * (2.3 if x.get("heavy") else 1.6) + chip_fs * 1.3 for x in tasks),
               default=0) + 28 * s if k and tasks and w >= h else 0
    rows = 2 if not k and n >= 4 else 1
    per = math.ceil(n / rows)
    gap = max(16 * s, h * (0.08 if rows > 1 else 0.05))
    f = 1.0
    while f >= 0.45 - 1e-9:
        row_h = (h - 2 * pad - (rows - 1) * gap) / rows
        S = min(row_h * (0.94 if rows > 1 else 1), (h * 0.6 if k else row_h) * f, (340 if w < h else 240) * s * f)
        nfs = max(lab_min, min(46 * s, S * 0.23))
        nw = [max(S * 0.92, _tw(_label(x.get("label")), nfs) + 40 * s) for x in chain]
        rh = min(h * 0.46, 190 * s, (h - 2 * pad - gap * (k - 1)) / k) if k else 0
        logo_b = min(rh * 0.5, 70 * s * max(f, 0.8))
        bw_ = max((logo_b + 22 * s + max(_tw(t, max(lab_min, min(58 * s, rh * 0.8 / (len(names) * 1.08))), 800) for t in names) + 56 * s
                   for names in ([l.get("text", "") for l in x["lines"]] if x.get("lines") else [_label(x.get("label"))]
                                 for x in branches)), default=0)
        wire_min, wire_b = 56 * s * f, 120 * s * f
        row_w = sum(nw[:per]) + max(0, per - 1) * wire_min
        need = lane + row_w + (wire_b + bw_ if k else 0) + 2 * pad
        if need > w and f > 0.5:
            f -= 0.05
            continue
        wires = max(0, per - 1) + (1.6 if k else 0)
        add = min(max(0.0, w - need) / wires, 90 * s) if wires else 0
        core = row_w + max(0, per - 1) * add + (wire_b + add * 1.6 + bw_ if k else 0)
        x0 = max(pad, (w - core) / 2 - lane) + lane
        return [round(bx + x0 / W * 100, 1), round(bx + (x0 + core) / W * 100, 1)]
    return None


def cluster_ink(c):
    """[x0, x1] in % of the frame for a vertical logo_cluster laid out in its band (Overlays.tsx), else None."""
    p = (c.get("anim") or {}).get("props") or {}
    if not p.get("band"):
        return None
    if len(p.get("logos") or []) < 2:
        return [50 - p.get("size", LOGO_SIZE) / 2, 50 + p.get("size", LOGO_SIZE) / 2]
    return list(p["band"])


def explain_ink(c, W, H):
    """Where a flow or logo_cluster card draws, [x0, x1] % of the width; None for any other card."""
    t = (c.get("anim") or {}).get("type")
    return flow_ink(c, W, H) if t == "flow" else cluster_ink(c) or [0, 0] if t == "logo_cluster" else None


def overlay_led(c):
    """A box card drawn by an overlay format (a capture, chat, post, the flow diagram...): lay_out starts it OVERLAY_LEAD_S x k
    before its word so its entrance has landed on the word. quality.py times its landing the same way."""
    return (c.get("layout") != "scene" and c.get("lane") != "logo"
            and bool(c.get("src") or (c.get("anim") or {}).get("type") in OVERLAYS + ("social_post", "flow")))


OFF_SCREEN = 30   # % of the runtime the creator is off screen (look.py face.present_pct) from which her cards are cut-aways


DARK_CARDS = ("notes", "terminal")   # dark cards: always on the light ground (Scene.tsx sceneGrounds)


def scene_grounds(cards, style):
    """The grounds of her cut-aways: light paper and dark ink in the share that keeps her measured brightness (look.py
    grade.luma; the footage is graded to it, so the scenes average it too), spread through the video; a dark card
    always on paper. No measured luma: Scene.tsx's own cycle."""
    luma = (style.get("grade") or {}).get("luma")
    scenes = sorted((c for c in cards if c.get("scene_by") == "creator" and not c.get("ground")), key=lambda c: c["start"])
    if luma is None or not scenes:
        return cards
    want, light = min(1.0, max(0.0, (luma - 13) / 242)), 0   # paper ~255, ink ~13
    for k, c in enumerate(scenes, 1):
        dark_card = (c.get("anim") or {}).get("type") in DARK_CARDS
        c["ground"] = "ground" if dark_card or abs((light + 1) / k - want) < abs(light / k - want) else "ink"
        light += c["ground"] == "ground"
    return cards


def off_screen(style):
    """True when the creator is off screen OFF_SCREEN% of the time or more: her pictures take the whole frame
    (b-roll, screen recordings), so a picture card with no layout of its own becomes a scene."""
    p = (style.get("face") or {}).get("present_pct")
    return took(style, "graphics") and p is not None and 100 - p >= OFF_SCREEN


FACE_BACK_S = 8.0   # cut-aways never keep the speaker off screen longer than this (the 50/50 face_every_s rule)


def hold_scenes(cards, words, duration, share):
    """A creator off screen `share` of the time: while her cut-aways cover less than that, each scene plan.py made for
    her holds to the end of the sentence it lands in, never into the next card and never keeping the face away more
    than FACE_BACK_S in one run of cut-aways."""
    order = sorted(cards, key=lambda c: c["start"])
    have = sum(c["end"] - c["start"] for c in order if c.get("layout") == "scene")
    ends = [w["end"] for i, w in enumerate(words) if ends_sentence(w["text"]) or i == len(words) - 1]
    run0 = run1 = None
    for k, c in enumerate(order):
        if c.get("layout") == "scene":
            run0 = c["start"] if run1 is None or c["start"] - run1 > 0.5 else run0
            if c.get("scene_by") == "creator" and have < share * duration:
                nxt = min([o["start"] for o in order[k + 1:]] + [duration])
                end = min(next((e for e in ends if e > c["end"]), c["end"]), nxt - 0.3, run0 + FACE_BACK_S)
                if end > c["end"]:
                    have += end - c["end"]
                    c["end"] = round(end, 3)
            run1 = c["end"]
    return cards


def lay_out(cards, aspect, face, style, split_ok):
    """Gives every card its layout. A scene starts SCENE_LEAD_S x k earlier, a hard cut in no earlier (never before the card
    before it in its lane ends). Returns (cards, any card in the split panel)."""
    n = 0
    lead = SCENE_LEAD_S * MOTION_K.get(pick_motion(style), 1.0)
    prev_end = {}
    away = off_screen(style)
    for c in sorted(cards, key=lambda c: c["start"]):
        if away and not c.get("layout") and c.get("lane") != "logo":
            c["layout"], c["scene_by"] = "scene", "creator"   # she cuts away from herself: her pictures take the whole frame
        f = frame_of(c, aspect)
        if f == "split" and not split_ok:
            f = "scene" if c.get("layout") == "split" else "box"   # no panel in overlay: a box, unless the beat asked for the panel
        c["_f"] = f
        if f == "scene":
            cyc = scene_cycle(style)
            tin = c.get("transition_in") or (cyc[n % len(cyc)] if cyc else TRANSITIONS[0])
            c["start"] = round(max(0.0, prev_end.get(c.get("lane"), 0.0), c["start"] - (0 if tin == "cut" else lead)), 3)
            as_scene(c, face, style, n)
            n += 1
        else:
            c["layout"] = "box"
            if overlay_led(c):
                c["start"] = round(max(0.0, prev_end.get(c.get("lane"), 0.0), c["start"] - OVERLAY_LEAD_S * MOTION_K.get(pick_motion(style), 1.0)), 3)
        prev_end[c.get("lane")] = c["end"]
    return cards, any(c["_f"] == "split" for c in cards)


def pick_look(style, prof, prof_mod):
    """plan.json "look". No house palette: overlays are neutral chrome (white cards, near-black text, a soft
    shadow) and colour comes from the real content. Order: the user's brand kit > the copied creator's
    measured palette (only its saturated accent, as the highlighter) > neutral. A style.json look that
    names a preset (editorial, poster-*, ...) opts in to that preset whole."""
    if (style.get("look") or {}).get("preset"):
        return prof_mod.resolve_look(style, prof, warn=lambda m: print(f"warning: {m}", file=sys.stderr))
    brand = prof_mod.brand_look((prof or {}).get("brand") or {})
    creator = prof_mod.creator_look(style)
    look = {"preset": "neutral"}
    accent = brand.get("accent") or creator.get("accent")
    if accent:
        look["mark"] = accent
    for k in ("font", "font_display"):
        if brand.get(k) or creator.get(k):
            look[k] = brand.get(k) or creator.get(k)
    if brand.get("ink"):
        look["ink"] = brand["ink"]
    return look


def sticker_crop(c):
    """The part of a sticker's picture the card shows, image px: its "crop", else Overlays.tsx Sticker's trim of
    capture.mjs's padding."""
    p = c.get("props") or {}
    if p.get("crop"):
        return list(p["crop"])
    w0, h0 = c["size"]
    t = round(min(h0 * 0.08, w0 * 0.035))
    return [t, t, w0 - 2 * t, h0 - 2 * t]


def cut_lines(crop, lines):
    """The text lines (image px) a crop [x, y, w, h] crosses: neither wholly inside it nor wholly out."""
    x0, y0, x1, y1 = crop[0], crop[1], crop[0] + crop[2], crop[1] + crop[3]
    return [ln for ln in lines if ln[0] < x1 and ln[0] + ln[2] > x0 and ln[1] < y1 and ln[1] + ln[3] > y0
            and not (ln[0] >= x0 and ln[1] >= y0 and ln[0] + ln[2] <= x1 and ln[1] + ln[3] <= y1)]


def whole_lines(crop, lines, size, pad=4):
    """The crop grown (or, past the picture's edge, shrunk) until no line of text crosses its edge: every line
    wholly shown or wholly out (capture.mjs snapClip, on the picture)."""
    x0, y0, x1, y1 = crop[0], crop[1], crop[0] + crop[2], crop[1] + crop[3]
    for _ in range(6):
        hit = cut_lines([x0, y0, x1 - x0, y1 - y0], lines)
        if not hit:
            break
        for lx, ly, lw, lh in (ln[:4] for ln in hit):
            if ly < y0:
                y0 = ly - pad if ly - pad >= 0 else ly + lh + pad
            if ly + lh > y1:
                y1 = ly + lh + pad if ly + lh + pad <= size[1] else ly - pad
            if lx < x0:
                x0 = lx - pad if lx - pad >= 0 else lx + lw + pad
            if lx + lw > x1:
                x1 = lx + lw + pad if lx + lw + pad <= size[0] else lx - pad
    x0, y0 = max(0, x0), max(0, y0)
    return [round(x0), round(y0), round(min(size[0], x1) - x0), round(min(size[1], y1) - y0)]


def with_formats(images, visuals):
    """A capture beat's "format" (shot | browser | sticker | plain) and "props" (label, crop, rotate, zoom,
    cursor) reach its card. capture.mjs names a capture images/capture-<i>-<word>.png after the i-th capture
    beat, so the beat is found by that index; a browser gets the beat's url when it has none."""
    beats = [v for v in visuals if v.get("kind") == "capture"]
    out = []
    for im in images:
        m = re.match(r"images/capture-(\d+)-", im.get("src", ""))
        b = beats[int(m.group(1)) - 1] if m and int(m.group(1)) <= len(beats) else {}
        im = dict(im)
        if b.get("format") and "format" not in im:
            im["format"] = b["format"]
        props = {**(b.get("props") or {}), **(im.get("props") or {})}
        if im.get("format") == "browser" and b.get("url"):
            props.setdefault("url", b["url"])
        if props:
            im["props"] = props
        if im.get("format") == "sticker" and im.get("lines") and im.get("size"):
            # the card's crop keeps every line of the sentence whole (a trim into the text cut words off)
            im["props"] = {**props, "crop": whole_lines(sticker_crop(im), im["lines"], im["size"])}
        if b.get("box") or im.get("box"):
            im["_own_box"] = True
        out.append(im)
    return out


CAP_GLYPH = 0.35      # half a one-word lowercase caption's ink height, in font sizes (bold, x-height plus ascenders)
EYES_SHARE = 0.45     # the eyes, down the head box (hair to chin)
CHIN_SHARE = 0.1      # face.py grows the face down by 0.15 of its height; that is a tenth of the head box


def heads_median(face):
    """(top, bottom) of the head box, the median over the take, % down; None with no head found."""
    bs = sorted((h["box"] for h in (face or {}).get("heads", []) if h.get("box")), key=lambda b: b[1] + b[3])
    if not bs:
        return None
    m = bs[len(bs) // 2]
    tops = sorted(b[1] for b in bs)
    return tops[len(tops) // 2], m[1] + m[3]


def above_face(style):
    """True when the creator's captions sit above her face (look.py's face and caption centres), so ours go over
    the head, not under the chin, when they would land on it."""
    c, f = style.get("captions") or {}, style.get("face") or {}
    return bool(c.get("y_pct") and f.get("y_pct") and f.get("height_pct")) and c["y_pct"] < f["y_pct"] - f["height_pct"] / 2


def page_tall(chunks):
    """The tallest caption page against a one-line page: a big keyword (its line plus up to two at the page size) or a
    stacked page (two lines, Captions.tsx STACK_K bigger, 1.14 line height)."""
    return max([1.0] + [c["big"] + 1.14 * (len(c["words"]) > 1) for c in chunks if c.get("big")]
               + [2 * 1.14 * 1.25 for c in chunks if c.get("lines") == 2])


def caption_under_chin(cap, face, aspect, above=False, tall=1.0):
    """Captions never on the face. A vertical caption line that falls inside the head (face.json, the median head
    over the take) moves to the head box's bottom edge, the chin line just below the mouth, held inside the safe
    zone (its ink above y 1440); with above (the creator's captions sit over her face), to just over the head
    when that is inside the safe zone. Changes cap["y_pct"]; returns the chin line (% down) when it moved under
    the chin, else None."""
    hm = aspect == "9:16" and heads_median(face)
    if not hm or not hm[0] - 2 < cap["y_pct"] < hm[1]:
        return None
    half = CAP_GLYPH * (cap.get("size_pct") or 4.4)
    cap["off_face_from"] = cap["y_pct"]   # style_check.py: moved off the face on purpose, not a mismatch
    if above and hm[0] - 0.6 - 2 * half * tall >= SAFE[aspect][1]:
        cap["y_pct"] = round(hm[0] - 0.6 - half * tall, 1)   # the tallest page clears the head
        return None
    lowest = 100 - SAFE[aspect][3] - half
    cap["y_pct"] = round(min(hm[1] + 0.6, lowest), 1)
    return hm[1]


def clear_chin(zooms, face, cap):
    """A push zoom grows the head from its top, so the chin moves down into captions set under it. Each zoom's scale
    is held to what keeps the chin (face.json's head bottom less the chin margin) above the captions' ink; one
    held under 1.02 is dropped."""
    top = cap["y_pct"] - CAP_GLYPH * (cap.get("size_pct") or 4.4)
    out = []
    for z in zooms:
        hd = head_during(face["heads"], face.get("step_s", 0.5), z["start"], z["end"])
        oy = (z.get("origin") or [50, 30])[1]
        chin = hd and hd[3] - CHIN_SHARE * (hd[3] - hd[1])
        want = z.pop("want", z["scale"])
        if chin and chin > oy:
            k = (top - oy) / (chin - oy)
            # held under the creator's punch: grow from the chin instead, the head rising (her 2x on a close shot
            # crops the hair too), as far as keeps the eyes inside the safe zone and the head inside the width
            eyes = hd[1] + EYES_SHARE * (hd[3] - hd[1])
            up = min(want, (chin - SAFE["9:16"][1]) / max(1, chin - eyes), 100 / max(1, hd[2] - hd[0]))
            if up > max(k, 1.02) and chin < top:
                out.append({**z, "scale": round(up, 3), "origin": [z.get("origin", [50, 30])[0], round(chin, 1)]})
                continue
            if k < 1.02:
                continue
            z = {**z, "scale": round(min(z["scale"], k), 3)}
        out.append(z)
    return out


def one_per_page(images, visuals):
    """Never the same page twice: a capture of a URL already captured in this edit is dropped (one capture of a
    page, cropped to the line that matters, then an animation or another page)."""
    url = {(clean(v.get("word", "")).lower(), v.get("nth") or 1): v["url"].rstrip("/").lower()
           for v in visuals if v.get("kind") == "capture" and v.get("url")}
    seen, out = set(), []
    for im in images:
        u = url.get((clean(im.get("word", "")).lower(), im.get("nth") or 1))
        if u and u in seen:
            print(f"warning: '{im.get('word')}' captures {u} again; the same page twice reads as one screenshot "
                  "on repeat. Dropped: show an animation of what is said there instead", file=sys.stderr)
            continue
        seen.add(u)
        out.append(im)
    return out


@with_sfx
def build(style, words, meta, images=(), aspect="auto", cuts=(), visuals=(), edit_dir=None, layout=None, profile=None,
          behind=None):
    """behind: cards in BEHIND formats sit behind the speaker (default: the profile's "behind" answer, or the
    style's own "behind", as the sample Card edit style sets)."""
    if behind is None:
        behind = bool((profile or {}).get("behind") or style.get("behind"))
    words = [w for w in words if w.get("type", "word") == "word" and w["text"].strip()]
    if aspect == "auto":
        aspect = "9:16" if meta["height"] > meta["width"] else "16:9"
    width, height = SIZES[aspect]
    fps = source_fps(meta["fps"])
    duration = meta["duration"]
    visuals = anti_generic(list(visuals), profile)
    cap = dict(style.get("captions") or {})
    _, top, _, bottom = SAFE[aspect]
    cap["y_pct"] = min(max(cap.get("y_pct") or 70, top + 5), 100 - bottom - 4)   # clear of the app's UI
    if aspect == "9:16":   # centred captions keep the safe zone's wider side margin on both sides
        m = max(SAFE[aspect][0], SAFE[aspect][2])
        cap["width_pct"] = min(cap.get("width_pct") or 86, 100 - 2 * m)
    chunks = mark_emph(chunk_captions(words, cap.get("words_per_caption") or 3, cap.get("case", "sentence"))) \
        if cap.get("present", True) else []
    if took(style, "captions"):
        chunks = type_pages(chunks, cap)
        if cap.get("light_face") and any(c.get("face") == "light" for c in chunks):
            cap["light_font"] = LIGHT_FONT.get(cap["light_face"], cap.get("font_match"))
    fj = edit_dir and Path(edit_dir) / "face.json"
    face = json.loads(fj.read_text(encoding="utf-8")) if fj and fj.exists() else None
    chin = caption_under_chin(cap, face, aspect, took(style, "captions") and above_face(style), page_tall(chunks))
    lay = {**SPLIT, **(style.get("layout") or {}), **(layout or {})}
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
    from ai_editor import profile as prof_mod
    head = {"video": meta["video"], "width": width, "height": height, "fps": fps,
            "durationInFrames": round(duration * fps),
            "look": pick_look(style, profile, prof_mod),
            "motion": pick_motion(style)}
    grade = grade_for(style, Path(edit_dir) / meta["video"]) if edit_dir else None
    if grade:
        head["grade"] = grade
    if ((layout or {}).get("mode") or (style.get("layout") or {}).get("mode")) == "letterbox":
        if visuals:
            print("note: letterbox shows one opening photo only; visuals.json beats are not drawn", file=sys.stderr)
        return letterbox_plan(head, style, words, meta, images, face, {**(style.get("layout") or {}), **(layout or {})})
    board = lay.get("mode") == "board"
    if board and aspect != "16:9":
        sys.exit("ERROR: the board layout is 16:9 only (the canvas, the side overlays and the speaker's left-right "
                 "reframes need a wide frame); use --aspect 16:9 or another style for vertical")
    pace =(style.get("pace") or {}) if took(style, "pace") else {}
    # Explaining cards are scenes or sit in the split panel; the panel opens only when a card needs it,
    # unless the layout was set by hand (overlay: split cards become scenes).
    explicit = (layout or {}).get("mode") or (style.get("layout") or {}).get("mode")
    if lay.get("mode") == "split" and aspect != "9:16" and explicit:
        sys.exit("ERROR: the split layout is vertical only; use --layout overlay for 16:9")
    split_ok = aspect == "9:16" and explicit != "overlay"
    seam = lay["seam"]
    split_y = min(seam + SPLIT_CAP_BELOW, 100 - bottom - 4)
    split_now = split_ok and (explicit == "split")
    images = text_labels(kind_formats(with_formats(one_per_page(images, visuals), visuals), style), style)
    probe_cards = place_cards(list(images) + anim_items(visuals, edit_dir, style), words, duration, style, aspect)
    _, wants_split = lay_out(probe_cards, aspect, face, style, split_ok)
    split_now = split_now or wants_split
    logo_y = split_y if split_now else cap["y_pct"]
    cards = thin_cards(place_cards(list(images) + anim_items(visuals, edit_dir, style) + logo_items(visuals, edit_dir, logo_y, aspect, pictures_only(style)),
                                   words, duration, style, aspect), duration, style.get("cards"))
    cards, _ = lay_out(cards, aspect, face, style, split_ok)
    cards = scene_grounds(cards, style)
    if off_screen(style):
        cards = hold_scenes(cards, words, duration, 1 - style["face"]["present_pct"] / 100)
    gap = card_gap_s(style)
    quiet = [g for g in card_gaps(cards, duration) if g[1] - g[0] > gap]
    cover = audio_cover(edit_dir, words)
    if cover:   # the cover's own push replaces the zooms: two moves at once compete for the eye
        quiet = []
    zooms = [] if cover else place_zooms(style.get("zoom") or {}, words, duration, list(cuts), pace.get("cut_kinds"), quiet,
                                         pace.get("median_shot_s"))
    for z in zooms if face else []:
        # grow from the top of the head, centred on it: the face holds its place and the hair never rises
        # into a card placed above the head (a zoom about the face's middle pushed the hair up into it)
        hd = head_during(face["heads"], face.get("step_s", 0.5), z["start"], z["end"])
        if hd:
            z["origin"] = [round((hd[0] + hd[2]) / 2, 1), round(hd[1], 1)]
            # never past the frame: grown from the head's top, the head stays whole (a 2x punch on her wide shot is
            # a 1.6x on a close one)
            fit = round(min(100 / max(1, hd[2] - hd[0]), (100 - hd[1]) / max(1, hd[3] - hd[1])), 2)
            if z["scale"] > fit:
                z["want"], z["scale"] = z["scale"], max(1.0, fit)
    if chin is not None and not split_now:
        zooms = clear_chin(zooms, face, cap)
    for z in zooms:
        z.pop("want", None)
    for a, b in quiet:
        said = [f"'{n}' at {x['start']:.1f} s" for x in named_beats(edit_dir) if a <= x["start"] < b for n in x["names"]]
        print(f"warning: no card for {b - a:.1f} s ({a:.1f}-{b:.1f} s, the rule is {gap:.0f} s): "
              + (f"{', '.join(said)} is named there: show it (a capture, post or logo in visuals.json)" if said else
                 f"nothing named there, so the speaker carries it with a zoom change every {QUIET_HOLD_S:.0f} s"),
              file=sys.stderr)
    zooms = clear_entrances(zooms, cards)
    scenes = [c for c in cards if c["_f"] == "scene"]
    rest = [c for c in cards if c["_f"] != "scene"]
    if split_now:
        art = split_art_box(seam)
        full_y = cap["y_pct"]   # where captions sit while the speaker has the whole frame
        cap["y_pct"] = split_y
        # a logo is dropped while a scene or a panel card is up (the frame is already showing the visual)
        rest = split_cards(rest + [{**c, "lane": None} for c in scenes], art)
        rest = readable_captures([c for c in rest if c.get("_f") != "scene"], aspect, pictures_only(style))
        if lay.get("face_every_s"):
            rest = face_every(rest, float(lay["face_every_s"]))
        out = {**head, "layout": {"mode": "split", "ground": lay["ground"], "seam": seam, "art": art,
                                  "speaker": speaker_frame(face, seam, -(CUTOUT_BREAKOUT - 2) if lay.get("variant") == "cutout" else HEAD_ROOM),
                                  "caption_full_y": full_y,
                                  **({"variant": "cutout", "breakout": CUTOUT_BREAKOUT} if lay.get("variant") == "cutout" else {})}}
    else:
        near = lambda c: c.get("lane") == "logo" and any(sc["start"] - 0.5 < c["end"] and c["start"] < sc["end"] + 0.5 for sc in scenes)
        for c in filter(near, rest):
            print(f"warning: the '{c['trigger_word']}' logo is within 0.5 s of a scene, dropped: end the scene sooner "
                  "(hold_s) or move the logo", file=sys.stderr)
        rest = [c for c in rest if not near(c)]
        # the head as it is drawn: grown by the zooms (and moved by the pans), as check.py plan measures it
        from check import on_screen
        moved = {"zooms": zooms, "pans": place_pans((style.get("camera") or {}) if took(style, "pace") else {}, duration)}
        seen = face and {**face, "heads": [{**h, "box": on_screen(h["box"], h["t"], moved) if h.get("box") else None}
                                           for h in face["heads"]]}
        rest = place_overlays(rest, seen, cap["y_pct"], aspect, graphics(style, "layout").get("layout"))
        rest = avoid_heads(rest, seen, cap["y_pct"], aspect)
        rest = readable_captures(rest, aspect, pictures_only(style))
        if behind and not board:
            rest = tuck_behind(rest, face, aspect)
        out = dict(head)
    cards = clear_caption_paths(creator_motion(sorted(rest + scenes, key=lambda c: c["start"]), style, aspect), cap["y_pct"], aspect)
    for c in cards:
        px = c.get("layout") != "scene" and c.get("size") and capture_xh(c, aspect)
        if px and px < READ_XH and (aspect == "9:16" or c.get("format") == "sticker") and not pictures_only(style):
            print(f"warning: '{c['trigger_word']}' capture text renders at {px:.0f} px x-height (under {READ_XH}: "
                  "too small on a phone; check.py plan FAILs it on vertical). Cut it to a shorter sentence, a smaller \"fit\", "
                  "or a \"crop\" round the evidence in visuals.json", file=sys.stderr)
        c.pop("_f", None)
        c.pop("_own_box", None)
    for c in cards:   # logos sit round the head as drawn: grown by a zoom up while they are
        hd = ((c.get("anim") or {}).get("props") or {}).get("head") if (c.get("anim") or {}).get("type") == "logo_cluster" else None
        z = hd and next((z for z in zooms if z["start"] < c["end"] and c["start"] < z["end"]), None)
        if z:
            ox, oy = z.get("origin") or [50, 30]
            k = z["scale"]
            c["anim"]["props"]["head"] = [round(ox + (hd[0] - ox) * k, 1), round(oy + (hd[1] - oy) * k, 1), round(hd[2] * k, 1), round(hd[3] * k, 1)]
    extra = {"cover": cover} if cover and not split_now else {}
    if pictures_only(style):
        extra["card_kinds"] = list(style["card_kinds"])
    if pictures_only(style) and card_rate(style):   # a card edit: check.py plan FAILs a gap over card_gap_s
        extra["card_rate"] = card_rate(style)
    texts = text_items(visuals, words, duration, cards, face, cap["y_pct"], cap.get("size_pct"))
    if texts:
        extra["texts"] = texts
        # the title sits where the captions do: they wait until it has gone
        titles = [x for x in texts if x["kind"] == "title"]
        chunks = [c for c in chunks if not any(c["start"] < x["end"] and x["start"] < c["end"] for x in titles)]
        under_titles(cards, texts)   # check.py plan: screenshots stay pictures, text labels FAIL
    cards = min_show(cards, duration)
    pans = place_pans((style.get("camera") or {}) if took(style, "pace") else {}, duration)
    if pans and not split_now:
        extra["pans"] = pans
    hook = ((style.get("hook") or {}).get("winner") or {}) if took(style, "graphics") else {}
    if hook.get("first_graphic_s") is not None:
        # a soft rule, checked by check.py plan: the creator's winners show a graphic by then
        extra["targets"] = {"first_graphic_s": hook["first_graphic_s"],
                            "control_first_graphic_s": ((style.get("hook") or {}).get("control") or {}).get("first_graphic_s")}
    cards = scene_parts(cards, words, edit_dir)
    cards = drop_words_only(take_frames(cards, edit_dir, edit_dir and Path(edit_dir) / meta["video"], face), style)
    if board:   # logos -> tiles on the canvas, questions -> headings; the speaker's framing replaces the zooms and pans
        cards, out["layout"] = board_layout(cards, words, duration, face, edit_dir)
        zooms = []
        for k in ("pans", "cover", "texts"):
            extra.pop(k, None)
    typed = typed_texts(edit_dir)   # the user's own typed text goes in on every layout, the board too
    if typed:
        extra["texts"] = extra.get("texts", []) + typed
    return {**out, "captions": {"style": cap, "chunks": chunks}, "zooms": zooms, "card_gap_s": gap,
            "cards": cards, **extra}


def source_fps(fps):
    """The plan's frame rate: the source's own (29.97 stays 29.97003), so frame n of the plan is frame n of
    the cut. Rounding a 29.97 source to 30 drew 1997 frames from its 1996 and put the render a frame off
    the cut by the end (quality.py reads the cut frame by frame against the render; matte.py names its
    cutout frames by the cut's own frame numbers)."""
    if not fps:
        return 30
    return round(fps) if abs(fps - round(fps)) < 1e-3 else round(fps, 5)


def probe(video):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate:stream_side_data=rotation:format=duration",
                          "-of", "json", str(video)], capture_output=True, text=True)
    if out.returncode:
        sys.exit(f"ERROR: ffprobe could not read {video}")
    d = json.loads(out.stdout)
    s = d["streams"][0]
    w, h = s["width"], s["height"]
    if any(abs(sd.get("rotation", 0)) == 90 for sd in s.get("side_data_list", [])):
        w, h = h, w
    num, den = s["r_frame_rate"].split("/")
    return {"video": Path(video).name, "width": w, "height": h,
            "fps": int(num) / int(den or 1), "duration": float(d["format"]["duration"])}


def footage_grade(video, w=48):
    """(mean luma 0-255, mean HSV saturation 0-1) of the cut, one small frame a second: creator-teardown look.py's
    grade_of on the same pixels."""
    m = probe(video)
    h = max(2, round(w * m["height"] / m["width"] / 2) * 2)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"fps=1,scale={w}:{h}", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    if not raw:
        return None
    luma = sat = 0.0
    for k in range(0, len(raw) - 2, 3):
        r, g, b = raw[k], raw[k + 1], raw[k + 2]
        luma += 0.2126 * r + 0.7152 * g + 0.0722 * b
        mx = max(r, g, b)
        sat += (mx - min(r, g, b)) / mx if mx else 0
    n = len(raw) // 3
    return luma / n, sat / n


GRADE_B, GRADE_S = (0.7, 1.3), (0.5, 1.8)   # how far the footage is pushed towards her grade (CSS brightness, saturate)


def grade_for(style, video):
    """plan.json "grade": the CSS brightness and saturate that take the cut's mean luma and saturation to the
    creator's (look.py style.json "grade"), held inside GRADE_B / GRADE_S; None when hers is not measured or ours
    is already within 3%."""
    want = style.get("grade") if took(style, "graphics") else None
    have = want and Path(video).exists() and footage_grade(video)
    if not have or not want.get("luma") or not want.get("sat") or not have[0]:
        return None
    b = round(min(max(want["luma"] / have[0], GRADE_B[0]), GRADE_B[1]), 2)
    s = round(min(max(want["sat"] / have[1], GRADE_S[0]), GRADE_S[1]), 2) if have[1] > 0.01 else 1.0   # grey stays grey
    return None if abs(b - 1) < 0.03 and abs(s - 1) < 0.03 else {"brightness": b, "saturate": s}


# --- caption contrast: the footage behind each caption page, measured on the cut --------------------------
CONTRAST_MIN = 3.0     # WCAG 1.4.3 for large text; quality.py fails a caption under it (its CONTRAST_FAIL)
# What plan.py aims at: the render check's 4.5:1 WARN line (quality.py CONTRAST_WARN) plus 0.2. Plan estimates the
# footage in the caption's box at a quarter size; the render check reads the ring round the real glyphs at full
# size, which came out 0.1-0.2 lower on the sample. Aiming at the FAIL line (3.3) left pages the render WARNed
# that a new plan never touched (the sample's 4.36:1 at 20.77 s).
CONTRAST_TARGET = 4.7
# How far each step pulls the footage round the glyphs toward treat_color (alpha-composite in sRGB), as
# quality.py's contrast check sees it: fitted to renders of white captions on a bright (#E6E1D8) and a
# grey (#9A9A9A) desk, which agree to 0.04, rounded down. The renderer's default soft shadow, the
# treatment's denser shadow, that plus a 0.1 em stroke, and all of it on a 0.45 backing (Captions.tsx).
# glow: plain captions' step after the shadow (Captions.tsx), fitted the same way at TikTok Sans 600, 4.2%: 0.29 / 0.31.
PULL = {"plain": 0.07, "shadow": 0.12, "glow": 0.28, "stroke": 0.45, "backing": 0.7, "band": 0.55}
# band: plain captions' last step, the glow over a soft dark band the width of the frame behind the caption line
# (Captions.tsx), no edge: alpha 0.5 at its middle composited with the glow, rounded down. Never a box or a stroke.
TREATS = ("shadow", "stroke", "backing")
# Plain captions (profile.py PLAIN_CAPTIONS) take a shadow, then a glow, and keep the glow while it reads at
# PLAIN_MIN or better (the render check may WARN there, it does not FAIL). Only under that, where the page would
# actually fail, do they get the stroke and then the backing.
PLAIN_TREATS = ("shadow", "band")
PLAIN_MIN = CONTRAST_MIN + 0.3
LUM = [((v / 255) / 12.92 if v / 255 <= 0.04045 else ((v / 255 + 0.055) / 1.055) ** 2.4) for v in range(256)]


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[k:k + 2], 16) for k in (0, 2, 4))


def lum(rgb):
    return 0.2126 * LUM[rgb[0]] + 0.7152 * LUM[rgb[1]] + 0.0722 * LUM[rgb[2]]


def contrast(a, b):
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def treat_for(pixels, fill, pull, tc):
    """The footage pixels round a caption pulled toward tc by `pull` -> contrast with the fill at the worst
    spot: the 90th percentile toward the fill's own luminance (quality.py worst_contrast)."""
    lf = lum(fill)
    ls = sorted(lum([round(v + (t - v) * pull) for v, t in zip(px, tc)]) for px in pixels)
    worst = ls[int(0.9 * (len(ls) - 1))] if lf > 0.18 else ls[int(0.1 * (len(ls) - 1))]
    return contrast(lf, worst)


def pick_treat(pixels, style):
    """(treat or None, treat colour, contrast it reaches) for one caption page over these footage pixels.
    The creator's look first; then the smallest step that reaches CONTRAST_TARGET."""
    fill = hex_rgb(style.get("color") or "#FFFFFF")
    light = lum(fill) > 0.18
    # the treatment colour: the darkest (or lightest, for dark text) of the creator's palette that
    # stands 4.5:1 off the fill, else near-black (near-white)
    pal = [hex_rgb(style[k]) for k in ("stroke_color", "box_color", "highlight_color", "emphasis_color")
           if re.fullmatch(r"#?[0-9a-fA-F]{6}", str(style.get(k) or ""))]
    pal = [c for c in pal if contrast(lum(c), lum(fill)) >= 4.5]
    tc = (min if light else max)(pal, key=lum, default=(17, 17, 17) if light else (245, 245, 245))
    hexc = "#%02X%02X%02X" % tc
    plain = 0.0 if style.get("shadow") is False else PULL["plain"]
    if light:     # the renderer's default shadow is black
        got = treat_for(pixels, fill, plain, (0, 0, 0))
    else:
        got = treat_for(pixels, fill, 0.0, tc)
    if got >= CONTRAST_TARGET:
        return None, hexc, got
    # a creator measured with no stroke and no box (plain white over the footage) keeps that look first too
    # a creator measured with no stroke and no box keeps that: shadow, glow, then the soft band, never a stroke or box
    plain = is_plain(style)
    for t in PLAIN_TREATS if plain else TREATS:
        if plain and t == "band" and got >= PLAIN_MIN:
            return "shadow", hexc, got   # the soft shadow is enough to read: the band only where a page would fail
        got = treat_for(pixels, fill, PULL[t], tc)
        if got >= CONTRAST_TARGET:
            break
    return t, hexc, got


def caption_backdrops(plan, edit_dir, meta):
    """{chunk index: [RGB pixels]}: the footage behind each caption page as the render draws it (zoom and
    pan on the cut, check.py footage_affine), at a quarter of the output size, 4 samples a second.
    ponytail: split layout is measured as if the panel were closed (full-frame footage under the
    caption's y); check.py render measures the real frames either way."""
    from check import footage_affine
    from edit import footage_filter
    W, H = plan["width"] // 4, plan["height"] // 4
    cs, chunks = plan["captions"]["style"], plan["captions"]["chunks"]
    y = (plan.get("layout") or {}).get("caption_full_y") or cs.get("y_pct", 70)
    font = (cs.get("size_pct") or 6) / 100 * max(W, H)
    box_w = (cs.get("width_pct") or 86) / 100 * W
    scenes = [c for c in plan["cards"] if c.get("layout") == "scene"]
    want = {}
    for i, c in enumerate(chunks):
        if any(sc["start"] < c["end"] and c["start"] < sc["end"] for sc in scenes):
            continue    # a scene's ground is behind it, drawn in the scene's ink
        for t in (c["start"] + 0.05, (c["start"] + c["end"]) / 2, c["end"] - 0.05):
            want.setdefault(max(0, round(t * 4)), []).append(i)
    out = {}
    if not want:
        return out
    vf = footage_filter(plan, meta["width"], meta["height"]) + f",fps=4,scale={W}:{H}"
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(Path(edit_dir) / plan["video"]), "-vf", vf,
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    n = 0
    while True:
        buf = p.stdout.read(W * H * 3)
        if len(buf) < W * H * 3:
            break
        for i in want.get(n, ()):
            c = chunks[i]
            half = min(box_w / 2, 0.28 * font * len(c["text"]) + font / 2)
            rows = 1.3 if 0.55 * font * len(c["text"]) > box_w else 0.75     # two lines when it wraps
            (s, _, tx), (_, _, ty) = footage_affine(n / 4, plan, W, H)
            px = out.setdefault(i, [])
            for yy in range(max(0, int(y / 100 * H - rows * font)), min(H, int(y / 100 * H + rows * font) + 1), 2):
                for xx in range(max(0, int(W / 2 - half)), min(W, int(W / 2 + half) + 1), 2):
                    sx, sy = int((xx - tx) / s), int((yy - ty) / s)
                    if 0 <= sx < W and 0 <= sy < H:
                        k = 3 * (sy * W + sx)
                        px.append(tuple(buf[k:k + 3]))
        n += 1
    p.stdout.close()
    p.wait()
    return out


def treat_captions(plan, edit_dir, meta, floors=None):
    """Every caption page that would read under CONTRAST_TARGET on the footage behind it gets the smallest
    treatment that fixes it, in "treat" (Captions.tsx). The creator's own stroke or box already is one.
    floors: {page start "%.2f": treat} from contrast_floors, the least a page gets.
    Returns [(chunk index, treat, contrast or None)] for the pages it changed."""
    cs, chunks = plan["captions"]["style"], plan["captions"]["chunks"]
    floors = floors or {}
    done = {}
    if cs.get("treat") is False:   # the creator's plain captions, as measured: no shadow, glow, stroke or box added
        return []
    if chunks and not (cs.get("stroke") or cs.get("box")):
        for i, px in caption_backdrops(plan, edit_dir, meta).items():
            if not px:
                continue
            t, colour, got = pick_treat(px, cs)
            if t:
                chunks[i].update(treat=t, treat_color=colour)
                done[i] = (i, t, round(got, 2))
    order = steps_of(cs)
    for i, c in enumerate(chunks):
        least = floors.get(f"{c['start']:.2f}")
        if least not in order:   # a floor from before the band: the plain ladder's top step instead
            least = order[-1] if least else None
        if least and STEPS.index(least) > STEPS.index(c.get("treat")):
            c.update(treat=least, treat_color=c.get("treat_color") or pick_treat([(128, 128, 128)], cs)[1])
            done[i] = (i, least, None)
    # one treatment for the whole video: every page takes the strongest any page needed, never a mix (a glow on
    # most pages and a box on one reads as a mistake)
    top = max((c.get("treat") for c in chunks), key=STEPS.index, default=None)
    if top:
        colour = next(c["treat_color"] for c in chunks if c.get("treat") == top)
        for i, c in enumerate(chunks):
            if c.get("treat") != top:
                c.update(treat=top, treat_color=colour)
                done[i] = (i, top, done[i][2] if i in done else -1)   # -1: given it to match the rest
    return sorted(done.values())


STEPS = (None, "shadow", "glow", "band", "stroke", "backing")   # every treatment, least visible first



def is_plain(cs):
    """Plain white over the footage: the plain style, or a creator measured with no stroke and no box."""
    return cs.get("style") == "plain" or (cs.get("stroke") is False and cs.get("box") is False)


def steps_of(cs):
    """The treatments a page of this caption style steps through: plain captions have the glow, others skip it.
    Same test as pick_treat, so a page pick_treat gave the glow always has a next step."""
    return (None,) + PLAIN_TREATS if is_plain(cs) else (None,) + TREATS


def contrast_summary(changed, chunks, worst=3):
    """treat_captions' pages as one line: how many got each treatment, and the lowest contrasts they reach."""
    if not changed:
        return ""
    by = {}
    for _, t, _ in changed:
        by[t] = by.get(t, 0) + 1
    low = sorted((got, i) for i, _, got in changed if got and got > 0)[:worst]
    late = sum(1 for _, _, got in changed if got is None)
    same = sum(1 for _, _, got in changed if got == -1)
    return (f"captions: {len(changed)} of {len(chunks)} pages treated for contrast ("
            + ", ".join(f"{n} {t}" for t, n in sorted(by.items(), key=lambda kv: -kv[1])) + ")"
            + (f"; lowest reached: " + ", ".join(f"{got}:1 '{chunks[i]['text']}' at {chunks[i]['start']:.1f} s"
                                                 for got, i in low) if low else "")
            + (f"; {late} from the last render check" if late else "")
            + (f"; {same} only so every page has the same treatment" if same else ""))


def contrast_floors(edit_dir, out):
    """{page start: treat}: the caption pages the last render check (check<tag>.json, caption_contrast.low_at)
    read under CONTRAST_TARGET get one treatment past the one that render drew (the plan at `out`). Kept in
    contrast.json, so every later plan keeps them; each check is read once. This is what "plan again" does."""
    f, ck = edit_dir / "contrast.json", edit_dir / f"check{out.stem[len('plan'):]}.json"
    doc = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"pages": {}, "read": []}
    low = ((json.loads(ck.read_text(encoding="utf-8")).get("render") or {}).get("caption_contrast") or {}).get("low_at") \
        if ck.exists() else None
    stamp = f"{ck.name}@{ck.stat().st_mtime:.0f}" if ck.exists() else None
    if low and out.exists() and stamp not in doc["read"]:
        # a plain page keeps its glow unless the render read it under CONTRAST_MIN (fail_at): a WARN is its look
        fail = ((json.loads(ck.read_text(encoding="utf-8")).get("render") or {}).get("caption_contrast") or {}).get("fail_at") or []
        cap = json.loads(out.read_text(encoding="utf-8"))["captions"]
        order = steps_of(cap.get("style") or {})
        for c in cap["chunks"]:
            hit = lambda ts: any(c["start"] - 0.05 <= t <= c["end"] + 0.05 for t in ts)
            if hit(low) and not (c.get("treat") == "shadow" and order[-1] == "band" and not hit(fail)):   # a plain page's WARN keeps its look
                # the next step up on this style's ladder (a step from an older ladder, a glow, counts by its rank)
                nxt = next((o for o in order if STEPS.index(o) > STEPS.index(c.get("treat"))), order[-1])
                key = f"{c['start']:.2f}"
                if STEPS.index(nxt) > STEPS.index(doc["pages"].get(key)):
                    doc["pages"][key] = nxt
        doc["read"].append(stamp)
        f.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return doc["pages"]


def cut_points(edit_dir):
    """Where the jump cuts fall on cut.mp4, from the cut skill's decisions.json."""
    p = edit_dir / "decisions.json"
    if not p.exists():
        return []
    t, out = 0.0, []
    for span in json.loads(p.read_text(encoding="utf-8"))[:-1]:
        t += span["end"] - span["start"]
        out.append(round(t, 3))
    return out


def demo_punch():
    her = {"graphics": {"per_min": 10.3}}
    assert card_rate(her) == 10.3 and card_rate({**her, "cards": {"per_min": 2}}) == 2   # her rate; the user's cap wins
    assert card_rate({**her, "cards": {"on": False}}) == 0 and card_rate({"cards": {"per_min": 4}}) is None
    assert card_rate({**her, "blend": {"take": ["captions"]}}) is None
    ws = [{"text": "Go.", "start": t, "end": t + 0.3} for t in (0.0, 10.0, 20.0, 30.0)]
    z = place_zooms({"per_min": 12, "kind": "punch", "scale": 1.4, "on": "sentence_start"}, ws, 40.0, [], shot_s=2.4)
    # 12 measured zooms a minute = 6 punches, each in and back out
    assert [(x["start"], x["end"]) for x in z] == [(0.0, 2.4), (10.0, 12.4), (20.0, 22.4), (30.0, 32.4)], z
    assert len(place_zooms({"per_min": 6, "kind": "punch", "on": "sentence_start"}, ws, 40.0, [])) == 2
    # "fewer zooms" (taste zoom.per_min) is the rate: the 5 s hold fill and the quiet fill no longer add them back
    ur = user_rate({"zoom": {"per_min": 3, "max_hold_s": 5.0}}, {"zoom": {"per_min": 1}})["zoom"]
    assert ur == {"per_min": 3, "max_hold_s": 60.0, "fill_quiet": False}, ur
    assert user_rate({"zoom": {"max_hold_s": 5.0}}, {"zoom": {"per_min": 1, "max_hold_s": 4}})["zoom"] == {"max_hold_s": 5.0}


def demo():
    # music follows the creator (a bed in half her videos or more) unless the profile or the style page says otherwise
    snd = {"sound": {"music": {"present_pct": 100}}}
    assert music_wanted(snd, {}) is True and music_wanted(snd, {"sound": {"sfx": True}}) is True, "QA round 2: no bed"
    assert music_wanted(snd, {"sound": {"music": False}}) is False and music_wanted({**snd, "music": False}, {"sound": {"music": True}}) is False
    assert music_wanted({"sound": {"music": {"present_pct": 30}}}, {}) is False and music_wanted({}, {"sound": {"music": True}}) is True
    assert music_wanted({**snd, "blend": {"take": ["captions"]}}, {}) is False, "sound not taken from that creator"
    demo_punch()
    with tempfile.TemporaryDirectory() as td:   # the review page's typed text (texts.json) goes in as typed
        assert typed_texts(td) == [] and typed_texts(None) == []
        (Path(td) / "texts.json").write_text(json.dumps({"items": [{"id": "edit1-3", "text": "wait for it", "style": "box", "start": 1.0,
                                                                      "end": 4.0, "x_pct": 50, "y_pct": 40, "size_pct": 6}]}), encoding="utf-8")
        assert typed_texts(td) == [{"kind": "label", "text": "wait for it", "style": "box", "start": 1.0, "end": 4.0,
                                    "x_pct": 50, "y_pct": 40, "size_pct": 6}], typed_texts(td)
        (Path(td) / "texts.json").write_text(json.dumps({"items": [{"id": "t1", "text": "hug", "style": "block", "start": 0, "end": 1,
            "x_pct": 50, "y_pct": 40, "size_pct": 6, "font": "Anton", "color": "#FFD60A", "width_pct": 60}]}), encoding="utf-8")
        assert {k: typed_texts(td)[0][k] for k in ("style", "font", "color", "width_pct")} == \
            {"style": "block", "font": "Anton", "color": "#FFD60A", "width_pct": 60}, typed_texts(td)   # a re-plan keeps the look
    with tempfile.TemporaryDirectory() as td:   # the timeline's placed sounds (sounds.json) join the plan's sfx, in time order
        import sfx
        keep = sfx.own_cue
        sfx.own_cue = lambda e, n: (f".sfx/own-{Path(n).stem}.wav", 0.1) if n != "gone.wav" else (_ for _ in ()).throw(ValueError("gone"))
        try:
            (Path(td) / "sounds.json").write_text(json.dumps({"items": [{"id": "a1", "t": 2.0, "sound": "ding.mp3"},
                                                                        {"id": "a2", "t": 1.0, "sound": "gone.wav"}]}), encoding="utf-8")
            pl = placed_sounds({"fps": 30, "sfx": [{"t": 3.0, "src": ".sfx/pop.wav", "event": 3.0}]}, td)
            assert [(c["src"], c["event"], c.get("placed")) for c in pl["sfx"]] == [(".sfx/own-ding.wav", 2.0, "a1"),
                                                                                    (".sfx/pop.wav", 3.0, None)], pl
            assert pl["sfx"][0]["t"] == 1.9
        finally:
            sfx.own_cue = keep
    from preview import apply_overrides
    with tempfile.TemporaryDirectory() as td:   # the timeline's x on a sound the plan put there (overrides.json sfx deleted)
        (Path(td) / "overrides.json").write_text(json.dumps({"sfx": {"3.000": {"deleted": True}}}), encoding="utf-8")
        got = apply_overrides({"cards": [], "captions": {"chunks": []}, "sfx": [{"t": 2.9, "src": ".sfx/pop.wav", "event": 3.0},
                                                                                {"t": 5.0, "src": ".sfx/zoom.wav", "event": 5.0}]}, td)
        assert [c["src"] for c in got["sfx"]] == [".sfx/zoom.wav"], got["sfx"]
    hy = [{"text": t, "start": i * 0.3, "end": i * 0.3 + 0.25} for i, t in enumerate(["one", "-for", "-one", "deal"])]
    got = [c["text"] for c in chunk_captions(hy, 3, "sentence")]
    assert got == ["one-for-one deal"], got
    face = {"step_s": 0.5, "heads": [{"t": 0.0, "box": [30, 30, 40, 30]}, {"t": 0.5, "box": [30, 31, 40, 30]}]}
    top = {"start": 0.0, "end": 1.0, "box": [10, 15, 74, 22], "trigger_word": "a"}
    logo = {"start": 0.0, "end": 1.0, "box": [42, 50, 16, 9], "trigger_word": "b", "anim": {"type": "logo"}}
    tiny = {"start": 0.0, "end": 1.0, "box": [10, 25, 74, 22], "trigger_word": "c"}
    got = avoid_heads([top, logo, tiny], face, 68, "9:16")
    assert got[0]["box"] == [10, 15, 74, 13], got[0]["box"]           # shrunk to above the head
    lx, ly, lw, lh = got[1]["box"]
    # logo off the head (no room beside it inside the 14% side margins check.py plan holds: above it); tiny dropped
    assert (lx + lw <= 30 or lx >= 70 or ly + lh <= 30) and 14 <= lx and lx + lw <= 86 and len(got) == 2, got
    # placed off the head as drawn: a 1.2 zoom while the card is up grows the head past where face.json has it
    from check import check_plan, on_screen
    zs = [{"start": 0.0, "end": 2.0, "scale": 1.2, "kind": "punch", "ease_s": 0.0}]
    right = {"step_s": 0.5, "heads": [{"t": 0.0, "box": [36, 30, 30, 30]}]}      # room only on its right
    seen = {**right, "heads": [{**h, "box": on_screen(h["box"], h["t"], {"zooms": zs})} for h in right["heads"]]}
    for f, fails in ((right, True), (seen, False)):
        lg = avoid_heads([{**logo, "box": [42, 50, 16, 9]}], f, 68, "9:16")
        pl = {"width": 1080, "height": 1920, "fps": 30, "durationInFrames": 60, "zooms": zs, "cards": lg,
              "captions": {"style": {"y_pct": 68}, "chunks": []}}
        assert any("covers the head" in x["what"] for x in check_plan(pl, right)) == fails, (f, lg)
    assert safe_box([6, 3, 88, 27], "9:16") == [13.0, 13.1, 74.0, 22], safe_box([6, 3, 88, 27], "9:16")
    assert safe_box([50, 90, 20, 10], "9:16")[1] == 65
    words = []
    t = 0.0
    for i, text in enumerate("so this is how I edit. every video gets zooms and captions now. try notion today."
                             .split()):
        words.append({"text": text, "start": round(t, 2), "end": round(t + 0.3, 2), "type": "word"})
        t += 0.35 + (0.6 if text.endswith(".") else 0)
    style = {"zoom": {"per_min": 60, "kind": "punch", "scale": 1.2, "on": "sentence_start"},
             "captions": {"words_per_caption": 3, "case": "upper"},
             "cats": {"logo": {"hold_s": 2.0, "entrance": [["slide", 0.7]], "box": None}}}
    meta = {"video": "cut.mp4", "width": 3840, "height": 2160, "fps": 29.97, "duration": t}
    imgs = [{"src": "images/n.png", "word": "Notion"}]
    p = build(style, words, meta, imgs)
    assert (p["width"], p["height"], p["fps"]) == (1920, 1080, 29.97), p
    # the source's real rate: the real-footage test's 29.97 cut (1996 frames, 66.5998 s) planned at 30 drew 1997
    assert source_fps(30000 / 1001) == 29.97003 and source_fps(30.0) == 30 and source_fps(25) == 25 and source_fps(0) == 30
    assert round(66.599813 * source_fps(30000 / 1001)) == 1996 and int(66.599813 * 30) == 1997
    chunks = p["captions"]["chunks"]
    assert all(len(c["words"]) <= 3 for c in chunks)
    assert chunks[0]["text"] == "SO THIS IS" and chunks[1]["text"] == "HOW I EDIT", chunks[:2]
    assert all(a["end"] <= b["start"] for a, b in zip(chunks, chunks[1:]))
    z = p["zooms"]
    assert z and all(x["ease_s"] == 0 and x["scale"] == 1.2 for x in z)
    assert all(a["end"] <= b["start"] for a, b in zip(z, z[1:])), "zooms overlap"
    assert z[0]["end"] < z[1]["start"], "zoom-out gap missing: the frame would creep"
    c = p["cards"][0]
    notion = next(w for w in words if w["text"] == "notion")
    assert abs(c["start"] - (notion["start"] - 0.1 - OVERLAY_LEAD_S)) < 1e-6 and c["entrance"] == "slide", c   # leads by its entrance
    assert c["box"] == DEFAULT_BOX["16:9"]
    v = build(style, words, meta, aspect="9:16")
    assert (v["width"], v["height"]) == (1080, 1920)
    assert build(style, words, meta, imgs) == p, "not deterministic"
    push = place_zooms({"per_min": 30, "kind": "push", "duration_s": 0.5, "on": "emphasis"},
                       [w for w in words], t, [])
    assert push and push[0]["ease_s"] == 0.5
    vis = [{"word": "zooms", "kind": "anim", "type": "arrow_callout", "props": {"text": "zooms"}},
           {"word": "today", "kind": "anim", "type": "nope"},
           {"word": "edit", "kind": "capture", "url": "https://example.com"}]
    a = build(style, words, meta, imgs, visuals=vis)["cards"]
    assert [c.get("src") or c["anim"]["type"] for c in a] == ["arrow_callout", "images/n.png"], a
    zooms_w = next(w for w in words if w["text"] == "zooms")
    assert abs(a[0]["start"] - (zooms_w["start"] - 0.1)) < 1e-6 and "src" not in a[0] and a[0]["layout"] == "box"   # overlay first
    assert a[0]["anim"] == {"type": "arrow_callout", "props": {"text": "zooms", "word_at": 0.1}}   # its word, from its start
    assert a[0]["end"] <= a[1]["start"], "two cards at once"
    sc = [{"word": "every", "kind": "anim", "type": "flow", "hold_s": 3, "allow_icons": True,
           "props": {"nodes": [{"icon": "mail", "word": "video"}, {"label": "x", "word": "zooms", "off_word": "captions"}]}}]
    f = next(c for c in build(style, words, meta, visuals=sc)["cards"] if c["anim"]["type"] == "flow")
    every = next(w for w in words if w["text"] == "every")
    n0, n1 = f["anim"]["props"]["nodes"]
    assert n0["src"] == "images/icon-mail.svg" and abs(n0["at"] - (every["start"] + 0.35 - f["start"])) < 1e-6, f
    assert n1["off_at"] > n1["at"] > n0["at"] and "at" not in sc[0]["props"]["nodes"][0], f
    sp_face = {"step_s": 0.5, "heads": [{"t": 0.0, "box": [30, 31, 30, 29]}, {"t": 0.5, "box": None}]}
    fr = speaker_frame(sp_face, 50)
    assert fr["scale"] == 1 and fr["y"] == 27 and 31 - fr["y"] == HEAD_ROOM, fr      # hair HEAD_ROOM into the window
    assert abs(speaker_frame({"heads": [{"t": 0, "box": [45, 40, 10, 15]}]}, 50)["scale"] - MIN_HEAD / 15) < 1e-3   # small head scaled up
    assert speaker_frame(None, 50)["y"] == 25
    lg = {"start": 5.0, "end": 6.2, "box": [1, 1, 1, 1], "trigger_word": "l", "lane": "logo", "anim": {"type": "logo"}}
    big = {"start": 0.0, "end": 4.0, "box": [1, 1, 1, 1], "trigger_word": "b"}
    art = split_art_box(50)
    assert art == [13.0, 13.1, 74.0, 34.9], art   # centred: equal side margins
    sc2 = split_cards([big, lg, {**lg, "start": 3.5, "end": 4.7}], art)
    assert [c["box"] for c in sc2] == [art, art] and "lane" not in sc2[1] and sc2[1]["end"] == 6.5, sc2   # overlapping logo dropped
    vs = build(style, words, {**meta, "width": 1080, "height": 1920}, imgs, layout={"mode": "split"})
    assert vs["layout"]["mode"] == "split" and vs["captions"]["style"]["y_pct"] == 50 + SPLIT_CAP_BELOW
    assert all(c["box"] == art for c in vs["cards"]) and "layout" not in p
    # letterbox: 9:16 from a landscape take, the title from the first sentence, one word a page, the first image
    # beside the head (away from it) until the first sentence ends; every element inside the reels safe zone
    lb = build(style, words, meta, imgs, layout={"mode": "letterbox"})
    ly, cs = lb["layout"], lb["captions"]["style"]
    assert (lb["width"], lb["height"], lb["zooms"], lb["cards"]) == (1080, 1920, [], []) and ly["title"] == "so this is how i edit", ly
    assert all(len(c["words"]) == 1 and c["text"].islower() for c in lb["captions"]["chunks"]) and cs["color"] == LB_HIGHLIGHT
    assert ly["band"] == [0, 34.18, 100, 31.64] and ly["card"]["src"] == "images/n.png" and ly["card"]["to"] == 2.05, ly
    px = lambda b: (b[0] * 10.8, b[1] * 19.2, (b[0] + b[2]) * 10.8, (b[1] + b[3]) * 19.2)
    word_y = cs["y_pct"] * 19.2
    for x0, y0, x1, y1 in (px(ly["title_box"]), px(ly["card"]["box"]), (540 - cs["width_pct"] * 5.4, word_y - 30, 540 + cs["width_pct"] * 5.4, word_y + 30)):
        assert LB_SAFE[0] - 0.5 <= x0 and LB_SAFE[1] - 0.5 <= y0 and x1 <= LB_SAFE[2] + 0.5 and y1 <= LB_SAFE[3] + 0.5, (x0, y0, x1, y1)
    assert px(ly["title_box"])[3] < ly["band"][1] * 19.2 < word_y < (ly["band"][1] + ly["band"][3]) * 19.2
    right_head = {"heads": [{"t": 0, "box": [60, 20, 20, 40]}]}
    lr = letterbox_plan({"fps": 30}, {}, words, meta, imgs, right_head, {"title": "My Title"})["layout"]
    assert lr["card"]["box"][0] == round(100 * LB_SAFE[0] / 1080, 2) and lr["title"] == "my title", lr
    assert "card" not in build(style, words, meta, layout={"mode": "letterbox"})["layout"]
    assert build({**style, "layout": {"mode": "letterbox"}}, words, meta)["layout"]["mode"] == "letterbox"   # style.json picks it
    kit = {"cues": {n: {"attack_s": 0.2} for n in SFX_RANK}}
    sp = {"fps": 30, "durationInFrames": 300, "zooms": [{"start": 1.25}, {"start": 6.0}],
          "cards": [{"start": 1.0, "end": 3.0, "anim": {"type": "flow", "props": {"nodes": [{"at": 0.5}, {"at": 0.6}],
                                                                                   "tag": {"at": 1.5}}}},
                    {"start": 7.0, "end": 8.0, "src": "images/a.png"}]}
    sw = [{"text": t, "start": s, "end": s + 0.2} for t, s in (("a", 2.6), ("b", 2.9), ("c.", 7.5))]
    cues = place_sfx(sp, sw, kit)
    ev = [(c["event"], c["src"]) for c in cues]
    assert ev == [(1.1, ".sfx/whoosh-in.wav"), (2.5, ".sfx/hit.wav")], ev   # 10 s: two cues, the highest ranked
    assert all(abs(c["t"] - (c["event"] - 0.2)) < 0.5 / sp["fps"] for c in cues)   # started early by the attack
    # on a frame: Sfx.tsx starts a cue on frame round(t x fps); a t between frames played up to half a frame
    # early, and check.py's cue check (from t on) missed most of a short pop (the 12.9 s pop of the real run)
    ntsc = 30000 / 1001
    assert all(abs(c["t"] * ntsc - round(c["t"] * ntsc)) < 0.01 for c in place_sfx({**sp, "fps": ntsc}, sw, kit))
    assert all(b["event"] - a["event"] >= SFX_GAP_S for a, b in zip(cues, cues[1:]))   # 1.25 zoom and 1.6 pop lost
    sp["durationInFrames"] = 90   # 3 s: room for one cue, the highest ranked
    assert [c["src"] for c in place_sfx(sp, sw, kit)] == [".sfx/hit.wav"]
    sp["cards"][1]["entrance"] = "scale"
    sp["durationInFrames"] = 600
    assert ".sfx/whoosh-in.wav" not in [c["src"] for c in place_sfx(sp, sw, kit) if c["event"] > 7]   # a scaled card lands silent
    # anti-generic: stock captures and icon-only cards dropped, emoji stripped
    quiet = []
    ag = anti_generic([{"word": "a", "kind": "capture", "url": "https://unsplash.com/photos/x"},
                       {"word": "b", "kind": "anim", "type": "flow", "props": {"nodes": [{"icon": "mail"}, {"icon": "inbox"}]}},
                       {"word": "c", "kind": "anim", "type": "flow", "props": {"nodes": [{"icon": "mail"}, {"logo": "notion"}]}},
                       {"word": "d", "kind": "anim", "type": "arrow_callout", "props": {"text": "ship it \U0001F680"}}], None, quiet.append)
    assert [v["word"] for v in ag] == ["c", "d"] and ag[1]["props"]["text"] == "ship it" and len(quiet) == 3, (ag, quiet)
    assert ANIMS[:len(TEMPLATES)] == TEMPLATES and all(t in ANIMS for t in LEGACY + OVERLAYS) and not set(ANIMS) & set(TYPE_ONLY)
    # layouts: overlay first; a scene or the split panel only when a beat asks (an icon_burst on vertical goes in
    # the split panel when the split layout is on)
    fr = lambda t, a="9:16", **k: frame_of({"anim": {"type": t}, "trigger_word": "x", **k}, a)
    # a diagram is an overlay over the footage unless the beat asks for a scene (the speaker stays on screen)
    assert (fr("shot"), fr("flow"), fr("icon_burst"), fr("logo_sting"), fr("flow", layout="split"), fr("flow", layout="scene"),
            fr("flow", layout="box"), fr("flow", "16:9")) == ("box", "box", "split", "box", "split", "scene", "box", "box")
    assert frame_of({"src": "images/c.png", "trigger_word": "x"}, "9:16") == "box"
    assert (fr("chat", "16:9"), fr("icon_burst", "16:9", layout="split"), fr("arrow_callout", "16:9")) == ("box", "box", "box")
    # type cards are gone: an old visuals.json naming one is skipped
    assert type_only({"type": "counter"}) and type_only({"type": "versus"}) and not type_only({"type": "side_by_side"})
    # words alone are no card in a card edit: notes needs an avatar and a frame, terminal/chat a logo or picture
    assert words_only("notes", {"lines": [{"text": "Feedback"}]}) and words_only("terminal", {"lines": [{"text": "ls"}]})
    assert not words_only("notes", {"avatar": "images/a.jpg", "lines": [{"text": "Feedback", "src": "images/f.jpg"}]})
    assert not words_only("chat", {"logo": {"logo": "claude"}, "messages": [{"text": "hi"}]}) and not words_only("likes", {})
    ce = {"card_kinds": ["capture", "logo", "photo", "animation"]}
    tm = {"kind": "anim", "type": "terminal", "word": "skill", "props": {"lines": [{"text": "update skill"}]}}
    nt = {"kind": "anim", "type": "notes", "word": "feedback", "props": {"lines": [{"text": "Feedback", "word": "feedback"}]}}
    assert [i["anim"]["type"] for i in anim_items([tm, nt], None, ce)] == ["notes"]   # notes waits for take_frames
    assert [i["anim"]["type"] for i in anim_items([tm, nt], None, {})] == ["terminal", "notes"]   # text allowed: kept
    with tempfile.TemporaryDirectory() as td:   # take_frames: the avatar and a frame of the take, then the card passes
        v = Path(td) / "cut.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=s=180x320:d=3", "-pix_fmt", "yuv420p", str(v)], check=True)
        cs = take_frames([{"start": 1.0, "trigger_word": "feedback", "anim": {"type": "notes", "props": {"lines": [{"text": "Feedback", "at": 0.1}]}}}],
                         td, v, {"step_s": 0.5, "heads": [{"t": 1.0, "box": [30, 20, 40, 30]}]})
        p_ = cs[0]["anim"]["props"]
        assert (Path(td) / p_["avatar"]).exists() and (Path(td) / p_["lines"][0]["src"]).exists(), p_
        assert drop_words_only(cs, ce) == cs and drop_words_only([{"trigger_word": "x", "anim": tm}], ce) == []
        pg = take_frames([{"start": 0.5, "end": 2.5, "trigger_word": "x", "anim": {"type": "progress", "props": {"label": "Rendering"}}}], td, v)
        assert len(pg[0]["anim"]["props"]["thumbs"]) == 4 and not words_only("progress", pg[0]["anim"]["props"]), pg
    assert words_only("progress", {"label": "Rendering"})
    vm = {**meta, "width": 1080, "height": 1920}
    tv = [{"word": "notion", "nth": 1, "kind": "anim", "type": "flow", "layout": "scene", "props": {"nodes": [{"logo": "notion"}]}},
          {"word": "every", "nth": 1, "kind": "anim", "type": "caption_page", "hold_s": 2, "props": {}}]
    vp = build(style, words, vm, visuals=tv)
    assert vp["captions"]["style"]["width_pct"] == 74.0, vp["captions"]["style"]   # vertical captions inside the safe zone
    assert "layout" not in vp and vp["motion"] == "smooth" and vp["look"] == {"preset": "neutral"}, vp   # no panel, no house palette
    cp = next(c for c in vp["cards"] if c["anim"]["type"] == "caption_page")
    assert cp["layout"] == "box" and [w["text"] for w in cp["anim"]["props"]["words"]][:2] == ["every", "video"], cp
    assert cp["anim"]["props"]["words"][0]["start"] == round(next(w for w in words if w["text"] == "every")["start"] - cp["start"], 3)
    sl = next(c for c in vp["cards"] if c["anim"]["type"] == "flow")
    assert sl["layout"] == "scene" and sl["box"] == SCENE_BOX and sl["focus"] == [50, 31] \
        and (sl["transition_in"], sl["transition_out"]) == TRANSITIONS and "_f" not in sl, sl
    st = build({**style, "transitions": ["push", "block"]}, words, vm, visuals=tv + [
        {"word": "edit.", "nth": 1, "kind": "anim", "type": "flow", "layout": "scene", "props": {"nodes": [{"logo": "github"}]}}])
    assert [c["transition_in"] for c in st["cards"] if c.get("layout") == "scene"] == ["push", "block"]
    # a creator measured as only cutting ("transitions": []) gets hard cuts, not the match/iris default
    sc = [c for c in build({**style, "transitions": []}, words, vm, visuals=tv)["cards"] if c.get("layout") == "scene"]
    assert [(c["transition_in"], c["transition_out"]) for c in sc] == [("cut", "cut")], sc
    # a hard cut lands on its first frame: no SCENE_LEAD_S, it starts CARD_LEAD_S before its word like a box card;
    # a scene whose ground grows (match) keeps the lead
    wn = next(w["start"] for w in words if clean(w["text"]).lower() == "notion")
    assert sc[0]["start"] == round(wn - CARD_LEAD_S, 3), (sc[0]["start"], wn)
    assert sl["start"] == round(max(0.0, wn - CARD_LEAD_S - SCENE_LEAD_S * MOTION_K["smooth"]), 3) < sc[0]["start"], sl["start"]
    sp2 = build(style, words, vm, [{"src": "images/c.png", "word": "every", "nth": 1}], visuals=tv[:1])
    assert "layout" not in sp2 and [c["layout"] for c in sp2["cards"]] == ["box", "scene"], sp2["cards"]
    assert build(style, words, vm, visuals=[{"word": "zooms", "kind": "anim", "type": "counter", "opt_in": True, "props": {"to": 3}}])["cards"] == []
    # an overlay goes to the free region its picture fills best; on vertical only the band above the head is centred
    # (check.py plan FAILs a card beside the head), so a tall one goes there too
    hd_face = {"step_s": 0.5, "heads": [{"t": float(i) / 2, "box": [32, 34, 28, 23]} for i in range(30)]}
    wide = {"src": "images/w.png", "size": [1800, 600], "start": 0.0, "end": 2.0, "trigger_word": "w", "box": [1, 1, 1, 1]}
    tall = {"src": "images/t.png", "size": [600, 1400], "start": 0.0, "end": 2.0, "trigger_word": "t", "box": [1, 1, 1, 1]}
    lc = {"anim": {"type": "logo_cluster", "props": {}}, "start": 0.0, "end": 2.0, "trigger_word": "l", "box": [1, 1, 1, 1]}
    pw, pt, pl = place_overlays([wide, tall, lc], hd_face, 68, "9:16")
    # a close face fills the top: the photo goes below the chin, over the body, inside the side margins, never
    # over the captions (the band above the head is too thin to read)
    close = {"step_s": 0.5, "heads": [{"t": float(i) / 2, "box": [28, 12, 44, 26]} for i in range(30)]}
    [lo] = place_overlays([dict(wide)], close, 52.6, "9:16")
    assert lo["box"][1] >= 52.6 + 5 and lo["box"][0] == SAFE["9:16"][2] and lo["box"][1] + lo["box"][3] <= 100 - SAFE["9:16"][3], lo["box"]
    # a capture that is mostly picture (a book cover with a small caption) is kept for the picture
    cover = {"src": "images/c.png", "size": [600, 800], "pics": [[20, 20, 560, 700]], "lines": [[40, 740, 300, 20]], "box": [14, 58, 72, 20]}
    assert picture_share(cover) > 0.8 and capture_xh(cover, "9:16") is None and readable_captures([cover], "9:16") == [cover]
    assert 50 <= max(px for px in range(40, 59, 2) if 32 * px * LB_TITLE_EM <= 800) < LB_TITLE_PX   # a 32-character title: one line, near full size
    # a card under the captions that would slide down through them comes up from the bottom instead
    sl = {"src": "x.png", "box": [14, 60, 72, 18], "props": {"enter": {"kind": "slide", "dir": "top", "dist": 26}, "exit": {"kind": "slide", "dir": "left", "dist": 20}}}
    [sl] = clear_caption_paths([sl], 52.6, "9:16")
    assert sl["props"]["enter"]["dir"] == "bottom" and sl["props"]["exit"]["dir"] == "left", sl
    lw2 = [{"text": t, "start": 0.3 * i, "end": 0.3 * i + 0.2} for i, t in enumerate("I think you have a horrible mindset and you need".split())]
    assert letterbox_title(lw2) == "i think you have a horrible mindset", letterbox_title(lw2)
    assert pw["box"][:3] == [13.0, OVERLAY_TOP, 74.0] and pw["box"][1] + pw["box"][3] <= 34 - HEAD_GAP + 1e-6, pw["box"]
    assert pt["box"] == pw["box"], pt["box"]
    assert pl["box"] == [0, 0, 100, 100] and pl["anim"]["props"]["head"] == [32, 34, 28, 23], pl
    assert pl["anim"]["props"]["band"] == list(LOGO_BAND) and pl["anim"]["props"]["size"] == LOGO_SIZE, pl   # big, centred
    # a logo in passing leaves when its sentence ends, not 1.2 s later over the next one
    lw = [{"text": t, "start": 0.5 * i, "end": 0.5 * i + 0.4} for i, t in enumerate("models like Claude. jev is good".split())]
    lg2 = place_cards([{"word": "Claude", "anim": {"type": "logo"}, "lane": "logo", "hold_s": LOGO_S}], lw, 5, {}, "9:16")
    assert lg2[0]["end"] == lw[3]["start"], lg2
    # a sticker's rendered x-height: 26.5 PNG px, a 777 x 315 PNG in a 92% x 21.6% box on 1080 x 1920
    # (Overlays.tsx Sticker: the padding trimmed to 727 x 265, fitted in 98% of the box less a 12 px edge)
    st = {"format": "sticker", "size": [777, 315], "xh": 26.5, "box": [4, 10, 92, 21.6]}
    assert 34.4 < sticker_xh(st, "9:16") < 34.8, sticker_xh(st, "9:16")
    assert abs(capture_scale(st, "9:16") * 26.5 - sticker_xh(st, "9:16")) < 1e-6   # one model for both
    lab = {**st, "props": {"label": "example.com"}}   # a source row takes height and a wider edge
    assert sticker_area(lab, "9:16")[1] < sticker_area(st, "9:16")[1] - 60, sticker_area(lab, "9:16")
    # capture beat format and props reach the card by capture index; a browser gets the beat's url
    wf = with_formats([{"src": "images/capture-2-docs.png", "word": "x"}], [{"kind": "capture", "url": "https://a.b"},
        {"kind": "capture", "url": "https://c.d", "format": "browser", "props": {"label": "docs"}}])
    assert wf[0]["format"] == "browser" and wf[0]["props"] == {"label": "docs", "url": "https://c.d"}, wf
    # capture marks: at_word -> at, at_s -> at, neither -> 0.8
    mk = build(style, words, vm, [{"src": "images/c.png", "word": "every", "hold_s": 3, "marks": [
        {"kind": "box", "rect": [0, 0, 9, 9], "at_word": "zooms"}, {"kind": "ring", "rect": [0, 0, 9, 9], "at_s": 2.0},
        {"kind": "dim", "rect": [0, 0, 9, 9]}]}])["cards"][0]
    zw = next(w for w in words if w["text"] == "zooms")
    assert [m["at"] for m in mk["marks"]] == [round(zw["start"] - mk["start"], 3), 2.0, 0.8] and "at_word" not in mk["marks"][0], mk
    assert pick_motion({"pace": {"median_shot_s": 1.0}}) == "punchy" and pick_motion({"motion": {"personality": "calm"}}) == "calm"
    assert pick_motion({"pace": {"median_shot_s": 3.98}}) == "smooth" and pick_motion({}) == "smooth"
    em = mark_emph([{"words": [{"text": "so", "start": 0, "end": 0.1}, {"text": "really", "start": 0.1, "end": 0.6},
                               {"text": "fast", "start": 0.6, "end": 0.75}]}])
    assert em[0]["words"][1].get("emph") and not em[0]["words"][0].get("emph")
    # behind: a wide shot above the head grows down behind the hair, its mark stays clear of the head
    bf = {"step_s": 0.5, "heads": [{"t": float(i) / 2, "box": [32, 34, 28, 23]} for i in range(10)]}
    sh = {"src": "a.png", "format": "shot", "size": [1800, 800], "start": 0.0, "end": 3.0, "trigger_word": "s", "box": [4, 10, 92, 21.6],
          "marks": [{"kind": "highlight", "rect": [100, 100, 1600, 200]}]}
    low = {**sh, "marks": [{"kind": "highlight", "rect": [100, 650, 1600, 140]}], "trigger_word": "low"}
    chat = {"anim": {"type": "chat", "props": {}}, "start": 0.0, "end": 3.0, "trigger_word": "c", "box": [4, 10, 92, 21.6]}
    vc = {"anim": {"type": "video_card", "props": {}}, "start": 0.0, "end": 3.0, "trigger_word": "v", "box": [4, 10, 92, 21.6]}
    gs, gl, gc, gv = tuck_behind([dict(sh), dict(low), dict(chat), dict(vc)], bf, "9:16")
    assert gs["layer"] == "behind" and gs["box"][1] + gs["box"][3] > 34 and gs["key"][1] + gs["key"][3] < 34 - HEAD_GAP, gs
    assert gl["box"][1] + gl["box"][3] < gs["box"][1] + gs["box"][3], (gl, gs)    # a low mark tucks less
    # a moving card tucks too (it fills the band down to the hairline), its key part clear of the head; a clip does not
    assert gc["layer"] == "behind" and gc["key"][1] + gc["key"][3] < 34 - HEAD_GAP + 0.1, gc
    assert "layer" not in gv and gv["box"] == vc["box"]
    # the creator's measured fields: dealt in her shares, used only when the blend took their part
    d = deal({"cut": 58, "slide": 12}, 12)
    assert d.count("cut") == 10 and d[:2] == ["cut", "cut"] and deal({"x": 1}, 2) == ["x", "x"] and deal({}, 1) == [None]
    assert fit_of({"kind": "slide", "ease": "back.out(3.5)", "duration_s": 0.325, "from": "top", "distance_pct": 3.5}, "9:16") == \
        {"kind": "slide", "ease": "back.out(3.5)", "dur": 0.325, "dir": "top", "dist": 6.2}
    assert fit_of({"kind": "cut", "duration_s": 0.0}, "9:16", out=True) == {"kind": "cut", "ease": "none", "dur": 0}
    her = {**style, "graphics": {"entrances": [{"kind": "cut", "ease": "none", "share_pct": 60, "duration_s": 0},
                                              {"kind": "fade", "ease": "none", "share_pct": 40, "duration_s": 0.85, "fade": True}],
                                "exits": [{"kind": "cut", "ease": "none", "share_pct": 100, "duration_s": 0}],
                                "secondary_motion": {"still": 50, "push": 50}, "kinds": {"text card": 55, "real screenshot": 40},
                                "layout": {"zones_pct": {"top": 100}}},
           "hook": {"winner": {"first_graphic_s": 0.4}, "control": {"first_graphic_s": 4.3}},
           "camera": {"pan_per_min": 6.8}, "pace": {"cut_kinds": {"zoom-punch": 1, "hard": 3}}}
    caps = [{"src": f"images/capture-{i}-x.png", "word": w} for i, w in enumerate(("so", "every", "try"), 1)]
    hp = build(her, words, vm, caps)
    assert [c["entrance"] for c in hp["cards"]] == ["cut", "fade", "cut"], hp["cards"]
    c0 = hp["cards"][0]
    assert c0["props"]["enter"] == {"kind": "cut", "ease": "none", "dur": 0} and c0["props"]["exit"]["kind"] == "cut"
    assert c0["props"]["ambient"] == "still" and c0["format"] == "sticker" and hp["cards"][1]["format"] == "shot", hp["cards"]
    assert c0["props"]["word_at"] == round(words[0]["start"] - c0["start"], 3) and "_word_t" not in c0
    assert hp["targets"]["first_graphic_s"] == 0.4 and len(hp["pans"]) == round(t / 60 * 6.8) and "props" not in caps[0]
    no = build({**her, "blend": {"take": ["captions"]}}, words, vm, caps)   # parts not taken: the defaults
    assert all("enter" not in (c.get("props") or {}) for c in no["cards"]) and "targets" not in no and "pans" not in no
    assert [c["entrance"] for c in no["cards"]] == [c["entrance"] for c in build(style, words, vm, caps)["cards"]]
    # her layout leans a tall card to the top band, still clear of the head
    pt2 = place_overlays([dict(tall)], hd_face, 68, "9:16", {"zones_pct": {"top": 90, "middle": 10}})[0]
    assert pt2["box"][1] == OVERLAY_TOP and pt2["box"][1] + pt2["box"][3] <= 34 - HEAD_GAP + 1e-6, pt2["box"]
    assert heat({"grid": [[100, 0], [0, 0]]}, [0, 0, 50, 50]) == 1 and heat({"zones_pct": {"top": 40}}, [0, 10, 90, 20]) == 0.4
    # cut_kinds: a quarter of the cuts punch in
    cz = place_zooms({"per_min": 120 / t, "on": "every_cut"}, words, t, [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0], {"zoom-punch": 1, "hard": 3})
    assert [(z["start"], z["end"]) for z in cz] == [(2.0, 6.0)], cz   # 2 of 8 cuts change the zoom: in at 2, out at 6
    # her rate holds when the take has fewer cuts than hers: the rest land on sentence starts
    cz = place_zooms({"per_min": 360 / t, "on": "every_cut"}, words, t, [2.0], {"zoom-punch": 1, "hard": 3})
    assert len(cz) >= 2, cz   # one cut alone gave none
    # her sound: none a minute -> no cues; impact only -> no whooshes
    assert place_sfx(sp, sw, kit, {"sfx_per_min": 0}) == []
    assert all("whoosh" not in c["src"] for c in place_sfx(sp, sw, kit, {"kinds": {"impact": 100}}))
    if "impact" in kit["cues"]:   # mostly impacts: the zooms and scene cuts take the low boom
        assert {c["src"] for c in place_sfx(sp, sw, kit, {"kinds": {"impact": 57, "pop": 7}})} <= {".sfx/impact.wav", ".sfx/pop.wav"}
    # one lead model for plan, renderer and check: motion.ts carries the same two numbers
    ts = (Path(__file__).resolve().parents[3] / "remotion" / "src" / "motion.ts").read_text(encoding="utf-8")
    assert f"CARD_LEAD_S = {CARD_LEAD_S};" in ts and f"OVERLAY_LEAD_S = {OVERLAY_LEAD_S};" in ts, "motion.ts lead drifted"
    # the default style (no creator) on a 47 s cut whose sentences run 2-7 s: a zoom change at least every 5 s,
    # so check.py render never finds 6 s with nothing moving (the editorial {} planned 0 zooms here)
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
    from ai_editor.profile import DEFAULT_STYLE
    t, words = 0.0, []
    for n in [5, 4, 3, 7, 2, 4, 3, 2, 4, 3, 2, 3, 3] * 2:
        for k in range(int(n / 0.3)):
            words.append({"text": "word." if k == int(n / 0.3) - 1 else "word", "start": round(t, 2), "end": round(t + 0.25, 2)})
            t += 0.3
        t += 0.1
        if t > 47:
            break
    z = place_zooms(DEFAULT_STYLE["zoom"], words, t, [])
    moves = sorted([x["start"] for x in z] + [x["end"] for x in z if x["end"] < t])
    assert len(z) >= t / 10 and max(b - a for a, b in zip([0.0] + moves, moves + [t])) <= 5.0 + 1e-6, (t, moves)
    assert place_zooms({}, words, t, []) == []
    # every style page preset shows up in the plan (lib/ai_editor/presets.py)
    from ai_editor import presets
    pv = {**vm, "duration": t}
    for name, p in presets.ZOOM.items():
        zs = build(with_presets(DEFAULT_STYLE, {"zoom": {"preset": name}}), words, pv)["zooms"]
        assert (not zs) if name == "none" else zs and {(z["kind"], z["scale"]) for z in zs} == {(p["zoom"]["kind"], p["zoom"]["scale"])}, (name, zs[:2])
    for name, block in presets.captions().items():
        cs = build(with_presets(DEFAULT_STYLE, {"captions": {"preset": name}}), words, pv)["captions"]
        assert cs["style"]["effect"] == block["effect"] and cs["style"]["size_pct"] == block["size_pct"], (name, cs["style"])
        assert all(len(c["words"]) <= block.get("words_per_caption", 3) for c in cs["chunks"]), name
    many = [{"src": f"images/{i}.png", "word": "word", "nth": 5 * i + 1} for i in range(12)]   # 1.5 s apart: each shows 1.2 s
    for name, p in presets.CARDS.items():
        n = len(build({**DEFAULT_STYLE, "cards": {"per_min": p["per_min"]}}, words, pv, many)["cards"])
        assert n <= math.ceil(t / 60 * p["per_min"]), (name, n)
    assert len(build({**DEFAULT_STYLE, "cards": {"per_min": 99}}, words, pv, many)["cards"]) == 12
    assert build({**DEFAULT_STYLE, "cards": {"on": False}}, words, pv, many)["cards"] == []
    assert build({**DEFAULT_STYLE, "cards": {"per_min": 0}}, words, pv, many)["cards"] == [], "0 a minute is none, not unlimited"
    assert len(build(DEFAULT_STYLE, words, pv, many)["cards"]) <= math.ceil(t / 60 * 4), "the default style lands cards Sometimes"
    assert len(build({k: v for k, v in DEFAULT_STYLE.items() if k != "cards"}, words, pv, many)["cards"]) == 12, "no cap when none is set"
    for name in presets.LOOKS:
        assert build({**DEFAULT_STYLE, "look": {"preset": name}}, words, pv)["look"]["preset"] == name, name
    # the sample's punch at 28.05 s, 0.15 s before a flow scene at 28.2 s, snapped: a zoom change in a scene's
    # entrance goes under the scene (hidden); before a box card it finishes before the card starts; two zooms
    # closer than a punch's travel join (the out move would be cut short)
    zp = lambda a, b: {"start": a, "end": b, "scale": 1.18, "kind": "punch", "ease_s": 0}
    sc = clear_entrances([zp(24.0, 28.5), zp(31.0, 34.0)], [{"start": 28.2, "end": 36.0, "layout": "scene"}])
    assert [(z["start"], z["end"]) for z in sc] == [(24.0, 34.0)], sc
    bx = clear_entrances([zp(24.0, 28.5)], [{"start": 28.2, "end": 30.0, "layout": "box"}])
    assert bx[0]["end"] + PUNCH_S <= 28.2 - ENTER_S[0] + 1e-6, bx
    assert len(clear_entrances([zp(1.0, 3.0), zp(3.1, 5.0)], [])) == 1
    # a punch that a scene would swallow lands as the scene leaves
    assert [(z["start"], z["end"]) for z in clear_entrances([zp(10.0, 11.4)], [{"start": 10.1, "end": 12.8, "layout": "scene"}])] == [(13.55, 14.95)]
    with tempfile.TemporaryDirectory() as td:   # an audio clip: its cover moves on sentence starts, no zooms
        assert audio_cover(td, words) is None
        (Path(td) / "cover.png").write_bytes(b"")
        (Path(td) / "clip.json").write_text(json.dumps({"audio_only": True, "cover": "cover.png", "cover_box": [20, 17, 59, 33]}), encoding="utf-8")
        cv = audio_cover(td, words)
        assert cv["src"] == "cover.png" and cv["push"] > 1 and cv["pulses"] and cv["pulses"][0] >= 0.5, cv
        assert all(b - a >= 1 for a, b in zip(cv["pulses"], cv["pulses"][1:])), cv["pulses"]
    # a creator's sparse zooms (no max_hold_s) leave 12 s still; inside a stretch with no card (quiet) the frame
    # changes at least every QUIET_HOLD_S, and outside it her rhythm is untouched
    sparse = {"per_min": 2, "kind": "punch", "on": "sentence_start"}
    mv = lambda zs, a, b: sorted(x for z in zs for x in (z["start"], z["end"]) if a < x < b)
    hold_in = lambda zs, a, b: max(y - x for x, y in zip([a] + mv(zs, a, b), mv(zs, a, b) + [b]))
    assert hold_in(place_zooms(sparse, words, t, []), 10, 22) > QUIET_HOLD_S
    zq = place_zooms(sparse, words, t, [], quiet=[(10, 22)])
    assert hold_in(zq, 10, 22) <= QUIET_HOLD_S + 1e-6, mv(zq, 10, 22)
    assert mv(zq, 30, t) == mv(place_zooms(sparse, words, t, []), 30, t)
    assert card_gaps([{"start": 1, "end": 3}, {"start": 2, "end": 4}, {"start": 9, "end": 10}], 12) == [(0.0, 1), (4, 9), (10, 12)]
    assert card_gap_s({}) == GAP_S and card_gap_s({"graphics": {"per_min": 5.0}}) == 24.0
    # a card edit (card_kinds without "text"): a re-set sentence (capture.mjs "xh") is dropped, a sticker of the page
    # itself is drawn as a shot, and a small-text screenshot stays a picture instead of being cut to a line of words
    ce = {"card_kinds": ["capture", "logo", "photo", "animation"]}
    assert pictures_only(ce) and not pictures_only({}) and not pictures_only({"card_kinds": ["capture", "text"]})
    tl = text_labels([{"src": "a", "format": "sticker", "xh": 20}, {"src": "b", "format": "sticker", "props": {"crop": [0, 0, 9, 9]}},
                      {"src": "c"}], ce)
    assert [(c["src"], c.get("format"), c.get("props")) for c in tl] == [("b", "shot", None), ("c", None, None)], tl
    assert kind_formats([{"src": "images/capture-1-a.png"}], {**ce, "graphics": {"kinds": {"text card": 100}}})[0]["format"] == "shot"
    small = {"src": "images/capture-1-a.png", "size": [2000, 1400], "box": [13, 14, 74, 20], "trigger_word": "a", "start": 1, "end": 3,
             "lines": [[100, 600, 900, 40]], "marks": [{"kind": "highlight", "find": "x", "rect": [100, 600, 900, 40]}]}
    assert readable_captures([dict(small)], "9:16", True) == [small]
    assert readable_captures([dict(small)], "9:16")[0]["format"] == "sticker"
    # the card edit's title pill, running list and X stamp: on their words, inside the safe zone
    tw = [{"text": x, "start": i * 0.5, "end": i * 0.5 + 0.4} for i, x in enumerate("free credits the account the student page if not".split())]
    tx = text_items([{"kind": "title", "text": "Free credits"}, {"kind": "list", "items": [{"text": "the account", "word": "account"},
                     {"text": "the student page", "word": "student"}]}, {"kind": "stamp", "word": "not"}, {"kind": "title", "text": "x", "word": "nope"}],
                    tw, 5.0, [{"start": 3.0, "end": 4.5, "box": [13, 14, 74, 20]}], None, 66)
    assert [x["kind"] for x in tx] == ["title", "list", "stamp"], tx
    big = text_items([{"kind": "list", "items": [{"text": "the account", "word": "account"}]}], tw, 5.0, [], None, 66, 4.4)
    assert big[0]["size_pct"] == 4.4, "a list reads at the captions' size at least (QA round 4: 1.8 under 4.4)"
    with tempfile.TemporaryDirectory() as d:   # an image's own size from its header, for each format a user adds
        import struct
        png = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">IIBBBBB", 720, 1080, 8, 2, 0, 0, 0)
        (Path(d) / "a.png").write_bytes(png + b"\0" * 8)
        (Path(d) / "a.gif").write_bytes(b"GIF89a" + struct.pack("<HH", 30, 20))
        (Path(d) / "a.jpg").write_bytes(b"\xff\xd8\xff\xe0" + struct.pack(">H", 4) + b"JF" + b"\xff\xc0" + struct.pack(">HBHH", 11, 8, 1080, 720) + b"\0" * 8)
        assert [image_size(Path(d) / f) for f in ("a.png", "a.gif", "a.jpg", "none.png")] == [[720, 1080], [30, 20], [720, 1080], None]
    # no card on screen for under 1.2 s: one at the very end starts earlier, one boxed in by its neighbours goes
    ms = min_show([{"start": 1, "end": 3, "trigger_word": "a"}, {"start": 34.4, "end": 35.0, "trigger_word": "end"},
                   {"start": 3.2, "end": 3.6, "trigger_word": "tight"}, {"start": 3.7, "end": 6, "trigger_word": "b"}], 35.0)
    assert [(c["trigger_word"], c["start"], c["end"]) for c in ms] == [("a", 1, 2.5), ("tight", 2.5, 3.7), ("b", 3.7, 6),
                                                                       ("end", 33.8, 35.0)], ms
    assert tx[0]["start"] == 0 and tx[0]["y_pct"] >= SAFE["9:16"][1] and [i["at"] for i in tx[1]["items"]] == [1.4, 2.4], tx
    # the title box sits on the chest, its bottom on the safe zone's bottom line; a card above it keeps its box
    assert abs(title_bottom(tx[0]) - TITLE_BOTTOM) < 0.15 and tx[0]["y_pct"] > 60, tx[0]
    cs = [{"start": 0.5, "end": 3, "box": [13, 13.1, 74, 30]}]
    under_titles(cs, tx)
    assert cs[0]["box"] == [13, 13.1, 74, 30], cs
    # the cta owns the band: a card up with it ends as it lands, one starting under it waits until it ends
    cta = text_items([{"kind": "cta", "text": "edit", "label": "comment", "word": "page"}], tw, 5.0, [], None, 66)
    assert cta[0]["kind"] == "cta" and cta[0]["start"] == 2.9, cta
    cc = [{"start": 2.0, "end": 4.0, "box": [13, 14, 74, 20]}, {"start": 3.0, "end": 5.0, "box": [13, 14, 74, 20]}]
    under_titles(cc, cta)
    assert cc[0]["end"] == 2.9 and len(cc) == 1 or (cc[1]["start"] == cta[0]["end"]), cc
    # the title keeps its emoji; every other text loses it
    ag = anti_generic([{"kind": "title", "text": "New tool \U0001F929"}, {"kind": "anim", "type": "notes", "props": {"lines": [{"text": "ok \U0001F929"}]}}],
                      warn=lambda m: None)
    assert ag[0]["text"].endswith("\U0001F929") and ag[1]["props"]["lines"][0]["text"] == "ok", ag
    # captions never on the face: a line inside the head moves to the chin line, inside the safe zone
    fc = {"step_s": 0.5, "heads": [{"t": i / 2, "box": [35, 31, 48, 41.5]} for i in range(9)]}
    cp = {"y_pct": 64, "size_pct": 4.4}
    assert caption_under_chin(cp, fc, "9:16") == 72.5 and cp["y_pct"] == 73.1 <= 100 - SAFE["9:16"][3] - CAP_GLYPH * 4.4, cp
    ca = {"y_pct": 40, "size_pct": 4.4}   # her captions sit over her face: ours go over the head, inside the safe zone
    assert caption_under_chin(ca, fc, "9:16", above=True) is None and ca["y_pct"] == 28.9, ca
    assert above_face({"captions": {"y_pct": 38.6}, "face": {"y_pct": 48.9, "height_pct": 8.2}})
    assert not above_face({"captions": {"y_pct": 70}, "face": {"y_pct": 48.9, "height_pct": 8.2}})
    # her grade: a grey cut is pulled darker towards her luma; saturation of grey cannot be scaled, so it is held
    with tempfile.TemporaryDirectory() as gd:
        gv = Path(gd) / "g.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=0xA0A0A0:s=96x160:d=2", "-pix_fmt", "yuv420p",
                        str(gv)], check=True)
        lu, sa = footage_grade(gv)
        assert 150 < lu < 170 and sa < 0.02, (lu, sa)
        assert grade_for({"grade": {"luma": 120, "sat": 0.3}}, gv) == {"brightness": 0.76, "saturate": 1.0}
        assert grade_for({"grade": {"luma": lu, "sat": sa}}, gv) is None and grade_for({}, gv) is None
    ws = [{"text": t, "start": i, "end": i + 0.8} for i, t in enumerate("one two three. four five six seven eight nine ten eleven twelve.".split())]
    hs = hold_scenes([{"start": 0.5, "end": 1.5, "layout": "scene", "scene_by": "creator"}, {"start": 4.0, "end": 5.0, "layout": "scene",
                      "scene_by": "creator"}, {"start": 13.0, "end": 14.0}], ws, 14.0, 0.9)
    assert hs[0]["end"] == 2.8 and hs[1]["end"] == 11.8 and hs[2]["end"] == 14.0, hs   # to the sentence end, held under 8 s
    # her typography: accent keywords, a light second face, a big keyword, stacked pages; at her shares
    tw = [{"text": t, "start": i * 0.4, "end": i * 0.4 + 0.3} for i, t in enumerate(
        "we moved to london and it was the best thing so far but the rain never stops here in the city".split())]
    tc = type_pages(chunk_captions(tw, 2, "lower"), {"accent_pct": 25, "accent_keyword_pct": 80, "light_pct": 15,
                                                    "light_keyword_pct": 20, "big_ratio": 2.0, "stack_pct": 40})
    acc = [w["text"] for c in tc for w in c["words"] if w.get("emph")]
    assert acc and any(clean(a) not in STOP for a in acc), acc        # the accent lands on keyword pages, whole line
    assert sum(c.get("face") == "light" for c in tc) == round(len(tc) * 0.15) and any(c.get("big") == 2.0 for c in tc)
    assert sum(c.get("lines") == 2 for c in tc) == round(len(tc) * 0.4) and abs(page_tall(tc) - 3.14) < 0.01, tc   # a big keyword over one more line
    # a creator off screen half the time: picture cards become full-frame cut-aways, logos stay boxes
    oc, _ = lay_out([{"start": 1, "end": 3, "src": "images/a.png"}, {"start": 5, "end": 6, "lane": "logo", "src": "images/l.svg"}],
                    "9:16", None, {"face": {"present_pct": 44}}, False)
    assert [c["layout"] for c in oc] == ["scene", "box"], oc
    gs = scene_grounds([{"start": i, "scene_by": "creator", **({"anim": {"type": "notes"}} if i == 3 else {})} for i in range(4)], {"grade": {"luma": 115}})
    assert [c["ground"] for c in gs] == ["ink", "ground", "ink", "ground"], gs   # 42% paper for her 115; the notes card on paper
    assert not off_screen({"face": {"present_pct": 95}}) and not off_screen({"face": {"present_pct": 44}, "blend": {"take": ["captions"]}})
    assert caption_under_chin({"y_pct": 80, "size_pct": 4}, fc, "9:16") is None and caption_under_chin({"y_pct": 64}, None, "9:16") is None
    # a push zoom from the head's top is held so the chin stays above the captions; one that cannot move is dropped
    zz = clear_chin([{"start": 0, "end": 2, "scale": 1.15, "origin": [59, 31]}, {"start": 2, "end": 4, "scale": 1.15, "origin": [59, 70]}], fc, cp)
    assert zz[0]["scale"] == 1.15 and zz[0]["origin"][1] == 68.3 and zz[1]["scale"] == 1.15, zz   # grown from the chin instead: the head rises, kept
    assert clear_chin([{"start": 0, "end": 2, "scale": 1.15, "origin": [59, 31]}], fc, {"y_pct": 68, "size_pct": 4.4}) == []
    # one capture per page: the second capture of the same URL is dropped
    vis = [{"kind": "capture", "word": "a", "url": "https://x.dev/"}, {"kind": "capture", "word": "b", "url": "https://x.dev"},
           {"kind": "capture", "word": "c", "url": "https://y.dev"}]
    assert [i["word"] for i in one_per_page([{"word": w, "src": w} for w in "abc"], vis)] == ["a", "c"]
    assert tx[1]["end"] == 5.0 and tx[1]["x_pct"] >= SAFE["9:16"][0] and tx[2]["box"] == [13, 14, 74, 20] and tx[2]["start"] == 4.0, tx
    demo_contrast()
    demo_beats()
    print("demo ok")


def demo_contrast():
    """Caption contrast: the ladder on flat colours, then measured on real clips (ffmpeg)."""
    import tempfile
    from pathlib import Path
    white = {"color": "#FFFFFF"}
    assert pick_treat([(38, 38, 38)] * 9, white)[0] is None                   # dark: the creator's look
    assert pick_treat([(126, 126, 126)] * 9, white)[:2] == ("shadow", "#111111")
    # a grey the shadow lifts only to 3.15:1 (over the FAIL line, under the margin the render needs) gets a stroke
    assert treat_for([(160, 160, 160)] * 9, (255, 255, 255), PULL["shadow"], (17, 17, 17)) > CONTRAST_MIN
    assert pick_treat([(160, 160, 160)] * 9, white)[0] == "stroke"
    assert all(pick_treat([(g, g, g)] * 9, white)[2] >= CONTRAST_TARGET for g in range(0, 256, 8))
    # mid-grey footage reads 4.48:1 with the plain shadow: under the render check's 4.5 WARN, so it gets a step
    assert pick_treat([(128, 128, 128)] * 9, white)[0] is not None
    # "plan again" after a render check read a page too low: that page gets the next step, once per check
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "plan.json").write_text(json.dumps({"captions": {"chunks": [{"start": 1.0, "end": 2.0, "treat": "shadow"},
                                                                          {"start": 2.0, "end": 3.0}]}}), encoding="utf-8")
        (d / "check.json").write_text(json.dumps({"render": {"caption_contrast": {"low_at": [1.5]}}}), encoding="utf-8")
        assert contrast_floors(d, d / "plan.json") == {"1.00": "stroke"}
        assert contrast_floors(d, d / "plan.json") == {"1.00": "stroke"}       # the same check is read once
        pl = {"captions": {"style": {"stroke": True}, "chunks": [{"start": 1.0, "end": 2.0, "text": "a"}]}}
        assert treat_captions(pl, d, None, {"1.00": "stroke"}) == [(0, "stroke", None)]
    # the real-footage test printed 94 lines, one per page; now one line with the count and the worst three
    ch = [{"text": f"w{i}", "start": float(i)} for i in range(10)]
    got = contrast_summary([(i, "backing" if i % 3 else "stroke", 9.0 - i / 2) for i in range(9)] + [(9, "stroke", None)], ch)
    assert got.count("\n") == 0 and "10 of 10 pages" in got and "6 backing" in got and "4 stroke" in got, got
    assert "5.0:1 'w8'" in got and "'w5'" not in got and "1 from the last render check" in got, got
    assert contrast_summary([], ch) == ""
    assert pick_treat([(230, 225, 216)] * 9, white)[:2] == ("backing", "#111111")  # a bright desk
    # plain captions (the default): the soft shadow while it reads at PLAIN_MIN; under that (a page that would FAIL)
    # the soft band behind the line, never a glow smear, a stroke or a box
    plain = {"color": "#FFFFFF", "shadow": False, "style": "plain"}
    assert pick_treat([(160, 160, 160)] * 9, plain)[0] == "band" and pick_treat([(160, 160, 160)] * 9, white)[0] == "stroke"
    assert pick_treat([(126, 126, 126)] * 9, plain)[0] == "shadow"
    assert pick_treat([(190, 190, 190)] * 9, plain)[0] == "band"
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "plan.json").write_text(json.dumps({"captions": {"style": plain, "chunks": [
            {"start": 1.0, "end": 2.0, "treat": "shadow"}, {"start": 2.0, "end": 3.0, "treat": "shadow"}, {"start": 3.0, "end": 4.0, "treat": None}]}}), encoding="utf-8")
        (d / "check.json").write_text(json.dumps({"render": {"caption_contrast": {"low_at": [1.5, 2.5, 3.5], "fail_at": [2.5]}}}), encoding="utf-8")
        assert contrast_floors(d, d / "plan.json") == {"2.00": "band", "3.00": "shadow"}   # a WARN keeps the shadow
        # a minimal style with no stroke and no box got the glow from pick_treat: plan again steps it up, no crash
        mini = {"color": "#FFFFFF", "style": "minimal", "stroke": False, "box": False}
        (d / "contrast.json").unlink()
        (d / "plan.json").write_text(json.dumps({"captions": {"style": mini, "chunks": [
            {"start": 5.0, "end": 6.0, "treat": "glow"}]}}), encoding="utf-8")
        (d / "check.json").write_text(json.dumps({"render": {"caption_contrast": {"low_at": [5.5], "fail_at": [5.5]}}}), encoding="utf-8")
        assert contrast_floors(d, d / "plan.json")["5.00"] == "band"
        # one treatment per video: the strongest any page needed goes on every page
        tp = {"captions": {"style": {"color": "#FFFFFF", "stroke": True}, "chunks": [
            {"start": 5.0, "end": 6.0, "treat": "shadow", "treat_color": "#111111"}, {"start": 6.0, "end": 7.0}]}}
        treat_captions(tp, d, None, {"5.00": "backing"})
        assert [c["treat"] for c in tp["captions"]["chunks"]] == ["backing", "backing"], tp
    assert pick_treat([(230, 225, 216)] * 9, {**white, "stroke_color": "#1B2A4A"})[1] == "#1B2A4A"   # her palette
    assert pick_treat([(250, 250, 250)] * 9, {**white, "highlight_color": "#5A5A5A"})[0] == "backing"
    assert pick_treat([(20, 20, 20)] * 9, {"color": "#111111"})[:2] == ("backing", "#F5F5F5")     # dark text
    words = [{"text": t, "start": round(0.2 + i * 0.32, 2), "end": round(0.5 + i * 0.32, 2), "type": "word"}
             for i, t in enumerate("this desk is far too bright".split())]
    style = {"captions": {"words_per_caption": 3, "y_pct": 68, "size_pct": 5, "color": "#FFFFFF", "stroke": False}}
    with tempfile.TemporaryDirectory() as d:
        for colour, want in (("0xE6E1D8", {"backing"}), ("0x262626", {None})):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={colour}:s=270x480:r=30:d=2.2",
                            "-f", "lavfi", "-i", "sine=d=2.2", "-vf", "noise=alls=12:allf=t", "-pix_fmt", "yuv420p",
                            f"{d}/cut.mp4"], check=True)
            meta = probe(Path(d) / "cut.mp4")
            pl = build(style, words, meta, edit_dir=d)
            treat_captions(pl, d, meta)
            got = {c.get("treat") for c in pl["captions"]["chunks"]}
            assert got == want, (colour, pl["captions"]["chunks"])
        # no style.json (the no-creator path): a note and the default style, never a traceback
        import os
        (Path(d) / "captions.json").write_text(json.dumps(words), encoding="utf-8")
        r = subprocess.run([sys.executable, __file__, f"{d}/style.json", f"{d}/captions.json"], capture_output=True,
                           text=True, env={**os.environ, "AI_EDITOR_HOME": d})
        assert r.returncode == 0 and "default style" in r.stderr, r.stderr
        assert json.loads((Path(d) / "plan.json").read_text(encoding="utf-8"))["zooms"], r.stdout
        # a creator style with the user's corrections on it: measured 6 < taste.json 7 < style.overrides.json 4.5
        cs = Path(d) / "creator-teardowns" / "alice"
        cs.mkdir(parents=True)
        (cs / "style.json").write_text(json.dumps({"handle": "alice", **style, "captions": {**style["captions"], "size_pct": 6}}), encoding="utf-8")
        (cs / "style.overrides.json").write_text('{"captions": {"size_pct": 4.5}}', encoding="utf-8")
        (Path(d) / "taste.json").write_text('{"captions": {"size_pct": 7, "y_pct": 60}}', encoding="utf-8")
        (Path(d) / "style.json").write_text(json.dumps({**json.loads((cs / "style.json").read_text(encoding="utf-8")),
                                                         "source": [str(cs / "style.json")]}), encoding="utf-8")
        for sj in (Path(d) / "style.json", cs / "style.json"):   # the edit's copy, or the creator's file itself
            r = subprocess.run([sys.executable, __file__, str(sj), f"{d}/captions.json"], capture_output=True,
                               text=True, env={**os.environ, "AI_EDITOR_HOME": d})
            cap = json.loads((Path(d) / "plan.json").read_text(encoding="utf-8"))["captions"]["style"]
            assert r.returncode == 0 and cap["size_pct"] == 4.5 and cap["y_pct"] == 60, (r.stderr, cap)
        # the user's own caption style (custom/captions/bold.json) named in taste.json: over the creator's captions,
        # under taste.json's own keys and this style's overrides. A template's user defaults sit under a beat's props.
        lib = Path(d) / "lib"
        (lib / "custom" / "captions").mkdir(parents=True)
        (lib / "custom" / "templates").mkdir()
        (lib / "custom" / "captions" / "bold.json").write_text('{"color": "#FFE600", "y_pct": 50, "size_pct": 9}', encoding="utf-8")
        (lib / "custom" / "templates" / "flow.json").write_text('{"direction": "down", "gap": 2}', encoding="utf-8")
        (Path(d) / "taste.json").write_text('{"captions": {"size_pct": 7, "y_pct": 60, "preset": "bold"}}', encoding="utf-8")
        env = {**os.environ, "AI_EDITOR_HOME": d, "AI_EDITOR_LIBRARY": str(lib)}
        r = subprocess.run([sys.executable, __file__, str(cs / "style.json"), f"{d}/captions.json"], capture_output=True, text=True, env=env)
        cap = json.loads((Path(d) / "plan.json").read_text(encoding="utf-8"))["captions"]["style"]
        assert r.returncode == 0 and (cap["color"], cap["y_pct"], cap["size_pct"]) == ("#FFE600", 60, 4.5), (r.stderr, cap)
        old_lib = os.environ.get("AI_EDITOR_LIBRARY")
        os.environ["AI_EDITOR_LIBRARY"] = str(lib)
        try:
            got = anim_items([{"kind": "anim", "type": "flow", "word": "x", "props": {"gap": 5}}])[0]["anim"]["props"]
        finally:
            os.environ.pop("AI_EDITOR_LIBRARY") if old_lib is None else os.environ.update(AI_EDITOR_LIBRARY=old_lib)
        assert got == {"direction": "down", "gap": 5}, got


# One beat at a time, for the overlays skill: which beat made a card, and a change to just that beat.
BEAT_FILES = ("visuals.json", "images.json")


def said(words, word):
    """Start times of each time `word` is said."""
    w = clean(word).lower()
    return [x["start"] for x in words if x.get("type", "word") == "word" and clean(x["text"]).lower() == w]


def card_sources(plan, words, sources):
    """Per plan card: (nth, word time, [(file, index)]): which time its word is said and the beats that made it.
    A card starts before its word, so its word is the first time it is said from the card's start on."""
    out = []
    for c in plan["cards"]:
        w = c.get("trigger_word") or ""
        ts = said(words, w)
        nth = next((k + 1 for k, t in enumerate(ts) if t >= c["start"] - 0.01), None)
        hits = [(name, i) for name, items in sources for i, b in enumerate(items)
                if clean(b.get("word") or "").lower() == clean(w).lower() and b.get("nth", nth) == nth]
        out.append((nth, ts[nth - 1] if nth else None, hits))
    return out


def find_beats(ref, plan, words, sources):
    """'card:3' (plan.cards[3], as the review page names it), '0:15' / '15.4s' (the card up then), or
    'word' / 'word@2' -> [(file, index)] of the beats it means."""
    m = re.fullmatch(r"card:?(\d+)", ref)
    if m:
        i = int(m.group(1))
        return card_sources(plan, words, sources)[i][2] if i < len(plan["cards"]) else []
    if re.fullmatch(r"(\d+:)?\d+(\.\d+)?s?", ref):
        mm, _, sec = ref.rstrip("s").rpartition(":")
        t = (int(mm) * 60 if mm else 0) + float(sec)
        cs = plan["cards"]
        up = sorted((i for i, c in enumerate(cs) if c["start"] <= t < c["end"]), key=lambda i: cs[i].get("lane") == "logo")
        near = up or sorted((i for i, c in enumerate(cs) if min(abs(c["start"] - t), abs(c["end"] - t)) < 1.5),
                            key=lambda i: abs(cs[i]["start"] - t))
        return card_sources(plan, words, sources)[near[0]][2] if near else []
    word, _, nth = ref.partition("@")
    return [(name, i) for name, items in sources for i, b in enumerate(items)
            if clean(b.get("word") or "").lower() == clean(word).lower() and (not nth or b.get("nth", 1) == int(nth))]


def set_key(d, key, value):
    """'props.label' = value inside d; None removes the key."""
    *head, last = key.split(".")
    for k in head:
        d = d.setdefault(k, {})
    if value is None:
        d.pop(last, None)
    else:
        d[last] = value


def keep_rendered(out):
    """Before a re-plan overwrites out: a plan no newer than its render is the plan that render came from.
    Kept as render.plan.json (edit.py render writes it too), which edit.py patch diffs against."""
    rendered = out.parent / f"render{out.stem[len('plan'):]}.mp4"
    snap = rendered.with_suffix(".plan.json")
    if rendered.exists() and out.exists() and not snap.exists() and out.stat().st_mtime <= rendered.stat().st_mtime:
        snap.write_bytes(out.read_bytes())


def demo_beats():
    """plan.py cards / beat: a card traced to its beat, one beat changed, beats added in spoken order."""
    import contextlib, io, os
    words = [{"text": t, "start": s, "end": s + 0.3, "type": "word"} for t, s in
             [("This", 14.9), ("is", 15.1), ("the", 15.2), ("Duolingo", 15.42), ("one.", 15.8), ("reference", 13.2), ("Duolingo.", 17.0)]]
    words.sort(key=lambda w: w["start"])
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        (d / "captions.json").write_text(json.dumps(words), encoding="utf-8")
        (d / "visuals.json").write_text(json.dumps([{"word": "Duolingo", "nth": 1, "kind": "logo", "brand": "Duolingo"},
                                                    {"word": "Duolingo", "nth": 2, "kind": "logo", "brand": "Duolingo"}]), encoding="utf-8")
        (d / "plan.json").write_text(json.dumps({"cards": [
            {"anim": {"type": "logo"}, "lane": "logo", "start": 15.32, "end": 16.3, "trigger_word": "Duolingo", "box": [40, 50, 20, 11]},
            {"anim": {"type": "logo"}, "lane": "logo", "start": 16.9, "end": 17.9, "trigger_word": "Duolingo", "box": [40, 50, 20, 11]}]}), encoding="utf-8")

        def run(*a):
            o = io.StringIO()
            with contextlib.redirect_stdout(o):
                beat_cmd(list(a))
            return o.getvalue()
        out = run("cards", t)
        assert "card:0  15.32-16.30 s  logo  'Duolingo'@1  box 40,50,20,11  <- visuals.json[0]" in out, out
        assert "'Duolingo'@2" in out and "visuals.json[1]" in out, out
        run("beat", t, "0:15", "box=[40,17,20,11]", "props.label=Duolingo")   # 0.32 s before the card: the card it means
        vis = json.loads((d / "visuals.json").read_text(encoding="utf-8"))
        assert vis[0]["box"] == [40, 17, 20, 11] and vis[0]["props"] == {"label": "Duolingo"} and "box" not in vis[1], vis
        run("beat", t, "card:1", "hold_s=2.5")
        run("beat", t, "Duolingo@1", "props=null")
        vis = json.loads((d / "visuals.json").read_text(encoding="utf-8"))
        assert vis[1]["hold_s"] == 2.5 and "props" not in vis[0], vis
        (d / "fill.json").write_text(json.dumps([{"word": "reference", "nth": 1, "kind": "anim", "type": "flow", "props": {}}]), encoding="utf-8")
        run("beat", t, "--add", str(d / "fill.json"))
        assert [b["word"] for b in json.loads((d / "visuals.json").read_text(encoding="utf-8"))] == ["reference", "Duolingo", "Duolingo"]
        run("beat", t, "card:1", "--drop")
        assert [b.get("nth") for b in json.loads((d / "visuals.json").read_text(encoding="utf-8"))] == [1, 1]
        try:
            run("beat", t, "9:00", "box=[1,1,1,1]")
            raise AssertionError("no exit")
        except SystemExit as e:
            assert "plan.py cards" in str(e.code)
        # the rendered plan is kept before a re-plan overwrites it, once
        (d / "render.mp4").write_bytes(b"x")
        os.utime(d / "plan.json", (1, 1))
        keep_rendered(d / "plan.json")
        assert (d / "render.plan.json").read_bytes() == (d / "plan.json").read_bytes()
        (d / "plan.json").write_text("{}", encoding="utf-8")
        keep_rendered(d / "plan.json")
        assert (d / "render.plan.json").read_bytes() != b"{}"


def beat_cmd(argv):
    ap = argparse.ArgumentParser(prog="plan.py cards|beat")
    ap.add_argument("cmd", choices=["cards", "beat"])
    ap.add_argument("edit")
    ap.add_argument("ref", nargs="?", help="card:3, 0:15 or 15.4s, word or word@2; zoom@7.2 with --drop: no zoom there")
    ap.add_argument("sets", nargs="*", help="key=value (JSON, or plain text); props.label=x sets inside; key=null removes")
    ap.add_argument("--drop", action="store_true", help="remove the beat")
    ap.add_argument("--add", nargs="+", metavar="FILE", help="beats (a JSON list, e.g. a template-filler's) into visuals.json in spoken order")
    ap.add_argument("--plan", default="plan.json")
    a = ap.parse_args(argv)
    edit = Path(a.edit).resolve()
    rd = lambda n, d: json.loads((edit / n).read_text(encoding="utf-8")) if (edit / n).exists() else d
    words = rd("captions.json", None) or rd("words.json", [])
    plan = rd(a.plan, {"cards": []})
    sources = [(n, rd(n, [])) for n in BEAT_FILES]
    if a.cmd == "cards":
        sys.path.insert(0, str(Path(__file__).parent))
        from sheet import kind
        for i, (c, (nth, t, hits)) in enumerate(zip(plan["cards"], card_sources(plan, words, sources))):
            box = ",".join(f"{v:g}" for v in (round(x, 1) for x in c.get("box") or []))
            print(f"card:{i}  {c['start']:.2f}-{c['end']:.2f} s  {kind(c)}  '{c.get('trigger_word', '')}'@{nth}  box {box}"
                  + (f"  {c['layer']}" if c.get("layer") else "") + "  <- " + (", ".join(f"{n}[{j}]" for n, j in hits) or "no beat found"))
        print(f"{len(plan['cards'])} cards in {a.plan}. The stills sheet's 'card N' is card:N-1.")
        return
    changed = []
    if a.add:
        vis = dict(sources)["visuals.json"]
        at = lambda b: (said(words, b.get("word") or "")[b.get("nth", 1) - 1:] or [math.inf])[0]
        for f in a.add:
            for b in json.loads(Path(f).read_text(encoding="utf-8")):
                if at(b) == math.inf:
                    print(f"warning: '{b.get('word')}' (time {b.get('nth', 1)}) is never said in this cut; added anyway, plan.py will skip it",
                          file=sys.stderr)
                k = next((i for i, x in enumerate(vis) if at(x) > at(b)), len(vis))
                vis.insert(k, b)
                changed.append(f"added {b.get('kind')} {b.get('type') or b.get('brand') or ''} on '{b.get('word')}'".replace("  ", " "))
        (edit / "visuals.json").write_text(json.dumps(vis, indent=1), encoding="utf-8")
    elif a.ref and a.ref.startswith("zoom@") and a.drop:   # "no zoom here": kept in overrides.json, so every re-plan keeps it out
        mm, _, sec = a.ref[5:].rstrip("s").rpartition(":")
        t = (int(mm) * 60 if mm else 0) + float(sec)
        z = min(plan.get("zooms") or [], key=lambda z: 0 if z["start"] <= t < z["end"] else min(abs(z["start"] - t), abs(z["end"] - t)), default=None)
        if z is None or not (z["start"] - 1.5 <= t < z["end"] + 1.5):
            sys.exit(f"no zoom at {a.ref[5:]}: plan.json has " + (", ".join(f"{x['start']:.1f}-{x['end']:.1f}s" for x in plan.get("zooms") or []) or "none"))
        f = edit / "overrides.json"
        ov = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        ov.setdefault("zooms", {})[f"{z['start']:.3f}"] = {"deleted": True}
        f.write_text(json.dumps(ov, indent=1), encoding="utf-8")
        changed.append(f"dropped the zoom {z['start']:.1f}-{z['end']:.1f}s (overrides.json)")
    elif a.ref:
        hits = find_beats(a.ref, plan, words, sources)
        if not hits:
            sys.exit(f"no beat matches {a.ref!r}: plan.py cards {edit} lists every card and the beat it came from")
        for name, i in sorted(hits, reverse=True):
            items = dict(sources)[name]
            if a.drop:
                changed.append(f"dropped {name}[{i}] '{items[i].get('word')}'")
                items.pop(i)
                continue
            for kv in a.sets:
                k, _, v = kv.partition("=")
                try:
                    v = json.loads(v)
                except ValueError:
                    pass
                set_key(items[i], k, v)
            changed.append(f"{name}[{i}] '{items[i].get('word')}': " + json.dumps(items[i]))
        for name, items in sources:
            if any(n == name for n, _ in hits):
                (edit / name).write_text(json.dumps(items, indent=1), encoding="utf-8")
    else:
        sys.exit("give a beat (card:3, 0:15, word@2) with key=value or --drop, or --add FILE")
    for line in changed:
        print(line)
    if changed:
        print("next: a new or changed capture, logo or post needs capture.mjs first; then plan.py again (style-edit step 4)")


def effective_style(sp, prof, edit_dir, count=True):
    """style.json as the plan uses it: the measured style (the default style when missing), the style page's presets
    over it, then the user's taste.json, the corrections saved on this style and this video's own settings. So the
    user's choice > the creator > the default."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
    from ai_editor import taste, profile
    sp = Path(sp)
    style = json.loads(sp.read_text(encoding="utf-8") or "{}") if sp.is_file() else None
    if not style:
        print(f"note: {sp} {'is empty' if style == {} else 'not found'}; planning with the default style. To keep it "
              f"with the edit: python3 {Path(profile.__file__)} style {edit_dir}", file=sys.stderr)
        style = profile.default_style(prof)
    mine = taste.load_json(edit_dir, count=count, style=sp)
    return profile.fill_transitions(user_rate(taste.merge(with_presets(style, mine), mine), mine),
                                    lambda m: print(f"note: {m}", file=sys.stderr))


def user_rate(style, mine):
    """A zoom rate the user set ("fewer zooms" -> zoom.per_min) is the rate: the hold fill (max_hold_s, a change at
    least every 5 s) and the quiet-stretch fill would add the zooms back, so they stretch to one change per
    60 / per_min s. Without this a per_min under the style's own changed nothing on most takes."""
    uz = mine.get("zoom") if isinstance(mine.get("zoom"), dict) else {}
    if uz.get("per_min") and "max_hold_s" not in uz:
        z = style.setdefault("zoom", {})
        z["max_hold_s"] = max(z.get("max_hold_s") or 0, round(60 / uz["per_min"], 1))
        z["fill_quiet"] = False
    return style


def demo_face_every():
    cs = [{"start": 0.0, "end": 4.0, "trigger_word": "a"}, {"start": 4.5, "end": 7.0, "trigger_word": "b"},
          {"start": 7.5, "end": 11.0, "trigger_word": "c"}, {"start": 11.2, "end": 11.8, "trigger_word": "d"}]
    out = face_every(cs, 8)
    assert [c["trigger_word"] for c in out] == ["a", "b", "c", "d"] and out[2]["start"] == 8.5, out   # c waits for a face beat
    assert face_every([*cs[:2], {"start": 7.5, "end": 9.8, "trigger_word": "e"}], 8)[-1]["start"] == 8.5
    assert len(face_every([*cs[:2], {"start": 7.5, "end": 8.6, "trigger_word": "f"}], 8)) == 2   # too short after the wait
    held = face_every([dict(c) for c in cs[:2]], 8)
    assert held[0]["end"] == 4.5 and held[1]["end"] == 7.0, held   # held across the 0.5 s gap, never an empty panel


def demo_board():
    ws = [{"text": t, "start": i * 0.8, "end": i * 0.8 + 0.6} for i, t in enumerate(
        "So which tool should you use? I use Notion and Linear. It is fine. Then Claude writes it. Why does it work? Nobody knows.".split())]
    at = lambda w: next(x["start"] for x in ws if clean(x["text"]) == w)   # noqa: E731
    logo = lambda w, slug: {"anim": {"type": "logo", "props": {"src": f"images/logo-{slug}.svg"}}, "start": at(w) - 0.1,   # noqa: E731
                            "end": at(w) + 1.5, "trigger_word": w, "lane": "logo"}
    over = {"anim": {"type": "notes", "props": {}}, "start": at("fine") - 0.1, "end": at("fine") + 0.6, "trigger_word": "fine",
            "box": [10, 10, 80, 30]}
    cards, L = board_layout([logo("Notion", "notion"), logo("Linear", "linear"), over, logo("Claude", "claude")], ws, 20.0, None)
    b1, b2 = L["boards"]
    assert [t["label"] for t in b1["tiles"]] == ["notion", "linear"] and b1.get("question"), b1   # tiles after a question: it rises
    assert [w for w, _ in b1["heading"]] == ["which", "tool", "should", "you", "use"], b1["heading"]   # "so" dropped
    assert b1["start"] <= b1["rise"] < b1["tiles"][0]["at"] and b1["end"] <= over["start"] - 0.5, b1
    assert [w for w, _ in b2["heading"]][-1] == "claude" and b2["x"] != b1["x"] and b2["y"] > b1["y"], b2
    assert len(cards) == 1 and cards[0]["box"] == BOARD_OVERLAY_BOX[0] and cards[0]["side"] == "left"   # the overlay, left
    assert any(k[2] == 1 and k[0] < over["start"] for k in L["face"]), L["face"]   # the speaker moved right before it
    assert [q["words"][0][0] for q in L["questions"]] == ["why"], L["questions"]   # a question with no board: centred
    assert [n for _, n in L["cues"]].count("whoosh-in") == 1 and "zoom" in [n for _, n in L["cues"]], L["cues"]


def main():
    if sys.argv[1:] == ["demo"]:
        demo_face_every()
        demo_board()
        import os
        os.environ["AI_EDITOR_LIBRARY"] = tempfile.mkdtemp(prefix="plan_demo_lib_")   # never the user's custom/ folder
        return demo()
    if sys.argv[1:2] in (["cards"], ["beat"]):
        return beat_cmd(sys.argv[1:])
    ap = argparse.ArgumentParser()
    ap.add_argument("style")
    ap.add_argument("words")
    ap.add_argument("--images")
    ap.add_argument("--aspect", choices=["auto", "9:16", "16:9"], default="auto")
    ap.add_argument("--layout", choices=["overlay", "split", "letterbox", "board"], help="default: style.json layout.mode, else overlay")
    ap.add_argument("--title", help="letterbox: the title above the band (default: the first sentence, lowercase)")
    ap.add_argument("--out")
    ap.add_argument("--no-sfx", action="store_true", help="no sound cues (same as \"sfx\": false in style.json)")
    ap.add_argument("--behind", choices=["on", "off"], help="cards behind the speaker (default: the profile's answer); "
                    "on needs matte.py before stills")
    a = ap.parse_args()
    edit_dir = Path(a.words).resolve().parent
    video = edit_dir / "cut.mp4"
    if not video.exists():
        sys.exit(f"ERROR: no cut.mp4 in {edit_dir}. Run the cut skill first.")
    img = Path(a.images) if a.images else edit_dir / "images.json"
    images = json.loads(img.read_text(encoding="utf-8")) if img.exists() else []
    for x in images:   # the card fits the picture at its own ratio, centred in its box
        if isinstance(x, dict) and x.get("src") and not x.get("size") and not str(x["src"]).endswith(".json"):
            x["size"] = image_size(edit_dir / x["src"]) or x.get("size")
            if not x["size"]:
                x.pop("size")
    vis = edit_dir / "visuals.json"
    visuals = json.loads(vis.read_text(encoding="utf-8")) if vis.exists() else []
    # The user's own settings (taste skill) win over the creator's measured style; corrections saved on this
    # style (its style.overrides.json) win over the every-video ones (taste.load_json, styleskill.py).
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
    from ai_editor import taste, profile, review
    review.step(edit_dir, "plan")   # the review page's "Making the edit" bar, when it waits on this edit
    prof = profile.load()   # the start skill's answers: brand kit, what to avoid, sound
    sp = Path(a.style)
    style = effective_style(sp, prof, edit_dir)
    plan = build(style, json.loads(Path(a.words).read_text(encoding="utf-8")),
                 probe(video), images, a.aspect, cut_points(edit_dir), visuals, edit_dir,
                 {k: v for k, v in (("mode", a.layout), ("title", a.title)) if v} or None, prof, None if a.behind is None else a.behind == "on")
    out = Path(a.out) if a.out else edit_dir / "plan.json"
    treated = treat_captions(plan, edit_dir, probe(video), contrast_floors(edit_dir, out))
    line = contrast_summary(treated, plan["captions"]["chunks"])
    if line:
        print(line, file=sys.stderr)
    if a.no_sfx or (prof.get("sound") or {}).get("sfx") is False:
        plan["sfx"] = []
    want_music = music_wanted(style, prof)   # the style page's switch, else the profile, else the creator
    music = ((style.get("sound") or {}).get("music") or {}) if took(style, "sound") else {}
    bed = edit_dir / ".sfx" / "music.wav"
    if want_music and not bed.exists():   # nobody laid one (the Sound step was skipped): a generated bed at her level
        try:
            import sfx
            sfx.music(edit_dir, under_db=music.get("level_db"))
        except Exception as e:   # noqa: BLE001  no numpy outside the venv, no ffprobe: say so, check.py fails the plan
            print(f"music: this edit should have a bed and none could be made ({e}); run sfx.py music {edit_dir}", file=sys.stderr)
    if bed.exists() and want_music is not False:
        plan["music"] = {"src": ".sfx/music.wav"}   # sfx.py music: the bed, ducked under the speech
    if music.get("present_pct") is not None and music["present_pct"] < MUSIC_PCT and "music" in plan:
        print(f"music: the creator runs a bed under only {music['present_pct']}% of her videos; the bed in .sfx/music.wav "
              "is not her look: delete it and plan again unless the user asked for music", file=sys.stderr)
    from preview import apply_overrides   # edits/<name>/overrides.json, written by the preview page
    plan = apply_overrides(plan, edit_dir, out.name)
    plan = placed_sounds(plan, edit_dir)   # the sounds the user put on the timeline (sounds.json)
    allow = (style.get("look") or {}).get("allow") or []
    if allow:   # the AI tells this style asks for by name (ai_tells.for_brand): the 50/50's paper ground
        plan["allow_tells"] = list(allow)
    import matte   # a re-plan keeps the speaker's cutout wherever matte.py already cut every frame it needs
    if matte.behind_ranges(plan):
        plan["cutouts"] = matte.kept(plan, edit_dir)
        if len(plan["cutouts"]) < len(matte.behind_ranges(plan)):
            print(f"behind cards: run matte.py {edit_dir}" + (f" --plan {out.name}" if out.name != "plan.json" else "")
                  + " (it cuts only the frames not cut yet)", file=sys.stderr)
    keep_rendered(out)
    out.write_text(json.dumps(plan, indent=1), encoding="utf-8")
    from ai_tells import check_plan as ai_tells, for_brand   # the AI-made look (references/ai-tells.md)
    for f in for_brand(ai_tells(plan, visuals), prof.get("brand"), plan.get("allow_tells")):
        print(f"{'error' if f['level'] == 'BAN' else 'warning'}: AI tell '{f['tell']}': {f['where']} -> {f['fix']}", file=sys.stderr)
    print(f"{out}: {plan['width']}x{plan['height']}, {plan['durationInFrames'] / plan['fps']:.1f} s, "
          f"{len(plan['captions']['chunks'])} captions, {len(plan['zooms'])} zooms, {len(plan['cards'])} cards")
    from style_check import check as style_check, report   # the plan against the copied style (style_check.py)
    print(report(style_check(plan, style), style), file=sys.stderr)


if __name__ == "__main__":
    main()
