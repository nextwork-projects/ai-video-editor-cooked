#!/usr/bin/env python3
"""Live reload for the local pages (home.py, review.py): an open tab always shows the newest UI.

The page HTML is read per request, but the Python is not. reexec_on_change() watches every .py in this
folder and, when one changes and still compiles, re-executes the server on the same port. It also moves the server
onto a newer installed version: /plugin update (and Settings' Update) adds .../ai-editor/<version>/ beside the old
one, so every open page (the window and each video's page) restarts from the newest copy (newer_copy). page_version()
goes into each /state answer; the page reloads itself when it changes (never while the user is typing or
an upload is running). Uploads in flight hold off the restart (busy()).

    python3 live.py demo     self-check
Stdlib only.
"""
import contextlib
import hashlib
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
_busy = [0]
_lock = threading.Lock()


def page_version(*pages):
    """Changes when a page file or any Python file here changes, or on another version's folder (a copy can keep the times)."""
    files = [Path(p) for p in pages] + sorted(HERE.glob("*.py"))
    stamp = "|".join([str(HERE)] + [f"{f.name}:{f.stat().st_mtime_ns}" for f in files if f.exists()])
    return hashlib.sha1(stamp.encode()).hexdigest()[:12]


@contextlib.contextmanager
def busy():
    """Around an upload: no restart under it."""
    with _lock:
        _busy[0] += 1
    try:
        yield
    finally:
        with _lock:
            _busy[0] -= 1


def argv_with_port(argv, port):
    a = list(argv)
    a[0] = os.path.abspath(a[0])
    if "--port" in a and a.index("--port") + 1 < len(a):
        a[a.index("--port") + 1] = str(port)
    else:
        a += ["--port", str(port)]
    return a


def vkey(name):
    """(2, 7, 15) for a version folder name such as "2.7.15" or "2.7.15-6798eb0", else None."""
    parts = name.split("-")[0].split(".")
    return tuple(int(x) for x in parts) if len(parts) >= 2 and all(x.isdigit() for x in parts) else None


def newer_copy(here=HERE):
    """This folder in a newer installed version beside this one (.../ai-editor/<version>/lib/ai_editor), else None.
    A checkout (no version folder) never has one: git updates it in place and the file watch restarts it."""
    ver = here.parents[1]
    mine = vkey(ver.name)
    if not mine:
        return None
    try:
        best = max((d for d in ver.parent.iterdir() if vkey(d.name) and (d / "lib" / "ai_editor" / "live.py").is_file()),
                   key=lambda d: vkey(d.name), default=None)
    except OSError:
        return None
    return best / "lib" / "ai_editor" if best and vkey(best.name) > mine else None


def reexec_on_change(srv, poll=1.0):
    """Run in a daemon thread beside serve_forever()."""
    snap = lambda: {p: p.stat().st_mtime_ns for p in HERE.glob("*.py")}
    s0, tick = snap(), 0
    while True:
        time.sleep(poll)
        tick += 1
        new = newer_copy() if tick % 10 == 0 and not _busy[0] else None
        if new and (new / Path(sys.argv[0]).name).is_file():   # an update installed a newer version: move onto it
            time.sleep(3)   # the copy finishes landing
            try:
                compile((new / Path(sys.argv[0]).name).read_text(encoding="utf-8"), sys.argv[0], "exec")
            except (OSError, SyntaxError):
                continue
            print(f"version {new.parents[1].name} installed: restarting from it on the same port", flush=True)
            port = srv.server_address[1]
            srv.server_close()
            argv = argv_with_port(sys.argv, port)
            os.execv(sys.executable, [sys.executable, str(new / Path(sys.argv[0]).name), *argv[1:]])
        s = snap()
        if s == s0 or _busy[0]:
            continue
        changed, s0 = [p for p in s if s0.get(p) != s[p]], s
        try:
            for p in changed:
                compile(p.read_text(encoding="utf-8"), str(p), "exec")
        except SyntaxError as e:
            print(f"{Path(e.filename or '').name} changed but does not compile, still on the old code: {e}", flush=True)
            continue
        print(f"{', '.join(p.name for p in changed)} changed: restarting on the same port", flush=True)
        port = srv.server_address[1]
        srv.server_close()
        os.execv(sys.executable, [sys.executable] + argv_with_port(sys.argv, port))


def demo():
    with tempfile.TemporaryDirectory() as d:
        page = Path(d) / "home.html"
        page.write_text("<p>v1</p>", encoding="utf-8")
        v1 = page_version(page)
        assert page_version(page) == v1, "stable while nothing changes"
        st = page.stat()
        os.utime(page, ns=(st.st_atime_ns, st.st_mtime_ns + 2_000_000_000))
        assert page_version(page) != v1, "an edit to the page changes the version"
    assert argv_with_port(["home.py", "serve"], 47821)[-2:] == ["--port", "47821"]
    assert argv_with_port(["review.py", "x", "serve", "--port", "0", "--no-open"], 51234)[3:5] == ["--port", "51234"]
    with tempfile.TemporaryDirectory() as d:   # an update added a newer version folder: that copy, never an older one
        root = Path(d) / "ai-editor"
        for v in ("2.7.13", "2.7.15", "2.7.9", "notes"):
            (root / v / "lib" / "ai_editor").mkdir(parents=True)
            (root / v / "lib" / "ai_editor" / "live.py").write_text("", encoding="utf-8")
        assert newer_copy(root / "2.7.13" / "lib" / "ai_editor") == root / "2.7.15" / "lib" / "ai_editor"
        assert newer_copy(root / "2.7.15" / "lib" / "ai_editor") is None
        assert newer_copy(Path(d) / "repo" / "plugins" / "ai-editor" / "lib" / "ai_editor") is None, "a checkout"
        assert vkey("2.7.13-6798eb0") == (2, 7, 13) and vkey("notes") is None
    with busy():
        assert _busy[0] == 1
    assert _busy[0] == 0
    print("live demo ok")


if __name__ == "__main__":
    demo() if sys.argv[1:] == ["demo"] else print(__doc__)
