#!/usr/bin/env python3
"""Claude's questions in the editor's window. Stdlib only.

A PreToolUse hook on AskUserQuestion (hooks/hooks.json) runs this with the hook JSON on stdin. When the
home page or a review page is open and showing right now, the question appears there and the user answers
in the page: the hook returns the answers as the tool's input (permissionDecision "allow" + updatedInput
with "answers", the documented way to answer AskUserQuestion from a hook), so the terminal box never shows.

    python3 askhook.py           the hook (stdin: hook JSON). Prints nothing and exits 0 when no page is
                                 showing, on "Answer in Claude Code instead", once every page that had the
                                 question closed (never on time alone while one is open) and on any error:
                                 Claude Code then shows its own question box
    python3 askhook.py demo      self-check against a throwaway server

How a page is found: home.py and review.py each write $AI_EDITOR_HOME/pages/<port> (0600) when they start,
JSON {"url": the page's URL with its token, "kind": "home" | "review", "session": the Claude Code session
that started it}, and touch it each time an open page polls GET /ask (ask.js: every second, less often in a
background tab, which the browser slows to about once a minute). A file touched in the last 90 s is an open page,
showing or not: a question for a video in a background tab waits there, the tab's title says "(1) Claude is asking"
and the page shows it the moment the tab is looked at. A closed tab says so (POST /ask/gone). No port is ever
scanned. An old file holding only the URL belongs to no session, so it never gets a question.

Which video: a question belongs to one video (asking_edit). The hook reads the asking Claude's own transcript
(transcript_path) and takes the video its latest command named, by its edit folder's full path or as edits/<name>
(a later `home.py status teardown|setup|skill...` means it moved on: no video). Else the video job that session took
last, else the edit it last ran a review.py command on. The hook sends it as "edit": only that video's editor takes
it, every page labels it with that video's name (review.json label or name, else the folder), and while it waits
<edit>/review/asking marks the video "Your turn" in Your videos; its open time goes to <edit>/review/asks.jsonl, which
review.py's "Made in" leaves out. With no video known, the session rules below decide.

Whose question: the hook sends its session_id with the question, and each server takes it only when that
session is working there (srv.ask_owner, set by register): a review page, the session that last ran a
command on that edit or holds that edit's video job on the home page (a session holding a job on the home page asks
only on that job's edit page, never another's); the home page, a session holding one of its jobs or listening for
one. Every open page that takes it gets it, and the first answer wins. When the video's editor took it, the home page
gets it marked "elsewhere": Home and its sidebar job card show a row "Claude is asking about <video>" with Open, not
the card, so a question about a video shows in that video's editor tab. A server that
knows no session at all (a Claude Code without CLAUDE_CODE_SESSION_ID) takes any question, as before. The
card says what it is about ("Claude (team-250k-general) asks"). No server takes it: the terminal box shows.

The servers (route() below, called from both):
    GET  /ask.js                 the card's script
    GET  /ask[?v=1]              the page's poll: the oldest open question or null (v=1: the page is showing)
                                 {id, questions, about, elsewhere}: elsewhere, the editor page has it too; "all":
                                 every open one, oldest first (Home: one row per question)
    GET  /ask?id=X               the hook's poll: {"result": null | {"answers": [...]} | {"terminal": true}}
    POST /ask {id, questions, elsewhere?}   the hook asks (elsewhere: the video's editor page has it too)
    POST /ask/answer {id, answers | terminal, images?}   the page answers (one string per question; images: one
                                 list of image data urls per question, saved where the server keeps them, see below)
    POST /ask/clear {id}         the hook is done: every page drops it
    POST /ask/gone               the tab closed (pagehide beacon): not showing any more, so no question waits on it

Images on an answer (the paperclip, a paste or a drop on the card): png, jpeg, gif or webp, under 15 MB each, at most 6
per answer, the review notes' limits. Saved on this computer only: a review page keeps them in <edit>/review/ beside its
notes' pictures, the home page in the asking job's <edit>/asks/ (or $AI_EDITOR_HOME/asks with no edit folder yet). The
answer Claude gets ends with a line "Attached images: /abs/a.png (Read each one to see it)".
"""
import base64
import json
import os
import re
import secrets
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

JS = Path(__file__).with_name("ask.js")
LIVE_S = 90          # a page polled this recently is open (a background tab polls about once a minute)
# No timeout while a page that has the question is open (polled in the last LIVE_S): the user answers there, however
# long they take (hooks.json gives the hook a day). Only once every such page closed does the terminal box show.
# AI_EDITOR_ASK_TIMEOUT (seconds) caps it anyway (the self-check).
KEEP_S = 120         # a question whose hook stopped polling (Esc in Claude Code) leaves the pages by then
CHECK_S = 20         # how often the waiting hook looks for an open page
TERM_S = 1800       # a Terminal notice older than this: Claude gave up waiting, or the user answered elsewhere
MARK_S = 120         # <edit>/review/asking older than this: its hook stopped (the hook touches it while it waits)
MAX_IMAGE = 15 << 20      # an attached image (review notes and answers)
MAX_IMAGES = 6
MAX_BODY = MAX_IMAGES * MAX_IMAGE * 4 // 3 + (1 << 20)   # a POST carrying that many, base64


def save_images(folder, imgs, prefix, keep=()):
    """Attached pictures: names already kept (keep) and pasted, dropped or picked data urls (saved into folder).
    Only png, jpeg, gif and webp, under MAX_IMAGE each, at most MAX_IMAGES. The saved names, in order."""
    out = []
    for im in imgs:
        if len(out) == MAX_IMAGES or not isinstance(im, str):
            continue
        if im in keep:
            out.append(im)
            continue
        m = re.match(r"data:image/(png|jpeg|gif|webp);base64,(.+)", im, re.S)
        if not m:
            continue
        try:
            raw = base64.b64decode(m[2])
        except ValueError:
            continue
        if len(raw) > MAX_IMAGE:
            continue
        folder.mkdir(parents=True, exist_ok=True)
        k = 1
        while any((folder / f"{prefix}-img{k}.{x}").exists() for x in ("jpg", "png", "gif", "webp")):
            k += 1
        name = f"{prefix}-img{k}.{'jpg' if m[1] == 'jpeg' else m[1]}"
        (folder / name).write_bytes(raw)
        out.append(name)
    return out


def with_images(text, paths):
    """An answer and the images attached to it, as the text Claude reads."""
    if not paths:
        return text
    line = "Attached images: " + ", ".join(str(p) for p in paths) + " (Read each one to see it)"
    return text + "\n" + line if text else line


def pages():
    return Path(os.environ.get("AI_EDITOR_HOME", "").strip() or Path.home() / ".ai-video-editor") / "pages"


def session():
    """The Claude Code session this process runs in (Bash commands Claude runs carry it), or ""."""
    return os.environ.get("CLAUDE_CODE_SESSION_ID", "").strip()


def claude_env(env=None):
    """Which Claude Code runs this command, from its env: {session, host_session, kind}, kind "desktop" (the Claude
    desktop app's Code tab), "terminal" (the CLI) or "other" (an IDE, the SDK); {} outside Claude Code."""
    env = os.environ if env is None else env
    sid = env.get("CLAUDE_CODE_SESSION_ID", "").strip()
    if not sid:
        return {}
    ep = env.get("CLAUDE_CODE_ENTRYPOINT", "").strip()
    kind = "desktop" if ep == "claude-desktop" else "terminal" if ep in ("", "cli") else "other"
    return {"session": sid, "host_session": env.get("CLAUDE_CODE_HOST_SESSION_ID", "").strip(), "kind": kind}


def register(srv, url, kind=None, owner=None, where=None, folder=None):
    """A server's page file, touched while a page is showing. owner(session_id) -> what the question is
    about ("" for nothing to name), or None when that session's questions do not belong on this page.
    where(session_id) -> the folder an answer's images are saved in (default $AI_EDITOR_HOME/asks).
    folder: a review page's edit folder (in the page file, so the hook knows which video each editor shows)."""
    srv.ask_url, srv.asks = url, {}
    srv.ask_kind = kind or getattr(srv, "ask_kind", None)
    srv.ask_owner = owner or getattr(srv, "ask_owner", None)
    srv.ask_where = where or getattr(srv, "ask_where", None)
    srv.ask_folder = folder or getattr(srv, "ask_folder", None)
    p = pages() / str(srv.server_address[1])
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with os.fdopen(os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
            json.dump({"url": url, "kind": srv.ask_kind, "session": session(),
                       **({"folder": str(Path(srv.ask_folder).resolve())} if srv.ask_folder else {})}, f)
        os.utime(p, (0, 0))   # not showing until a page polls
    except OSError:
        pass


def same_origin(h):
    """A POST from the page itself: no Origin header (curl, the hook) or this server's own address."""
    o = h.headers.get("Origin")
    return not o or o == "http://" + (h.headers.get("Host") or "")


def _seen(srv):
    p = pages() / str(srv.server_address[1])
    try:
        os.utime(p)
    except FileNotFoundError:
        register(srv, srv.ask_url)
        os.utime(p)
    except OSError:
        pass


def route(h, method, path, query, body=None):
    """Serves /ask* for a home or review handler h (already authorized). True when it answered."""
    if not (path == "/ask.js" or path == "/ask" or path.startswith("/ask/")):
        return False
    srv = h.server
    asks = getattr(srv, "asks", None)
    if asks is None:
        srv.asks = asks = {}
    for k in [k for k, a in asks.items() if time.time() - a.get("polled", a["at"]) > KEEP_S]:
        asks.pop(k, None)
    if method == "GET" and path == "/ask.js":
        h.send(200, JS.read_bytes(), "text/javascript; charset=utf-8")
    elif method == "GET" and path == "/ask":
        if query.get("id"):
            a = asks.get(query["id"])
            if a:   # the hook still waits on it: it stays
                a["polled"] = time.time()
            h.send(200 if a else 404, {"result": a and a.get("result")})
        else:
            if getattr(srv, "ask_url", None):   # open, showing or in a background tab
                _seen(srv)
            every = [dict(id=k, questions=a["questions"], about=a.get("about") or "", **({"elsewhere": True} if a.get("elsewhere") else {}))
                     for k, a in sorted(asks.items(), key=lambda x: x[1]["at"]) if not a.get("result")]
            h.send(200, {"ask": every[0] if every else None, "all": every, "terminal": terminal()})   # all: Home shows one row per open question
    elif method == "POST" and path == "/ask":
        qs = body.get("questions")
        if not (isinstance(body.get("id"), str) and isinstance(qs, list) and 0 < len(qs) <= 10):
            return h.send(400, {}) or True
        owner, sid = getattr(srv, "ask_owner", None), body.get("session")
        edit = Path(body["edit"]).resolve() if isinstance(body.get("edit"), str) and body["edit"] else None
        mine = getattr(srv, "ask_folder", None)
        if edit:   # the hook knows the video: that video's editor only, and Home names it
            if mine and Path(mine).resolve() != edit:
                return h.send(409, {}) or True
            about = edit_name(edit)
        else:
            about = owner(sid if isinstance(sid, str) else "") if owner else None
        if about is None:   # another session's question: not for this page
            return h.send(409, {}) or True
        where = getattr(srv, "ask_where", None)
        folder = (edit / ("review" if mine else "asks")) if edit else where(sid if isinstance(sid, str) else "") if where else None
        asks[body["id"]] = {"questions": qs, "at": time.time(), "about": about, "elsewhere": body.get("elsewhere") is True,
                            "dir": str(folder or pages().parent / "asks"), **({"edit": str(edit)} if edit else {})}
        h.send(200, {})
    elif method == "POST" and path == "/ask/answer":
        a = asks.get(body.get("id"))
        ans = body.get("answers")
        if not a or a.get("result"):
            return h.send(409, {}) or True
        imgs = body.get("images") or [[] for _ in a["questions"]]
        if body.get("terminal") is True:
            a["result"] = {"terminal": True}
        elif isinstance(ans, list) and len(ans) == len(a["questions"]) and isinstance(imgs, list) \
                and len(imgs) == len(ans) and all(isinstance(x, str) and len(x) <= 4000 and isinstance(m, list)
                                                  and (x.strip() or m) for x, m in zip(ans, imgs)):
            folder, tag = Path(a["dir"]), re.sub(r"[^\w-]", "", body["id"])[:16]
            out = [with_images(x.strip(), [folder / n for n in save_images(folder, m, f"ask-{tag}-q{k + 1}")])
                   for k, (x, m) in enumerate(zip(ans, imgs))]
            if not all(out):   # images only, and none of them an image
                return h.send(400, {}) or True
            a["result"] = {"answers": out}
        else:
            return h.send(400, {}) or True
        h.send(200, {})
    elif method == "POST" and path == "/ask/gone":
        try:
            os.utime(pages() / str(srv.server_address[1]), (0, 0))
        except OSError:
            pass
        h.send(200, {})
    elif method == "POST" and path == "/ask/clear":
        asks.pop(body.get("id"), None)
        h.send(200, {})
    else:
        h.send(404, {})
    return True


# ---------------------------------------------------------------- the hook
def terminal():
    """Claude waiting for the user in a Terminal window (toolhook.py notify), under TERM_S old, else None."""
    try:
        t = json.loads((pages().parent / "terminal.json").read_text(encoding="utf-8"))
        return t if time.time() - float(t["at"]) < TERM_S else None
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def say_terminal(sid, message):
    """Every open page shows "Claude needs you in the Terminal window" with message and chimes once (ask.js).
    The session's next tool call or prompt clears it (toolhook.py)."""
    try:
        f = pages().parent / "terminal.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"session": sid, "message": str(message)[:300], "at": round(time.time(), 2)}), encoding="utf-8")
        return f
    except OSError:
        return None


def live_pages(kind=None):
    """The page files of pages showing now (of that kind): {url, kind, session, folder?}. Old plain-URL files are
    left out: no session owns them."""
    out = []
    try:
        for f in pages().iterdir():
            if time.time() - f.stat().st_mtime < LIVE_S:
                try:
                    d = json.loads(f.read_text(encoding="utf-8"))
                except ValueError:
                    continue
                url = d.get("url") if isinstance(d, dict) else None
                if isinstance(url, str) and url.startswith(("http://127.0.0.1:", "http://localhost:")) and "/?t=" in url \
                        and (kind is None or d.get("kind") == kind):
                    out.append(d)
    except OSError:
        pass
    return out


def live(kind=None):
    """The URLs of pages showing now (of that kind)."""
    return [d["url"] for d in live_pages(kind)]


def edit_name(edit):
    """A video's name as Your videos shows it: the editor's label or name, else its folder's name."""
    try:
        r = json.loads((Path(edit) / "review.json").read_text(encoding="utf-8"))
        return str(r.get("label") or r.get("name") or Path(edit).name)
    except (OSError, ValueError, AttributeError):
        return Path(edit).name


def home_jobs():
    try:
        jobs = json.loads((pages().parent / "home" / "state.json").read_text(encoding="utf-8")).get("jobs") or []
        return [j for j in jobs if isinstance(j, dict)]
    except (OSError, ValueError, AttributeError):
        return []


def commands(transcript, tail=4 << 20):
    """The tool calls in a Claude Code transcript (JSONL), oldest first, as text: what that Claude ran, in order."""
    try:
        with open(transcript, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - tail))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except (OSError, TypeError, ValueError):
        return []
    out = []
    for ln in lines:
        if '"tool_use"' not in ln:
            continue
        try:
            msg = json.loads(ln).get("message") or {}
        except ValueError:
            continue
        for c in msg.get("content") or [] if isinstance(msg, dict) else []:
            if isinstance(c, dict) and c.get("type") == "tool_use" and c.get("name") != "AskUserQuestion":
                out.append(json.dumps(c.get("input"), ensure_ascii=False))
    return out


OTHER_JOB = re.compile(r"(?:home\.py|\$\{?H\}?)\W{0,3}\s*status (?:setup|teardown|skill|style-change|skill-change|skill-new)\b")


def asking_edit(payload, sid=""):
    """The one video a question is about, or None. Best: of the videos the window knows (the home jobs' edit folders
    and every open editor), the one the asking Claude's own last command named (its transcript, the hook's
    transcript_path), by full path or as edits/<name> from the library. Else the video job that session holds, the
    one it took last. Else the edit it last ran a review.py command on (review/.session)."""
    cands = {Path(j["args"]["edit"]).resolve() for j in home_jobs() if j.get("type") == "video"
             and isinstance((j.get("args") or {}).get("edit"), str) and j["args"]["edit"]}
    cands |= {Path(d["folder"]).resolve() for d in live_pages("review") if isinstance(d.get("folder"), str)}
    pats = [(f, re.compile("(?:" + "|".join(re.escape(x) for x in {str(f), json.dumps(str(f))[1:-1], f"edits/{f.name}"})
                            + r")(?![\w.-])")) for f in cands]
    for cmd in reversed(commands(payload.get("transcript_path"))):
        hit = max(((m.start(), f) for f, p in pats for m in p.finditer(cmd)), default=None, key=lambda x: x[0])
        if hit:
            return hit[1]
        if OTHER_JOB.search(cmd):   # it moved on to setup, a creator or a skill since: about no video
            return None
    if not sid:
        return None
    held = [j for j in home_jobs() if j.get("type") == "video" and j.get("state") == "taken" and j.get("owner") == sid
            and isinstance((j.get("args") or {}).get("edit"), str)]
    if held:
        return Path(max(held, key=lambda j: j.get("u") or 0)["args"]["edit"]).resolve()
    ran = []
    for f in cands:
        try:
            p = f / "review" / ".session"
            if p.read_text(encoding="utf-8").strip() == sid:
                ran.append((p.stat().st_mtime, f))
        except OSError:
            pass
    return max(ran)[1] if ran else None


def mark(edit, start, end=None):
    """<edit>/review/asking while a question waits on the user (Your videos: "Your turn"), and each one's open time in
    <edit>/review/asks.jsonl once it closes (review.py timings takes it out of "Made in")."""
    try:
        d = Path(edit) / "review"
        d.mkdir(parents=True, exist_ok=True)
        if end is None:
            (d / "asking").write_text(str(start), encoding="utf-8")
            return
        (d / "asking").unlink(missing_ok=True)
        with open(d / "asks.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"start": round(start, 2), "end": round(end, 2)}) + "\n")
    except OSError:
        pass


def _call(url, path, body=None, timeout=3):
    base, tok = url.split("/?t=", 1)
    sep = "&" if "?" in path else "?"
    req = urllib.request.Request(base + path + sep + "t=" + tok, json.dumps(body).encode() if body is not None else None,
                                 method="POST" if body is not None else "GET")
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read() or b"{}")


def relay(payload, timeout=None, poll=0.5):
    """The hook's stdout (a JSON string), or None for Claude Code's own question box."""
    if payload.get("tool_name") != "AskUserQuestion":
        return None
    ti = payload.get("tool_input") or {}
    qs = ti.get("questions")
    if not isinstance(qs, list) or not qs:
        return None
    sid = payload.get("session_id")
    sid = sid if isinstance(sid, str) else ""
    qid = secrets.token_urlsafe(12)
    sent = []
    about = asking_edit(payload, sid)
    edit = live("review")
    for u in edit + [u for u in live() if u not in edit]:   # the video's editor first; Home marked when an editor has it
        try:
            _call(u, "/ask", {"id": qid, "questions": qs, "session": sid, "elsewhere": bool(sent) and u not in edit,
                              **({"edit": str(about)} if about else {})})
            sent.append(u)
        except Exception:   # 409: another session's page
            pass
    if not sent:   # no page took it: it goes to the terminal box, and every open page says so
        say_terminal(sid, "Claude is asking: " + str(qs[0].get("question") or "a question"))
        return None
    t0, result = time.time(), None
    if about:
        mark(about, t0)
    cap = timeout or float(os.environ.get("AI_EDITOR_ASK_TIMEOUT") or 0)
    end, beat = time.time() + cap if cap else None, 0
    try:
        while result is None and (end is None or time.time() < end):
            if time.time() - beat > CHECK_S:
                beat = time.time()
                if not set(sent) & set(live()):   # every page that had it closed: the terminal box
                    say_terminal(sid, "Claude is asking: " + str(qs[0].get("question") or "a question"))
                    break
                if about:
                    try:
                        os.utime(Path(about) / "review" / "asking")
                    except OSError:
                        pass
            for u in list(sent):
                try:
                    result = _call(u, "/ask?id=" + qid).get("result")
                except Exception:   # that page's server stopped: the others may still answer
                    sent.remove(u)
                if result:
                    break
            if not sent:
                break
            if result is None:
                time.sleep(poll)
    finally:
        if about:
            mark(about, t0, time.time())
        for u in sent:
            try:
                _call(u, "/ask/clear", {"id": qid})
            except Exception:
                pass
    if not result or not result.get("answers"):
        return None
    answers = {q.get("question", f"Question {i + 1}"): a for i, (q, a) in enumerate(zip(qs, result["answers"]))}
    return json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "allow",
        "permissionDecisionReason": "The user answered in the editor window.",
        "updatedInput": dict(ti, answers=answers)}})


def main():
    try:
        out = relay(json.loads(sys.stdin.read() or "{}"))
        if out:
            print(out)
    except Exception:
        pass   # never break Claude Code: its own box shows
    sys.exit(0)


# ---------------------------------------------------------------- demo
def demo():
    import shutil
    import subprocess
    import tempfile
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    tmp = Path(tempfile.mkdtemp(prefix="askhook_demo_"))
    os.environ["AI_EDITOR_HOME"] = str(tmp)
    tok = "demo-token"

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, body, ctype="application/json"):
            b = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def q(self):
            from urllib.parse import parse_qs, urlsplit
            s = urlsplit(self.path)
            return s.path, {k: v[0] for k, v in parse_qs(s.query).items()}

        def do_GET(self):
            path, q = self.q()
            assert q.get("t") == tok
            route(self, "GET", path, q) or self.send(404, {})

        def do_POST(self):
            path, q = self.q()
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            route(self, "POST", path, q, body) or self.send(404, {})

    def mk(sid, about, kind="review"):   # a page owned by one session
        srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{srv.server_address[1]}/?t={tok}"
        register(srv, url, kind, owner=lambda s: about if s == sid else None)
        return srv, url
    srv, url = mk("sess-A", "team-250k-general")
    qs = [{"question": "Which cut?", "header": "Cut", "multiSelect": False,
           "options": [{"label": "Tight (Recommended)", "description": "Every pause out"}, {"label": "Loose", "description": ""}]},
          {"question": "Which parts?", "header": "Parts", "multiSelect": True,
           "options": [{"label": "Captions", "description": ""}, {"label": "Zooms", "description": ""}]}]
    payload = {"hook_event_name": "PreToolUse", "tool_name": "AskUserQuestion", "tool_input": {"questions": qs},
               "session_id": "sess-A"}
    me = [sys.executable, str(Path(__file__).resolve())]

    # no page showing (registered, never polled): exits 0 at once, prints nothing
    t0 = time.time()
    r = subprocess.run(me, input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert r.returncode == 0 and r.stdout == "" and time.time() - t0 < 5, r
    # another tool, or garbage on stdin: silent
    for s in (json.dumps(dict(payload, tool_name="Bash")), "not json"):
        r = subprocess.run(me, input=s, capture_output=True, text=True, encoding="utf-8", timeout=30)
        assert r.returncode == 0 and r.stdout == "", r

    def page(url=url):   # a showing page: polls with v=1 until a question appears
        for _ in range(200):
            a = _call(url, "/ask?v=1")["ask"]
            if a:
                return a
            time.sleep(0.05)
        raise AssertionError("the question never reached the page")

    def run_hook(payload=payload):
        box = {}
        th = threading.Thread(target=lambda: box.update(r=subprocess.run(
            me, input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8", timeout=60)))
        th.start()
        return th, box

    _call(url, "/ask?v=1")
    assert [u for u in live()] == [url]
    # the answer path: one option, and the user's own words for a multi-select
    th, box = run_hook()
    a = page()
    assert a["questions"] == qs and a["about"] == "team-250k-general", a
    for bad in ({"id": a["id"], "answers": ["only one"]}, {"id": a["id"], "answers": ["x", ""]}, {"id": "nope", "answers": ["a", "b"]}):
        try:
            _call(url, "/ask/answer", bad)
            raise AssertionError(f"accepted {bad}")
        except urllib.error.HTTPError as e:
            assert e.code in (400, 409), e.code
    _call(url, "/ask/answer", {"id": a["id"], "answers": ["Tight (Recommended)", "Captions, Zooms"]})
    th.join()
    r = box["r"]
    assert r.returncode == 0, r
    o = json.loads(r.stdout)["hookSpecificOutput"]
    assert o["hookEventName"] == "PreToolUse" and o["permissionDecision"] == "allow", o
    assert o["updatedInput"] == {"questions": qs, "answers": {"Which cut?": "Tight (Recommended)", "Which parts?": "Captions, Zooms"}}, o
    assert _call(url, "/ask?v=1")["ask"] is None and not srv.asks, "answered: it leaves every page"
    # images on an answer: saved where the server keeps them, their absolute paths in the answer Claude gets
    png = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJ"
           "RU5ErkJggg==")
    srv.ask_where = lambda s: tmp / "edit" / "review"
    th, box = run_hook()
    a = page()
    for bad in ({"id": a["id"], "answers": ["", "x"], "images": [["data:text/html;base64,PGI+"], []]},
                {"id": a["id"], "answers": ["x", "y"], "images": [[png]]}):
        try:
            _call(url, "/ask/answer", bad)
            raise AssertionError(f"accepted {bad}")
        except urllib.error.HTTPError as e:
            assert e.code == 400, e.code
    _call(url, "/ask/answer", {"id": a["id"], "answers": ["Loose", ""], "images": [[png, "data:text/html;base64,PGI+"], [png]]})
    th.join()
    got = json.loads(box["r"].stdout)["hookSpecificOutput"]["updatedInput"]["answers"]
    saved = sorted((tmp / "edit" / "review").iterdir())
    assert [f.name for f in saved] == [f"ask-{a['id'][:16]}-q1-img1.png", f"ask-{a['id'][:16]}-q2-img1.png"], saved
    assert got == {"Which cut?": f"Loose\nAttached images: {saved[0]} (Read each one to see it)",
                   "Which parts?": f"Attached images: {saved[1]} (Read each one to see it)"}, got
    assert saved[0].read_bytes()[:4] == b"\x89PNG" and saved[0].is_absolute()
    srv.ask_where = None
    # "Answer in Claude Code instead": silent, cleared
    th, box = run_hook()
    _call(url, "/ask/answer", {"id": page()["id"], "terminal": True})
    th.join()
    assert box["r"].returncode == 0 and box["r"].stdout == "" and not srv.asks, box["r"]
    # timeout: silent, cleared
    os.environ["AI_EDITOR_ASK_TIMEOUT"] = "1"
    th, box = run_hook()
    page()
    th.join()
    assert box["r"].returncode == 0 and box["r"].stdout == "" and not srv.asks, box["r"]
    os.environ.pop("AI_EDITOR_ASK_TIMEOUT")
    # two sessions, two pages: each question lands only on its own session's page
    srv2, url2 = mk("sess-B", "")
    _call(url2, "/ask?v=1")
    assert sorted(live()) == sorted([url, url2]) and live("home") == []
    th, box = run_hook(dict(payload, session_id="sess-B"))
    b = page(url2)
    assert b["about"] == "" and _call(url, "/ask?v=1")["ask"] is None, "B's question stays off A's page"
    _call(url2, "/ask/answer", {"id": b["id"], "answers": ["Loose", "Zooms"]})
    th.join()
    assert json.loads(box["r"].stdout)["hookSpecificOutput"]["updatedInput"]["answers"]["Which cut?"] == "Loose"
    th, box = run_hook()
    assert page()["about"] == "team-250k-general" and _call(url2, "/ask?v=1")["ask"] is None, "A's stays off B's"
    _call(url, "/ask/answer", {"id": page()["id"], "terminal": True})
    th.join()
    # the home page open too, also A's: A's question shows as a card in A's editor, and on Home marked "elsewhere"
    # (Home shows a row with Open); B's (no editor of its own) on Home as the card
    srvH, urlH = mk("sess-A", "", "home")
    srvH.ask_owner = lambda s: "" if s in ("sess-A", "sess-D") else None
    _call(urlH, "/ask?v=1")
    th, box = run_hook()
    a = page()
    assert a["about"] == "team-250k-general" and "elsewhere" not in a and page(urlH)["elsewhere"] is True, "the editor, Home marked"
    _call(urlH, "/ask/answer", {"id": a["id"], "answers": ["Loose", "Zooms"]})   # answered on Home: the editor drops it too
    th.join()
    assert json.loads(box["r"].stdout)["hookSpecificOutput"]["updatedInput"]["answers"]["Which cut?"] == "Loose"
    assert not srv.asks and not srvH.asks
    # a background tab (polls without v=1, about once a minute): still open, so the question waits there, not the terminal
    os.utime(pages() / str(srvH.server_address[1]), (0, 0))
    os.utime(pages() / str(srv.server_address[1]), (time.time() - 60,) * 2)
    th, box = run_hook()
    for _ in range(100):
        if srv.asks:
            break
        time.sleep(0.05)
    assert srv.asks and not srvH.asks, "a tab polled 60 s ago still gets it"
    _call(url, "/ask")   # the hidden tab's next poll delivers it
    _call(url, "/ask/answer", {"id": next(iter(srv.asks)), "terminal": True})
    th.join()
    _call(urlH, "/ask?v=1")
    th, box = run_hook(dict(payload, session_id="sess-D"))
    d = page(urlH)
    assert not srv.asks and not srv2.asks, "no editor takes D's: Home does"
    _call(urlH, "/ask/answer", {"id": d["id"], "terminal": True})
    th.join()
    srvH.shutdown()
    srvH.server_close()
    (pages() / str(srvH.server_address[1])).unlink()
    # a third session with no page of its own, or no session id: the terminal box, at once
    for p in (dict(payload, session_id="sess-C"), {k: v for k, v in payload.items() if k != "session_id"}):
        t0 = time.time()
        r = subprocess.run(me, input=json.dumps(p), capture_output=True, text=True, encoding="utf-8", timeout=30)
        assert r.returncode == 0 and r.stdout == "" and time.time() - t0 < 5 and not srv.asks and not srv2.asks, r
    # a server that knows no session (Claude Code without the env var): any session's question, as before
    srv3, url3 = mk("", "")
    srv3.ask_owner = lambda s: ""
    _call(url3, "/ask?v=1")
    th, box = run_hook(dict(payload, session_id="sess-C"))
    c = page(url3)
    _call(url3, "/ask/answer", {"id": c["id"], "terminal": True})
    th.join()
    # the tab closed (pagehide beacon): that page is not showing any more
    _call(url3, "/ask/gone", {})
    assert url3 not in live()
    srv3.shutdown()
    srv3.server_close()
    (pages() / str(srv3.server_address[1])).unlink()
    # an old page file with only a URL: no session owns it
    old = pages() / "1"
    old.write_text(url, encoding="utf-8")
    assert old.stat().st_mtime > time.time() - LIVE_S and url in live() and live().count(url) == 1
    old.unlink()
    srv2.shutdown()
    srv2.server_close()
    (pages() / str(srv2.server_address[1])).unlink()
    # one session, three videos open (QA round 3: the question showed in all three editors, each with its own name):
    # the video its last command named gets it, labelled with that video's name; no other editor; Home names it too
    eds = [tmp / "lib" / "edits" / n for n in ("take", "take-2", "sample-video")]
    vs = []
    for e in eds:
        (e / "review").mkdir(parents=True)
        (e / "review" / ".session").write_text("sess-M", encoding="utf-8")
        s_, u_ = mk("sess-M", e.name)
        register(s_, u_, "review", folder=e)
        _call(u_, "/ask?v=1")
        vs.append((s_, u_))
    (eds[1] / "review.json").write_text(json.dumps({"name": "Second take"}), encoding="utf-8")
    sH, uH = mk("sess-M", "", "home")
    _call(uH, "/ask?v=1")
    tr = tmp / "t.jsonl"
    use = lambda *cmds: tr.write_text("\n".join(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Bash", "input": {"command": c}}]}}) for c in cmds) + "\n", encoding="utf-8")
    use(f"python3 review.py {eds[0]} wait", f'cd {tmp / "lib"} && python3 "$R" edits/take-2 status rendering', "ls")
    pm = dict(payload, session_id="sess-M", transcript_path=str(tr))
    assert asking_edit(pm, "sess-M") == eds[1].resolve(), "edits/take-2, the last one named (never take)"
    th, box = run_hook(pm)
    a = page(vs[1][1])
    assert a["about"] == "Second take" and not vs[0][0].asks and not vs[2][0].asks, "that video's editor only, by its name"
    h = page(uH)
    assert h["about"] == "Second take" and h["elsewhere"] is True, h
    assert (eds[1] / "review" / "asking").is_file(), "Your videos: its turn"
    _call(vs[1][1], "/ask/answer", {"id": a["id"], "answers": ["Loose", "Zooms"]})
    th.join()
    w = [json.loads(x) for x in (eds[1] / "review" / "asks.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(w) == 1 and w[0]["end"] >= w[0]["start"] and not (eds[1] / "review" / "asking").exists(), w
    use(f"python3 review.py {eds[2]} round", 'python3 "$H" status teardown --step "Listed their videos"')
    assert asking_edit(pm, "") is None, "moved on to a creator: about no video"
    use("ls")   # nothing named: the edit it last ran review.py on
    os.utime(eds[0] / "review" / ".session", (time.time() + 5,) * 2)
    assert asking_edit(pm, "sess-M") == eds[0].resolve()
    for s_, _ in vs + [(sH, uH)]:
        s_.shutdown()
        s_.server_close()
        (pages() / str(s_.server_address[1])).unlink()
    # no time limit while the page is open: a question waits there; the terminal box only once that page closed
    global CHECK_S
    CHECK_S, box = 0.2, {}
    _call(url, "/ask?v=1")
    th = threading.Thread(target=lambda: box.update(r=relay(payload)))
    th.start()
    page()
    time.sleep(1)
    assert th.is_alive(), "still waiting on the open page"
    os.utime(pages() / str(srv.server_address[1]), (0, 0))   # the tab closed
    th.join(10)
    assert not th.is_alive() and box["r"] is None and not srv.asks, "every page closed: the terminal box"
    CHECK_S = 20
    # the page went away (not polled for LIVE_S): silent again
    os.utime(pages() / str(srv.server_address[1]), (time.time() - LIVE_S - 1,) * 2)
    assert live() == [] and relay(payload) is None
    srv.shutdown()
    srv.server_close()
    shutil.rmtree(tmp, ignore_errors=True)
    print("askhook demo ok")


if __name__ == "__main__":
    demo() if sys.argv[1:2] == ["demo"] else main()
