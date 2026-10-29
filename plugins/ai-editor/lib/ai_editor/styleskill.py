#!/usr/bin/env python3
"""Every saved style is a small skill, and feedback on that style edits the skill.

    python3 styleskill.py write <style.json> [--format <skill-name>]   edit-like-<slug> for a creator, a blend or a
                                  -mine style (a "-mine" folder is named after its creator). --format links the
                                  bigger format skill when creator-teardown's skill-handoff gate passed.
    python3 styleskill.py write --mine          my-style: the user's own style (profile + taste)
    python3 styleskill.py learn <style.json> <section> "<rule>" [key=value] [--edit edits/NAME]
                                  a correction at the "this style" scope (taste.py add --style does the same)
    python3 styleskill.py demo                  self-check

Names: the home page can rename a style ("Fast cuts" -> skill fast-cuts) and give it a "Use it for" line.
Both live in <taste folder>/style-names.json, keyed "mine" or the creator slug, with the style's path.
Every write regenerates the description from the current names: what the style copies, its trigger
phrases (from its own name only), "Use for:" and a "Not for:" that names the other saved styles, so two
styles never claim the same phrase. A rename or a Use-for edit rewrites every saved style's skill.

Where: AI_EDITOR_SKILLS (a self-check that moves taste.HOME: <that folder>/skills), else <cwd>/.claude/skills when the user works in a project that has a .claude
folder, else ~/.claude/skills. The skill is thin: triggers, how to run the editor with that style, what it
copies, and "## Learned from your feedback", rebuilt from rules.json (taste.py) on every save, so a rule is
one bullet with its count, last date and any regression.

The measured style.json is never written. A correction's setting goes to style.overrides.json in the
creator's own folder (creator-teardowns/<slug>/; a re-study rewrites style.json, never this file).
taste.load_json() lays it over taste.json, so: measured style.json < taste.json (every video)
< style.overrides.json (this style) < this-video settings. The narrower, later correction wins.
Stdlib only.
"""
import datetime
import json
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ai_editor import taste  # noqa: E402

MINE = "my-style"
OVERRIDES = "style.overrides.json"
HOME = Path(os.environ.get("AI_EDITOR_HOME", Path.home() / ".ai-video-editor"))   # the real taste folder
FORMAT_LINE = re.compile(r"Script format: the `([^`]+)` skill")


def _scratch(p):
    """True for a folder inside the system temp dir (a test or scratch AI_EDITOR_HOME)."""
    import tempfile
    try:
        r = Path(p).resolve()
    except OSError:
        return False
    roots = {Path(tempfile.gettempdir()).resolve(), Path("/tmp").resolve(), Path("/private/tmp"), Path("/var/folders")}
    return any(r == t or t in r.parents for t in roots)


def skills_dir():
    env = os.environ.get("AI_EDITOR_SKILLS")
    if env:
        return Path(env)
    if taste.HOME != HOME:   # a self-check pointed the taste at a temp folder: its skills go there too
        return taste.HOME / "skills"
    if _scratch(HOME):       # a test home in a temp folder never writes the user's real skills
        return HOME / "skills"
    proj = Path.cwd() / ".claude"
    return proj / "skills" if proj.is_dir() else Path.home() / ".claude" / "skills"


def slug(style_path):
    s = re.sub(r"-mine$", "", Path(style_path).resolve().parent.name.lower())
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "creator"


def key(style_path=None):
    return "mine" if style_path is None else slug(style_path)


def names_path():
    return taste.HOME / "style-names.json"


def names():
    try:
        return json.loads(names_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_names(d):
    names_path().parent.mkdir(parents=True, exist_ok=True)
    names_path().write_text(json.dumps(d, indent=2), encoding="utf-8")


def name(style_path=None):
    n = names().get(key(style_path), {}).get("skill")
    if n or style_path is None:
        return n or MINE
    d = display(style_path)   # a sample style's own name ("Card edit" -> card-edit), else edit-like-<creator>
    return re.sub(r"[^a-z0-9]+", "-", d.lower()).strip("-")[:40] if not d.startswith("@") else f"edit-like-{slug(style_path)}"[:64].rstrip("-")


def display(style_path=None):
    """What the page and the triggers call it: the name the user gave, else My style / @handle."""
    n = names().get(key(style_path), {}).get("name")
    if n:
        return n
    if style_path is None:
        return "My style"
    try:   # a sample style the plugin ships names itself
        n = json.loads(Path(style_path).read_text(encoding="utf-8") or "{}").get("name")
    except (OSError, ValueError):
        n = None
    return n or "@" + re.sub(r"-mine$", "", Path(style_path).resolve().parent.name)


def use_for(style_path=None):
    return names().get(key(style_path), {}).get("use_for") or ""


# The steps a style runs around its own edit, on or off per style (style-names.json "chain"): logo-pack before the
# edit, and for a skill style the motion skill's clips handed to its skill (a settings style's motion is its
# motion.amount setting instead).
CHAIN = {"logos": True, "motion": False}


def chain(style_path=None):
    c = names().get(key(style_path), {}).get("chain") or {}
    return {k: bool(c.get(k, v)) for k, v in CHAIN.items()}


def set_chain(style_path, step, on):
    if step not in CHAIN:
        raise ValueError(f"step is one of {', '.join(CHAIN)}")
    d = names()
    e = d.get(key(style_path), {})
    d[key(style_path)] = {**e, "chain": {**chain(style_path), step: bool(on)},
                          "path": e.get("path") or (str(preferred(style_path)) if style_path else None)}
    _save_names(d)
    return chain(style_path)


# Skills the user chained onto a style's "What runs": [{"skill", "at"}], "before" the edit (after the cut's approve)
# or "after" (on the finished video, after the final approve), in the order added (style-names.json "skills").
CHAIN_AT = ("before", "after")


def chain_skills(style_path=None):
    xs = names().get(key(style_path), {}).get("skills") or []
    return [{"skill": x["skill"], "at": x.get("at") if x.get("at") in CHAIN_AT else "after"}
            for x in xs if isinstance(x, dict) and isinstance(x.get("skill"), str) and x["skill"]]


def set_chain_skill(style_path, skill, at=None):
    """Add skill at "before" or "after" (moved there when already chained), or take it out with at=None."""
    skill = str(skill or "").strip().lstrip("/")
    if not re.fullmatch(r"[a-z0-9][a-z0-9:_-]{0,63}", skill):
        raise ValueError("not a skill name")
    if at is not None and at not in CHAIN_AT:
        raise ValueError(f"at is one of {', '.join(CHAIN_AT)}")
    d = names()
    e = d.get(key(style_path), {})
    xs = [x for x in chain_skills(style_path) if x["skill"] != skill] + ([{"skill": skill, "at": at}] if at else [])
    d[key(style_path)] = {**e, "skills": xs, "path": e.get("path") or (str(preferred(style_path)) if style_path else None)}
    _save_names(d)
    return xs


def plugin_skill_names():
    return {p.parent.name for p in Path(__file__).resolve().parents[3].glob("*/skills/*/SKILL.md")}


def rename(style_path, new):
    """A style's new name: the display name as typed, the skill as its slug (3-40 of a-z, 0-9, hyphens).
    Refused when the slug is taken by another skill folder or a plugin skill. Every style skill is rewritten."""
    new = " ".join(str(new or "").split())
    if not re.fullmatch(r"[A-Za-z0-9@][A-Za-z0-9@ ._-]{0,39}", new):   # "Like @some.creator" is fine
        raise ValueError("Use letters, numbers, spaces or hyphens, up to 40.")
    sl = re.sub(r"[^a-z0-9]+", "-", new.lower()).strip("-")
    if not 3 <= len(sl) <= 40:
        raise ValueError("Use at least 3 letters or numbers.")
    old = name(style_path)
    if sl != old and ((skills_dir() / sl).exists() or sl in plugin_skill_names()
                      or any(v.get("skill") == sl for v in names().values())):
        raise ValueError(f"/{sl} is already a skill. Pick another name.")
    d = names()
    d[key(style_path)] = {**d.get(key(style_path), {}), "name": new, "skill": sl,
                          "path": str(preferred(style_path)) if style_path else None}
    _save_names(d)
    src = skills_dir() / old
    if sl != old and src.is_dir():
        src.rename(skills_dir() / sl)
    write(style_path)
    rewrite_all()
    return sl


def set_use_for(style_path, text):
    text = " ".join(str(text or "").split())[:160].rstrip(".")
    d = names()
    d[key(style_path)] = {**d.get(key(style_path), {}), "use_for": text, "path": str(preferred(style_path)) if style_path else None}
    _save_names(d)
    write(style_path)
    rewrite_all()


def saved():
    """Every saved style skill this folder knows: [(style path or None, skill name)]."""
    out = []
    for k, v in names().items():
        sp = None if k == "mine" else Path(v.get("path") or "")
        if (sp is None or sp.is_file()) and (skills_dir() / name(sp) / "SKILL.md").exists():
            out.append((sp, name(sp)))
    return out


def rewrite_all():
    for sp, _ in saved():
        write(sp)


def remove(style_path, rm=None):
    """A deleted style: its skill folder and its names entry go; the other skills stop naming it."""
    sk = skills_dir() / name(style_path)
    d = names()
    d.pop(key(style_path), None)
    _save_names(d)
    try:   # a skill style's own skill (style.json "skill") is the user's, never ours to delete
        theirs = json.loads(Path(style_path).read_text(encoding="utf-8") or "{}").get("skill")
    except (OSError, ValueError, TypeError):
        theirs = None
    if sk.is_dir() and sk.parent == skills_dir() and sk.name not in (MINE, theirs):
        import shutil
        (rm or shutil.rmtree)(sk)   # home.py passes its Trash
    rewrite_all()
    return sk


def scope(style_path=None):
    return "all" if style_path is None else f"style:{slug(style_path)}"


def overrides_path(style_path):
    """In the creator's own folder: <h>-mine and <h> share one file."""
    d = Path(style_path).resolve().parent
    return d.parent / re.sub(r"-mine$", "", d.name) / OVERRIDES


def load_overrides(style_path):
    p = overrides_path(style_path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def set_override(style_path, key, value=None, drop=False):
    p = overrides_path(style_path)
    data = load_overrides(style_path)
    data = taste.unset_key(data, key) if drop else taste.set_key(data, key, value)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return p


def sources(path):
    """The creator style.json(s) an edit used: its style.json's "source" (profile.py style writes it), or the
    file itself when it sits in creator-teardowns/<x>/. [] for the default style."""
    p = Path(path)
    f = p / "style.json" if p.is_dir() else p
    if not f.is_file():
        return []
    try:
        s = json.loads(f.read_text(encoding="utf-8") or "{}")
    except ValueError:
        return []
    if s.get("source"):
        return [Path(x) for x in s["source"]]
    return [f.resolve()] if f.resolve().parent.parent.name == "creator-teardowns" else []


def preferred(style_path):
    """<h>/style.json with a <h>-mine beside it (the parts the user ticked): the -mine one."""
    p = Path(style_path).resolve()
    mine = p.parent.parent / f"{p.parent.name}-mine" / "style.json"
    return mine if mine.is_file() else p


def copies(style):
    """What the style copies, in measured numbers only; parts left out of a --take blend are skipped."""
    take = (style.get("blend") or {}).get("take")
    has = lambda part: take is None or part in take
    out = []
    c = style.get("captions") or {}
    if has("captions") and c and c.get("present") is not False:
        bits = [f"{c['size_pct']}% tall" if c.get("size_pct") else "", f"{c['words_per_caption']} words a caption"
                if c.get("words_per_caption") else "", c.get("color") or "", c.get("font_match") or ""]
        out.append("captions (" + ", ".join(b for b in bits if b) + ")" if any(bits) else "captions")
    p, z = style.get("pace") or {}, style.get("zoom") or {}
    if has("pace") and (p or z):
        bits = [f"a cut every {p['median_shot_s']} s" if p.get("median_shot_s") else "",
                f"{z['per_min']} zooms a minute" if z.get("per_min") is not None else ""]
        out.append("pace (" + ", ".join(b for b in bits if b) + ")" if any(bits) else "pace")
    g = style.get("graphics") or {}
    if (has("graphics") or has("entrances") or has("visuals")) and g:
        out.append(f"visuals (graphics on {g['share_pct']}% of the video)" if g.get("share_pct") is not None else "visuals")
    if has("sound") and (style.get("sound") or style.get("sfx") is not None):
        out.append("sound" + (" (no sound effects)" if style.get("sfx") is False else ""))
    return out


def learned(sc):
    """One bullet per rule of this scope, from rules.json (deduplicated there, as taste rules are)."""
    rules = [r for r in taste.load_rules() if r["scope"] == sc and not r.get("off")] if taste.rules_path().exists() else []   # off: not followed
    lines = []
    for r in rules:
        setting = f" Setting: `{r['setting']} = {json.dumps(r['value'])}`." if r.get("setting") else ""
        last = r["corrections"][-1]["at"][:10] if r["corrections"] else "never"
        reg = r["regressions"]
        lines.append(f"- {r['rule']}.{setting} Said {len(r['corrections'])}x, last {last}."
                     + (f" Came back after it was applied: {len(reg)}x, last {reg[-1]['at'][:10]}." if reg else ""))
    return lines


def body(style_path=None, fmt=None):
    if style_path is None:
        prof = json.loads((taste.HOME / "profile.json").read_text(encoding="utf-8")) if (taste.HOME / "profile.json").exists() else {}
        who = ", ".join("@" + c["handle"] + (f" ({', '.join(c['take'])})" if c.get("take") else "")
                        for c in prof.get("creators") or [] if c.get("handle")) or "no creator (the default style)"
        cap = (prof.get("captions") or {}).get("style") or "creator"
        desc = describe(None, f"the user's own saved style (copies {who}; captions: {cap})",
                        ["edit it the way I like"], "the user's own videos, their profile and every correction saved as My style")
        head = (f"# {display()}\n\nEdits the user's video in their own style with the ai-editor plugin.\n\n"
                f"- Profile: `{taste.HOME / 'profile.json'}` (copies {who}; captions: {cap})\n"
                f"- Taste: `{taste.HOME / 'taste.md'}` and `taste.json` (the settings the scripts read)\n\n"
                "## Run\n\n1. Run the ai-editor `start` skill on the user's video. It reads the profile and the taste by itself.\n"
                "2. Review notes that are preferences: scope `My style` saves them to the taste and to the section below.\n\n"
                "Follow every rule in \"Learned from your feedback\".\n")
        empty = "Nothing yet. Notes saved at \"My style\" land here."
    else:
        sp = Path(style_path).resolve()
        style = json.loads(sp.read_text(encoding="utf-8") or "{}")
        h = re.sub(r"-mine$", "", style.get("handle") or sp.parent.name)   # editplan --take names it <h>-mine
        parts = copies(style)
        mix = list((style.get("blend") or {}).get("weights") or [])
        who, said = (f"the {h} blend of " + " and ".join("@" + x for x in mix), h) if len(mix) > 1 else (f"@{h}'s style", "@" + h)
        one = style.get("format") if len(mix) <= 1 else None   # creator-teardown's format check: the one format it copies
        sample = style.get("sample")   # shipped with the plugin (presets/styles/), not measured from a creator
        if sample:
            said = style.get("name") or h
            who, what, extra = f"the {said} sample style", f"the {said} sample style, for {one}", [f"the {said.lower()} style"]
        else:
            what = f"{who}, copying their {one}" if one else f"{who}, measured from their videos"
            extra = [f"edit my video like {said}", f"in {said}'s style", f"make it look like {h}'s videos"]
        desc = describe(sp, what + (f" ({', '.join(p.split(' (')[0] for p in parts)})" if parts else ""), extra,
                        "videos meant to look like that creator's, with the corrections given on this style")
        h = said if sample else "@" + (said.lstrip("@") if len(mix) > 1 else h)
        head = (f"# Edit like {said}\n\nEdits the user's video in {who} ({'ships with the plugin' if sample else 'measured'}) with the ai-editor plugin.\n\n"
                f"- Style: `{sp}` ({'the plugin keeps it current' if sample else 'measured by creator-teardown'}; never edit it by hand)\n"
                f"- Corrections: `{overrides_path(sp)}` (laid over the style; a re-study keeps them)\n"
                + (f"- Format: their {one} (videos of other formats were left out)\n" if one else "")
                + (f"- Copies: {'; '.join(parts)}\n" if parts else "")
                + (f"- Script format: the `{fmt}` skill (it writes the script; this one edits the footage)\n" if fmt else "")
                + "\n## Run\n\n"
                "1. Run the ai-editor `start` skill on the user's video. At its \"Blend the style\" step use this style\n"
                "   instead of the profile's creators (`$P` is the plugin's `lib/ai_editor/profile.py`):\n"
                f"   `python3 \"$P\" style edits/<name> --from \"{sp}\"`\n"
                "2. Then cut and style-edit as start says. plan.py and the cut lay the corrections over the style themselves.\n"
                "   Cards come at this creator's rate, kinds and place (route.py marks the `want` lines); fix every `style:`\n"
                "   line plan.py's style check prints before the stills.\n"
                f"3. Review notes that are preferences: ask the scope with `This style ({h}) (Recommended)` first, then\n"
                "   `review.py edits/<name> learn --scope this-style ...`. They land in the section below.\n\n"
                "Follow every rule in \"Learned from your feedback\". Where one disagrees with the user's general taste,\n"
                "the rule here wins on this style.\n")
        empty = f"Nothing yet. Notes saved at \"This style ({h})\" land here."
    rules = learned(scope(style_path))
    front = f"---\nname: {name(style_path)}\ndescription: {desc}\n---\n\n"
    return front + head + "\n## Learned from your feedback\n\n" + ("\n".join(rules) if rules else empty) + "\n"


def describe(style_path, what, extra, default_use):
    """The skill's description, from the current names: what it is, its phrases, Use for, Not for (the other styles)."""
    n, disp = name(style_path), display(style_path)
    low = disp.lower()
    phrases = [f"edit my video in {low}", f"use {low}"] + ([] if low.endswith("style") else [f"{low} style"]) + [f"/{n}"]
    if style_path is not None and low.startswith("@"):
        phrases = phrases[:2] + [f"/{n}"]
    phrases += [x for x in extra if x.lower() not in phrases]
    if not low.startswith("@"):
        phrases = [x for x in phrases if "@" not in x]   # renamed: the creator's handle stays in "what", not in a phrase
    others = [f"{display(sp)} (/{nm})" for sp, nm in saved() if nm != n]
    text = (f"Edits the user's video in {what}. Use when the user says " + ", ".join(f'"{x}"' for x in phrases)
            + f". Use for: {use_for(style_path) or default_use}. Not for: "
            + (", ".join(others) + ", " if others else "") + "studying a new creator (creator-teardown), a correction meant for every video (taste).")
    while len(text) > 1024 and others:   # Claude Code's description limit: drop the longest tail of other names
        others.pop()
        text = text[:text.index("Not for: ") + 9] + ", ".join(others) + (", " if others else "") + "studying a new creator (creator-teardown)."
    return text[:1024]


def write(style_path=None, fmt=None):
    """Write or refresh the thin skill; returns its SKILL.md path. A format skill linked before is kept."""
    if style_path is not None:
        style_path = preferred(style_path)
    out = skills_dir() / name(style_path) / "SKILL.md"
    if fmt is None and out.exists():
        m = FORMAT_LINE.search(out.read_text(encoding="utf-8"))
        fmt = m.group(1) if m else None
    out.parent.mkdir(parents=True, exist_ok=True)
    d = names()   # remember where the style lives, so a rename of another style can rewrite this skill
    want = {**d.get(key(style_path), {}), "path": str(style_path) if style_path else None}
    if d.get(key(style_path)) != want:
        d[key(style_path)] = want
        _save_names(d)
    out.write_text(body(style_path, fmt), encoding="utf-8")
    return out


def learn(style_path, section, rule, setting=None, value=None, edit=None, source=None):
    """A correction at this style's scope: rules.json (counted, deduplicated), the overrides file and the
    skill's section. style_path None = the user's own style (taste.json, my-style)."""
    return taste.add(section, rule, setting, value, scope(style_path), edit, source, style=style_path)


def demo():
    import tempfile
    assert _scratch(Path(tempfile.gettempdir()) / "x") and not _scratch(Path.home() / ".ai-video-editor")
    old = os.environ.get("AI_EDITOR_SKILLS"), taste.HOME
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        os.environ["AI_EDITOR_SKILLS"] = str(d / "skills")
        taste.HOME = d / "home"
        sp = d / "creator-teardowns" / "some.creator" / "style.json"
        sp.parent.mkdir(parents=True)
        measured = {"handle": "some.creator", "captions": {"present": True, "size_pct": 6.0, "words_per_caption": 3,
                                                            "color": "#FFFFFF"}, "pace": {"median_shot_s": 2.1},
                    "zoom": {"per_min": 4}, "graphics": {"share_pct": 40}}
        sp.write_text(json.dumps(measured), encoding="utf-8")
        md = write(sp)
        assert md == d / "skills" / "edit-like-some-creator" / "SKILL.md", md
        t = md.read_text(encoding="utf-8")
        assert t.startswith("---\nname: edit-like-some-creator\ndescription: ") and "edit my video like @some.creator" in t
        assert "6.0% tall, 3 words a caption" in t and f"--from \"{sp.resolve()}\"" in t and "Nothing yet" in t, t
        assert len(t.split("description: ")[1].split("\n")[0]) <= 1024
        sp.write_text(json.dumps({**measured, "format": "talking-head videos with word captions"}), encoding="utf-8")
        t = write(sp).read_text(encoding="utf-8")
        assert "@some.creator's style, copying their talking-head videos with word captions" in t.split("\n")[2], t[:400]
        sp.write_text(json.dumps(measured), encoding="utf-8")
        # an edit made with it records the source; the overrides apply over the measured style
        ed = d / "edits" / "vid"
        ed.mkdir(parents=True)
        (ed / "cut.mp4").write_bytes(b"")
        (ed / "style.json").write_text(json.dumps({**measured, "source": [str(sp.resolve())]}), encoding="utf-8")
        assert sources(ed) == [sp.resolve()] and sources(sp) == [sp.resolve()] and sources(d / "nope") == []
        st, r = learn(sp, "captions", "Captions smaller", "captions.size_pct", 5, edit=ed)
        assert st == "added" and r["scope"] == "style:some-creator"
        assert load_overrides(sp) == {"captions": {"size_pct": 5}} and json.loads(sp.read_text(encoding="utf-8")) == measured
        assert taste.read_json() == {} and "Captions smaller" not in taste.load_md()["Captions"]   # not every video
        # said again before an edit used it: one bullet, count 2
        st, _ = learn(sp, "captions", "Captions a bit smaller", "captions.size_pct", 4.5, edit=ed)
        t = md.read_text(encoding="utf-8")
        assert st == "updated" and t.split("## Learned")[1].count("\n- ") == 1 and "Said 2x" in t and "captions.size_pct = 4.5" in t, t
        # plan.py's call: taste.json < overrides; counted as applied to that edit
        taste.add("captions", "Captions bigger", "captions.size_pct", 7)   # every video
        old_argv, sys.argv = sys.argv, ["plan.py", str(ed / "style.json"), str(ed / "captions.json")]
        try:
            got = taste.merge(measured, taste.load_json(style=ed / "style.json"))
        finally:
            sys.argv = old_argv
        assert got["captions"]["size_pct"] == 4.5 and got["captions"]["words_per_caption"] == 3, got
        # said again after it was applied: a regression, shown in the skill
        st, _ = learn(sp, "captions", "Captions smaller still", "captions.size_pct", 4, edit=ed)
        t = md.read_text(encoding="utf-8")
        assert st == "regression" and "Said 3x" in t and "Came back after it was applied: 1x" in t, t
        assert "this style (@some-creator)" in taste.report(), taste.report()
        # a re-study rewrites style.json: the corrections stay
        sp.write_text(json.dumps({**measured, "captions": {**measured["captions"], "size_pct": 6.4}}), encoding="utf-8")
        assert write(sp) == md and load_overrides(sp) == {"captions": {"size_pct": 4}}
        assert "Said 3x" in md.read_text(encoding="utf-8")
        # the ticked parts (<h>-mine) take over the same skill and share the same corrections; a format link stays
        mine = sp.parent.parent / "some.creator-mine" / "style.json"
        mine.parent.mkdir()
        mine.write_text(json.dumps({**measured, "handle": "some.creator-mine", "blend": {"take": ["captions"]}}), encoding="utf-8")
        assert write(mine, fmt="numbered-list") == md and overrides_path(mine) == overrides_path(sp)
        assert write(sp) == md   # a later re-study of <h> keeps pointing at the -mine parts
        t = md.read_text(encoding="utf-8")
        assert "like @some.creator\"" in t and "Script format: the `numbered-list` skill" in t and str(mine.resolve()) in t and "pace (" not in t, t
        # "my style": taste as before, and the my-style skill
        my = write()
        assert "name: my-style" in my.read_text(encoding="utf-8") and "Captions bigger." in my.read_text(encoding="utf-8")
        taste.forget(r["id"])
        assert load_overrides(sp) == {"captions": {}} and "Nothing yet" in md.read_text(encoding="utf-8")
        # rename: the skill folder moves, every style's description is rebuilt from the current names
        sp2 = d / "creator-teardowns" / "other.one" / "style.json"
        sp2.parent.mkdir()
        sp2.write_text(json.dumps({"handle": "other.one", "pace": {"median_shot_s": 1.2}}), encoding="utf-8")
        write(sp2)
        desc = lambda nm: (d / "skills" / nm / "SKILL.md").read_text(encoding="utf-8").split("description: ")[1].split("\n")[0]
        quoted = lambda t: set(re.findall(r'"([^"]+)"', t.split("Not for:")[0]))
        assert rename(sp, "Fast cuts") == "fast-cuts" and not md.exists() and display(sp) == "Fast cuts"
        new = d / "skills" / "fast-cuts" / "SKILL.md"
        t = new.read_text(encoding="utf-8")
        assert t.startswith("---\nname: fast-cuts\n") and '"/fast-cuts"' in t and '"edit my video in fast cuts"' in t and "edit-like-some-creator" not in t, t
        assert "Fast cuts (/fast-cuts)" in desc("edit-like-other-one") and "Fast cuts (/fast-cuts)" in desc("my-style")
        assert "edit-like-some-creator" not in desc("edit-like-other-one")
        assert not quoted(desc("fast-cuts")) & quoted(desc("edit-like-other-one")), "two styles claim one phrase"
        assert not quoted(desc("fast-cuts")) & quoted(desc("my-style"))
        set_use_for(sp, "talking-head reels about AI tools.")
        assert "Use for: talking-head reels about AI tools. Not for:" in desc("fast-cuts") and all(len(desc(n)) <= 1024 for n in ("fast-cuts", "my-style"))
        for bad, why in (("x", "at least 3"), ("../etc", "letters"), ("edit like other one", "already"), ("cut", "already")):
            try:   # too short, bad characters, another style's skill, a plugin skill
                rename(sp, bad)
                raise AssertionError(bad)
            except ValueError as e:
                assert why in str(e), (bad, e)
        try:
            rename(sp2, "Fast cuts")
            raise AssertionError("clash accepted")
        except ValueError as e:
            assert "already a skill" in str(e)
        remove(sp2)
        assert not (d / "skills" / "edit-like-other-one").exists() and "other.one" not in names() and "other.one" not in desc("fast-cuts")
        # a temp taste folder keeps its skills beside it; a project with a .claude folder gets them there
        del os.environ["AI_EDITOR_SKILLS"]
        assert skills_dir() == taste.HOME / "skills"
        taste.HOME = HOME
        cwd = os.getcwd()
        (d / "proj" / ".claude").mkdir(parents=True)
        os.chdir(d / "proj")
        try:
            assert skills_dir().resolve() == (d / "proj" / ".claude" / "skills").resolve()
        finally:
            os.chdir(cwd)
    if old[0] is None:
        os.environ.pop("AI_EDITOR_SKILLS", None)
    else:
        os.environ["AI_EDITOR_SKILLS"] = old[0]
    taste.HOME = old[1]
    print("styleskill demo ok")


def main():
    a = sys.argv[1:]
    flag = lambda k: a[a.index(k) + 1] if k in a and a.index(k) + 1 < len(a) else None
    if a == ["demo"]:
        return demo()
    if a[:1] == ["write"] and len(a) >= 2:
        sp = None if a[1] == "--mine" else a[1]
        if sp and not Path(sp).is_file():
            sys.exit(f"no {sp}")
        out = write(sp, flag("--format"))
        print(f"skill {out.parent.name} -> {out}")
    elif a[:1] == ["learn"] and len(a) >= 4:
        kv = [x for x in a[4:] if "=" in x and not x.startswith("--")]
        setting, _, raw = kv[0].partition("=") if kv else (None, "", "")
        st, r = learn(a[1], a[2], a[3], setting, taste.parse(raw) if setting else None, flag("--edit"))
        print(f"{st}: #{r['id']} {r['section']}: {r['rule']} (this style: {name(a[1])})")
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
