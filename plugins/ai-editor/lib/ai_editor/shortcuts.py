#!/usr/bin/env python3
"""The editor's keyboard shortcuts, saved per user. Stdlib only.

shortcuts.js holds the one table (action -> label, group, default keys), the matcher every key handler asks and the
editor the review page's "?" sheet and home Settings both show. This file keeps the user's changes in
$AI_EDITOR_HOME/keys.json (default ~/.ai-video-editor/keys.json), only the actions that differ from the default,
like {"split": ["Mod+K"]}, and answers both servers (review.py and home.py call route()):

    GET  /shortcuts.js   the script, with the saved changes inlined (KM_USER) so the first key press uses them
    GET  /keys           {"keys": {...}}: every open page reads it every 3 s
    POST /keys           {"action": "split", "combo": "Mod+K" | ["S", "Mod+K"] | []}   ([] = no key)
                         {"reset": "split"} | {"reset_all": true} | {"replace": {action: [combos]}} (a preset)
                         -> {"keys": {...}}, or 400 {"error"} for an unknown action, a fixed one, a bad combo or a
                         key the browser owns. Clashes are the page's to settle (it offers Swap).

    python3 shortcuts.py demo    self-check
"""
import json
import os
import re
import sys
import threading
from pathlib import Path

JS = Path(__file__).with_name("shortcuts.js")
NAMED = {"Space", "Enter", "Escape", "Tab", "Backspace", "Delete", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown",
         "Home", "End", "PageUp", "PageDown", "Insert", *(f"F{i}" for i in range(1, 13))}
RESERVED = {"Mod+Q", "Mod+W", "Mod+T", "Mod+R", "Mod+L", "Mod+Tab"}   # the browser's or the OS's
COMBO = re.compile(r"((?:Mod\+)?(?:Alt\+)?(?:Shift\+)?)(.+)")
_LOCK = threading.Lock()   # ponytail: one lock per process; home and review writing the same instant is the ceiling


def table():
    """{action: [id, label, group, defaults, options]} from shortcuts.js's KM_TABLE."""
    rows = json.loads(re.search(r"^const KM_TABLE=(\[.*?^\]);", JS.read_text(encoding="utf-8"), re.S | re.M)[1])
    return {r[0]: r for r in rows}


def keys_file():
    return Path(os.environ.get("AI_EDITOR_HOME", "").strip() or Path.home() / ".ai-video-editor") / "keys.json"


def valid(c):
    """A combo in shortcuts.js's shape: [Mod+][Alt+][Shift+]Key, a letter upper case, a symbol without Shift."""
    m = COMBO.fullmatch(c) if isinstance(c, str) else None
    if not m:
        return False
    k = m[2]
    if k in NAMED:
        return True
    if len(k) != 1 or not k.isprintable() or k == " ":
        return False
    if k.isascii() and k.isalpha():
        return k.isupper()
    return "Shift+" not in m[1]


def load():
    try:
        d = json.loads(keys_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    t = table()
    return {a: c for a, c in d.items() if a in t and isinstance(c, list) and all(valid(x) for x in c)} if isinstance(d, dict) else {}


def _combos(action, combos, t):
    if action not in t or (t[action][4:] and t[action][4].get("fixed")):
        raise ValueError("There is no shortcut by that name.")
    combos = [combos] if isinstance(combos, str) else combos
    if not isinstance(combos, list) or len(combos) > 4:
        raise ValueError("Give one to four keys.")
    for c in combos:
        if not valid(c):
            raise ValueError(f"{c!r} is not a key.")
        if c in RESERVED:
            raise ValueError("The browser owns that key. Pick another.")
    return list(dict.fromkeys(combos))


def change(body):
    """Applies one POST /keys body to keys.json and returns what it now holds."""
    t = table()
    with _LOCK:
        d = load()
        if body.get("reset_all"):
            d = {}
        elif "reset" in body:
            if body["reset"] not in t:
                raise ValueError("There is no shortcut by that name.")
            d.pop(body["reset"], None)
        elif "replace" in body:
            if not isinstance(body["replace"], dict):
                raise ValueError("replace takes {action: [keys]}.")
            d = {a: _combos(a, c, t) for a, c in body["replace"].items()}
        elif "action" in body:
            d[body["action"]] = _combos(body["action"], body.get("combo"), t)
        else:
            raise ValueError("Send action and combo, reset, reset_all or replace.")
        d = {a: c for a, c in d.items() if c != t[a][3]}   # back to the default: not a change
        f = keys_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_name(f"keys.{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(d, indent=1), encoding="utf-8")
        os.replace(tmp, f)
    return d


def route(h, method, path, query=None, body=None):
    """Serves /shortcuts.js and /keys for a home or review handler h (already authorized). True when it answered."""
    if method == "GET" and path == "/shortcuts.js":
        h.send(200, b"const KM_USER=" + json.dumps(load()).encode() + b";\n" + JS.read_bytes(), "text/javascript; charset=utf-8")
        return True
    if path != "/keys":
        return False
    if method == "GET":
        h.send(200, {"keys": load()})
        return True
    try:
        h.send(200, {"keys": change(body if isinstance(body, dict) else {})})
    except ValueError as e:
        h.send(400, {"error": str(e)})
    return True


def demo():
    import tempfile
    t = table()
    assert t["split"][3] == ["S", "Mod+B"] and t["undo"][3] == ["Mod+Z"] and t["cancel"][4]["fixed"], "the table parses"
    assert all(valid(c) for r in t.values() for c in r[3]), "every default is a combo"
    assert all(valid(c) for c in ["Mod+K", "Shift+Z", "Mod+Shift+Z", "Mod++", "?", "\\", "F5", "Alt+ArrowLeft", "é"])
    assert not any(valid(c) for c in ["s", "Shift+?", "Ctrl+K", "Mod+", "Space+Mod", "AudioVolumeUp", "", None, 3])
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["AI_EDITOR_HOME"] = tmp
        assert load() == {}
        assert change({"action": "split", "combo": "Mod+K"}) == {"split": ["Mod+K"]}
        assert json.loads((Path(tmp) / "keys.json").read_text(encoding="utf-8")) == {"split": ["Mod+K"]}, "only the changed action"
        assert change({"action": "fit", "combo": []}) == {"split": ["Mod+K"], "fit": []}, "no key at all is a change"
        assert change({"action": "fit", "combo": ["Shift+Z"]}) == {"split": ["Mod+K"]}, "the default again drops it"
        for bad in ({"action": "nope", "combo": "K"}, {"action": "cancel", "combo": "K"}, {"action": "split", "combo": "k"},
                    {"action": "split", "combo": "Mod+Q"}, {"reset": "nope"}, {"replace": []}, {}):
            try:
                change(bad)
                raise AssertionError(f"took {bad}")
            except ValueError:
                pass
        assert load() == {"split": ["Mod+K"]}, "a refused change keeps the file"
        assert change({"reset": "split"}) == {}
        assert change({"replace": {"split": ["Mod+K", "Mod+B"], "fit": ["\\", "Shift+Z"]}})["fit"] == ["\\", "Shift+Z"]
        assert change({"reset_all": True}) == {} and json.loads((Path(tmp) / "keys.json").read_text(encoding="utf-8")) == {}
        (Path(tmp) / "keys.json").write_text('{"split": ["Mod+K"], "gone": ["K"], "fit": ["bad key"]}', encoding="utf-8")
        assert load() == {"split": ["Mod+K"]}, "unknown actions and bad combos in the file are ignored"
    print("shortcuts.py demo: ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["demo"]:
        demo()
    else:
        print(__doc__)
