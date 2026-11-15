"""A skill tree: the user's own edit skills as formats, cuts, looks and visuals (skill-tree.json in the library).

With one in the library, Pick a style is four steps: Format, Cut, Look, Visuals, each set to its default.
A recipe format is one pick (its skill fixes cut, look and visuals). An open format then picks a cut preset,
a look skill and a visuals choice. No file: the page keeps its style cards.

The file (the library's skill-tree.json, often a link to the user's own repo):
  formats  [{id, label, kind: open|recipe, aspect, skill (recipe), cut, look {default, options}, visuals {default, options},
             preview, examples}]
  cuts     {skill, presets {name: what}}
  looks    {"auto-by-aspect": {"16:9": look, "9:16": look}, look: {label, what, preview, examples}}
  visuals  {name: {label, what, preview, examples}}
preview and examples are paths to real stills (~ allowed). Only those files are ever served (example_file).

  python3 skilltree.py demo
"""
import json
import sys
from pathlib import Path

NAME = "skill-tree.json"
IMAGE = (".jpg", ".jpeg", ".png", ".webp")


def load(root):
    """The library's tree, or None (no file, or not a tree)."""
    try:
        t = json.loads((Path(root) / NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return t if isinstance(t, dict) and isinstance(t.get("formats"), list) and isinstance(t.get("looks"), dict) else None


def _files(e):
    out = [x for x in (e.get("examples") or []) if isinstance(x, str)]
    if not out and isinstance(e.get("preview"), str):
        out = [e["preview"]]
    return out


def _entries(t):
    """Every entry that can carry examples: (kind, id) -> entry."""
    out = {("format", f.get("id")): f for f in t["formats"] if isinstance(f, dict)}
    out.update({("look", k): v for k, v in t["looks"].items() if isinstance(v, dict) and k != "auto-by-aspect"})
    out.update({("visual", k): v for k, v in (t.get("visuals") or {}).items() if isinstance(v, dict)})
    return out


def example_file(root, kind, id_, n):
    """The n-th example still of an entry, only when the tree names it and it is an image on disk."""
    t = load(root)
    e = t and _entries(t).get((kind, id_))
    fs = _files(e) if e else []
    if not 0 <= n < len(fs):
        return None
    f = Path(fs[n]).expanduser()
    return f if f.suffix.lower() in IMAGE and f.is_file() else None


def default_look(t, f, aspect):
    d = (f.get("look") or {}).get("default")
    return (t["looks"].get("auto-by-aspect") or {}).get(aspect) if d == "auto-by-aspect" else d


def for_page(root):
    """What Pick a style shows: each format, look and visual with its label, line and example URLs."""
    t = load(root)
    if not t:
        return None
    from urllib.parse import quote

    def urls(kind, id_, e):
        return [f"/tree/example?kind={kind}&id={quote(str(id_))}&n={i}" for i, x in enumerate(_files(e))
                if Path(x).expanduser().is_file()]
    looks = {k: {"label": v.get("label") or k, "what": v.get("what") or "", "examples": urls("look", k, v)}
             for k, v in t["looks"].items() if isinstance(v, dict) and k != "auto-by-aspect"}
    visuals = {k: {"label": v.get("label") or k, "what": v.get("what") or "", "examples": urls("visual", k, v)}
               for k, v in (t.get("visuals") or {}).items() if isinstance(v, dict)}
    formats = []
    for f in t["formats"]:
        if not isinstance(f, dict) or not f.get("id"):
            continue
        g = {k: f.get(k) for k in ("id", "label", "kind", "aspect", "skill", "cut")}
        g["examples"] = urls("format", f["id"], f)
        if f.get("kind") != "recipe":
            g["looks"] = [x for x in (f.get("look") or {}).get("options") or [] if x in looks]
            g["visuals"] = [x for x in (f.get("visuals") or {}).get("options") or [] if x in visuals]
            g["look"] = default_look(t, f, f.get("aspect")) or (g["looks"] or [None])[0]
            g["look_auto"] = (f.get("look") or {}).get("default") == "auto-by-aspect"   # the page picks by the clip's shape
            g["visual"] = (f.get("visuals") or {}).get("default")
            if not g["examples"] and g["look"] in looks:   # an open format shows its default look
                g["examples"] = looks[g["look"]]["examples"]
        formats.append(g)
    cuts = (t.get("cuts") or {}).get("presets") or {}
    return {"formats": formats, "looks": looks, "visuals": visuals, "cuts": cuts,
            "auto": t["looks"].get("auto-by-aspect") or {}}


def pick(root, b, aspect):
    """The page's picks checked against the tree: job args {format, cut, look, visuals, skill}, or a ValueError."""
    t = load(root)
    if not t:
        raise ValueError("No skill tree in this library.")
    f = next((x for x in t["formats"] if isinstance(x, dict) and x.get("id") == b.get("format")), None)
    if not f:
        raise ValueError("Pick a format.")
    if f.get("kind") == "recipe":
        return {"format": f["id"], "skill": f["skill"]}
    presets = (t.get("cuts") or {}).get("presets") or {}
    cut = b.get("cut") or f.get("cut")
    if cut not in presets:
        raise ValueError("That cut is not in the skill tree.")
    looks = (f.get("look") or {}).get("options") or []
    look = b.get("look") or default_look(t, f, aspect)
    if look not in looks:
        raise ValueError("That look is not one of this format's.")
    vis = (f.get("visuals") or {}).get("options") or []
    visual = b.get("visuals") or (f.get("visuals") or {}).get("default")
    if visual not in vis:
        raise ValueError("Those visuals are not one of this format's.")
    return {"format": f["id"], "cut": cut, "look": look, "visuals": visual, "skill": look}


def demo():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        r = Path(td)
        assert load(r) is None and for_page(r) is None
        img = r / "a.jpg"
        img.write_bytes(b"\xff\xd8x")
        (r / "secret.txt").write_text("no", encoding="utf-8")
        t = {"formats": [
            {"id": "talk", "label": "Talking reel", "kind": "open", "aspect": "9:16", "cut": "tight",
             "look": {"default": "auto-by-aspect", "options": ["look-a", "look-b"]},
             "visuals": {"default": "real", "options": ["real"]}},
            {"id": "rec", "label": "Recipe", "kind": "recipe", "aspect": "9:16", "skill": "rec-skill",
             "examples": [str(img), str(r / "secret.txt"), str(r / "gone.jpg")]}],
             "cuts": {"skill": "cut", "presets": {"tight": "jump cut", "light": "light"}},
             "looks": {"auto-by-aspect": {"9:16": "look-b", "16:9": "look-a"},
                       "look-a": {"label": "A", "what": "a"}, "look-b": {"label": "B", "what": "b", "preview": str(img)}},
             "visuals": {"real": {"label": "Real", "what": "real"}}}
        (r / NAME).write_text(json.dumps(t), encoding="utf-8")
        p = for_page(r)
        talk, rec = p["formats"]
        assert talk["look"] == "look-b" and talk["examples"] == p["looks"]["look-b"]["examples"] and len(talk["examples"]) == 1
        assert len(rec["examples"]) == 2 and "looks" not in rec   # the missing file is not listed
        assert example_file(r, "format", "rec", 0) == img
        assert example_file(r, "format", "rec", 1) is None   # named, but not an image: never served
        assert example_file(r, "format", "rec", 9) is None and example_file(r, "look", "nope", 0) is None
        assert pick(r, {"format": "rec", "look": "ignored"}, "9:16") == {"format": "rec", "skill": "rec-skill"}
        assert pick(r, {"format": "talk"}, "9:16") == {"format": "talk", "cut": "tight", "look": "look-b", "visuals": "real", "skill": "look-b"}
        assert pick(r, {"format": "talk", "cut": "light", "look": "look-a"}, "9:16")["look"] == "look-a"
        for bad in ({"format": "x"}, {"format": "talk", "cut": "zzz"}, {"format": "talk", "look": "look-c"},
                    {"format": "talk", "visuals": "film"}):
            try:
                pick(r, bad, "9:16")
                raise AssertionError(bad)
            except ValueError:
                pass
    print("skilltree demo ok")


if __name__ == "__main__":
    demo() if sys.argv[1:] == ["demo"] else print(__doc__)
