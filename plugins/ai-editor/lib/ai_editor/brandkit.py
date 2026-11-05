#!/usr/bin/env python3
"""The user's brand kit: one BRAND.md, read by a lenient parser, used on every video.

    python3 brandkit.py import <file.md>    copy a BRAND.md in, read it, save brand.json and the profile's "brand"
    python3 brandkit.py parse <file.md>     what the parser reads, as JSON (nothing saved)
    python3 brandkit.py show                brand.json
    python3 brandkit.py demo                self-check

Files: $AI_EDITOR_HOME/brand/ (default ~/.ai-video-editor/brand): BRAND.md (the source of truth), brand.json (what was
read from it), the logo files it names (a link is downloaded in), BRAND.draft.md (Make one with Claude), refs/ (the
pictures given to that job), job.json (its state). The template ships beside this file (BRAND.template.md).

What it reads: headings like Colours / Colors / Palette, Fonts / Typography, Logo, Voice / Tone, Words to use, Words to
avoid, Do, Don't, Captions, Sounds; a sub-heading with no kind of its own belongs to its parent. Hex codes anywhere,
with a name (the text or table cell before it) and a role (background / ground -> ground, text / ink -> ink, accent,
primary) from the line or its heading; hex codes under a Forbidden / Avoid heading are colours to avoid. Fonts as
"Display: X" / "Body: X" lines, table rows or bare names (first display, then body). A logo as a path, a link or a
markdown image under Logo or on a line naming the logo. Lists under the word and do/don't headings. Everything else is
kept as notes. Anything in <angle brackets> is a template placeholder and is skipped.

Profile "brand" (profile.py brand_look reads it): {"colors": [hex], "roles": {"ground", "ink", "accent"}, "font",
"font_body", "logo", "voice", "use", "avoid", "do", "dont", "captions", "sounds", "notes", "kit": BRAND.md path,
"use_creator": false}. "use_creator": true is the Brand page's "Use for every video" off. Stdlib only.
"""
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

TEMPLATE = Path(__file__).with_name("BRAND.template.md")
IMG_EXT = (".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif")
JOB_S = 600   # the Claude job's time limit
HEX = re.compile(r"(?<![\w&])#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![0-9a-zA-Z])")
PLACEHOLDER = re.compile(r"`[^`\n]*`|<[A-Za-z][^<>\n|]{0,118}>")   # inline code is kept: `<slug>` is not a placeholder
# heading -> kind, first match wins (the avoid kinds before the plain ones: "Forbidden colors" is not a palette)
KINDS = [("words", r"\bwords?\b|vocab|phras|wording|\bsay\b"),
         ("dodont", r"\bdos?\b.*\bdon.?ts?\b"),
         ("dont", r"don.?ts?\b|^never\b|forbidden|^avoid|banned|what not"),
         ("do", r"\bdos?\b|do's|\balways\b"),
         ("colors", r"colou?r|palette|swatch"),
         ("fonts", r"font|typograph|\btype\b|typeface"),
         ("logo", r"\blogo|wordmark|\bmark\b"),
         ("voice", r"voice|\btone\b|personality|writing"),
         ("captions", r"caption|subtitle"),
         ("sounds", r"sound|music|audio|\bsfx\b")]
ROLES = [("ground", r"\bbackground\b|\bbg\b|\bground\b|\bcanvas\b"), ("ink", r"\btext\b|\bink\b|\bforeground\b"),
         ("accent", r"\baccent\b|\bhighlight\b"), ("primary", r"\bprimary\b")]
FONT_ROLES = [("display", r"display|heading|headline|title|\bh1\b"), ("body", r"\bbody\b|\btext\b|paragraph|\bui\b|\bcopy\b"),
              ("mono", r"\bmono|\bcode\b")]


def home():
    return Path(os.environ.get("AI_EDITOR_HOME", "").strip() or Path.home() / ".ai-video-editor")


def folder():
    return home() / "brand"


def kind_of(heading):
    h = heading.lower()
    for k, rx in KINDS:
        if re.search(rx, h):
            if k == "words":
                return "avoid" if re.search(r"avoid|don|never|ban|not", h) else "use"
            if k == "dont" and re.search(r"colou?r|palette|hex", h):
                return "avoid_colors"
            return k
    return None


def clean(s):
    """A cell or label without markdown: bold, code, links, bullets, a trailing colon or full stop."""
    s = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"[*_`~]+", "", s)
    s = re.sub(r"^\s*(?:[-+>]|\d+[.)])\s+", "", s)   # a bullet or "1." (a lone "*" bullet went with the bold marks)
    return s.strip().strip(":=-–→ ").strip().rstrip(".").strip()


def cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")] if line.lstrip().startswith("|") else None


def role_in(text, roles=ROLES):
    """The role keyword that comes first in text, or None."""
    hits = [(m.start(), r) for r, rx in roles for m in [re.search(rx, text.lower())] if m]
    return min(hits)[1] if hits else None


def items(line):
    """A list line's items: the bullet text (a table row: its cells, "first: rest"), split on commas when every piece
    is a short phrase."""
    cs = [clean(c) for c in cells(line) or [] if clean(c)]
    t = cs[0] + (": " + " ".join(cs[1:]) if len(cs) > 1 else "") if cs else clean(line)
    parts = [p.strip() for p in t.split(",")]
    return parts if len(parts) > 1 and all(0 < len(p.split()) <= 4 for p in parts) else [t] if t else []


def font_name(s):
    s = clean(re.split(r"[(,;]| - | – |\bor\b|\bwith\b|\bfallback", clean(s))[0])
    s = s.strip("'\" ")
    return s if 0 < len(s) <= 40 and len(s.split()) <= 4 and not re.search(r"[.!?]$", s) else None


def find_logo(line):
    """A link or path to an image on the line, or None."""
    m = re.search(r"!\[[^\]]*\]\(([^)\s]+)", line) or re.search(r"\]\(([^)\s]+)\)", line) \
        or re.search(r"(https?://[^\s)>\"'`]+)", line) \
        or re.search(r"((?:~|\.{1,2})?/?[\w./ -]*?\w\.(?:svg|png|jpe?g|webp|gif))\b", line, re.I)
    return m.group(1).strip() if m else None


def fetch_logo(ref, base, into, unread):
    """Copy or download the logo into `into`; its path there, or None (and a line in unread)."""
    into.mkdir(parents=True, exist_ok=True)
    if re.match(r"https?://", ref):
        from net import urlopen
        import urllib.request
        ext = Path(ref.split("?")[0]).suffix.lower()
        try:
            with urlopen(urllib.request.Request(ref, headers={"User-Agent": "cooked."}), 15) as r:
                data = r.read(10 << 20)
                ct = r.headers.get("Content-Type") or ""
        except Exception as e:  # noqa: BLE001
            unread.append(f"Logo {ref}: could not download it ({e})")
            return None
        if ext not in IMG_EXT:
            ext = {"image/svg+xml": ".svg", "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}.get(ct.split(";")[0])
        if not ext:
            unread.append(f"Logo {ref}: the link is not a picture")
            return None
        dest = into / ("logo" + ext)
        dest.write_bytes(data)
        return str(dest)
    p = Path(ref).expanduser()
    if not p.is_absolute() and base:
        p = Path(base) / p
    if not p.is_file():
        unread.append(f"Logo {ref}: no file there")
        return None
    dest = into / ("logo" + p.suffix.lower())
    if p.resolve() != dest.resolve():
        shutil.copyfile(p, dest)
    return str(dest)


def parse(text, base=None, into=None):
    """BRAND.md text -> the kit (brand.json's shape). base: the folder relative logo paths start from. into: where a
    logo is copied or downloaded to (None: the logo is named, not fetched)."""
    lines = text.replace("\r\n", "\n").split("\n")
    # a table's header row (the line before |---|) is not data
    sep = re.compile(r"^\s*\|?\s*:?-{2,}")
    lines = [ln for i, ln in enumerate(lines) if not (i + 1 < len(lines) and sep.match(lines[i + 1]) and "|" in lines[i + 1])
             and not (sep.match(ln) and "|" in ln)]
    kit = {"colors": [], "fonts": {}, "logo": None, "voice": "", "use": [], "avoid": [], "do": [], "dont": [],
           "avoid_colors": [], "captions": "", "sounds": "", "notes": "", "unread": []}
    texts = {"voice": [], "captions": [], "sounds": []}
    notes, held, seen = [], 0, {}
    stack = []   # (level, kind, heading)
    loose = []   # hex codes outside a colour section: added after, when new
    fence = False
    for raw in lines:
        if raw.strip().startswith("```"):
            fence = not fence
            notes.append(raw)
            continue
        line = PLACEHOLDER.sub(lambda x: x.group(0) if x.group(0).startswith("`") else "", raw)
        if line != raw:
            held += 1
            if not HEX.search(line) and len(clean(line).split()) <= 3:   # only the label is left: nothing to read
                continue
        m = None if fence else re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            lvl, head = len(m.group(1)), clean(re.sub(r"^[\d.]+\s*", "", m.group(2)))
            while stack and stack[-1][0] >= lvl:
                stack.pop()
            k = kind_of(head) if lvl > 1 or stack else None
            if k is None and stack:
                k = stack[-1][1]
            stack.append((lvl, k, head))
            notes.append(raw)
            continue
        if not line.strip() or re.fullmatch(r"[\s\-_*|:<>=]*", line):
            if not raw.strip():
                notes.append("")
            continue
        kind, head = (stack[-1][1], stack[-1][2]) if stack else (None, "")
        used = False
        found = list(HEX.finditer(line))
        hexes = [("#" + x.group(1)).upper() for x in found]
        if hexes and kind == "avoid_colors":
            kit["avoid_colors"] += [h for h in hexes if h not in kit["avoid_colors"]]
            used = True
        elif hexes:
            cs = cells(line)
            for i, h in enumerate(hexes):
                if cs:
                    name = next((clean(c) for c in cs if c and not HEX.search(c)), "")
                    role = role_in(" ".join(c for c in cs if c and not HEX.search(c)))
                else:   # the words between this hex and its neighbours: "#e5482c (accent) and ... paper #F5F2EC as the background"
                    before = line[found[i - 1].end() if i else 0:found[i].start()]
                    after = line[found[i].end():found[i + 1].start() if i + 1 < len(found) else len(line)]
                    name, role = clean(before), role_in(after) or role_in(before)
                name = name if len(name.split()) <= 4 else ""
                role = role or (role_in(head) if kind == "colors" else None)
                row = {"hex": h, "name": name, "role": role}
                (kit["colors"] if kind == "colors" else loose).append(row)
            used = kind == "colors"
        elif kind == "colors" and re.match(r"^\s*([-*+]|\d+[.)]|\|)", line) and len(clean(line).split()) <= 6:
            kit["unread"].append(f"Colours: no hex code in \"{clean(line)[:80]}\"")
        if kind == "fonts" and not hexes:
            cs = cells(line)
            label, val = (cs[0], next((c for c in cs[1:] if clean(c)), "")) if cs else \
                (re.split(r":|→|->| = | – | - ", clean(line), maxsplit=1) + [""])[:2] if re.search(r":|→|->| = | – | - ", clean(line)) else (None, line)
            role = role_in(label, FONT_ROLES) if label is not None else None
            name = font_name(val) if val else None
            if label is None and name and re.fullmatch(r"[A-Z0-9][\w-]*( [A-Z0-9][\w-]*){0,3}", clean(line)) \
                    and not line.rstrip().endswith(":"):   # a bare name ("Fraunces"): display, then body
                role = "display" if "display" not in kit["fonts"] else "body"
            if role and name:
                kit["fonts"].setdefault(role, name)
                used = True
            elif role and label is not None and not cs and len(clean(line).split()) <= 6:
                kit["unread"].append(f"Fonts: no font name in \"{clean(line)[:80]}\"")
        if kind == "logo" or re.search(r"\blogo\b", line, re.I):
            ref = find_logo(line)
            if ref and not kit["logo"]:
                kit["logo"] = fetch_logo(ref, base, into, kit["unread"]) if into else ref
                used = bool(kit["logo"]) or kind == "logo"
        if kind in ("use", "avoid", "do", "dont") and not used:
            kit[kind] += items(line)
            used = True
        elif kind == "dodont" and not used:
            t = clean(line)
            if re.match(r"(?i)(don.?t|never|avoid|no)\b|✗|❌", t):
                kit["dont"] += items(re.sub(r"(?i)^don.?t\s*:\s*", "", t))
            else:
                kit["do"] += items(re.sub(r"(?i)^do\s*:\s*", "", t))
            used = True
        elif kind in texts and not used:
            texts[kind].append(clean(line))
            used = True
        if not used:
            notes.append(raw)
    for row in loose:   # hex codes named outside a colour section, after the palette
        if row["hex"] not in [c["hex"] for c in kit["colors"]] and row["hex"] not in kit["avoid_colors"]:
            kit["colors"].append(row)
    for row in kit["colors"]:
        seen.setdefault(row["hex"], row)
    kit["colors"] = list(seen.values())
    for k, v in texts.items():
        kit[k] = "\n".join(v).strip()
    kit["notes"] = re.sub(r"\n{3,}", "\n\n", "\n".join(notes)).strip()
    if held:
        kit["unread"].append(f"{held} line{'s' if held > 1 else ''} still hold{'s' if held == 1 else ''} the template's <placeholders>")
    return kit


def roles(kit):
    """ground / ink / accent from the kit's roles (accent, else primary); missing ones are left to brand_look's rule."""
    out = {}
    for want, have in (("ground", ("ground",)), ("ink", ("ink",)), ("accent", ("accent", "primary"))):
        for r in have:
            c = next((c["hex"] for c in kit["colors"] if c.get("role") == r), None)
            if c:
                out[want] = c
                break
    return out


def to_profile(kit, prev=None):
    """The profile's "brand" from a kit. prev: the brand saved before, for its "Use for every video" switch."""
    f = kit.get("fonts") or {}
    b = {"colors": [c["hex"] for c in kit["colors"]], "roles": roles(kit), "font": f.get("display") or f.get("body"),
         "font_body": f.get("body") if f.get("display") else None, "logo": kit.get("logo"),
         **{k: kit.get(k) for k in ("voice", "use", "avoid", "do", "dont", "captions", "sounds", "notes")},
         "kit": str(folder() / "BRAND.md"), "use_creator": bool((prev or {}).get("kit") and (prev or {}).get("use_creator"))}
    return {k: v for k, v in b.items() if v not in (None, "", [], {}) or k == "use_creator"}


def profile_path():
    return home() / "profile.json"


def read_profile():
    p = profile_path()
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def write_brand(brand):
    prof = read_profile()   # only the answered keys: profile.missing() reads the file
    prof["brand"] = brand
    home().mkdir(parents=True, exist_ok=True)
    profile_path().write_text(json.dumps(prof, indent=1), encoding="utf-8")


def save(text, base=None):
    """BRAND.md text in: written to the brand folder, read, brand.json and the profile's brand saved. The kit back."""
    d = folder()
    d.mkdir(parents=True, exist_ok=True)
    (d / "BRAND.md").write_text(text, encoding="utf-8")
    kit = parse(text, base=base or d, into=d)
    kit["source"], kit["saved"] = str(d / "BRAND.md"), time.time()
    (d / "brand.json").write_text(json.dumps(kit, indent=1), encoding="utf-8")
    write_brand(to_profile(kit, read_profile().get("brand")))
    (d / "BRAND.draft.md").unlink(missing_ok=True)
    return kit


def load():
    p = folder() / "brand.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def set_use(on):
    """The Brand page's "Use for every video": on = the kit sets the look (use_creator false)."""
    b = read_profile().get("brand") or {}
    if on and not b.get("kit"):
        raise ValueError("Add a brand kit first.")
    write_brand({**b, "use_creator": not on})


# ---------- Make one with Claude: a headless Claude Code CLI job (the plan allowance, never an API key) ----------
def job_state():
    try:
        j = json.loads((folder() / "job.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if j.get("state") == "running" and time.time() - j.get("at", 0) > JOB_S + 60:   # the window restarted under it
        j.update(state="failed", why="Claude stopped before it finished. Try again.")
    return j


def set_job(**j):
    folder().mkdir(parents=True, exist_ok=True)
    (folder() / "job.json").write_text(json.dumps({**j, "at": time.time()}), encoding="utf-8")


def job_prompt(url, about, pics):
    src = [f"- The website: {url}. Read it with WebFetch (the home page, then its stylesheet if the colours or fonts "
           "are not in the page): the real hex colours, the font-family names, and the logo's full https link."] if url else []
    if about:
        src.append(f"- What the user says about the brand: {about}")
    if pics:
        src.append("- Pictures of the brand in ./refs: " + ", ".join(pics) + ". Read each one and take the colours you can see.")
    return ("You make a brand kit file for a video editor. You run on your own with no chat: do not ask anything.\n"
            "Read ./BRAND.template.md. Write ./BRAND.draft.md in the same shape, filled from:\n" + "\n".join(src) +
            "\nRules: keep the template's headings. Replace every <placeholder> line with a real value or delete the line. "
            "Colours as hex codes with a name and a role (background, text, accent). Fonts by their real family names. "
            "The logo as its full link. Never invent a value: leave out what you could not find. "
            "Sentence case, plain words, no em dashes. Write only ./BRAND.draft.md.")


def run_job(url, about, pics, cli):
    import launcher
    d = folder()
    why = None
    if not cli:
        why = "Claude Code is not installed here, so it could not make your brand kit. Install it, or fill in the template."
    else:
        try:
            cmd = launcher.plan(claude=cli, prompt=job_prompt(url, about, pics))
            tools = ["WebFetch", "Read", "Write(./BRAND.draft.md)", "Edit(./BRAND.draft.md)"]
            with open(d / "claude.log", "w", encoding="utf-8") as log:
                p = subprocess.run(cmd[:-1] + ["--allowedTools", *tools, "-p", cmd[-1]], cwd=str(d), stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT, timeout=JOB_S)
            why = None if p.returncode == 0 else f"Claude stopped with an error (exit {p.returncode})."
        except Exception as e:  # noqa: BLE001  never left running: the page offers Try again
            why = "Claude took too long making your brand kit." if isinstance(e, subprocess.TimeoutExpired) else f"Claude Code did not start: {e}"
    if not why and not (d / "BRAND.draft.md").exists():
        why = "Claude finished without writing a brand kit."
    set_job(state="failed", why=why) if why else set_job(state="done")


def start_job(url="", about="", images=(), cli=None, wait=False):
    """Make one with Claude: images are [{"name", "data": base64 or a data: URL}], saved to refs/. Runs in a thread."""
    url, about = (url or "").strip(), (about or "").strip()[:4000]
    if url and not re.match(r"https?://", url):
        url = "https://" + url
    if not (url or about or images):
        raise ValueError("Give a website, a few lines about the brand or a picture.")
    if (job_state() or {}).get("state") == "running":
        raise ValueError("Claude is already making your brand kit.")
    d = folder()
    shutil.rmtree(d / "refs", ignore_errors=True)
    (d / "BRAND.draft.md").unlink(missing_ok=True)
    (d / "refs").mkdir(parents=True)
    shutil.copyfile(TEMPLATE, d / "BRAND.template.md")
    pics = []
    for i, im in enumerate(images or []):
        data = str(im.get("data") or "").split(",")[-1]
        name = re.sub(r"[^\w.-]+", "-", Path(str(im.get("name") or f"image{i}.png")).name)[:60]
        if Path(name).suffix.lower() not in IMG_EXT:
            continue
        (d / "refs" / name).write_bytes(base64.b64decode(data))
        pics.append(name)
    cli = os.environ.get("AI_EDITOR_CLAUDE") or shutil.which("claude") if cli is None else cli
    set_job(state="running", url=url, about=about, pics=pics)
    t = threading.Thread(target=run_job, args=(url, about, pics, cli), daemon=True)
    t.start()
    if wait:
        t.join()


def state():
    """GET /brand: the kit as read, the file, the switch, the Claude job and its draft."""
    d, j = folder(), job_state()
    md = d / "BRAND.md"
    draft = d / "BRAND.draft.md"
    b = read_profile().get("brand") or {}
    return {"kit": load() if md.exists() else None, "md": md.read_text(encoding="utf-8") if md.exists() else "",
            "use": bool(b.get("kit")) and not b.get("use_creator"), "path": str(md), "job": j,
            "draft": draft.read_text(encoding="utf-8") if draft.exists() and (j or {}).get("state") == "done" else None,
            "claude": bool(os.environ.get("AI_EDITOR_CLAUDE") or shutil.which("claude"))}


def route(h, method, path, q, body=None):
    """The Brand page's routes on the home server (h: its handler, with h.send). True when handled."""
    if not path.startswith("/brand"):
        return False
    try:
        if method == "GET" and path == "/brand":
            h.send(200, state())
        elif method == "GET" and path == "/brand/template":
            h.send(200, TEMPLATE.read_bytes(), "text/markdown; charset=utf-8")
        elif method == "GET" and path == "/brand/file":   # the logo, from the brand folder only
            p = (folder() / Path(q.get("n", [""])[0]).name)
            if p.suffix.lower() not in IMG_EXT or not p.is_file():
                h.send(404, {"error": "no such file"})
            else:
                import mimetypes
                h.send(200, p.read_bytes(), mimetypes.guess_type(p.name)[0] or "application/octet-stream")
        elif method == "POST" and path == "/brand/save":   # Import a file, Edit > Save and the Claude draft's Save
            md = str((body or {}).get("md") or "")
            if not md.strip():
                h.send(400, {"error": "The file is empty."})
            else:
                save(md)
                h.send(200, state())
        elif method == "POST" and path == "/brand/use":
            set_use(bool((body or {}).get("on")))
            h.send(200, state())
        elif method == "POST" and path == "/brand/claude":
            if (body or {}).get("clear"):
                (folder() / "job.json").unlink(missing_ok=True)
                (folder() / "BRAND.draft.md").unlink(missing_ok=True)
            else:
                start_job(body.get("url"), body.get("about"), body.get("images") or [])
            h.send(200, state())
        else:
            return False
    except ValueError as e:
        h.send(400, {"error": str(e)})
    return True


# ---------- self-check ----------
MESSY = """Acme brand stuff!!

Main colour is #e5482c (accent) and we put it on paper #F5F2EC as the background.
Text colour #1b1918

Typography
==========

## Type
Headings → **Fraunces** (Google), weight 600
body: IBM Plex Sans, 400
* not a font line at all

### Tone of voice
Dry. Warm. Never shouty.

## Do and don't
- Do: one idea per frame
- Don't: purple gradients, neon, glow

## Words we avoid
synergy, leverage, unlock

## Forbidden colours
- #7B61FF purple

## Random
Ship it on Fridays.
"""


def demo():
    import http.server
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="brandkit_demo_"))
    os.environ["AI_EDITOR_HOME"] = str(tmp / "home")
    # 1. the template: every value is a placeholder, so nothing is read and the page says so
    t = parse(TEMPLATE.read_text(encoding="utf-8"))
    assert not t["colors"] and not t["fonts"] and not t["logo"] and not t["voice"] and not t["use"] and not t["do"], t
    assert any("placeholder" in u for u in t["unread"]), t["unread"]
    assert "\u2014" not in TEMPLATE.read_text(encoding="utf-8"), "no em dashes in the template"
    # 2. a messy one: setext and odd headings, hex codes in prose, arrows, a do/don't list, words, forbidden colours
    m = parse(MESSY)
    hexes = {c["hex"]: c for c in m["colors"]}
    assert set(hexes) == {"#E5482C", "#F5F2EC", "#1B1918"}, m["colors"]
    assert roles(m) == {"accent": "#E5482C", "ground": "#F5F2EC", "ink": "#1B1918"}, roles(m)
    assert m["fonts"] == {"display": "Fraunces", "body": "IBM Plex Sans"}, m["fonts"]
    assert m["voice"].startswith("Dry.") and m["do"] == ["one idea per frame"] and m["dont"] == ["purple gradients", "neon", "glow"], m
    assert m["avoid"] == ["synergy", "leverage", "unlock"] and m["avoid_colors"] == ["#7B61FF"], m
    assert "Ship it on Fridays." in m["notes"] and "#7B61FF" not in hexes
    # 3. one written as tables, with a logo link served from a local http server (downloaded into the brand folder)
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10"/></svg>'
    (tmp / "www").mkdir()
    (tmp / "www" / "logo.svg").write_bytes(svg)

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(tmp / "www"), **k)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/logo.svg"
    tables = f"""# Northwind

## Palette
| Token | Hex | Use |
|---|---|---|
| `paper` | `#F8F5F0` | Default scene background |
| `leather` | `#1B1918` | Default text on paper |
| Cornflower | #308DED | Primary brand colour |

## Typography
| Role | Font |
|---|---|
| Headings | **Suisse Neue** |
| Body / UI | FK Grotesk Neue |

## Logo
![logo]({url})

## Captions
White, lower case, one word at a time.
"""
    try:
        kit = save(tables)
    finally:
        srv.shutdown()
    assert [c["hex"] for c in kit["colors"]] == ["#F8F5F0", "#1B1918", "#308DED"], kit["colors"]
    assert kit["colors"][0]["name"] == "paper" and roles(kit) == {"ground": "#F8F5F0", "ink": "#1B1918", "accent": "#308DED"}
    assert kit["fonts"] == {"display": "Suisse Neue", "body": "FK Grotesk Neue"}, kit["fonts"]
    assert kit["logo"] == str(folder() / "logo.svg") and Path(kit["logo"]).read_bytes() == svg, kit["logo"]
    assert kit["captions"].startswith("White") and not kit["unread"], kit["unread"]
    prof = json.loads(profile_path().read_text(encoding="utf-8"))
    b = prof["brand"]
    assert b["font"] == "Suisse Neue" and b["font_body"] == "FK Grotesk Neue" and b["roles"]["accent"] == "#308DED", b
    assert b["use_creator"] is False and b["kit"].endswith("BRAND.md") and list(prof) == ["brand"], prof   # only brand answered
    # the switch: off keeps the kit but the look stops using it (profile.brand_look)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import profile as pm
    assert pm.brand_look(b)["accent"] == "#308DED" and pm.brand_look(b)["font"] == "FK Grotesk Neue"
    set_use(False)
    assert read_profile()["brand"]["use_creator"] is True and pm.brand_look(read_profile()["brand"]) == {}
    save(tables.replace(url, "https://127.0.0.1:1/gone.svg"))   # a re-save keeps the switch; a dead link is said
    assert read_profile()["brand"]["use_creator"] is True and any("could not download" in u for u in load()["unread"])
    set_use(True)
    assert state()["use"] is True
    # 4. Make one with Claude: no CLI says so; a stub that writes nothing fails plainly; a fake one leaves a draft
    start_job(about="calm", cli="", wait=True)
    assert job_state()["state"] == "failed" and "not installed" in job_state()["why"]
    start_job(url="example.com", cli=shutil.which("true") or "true", wait=True)
    assert job_state()["state"] == "failed" and "without writing" in job_state()["why"], job_state()
    fake = tmp / "fake-claude"
    fake.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\" > args.txt\nprintf '## Colours\\n- Accent: #112233\\n' > BRAND.draft.md\n", encoding="utf-8")
    fake.chmod(0o755)
    start_job(url="https://example.com", images=[{"name": "shot.png", "data": base64.b64encode(b"png").decode()}], cli=str(fake), wait=True)
    assert job_state()["state"] == "done" and state()["draft"].startswith("## Colours"), job_state()
    args = (folder() / "args.txt").read_text(encoding="utf-8")
    assert "-p" in args and "WebFetch" in args and "Write(./BRAND.draft.md)" in args and "shot.png" in args and "example.com" in args, args
    assert (folder() / "refs" / "shot.png").read_bytes() == b"png" and "firecrawl" not in args.lower()
    save(state()["draft"])
    assert load()["colors"][0]["hex"] == "#112233" and state()["draft"] is None
    shutil.rmtree(tmp, ignore_errors=True)
    print("brandkit demo ok")


if __name__ == "__main__":
    a = sys.argv[1:]
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    if a[:1] == ["demo"]:
        demo()
    elif a[:1] == ["import"] and len(a) == 2:
        src = Path(a[1]).expanduser()
        kit = save(src.read_text(encoding="utf-8"), base=src.parent)
        print(json.dumps({k: kit[k] for k in ("colors", "fonts", "logo", "unread")}, indent=1))
    elif a[:1] == ["parse"] and len(a) == 2:
        print(json.dumps(parse(Path(a[1]).read_text(encoding="utf-8"), base=Path(a[1]).parent), indent=1))
    elif a[:1] == ["show"]:
        print(json.dumps(load(), indent=1))
    else:
        sys.exit(__doc__)
