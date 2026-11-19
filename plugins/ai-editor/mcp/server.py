#!/usr/bin/env python3
"""cooked. as an MCP server: the user's own Claude (Claude desktop, Claude Code, a claude.ai connector) drives the
editor through these tools, so all the AI runs on the user's Claude plan. No API key, no Anthropic API. Stdlib only.

Stdio JSON-RPC 2.0, one message per line: initialize, tools/list, tools/call (ping too). Each tool is a thin wrapper
over the CLIs in lib/ai_editor (review.py, scene.py, library.py).

    python3 server.py          serve on stdin/stdout (what the Claude app runs)
    python3 server.py demo     self-check: starts this server as a subprocess on a scratch library and calls it

The plugin it drives: $COOKED_PLUGIN, else the plugin this file sits in (plugins/ai-editor/mcp/), else the newest
installed copy under ~/.claude/plugins. The catch: MCP cannot wake Claude. Notes left on the page wait until a chat
calls get_notes.
"""
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

VERSION = "0.1.0"
# The Claude app starts this with a bare PATH: Homebrew's ffmpeg, node and python3 live here.
os.environ["PATH"] = os.pathsep.join(["/opt/homebrew/bin", "/usr/local/bin", os.environ.get("PATH", "")])
PROTOCOL = "2025-06-18"


def plugin_dir():
    env = os.environ.get("COOKED_PLUGIN", "").strip()
    here = Path(__file__).resolve().parent.parent
    cands = [Path(env).expanduser()] if env else []
    cands.append(here)
    cache = Path.home() / ".claude" / "plugins" / "cache"
    vers = sorted(cache.glob("*/ai-editor/*"), key=lambda p: [int(x) if x.isdigit() else 0 for x in p.name.split(".")])
    cands += vers[::-1] + list((Path.home() / ".claude" / "plugins" / "marketplaces").glob("*/plugins/ai-editor"))
    for c in cands:
        if (c / "lib" / "ai_editor" / "review.py").is_file():
            return c
    raise RuntimeError("cooked. is not installed: set COOKED_PLUGIN to the plugins/ai-editor folder")


LIB = None
SERVERS = {}   # edit folder -> Popen of review.py serve, stopped when this server exits


def lib():
    global LIB
    LIB = LIB or plugin_dir() / "lib" / "ai_editor"
    return LIB


def run(script, *args, timeout=120):
    p = subprocess.run([sys.executable, str(lib() / script), *map(str, args)], capture_output=True, text=True,
                       encoding="utf-8", timeout=timeout, stdin=subprocess.DEVNULL)
    out = (p.stdout + (p.stderr if p.returncode else "")).strip()
    if p.returncode:
        raise ToolError(out or f"{script} exited {p.returncode}")
    return out


class ToolError(Exception):
    pass


def videos():
    return json.loads(run("library.py", "list"))


def edit_dir(edit):
    """A folder path, or the name of an edit in the library."""
    p = Path(str(edit)).expanduser()
    if p.is_dir():
        return p.resolve()
    for v in videos():
        if edit in (v["name"], Path(v["dir"]).name):
            return Path(v["dir"])
    raise ToolError(f"no edit called {edit!r}: list_videos shows the names")


def page_url(d):
    """The running page for edit d, starting review.py serve when none answers."""
    url = None
    try:
        url = (d / "review" / ".server").read_text(encoding="utf-8").strip()
        urllib.request.urlopen(url.replace("/?t=", "/state?t="), timeout=2).read()
        return url
    except (OSError, ValueError):
        pass
    if not (d / "review.json").is_file():
        raise ToolError(f"{d.name} has no review page yet (no cut): run the cut first")
    p = subprocess.Popen([sys.executable, str(lib() / "review.py"), str(d), "serve", "--no-open"], stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, text=True, encoding="utf-8")
    SERVERS[str(d)] = p
    url = p.stdout.readline().strip()
    if not url.startswith("http"):
        raise ToolError("review.py serve did not print its address")
    return url


def call_page(url, path, body=None):
    base, tok = url.split("/?t=")
    req = urllib.request.Request(f"{base}{path}?t={tok}", None if body is None else json.dumps(body).encode(),
                                 {"Content-Type": "application/json"}, method="GET" if body is None else "POST")
    try:
        return json.loads(urllib.request.urlopen(req, timeout=10).read() or b"{}")
    except urllib.error.HTTPError as e:
        return {"status": e.code, **json.loads(e.read() or b"{}")}


# ---------------------------------------------------------------- tools
def t_list_videos(a):
    return json.dumps([{k: v.get(k) for k in ("name", "dir", "kind", "status", "stage", "draft", "video")} for v in videos()], indent=1)


def t_open_video(a):
    d = edit_dir(a["edit"])
    url = page_url(d)
    if a.get("open", True):
        webbrowser.open(url)
    return url


def t_get_notes(a):
    """review.py wait, stopped after timeout seconds (Ctrl-C, so its listening flag is cleaned up)."""
    d = edit_dir(a["edit"])
    p = subprocess.Popen([sys.executable, str(lib() / "review.py"), str(d), "wait"], stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True, encoding="utf-8")
    try:
        out, _ = p.communicate(timeout=float(a.get("timeout", 30)))
        return out.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        p.send_signal(signal.SIGINT)
        try:
            p.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
        return "NO NOTES YET: the user has not pressed Send or Approve. Call get_notes again later."


def t_show(a):
    return run("scene.py", "show", edit_dir(a["edit"]), *(["--at", a["at"]] if a.get("at") is not None else []))


def t_scene_ops(a):
    ops = a["ops"] if isinstance(a["ops"], str) else json.dumps(a["ops"])
    return run("scene.py", "ops", edit_dir(a["edit"]), ops, "--why", a.get("why") or "Claude's change")


def t_add_item(a):
    args = ["scene.py", "add", edit_dir(a["edit"]), a["type"], "--start", a["start"]]
    for k in ("end", "src", "text", "x", "y", "w", "h", "track"):
        if a.get(k) is not None:
            args += [f"--{k}", a[k]]
    if a.get("json"):
        args += ["--json", json.dumps(a["json"])]
    return run(*args, "--why", a.get("why") or f"add {a['type']}")


def t_resolve_note(a):
    args = ["review.py", edit_dir(a["edit"]), "resolve", a["id"], a.get("state", "fixed")]
    if a.get("reply"):
        args += ["--reply", a["reply"]]
    return run(*args)


def t_hand_back(a):
    args = ["review.py", edit_dir(a["edit"]), "round", "--scene"]
    for c in a.get("changed") or []:
        args += ["--changed", c]
    return run(*args)


def t_export(a):
    """The page's Export (POST /export, review.py export_job), waited for up to timeout seconds."""
    url = page_url(edit_dir(a["edit"]))
    r = call_page(url, "/export", {})
    if r.get("status"):
        return f"Export did not start: {r.get('error') or r}"
    end = time.time() + float(a.get("timeout", 600))
    while time.time() < end:
        s = call_page(url, "/export")
        if s.get("state") != "working":
            return json.dumps(s)
        time.sleep(2)
    return "Export still running: call export again to check, or watch the page."


E = {"edit": {"type": "string", "description": "The edit's name (from list_videos) or its folder path"}}
TOOLS = [
    ("list_videos", "Every video in the user's cooked. library, newest first: name, folder, status, stage, draft.",
     {}, [], t_list_videos),
    ("open_video", "Start the video's review page and open it in the browser. Returns the page URL.",
     {**E, "open": {"type": "boolean", "description": "Open the browser (default true)"}}, ["edit"], t_open_video),
    ("get_notes", "Wait for the user to press Send or Approve on the page, then return every note (time, text, words, "
     "what is on screen). Returns NO NOTES YET after timeout seconds.",
     {**E, "timeout": {"type": "number", "description": "Seconds to wait (default 30)"}}, ["edit"], t_get_notes),
    ("show", "The scene's items (ids, times, boxes) and the words said, to target a change. at: one moment in seconds.",
     {**E, "at": {"type": "number"}}, ["edit"], t_show),
    ("scene_ops", "Apply ops to scene.json (SCENE.md op format), with a one-line why the page shows.",
     {**E, "ops": {"type": ["array", "string"], "description": "The ops, as JSON"}, "why": {"type": "string"}},
     ["edit", "ops"], t_scene_ops),
    ("add_item", "Add one item to the scene: text, image, video, shape or audio.",
     {**E, "type": {"type": "string", "enum": ["text", "image", "video", "shape", "audio"]},
      "start": {"type": "number"}, "end": {"type": "number"}, "src": {"type": "string"}, "text": {"type": "string"},
      "x": {"type": "number"}, "y": {"type": "number"}, "w": {"type": "number"}, "h": {"type": "number"},
      "track": {"type": "string"}, "json": {"type": "object"}, "why": {"type": "string"}},
     ["edit", "type", "start"], t_add_item),
    ("resolve_note", "Mark a note fixed, wontfix or open, with an optional reply the user sees.",
     {**E, "id": {"type": "string"}, "state": {"type": "string", "enum": ["fixed", "wontfix", "open"]},
      "reply": {"type": "string"}}, ["edit", "id"], t_resolve_note),
    ("hand_back", "The notes were answered in the scene: open the next round on the page (review.py round --scene).",
     {**E, "changed": {"type": "array", "items": {"type": "string"}, "description": "Changes beyond the notes"}},
     ["edit"], t_hand_back),
    ("export", "Export what the page shows as one MP4 (the page's Export button). Waits up to timeout seconds.",
     {**E, "timeout": {"type": "number"}}, ["edit"], t_export),
]
BY_NAME = {t[0]: t for t in TOOLS}


def tool_list():
    return [{"name": n, "description": d, "inputSchema": {"type": "object", "properties": p, "required": r}}
            for n, d, p, r, _ in TOOLS]


def handle(msg):
    """One JSON-RPC message in, its response out (None for a notification)."""
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if mid is None:
        return None
    if method == "initialize":
        res = {"protocolVersion": params.get("protocolVersion") or PROTOCOL, "capabilities": {"tools": {}},
               "serverInfo": {"name": "cooked", "version": VERSION},
               "instructions": "cooked. edits the user's videos. list_videos, then open_video. Notes the user leaves "
                               "on the page arrive only when you call get_notes."}
    elif method == "ping":
        res = {}
    elif method == "tools/list":
        res = {"tools": tool_list()}
    elif method == "tools/call":
        t = BY_NAME.get(params.get("name"))
        if not t:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"unknown tool {params.get('name')}"}}
        try:
            res = {"content": [{"type": "text", "text": t[4](params.get("arguments") or {})}]}
        except (ToolError, RuntimeError, KeyError, subprocess.TimeoutExpired) as e:
            res = {"content": [{"type": "text", "text": f"ERROR: {e}"}], "isError": True}
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"no method {method}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": res}


def serve():
    try:
        for line in sys.stdin:
            if not line.strip():
                continue
            try:
                out = handle(json.loads(line))
            except ValueError:
                out = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
            if out:
                sys.stdout.write(json.dumps(out) + "\n")
                sys.stdout.flush()
    finally:
        for p in SERVERS.values():
            p.terminate()


# ---------------------------------------------------------------- self-check
def demo():
    import shutil
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="cooked-mcp-"))
    env = {**os.environ, "HOME": str(tmp), "AI_EDITOR_HOME": str(tmp / ".ai-video-editor"),
           "AI_EDITOR_LIBRARY": str(tmp / "lib"), "AI_EDITOR_NO_REOPEN": "1", "BROWSER": "true",
           "COOKED_PLUGIN": str(Path(__file__).resolve().parent.parent)}
    edit = tmp / "lib" / "edits" / "demo"
    edit.mkdir(parents=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=180x320:r=30:d=2", "-f", "lavfi",
                    "-i", "sine=duration=2", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(edit / "cut.mp4")], check=True)
    lib_dir = Path(env["COOKED_PLUGIN"]) / "lib" / "ai_editor"
    for args in (["review.py", edit, "start", "--video", edit / "cut.mp4", "--stage", "cut"],
                 ["scene.py", "from-video", edit, "--video", "cut.mp4"]):
        subprocess.run([sys.executable, str(lib_dir / args[0]), *map(str, args[1:])], env=env, check=True, capture_output=True)
    srv = subprocess.Popen([sys.executable, __file__], stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env, text=True)
    n = [0]

    def rpc(method, params=None):
        n[0] += 1
        srv.stdin.write(json.dumps({"jsonrpc": "2.0", "id": n[0], "method": method, "params": params or {}}) + "\n")
        srv.stdin.flush()
        r = json.loads(srv.stdout.readline())
        assert r["id"] == n[0], r
        return r

    def call(name, **args):
        r = rpc("tools/call", {"name": name, "arguments": args})["result"]
        return r.get("isError", False), r["content"][0]["text"]
    try:
        r = rpc("initialize", {"protocolVersion": PROTOCOL, "capabilities": {}, "clientInfo": {"name": "demo", "version": "0"}})
        assert r["result"]["serverInfo"]["name"] == "cooked", r
        srv.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        names = {t["name"] for t in rpc("tools/list")["result"]["tools"]}
        assert names == {"list_videos", "open_video", "get_notes", "show", "scene_ops", "add_item", "resolve_note",
                         "hand_back", "export"}, names
        err, out = call("list_videos")
        assert not err and json.loads(out)[0]["name"] == "demo", out
        err, out = call("show", edit="demo")
        assert not err and "video" in out, out
        err, out = call("add_item", edit="demo", type="text", start=0.5, end=1.5, text="hello", why="demo text")
        assert not err and "demo text" in out and "added" in out, out
        err, out = call("show", edit="demo", at=1)
        assert "hello" in out, out
        err, url = call("open_video", edit="demo", open=False)
        assert not err and url.startswith("http://127.0.0.1:") and "?t=" in url, url
        s = json.loads(urllib.request.urlopen(url.replace("/?t=", "/state?t="), timeout=5).read())
        assert s.get("folder") == str(edit.resolve()), s
        err, out = call("get_notes", edit="demo", timeout=2)
        assert out.startswith("NO NOTES YET"), out
        err, out = call("export", edit="demo", timeout=5)
        assert "Export opens on the edit" in out, out   # a cut round: the page's Export is for the styled edit
        err, out = call("show", edit="nope")
        assert err and "no edit called" in out, out
        assert "error" in rpc("tools/call", {"name": "bogus"}), "unknown tool is an error"
    finally:
        srv.stdin.close()
        srv.wait(timeout=10)
        shutil.rmtree(tmp, ignore_errors=True)
    try:
        urllib.request.urlopen(url.replace("/?t=", "/state?t="), timeout=2)
        raise AssertionError("the review server outlived the MCP server")
    except OSError:
        pass
    print("mcp demo ok")


if __name__ == "__main__":
    demo() if sys.argv[1:] == ["demo"] else serve()
