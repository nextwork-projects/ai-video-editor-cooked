#!/usr/bin/env python3
"""The videos, images and links a user adds to one video: New video's "Add videos, images or links" and the
editor's "Anything to add?". Stdlib only, stored on this computer only.

    <edit>/assets/asset-img1.png ...   the images (png, jpeg, gif, webp; under 15 MB each)
    <edit>/assets/asset-vid1.mp4 ...   the videos (mp4, mov, m4v, webm; under 2 GB each)
    <edit>/media/<name> ...            the editor's Media panel uploads (save_media): dragged onto the video by the user,
                                       not listed in assets.json, so Claude is not asked to place them
    <edit>/assets.json                 {"items": [{"kind": "image", "src": "assets/asset-img1.png", "name": "chart.png", "say": ""},
                                                  {"kind": "video", "src": "assets/asset-vid1.mov", "name": "demo.mov", "say": ""},
                                                  {"kind": "link", "url": "https://x.com/...", "site": "x", "say": "the launch"}]}

MAX_ITEMS (50) of any kind. `say` is the optional "Show when I say..." words. `site` is x, youtube, github or web.
visual-prep, style-edit and overlays put every item in first, as a card on its `say` words (else the line it is
about), before searching for anything else (images.json for an image, a video_card for a video; a post, youtube,
github or capture beat in visuals.json for a link).

Files arrive one per request (save_stream: the editor's upload), or already on disk under a staging folder the
caller names (add's {"file": path}: New video uploads before the edit folder exists). Pasted images can still come
as data urls ({"image": "data:image/..."}).

    python3 assets.py show <edit>      print assets.json
    python3 assets.py demo             self-check
"""
import json
import os
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import askhook  # noqa: E402

MAX_ITEMS = 50
MAX_VIDEO = 2 << 30
IMG_EXT = {".png": "png", ".jpg": "jpg", ".jpeg": "jpg", ".gif": "gif", ".webp": "webp"}
VID_EXT = {".mp4", ".mov", ".m4v", ".webm"}
SITES = {"x.com": "x", "twitter.com": "x", "youtube.com": "youtube", "youtu.be": "youtube", "github.com": "github"}


def site(url):
    host = urlparse(url).netloc.lower().split(":")[0]
    host = re.sub(r"^(www\.|m\.|mobile\.)", "", host)
    return SITES.get(host, "web")


def load(edit):
    try:
        return json.loads((Path(edit) / "assets.json").read_text(encoding="utf-8")).get("items") or []
    except (OSError, ValueError, AttributeError):
        return []


def _save(edit, items):
    f = Path(edit) / "assets.json"
    if not items:
        f.unlink(missing_ok=True)
        return items
    f.write_text(json.dumps({"items": items}, indent=1) + "\n", encoding="utf-8")
    return items


def kind_of(name):
    """"image", "video" or None, by the file's extension."""
    ext = Path(str(name)).suffix.lower()
    return "image" if ext in IMG_EXT else "video" if ext in VID_EXT else None


def _say(it):
    return re.sub(r"\s+", " ", str(it.get("say") or "")).strip()[:120]


def _slot(edit, kind, ext):
    """The next free <edit>/assets/asset-img<k>.<ext> or asset-vid<k>.<ext>."""
    folder, tag = Path(edit) / "assets", "img" if kind == "image" else "vid"
    folder.mkdir(parents=True, exist_ok=True)
    k = 1
    while any(folder.glob(f"asset-{tag}{k}.*")):
        k += 1
    return folder / f"asset-{tag}{k}{'.' + IMG_EXT[ext] if kind == 'image' else ext}"


def _fits(path, kind):
    n = Path(path).stat().st_size
    return 0 < n <= (askhook.MAX_IMAGE if kind == "image" else MAX_VIDEO)


def _inside(path, root):
    try:
        return Path(root).resolve() in Path(path).resolve().parents
    except (OSError, ValueError):
        return False


def add(edit, new, staged=None):
    """new: [{"url": ..., "say": ...} | {"image": "data:image/...", "name": ..., "say": ...} |
    {"file": <path under staged>, "name": ..., "say": ...}]. A link that is not http(s), a repeat, a file outside
    staged, a file of the wrong type or size, or anything past MAX_ITEMS is dropped. A file is hard-linked (else
    copied) in, so one upload can go into several edits. The full list after."""
    edit, items = Path(edit), load(edit)
    for it in new or []:
        if not isinstance(it, dict) or len(items) >= MAX_ITEMS:
            continue
        say, url = _say(it), str(it.get("url") or "").strip()
        if url:
            if not re.match(r"https?://[^\s/]+\.[^\s]+$", url, re.I) or len(url) > 2000 \
                    or any(x.get("url") == url for x in items):
                continue
            items.append({"kind": "link", "url": url, "site": site(url), "say": say})
        elif it.get("image"):
            saved = askhook.save_images(edit / "assets", [it["image"]], "asset")
            if saved:
                name = Path(str(it.get("name") or saved[0])).name[:120]
                items.append({"kind": "image", "src": f"assets/{saved[0]}", "name": name, "say": say})
        elif it.get("file") and staged:
            f = Path(str(it["file"]))
            kind = kind_of(f)
            if not kind or not _inside(f, staged) or not f.is_file() or not _fits(f, kind):
                continue
            out = _slot(edit, kind, f.suffix.lower())
            try:
                os.link(f, out)
            except OSError:
                shutil.copyfile(f, out)
            name = Path(str(it.get("name") or f.name)).name[:120]
            items.append({"kind": kind, "src": f"assets/{out.name}", "name": name, "say": say})
    return _save(edit, items)


def save_stream(edit, name, stream, n, say=""):
    """One uploaded file (the editor's "Anything to add?"): n bytes of stream into <edit>/assets/. The full list
    after; ValueError with the words to show when it cannot go in."""
    edit, items, name = Path(edit), load(edit), Path(str(name or "")).name[:120]
    kind = kind_of(name)
    if not kind:
        raise ValueError("Add a video (.mp4, .mov, .m4v, .webm) or an image (.png, .jpg, .gif, .webp).")
    if len(items) >= MAX_ITEMS:
        raise ValueError(f"{MAX_ITEMS} at most. Take one out first.")
    if not 0 < n <= (askhook.MAX_IMAGE if kind == "image" else MAX_VIDEO):
        raise ValueError(f"{name} is over {'15 MB' if kind == 'image' else '2 GB'}.")
    out = _slot(edit, kind, Path(name).suffix.lower())
    _stream_to(out, stream, n)
    items.append({"kind": kind, "src": f"assets/{out.name}", "name": name, "say": _say({"say": say})})
    return _save(edit, items)


def _stream_to(out, stream, n):
    """n bytes of stream into out, by way of a .part file: a stopped upload leaves nothing behind."""
    tmp = out.with_name(out.name + ".part")
    left = n
    with open(tmp, "wb") as f:
        while left > 0:
            b = stream.read(min(1 << 20, left))
            if not b:
                break
            f.write(b)
            left -= len(b)
    if left:
        tmp.unlink(missing_ok=True)
        raise ValueError("The upload stopped part way. Add it again.")
    os.replace(tmp, out)


def save_media(edit, name, stream, n):
    """The editor's Media panel: one file into <edit>/media/ under its own name (-2, -3 when taken). Not in assets.json:
    Claude is not asked to place it, the user drags it onto the video. Its src ("media/<name>")."""
    name = re.sub(r"[^\w.\- ]+", "", Path(str(name or "")).name).strip()[:120]
    kind = kind_of(name)
    if not kind or name.startswith("."):
        raise ValueError("Add a video (.mp4, .mov, .m4v, .webm) or an image (.png, .jpg, .gif, .webp).")
    if not 0 < n <= (askhook.MAX_IMAGE if kind == "image" else MAX_VIDEO):
        raise ValueError(f"{name} is over {'15 MB' if kind == 'image' else '2 GB'}.")
    folder = Path(edit) / "media"
    folder.mkdir(parents=True, exist_ok=True)
    out, k = folder / name, 2
    while out.exists():
        out, k = folder / f"{Path(name).stem}-{k}{Path(name).suffix}", k + 1
    _stream_to(out, stream, n)
    return f"media/{out.name}"


def media(edit, used=()):
    """The Media panel's files: media/ (newest first), the files in assets.json, then `used` (the srcs the plan's cards
    show). [{"src", "kind", "name"}], each file once."""
    edit, out = Path(edit), {}
    ms = sorted((p for p in (edit / "media").glob("*") if p.is_file() and kind_of(p)), key=lambda p: -p.stat().st_mtime)
    for src, name in [(f"media/{p.name}", p.name) for p in ms] + [(x["src"], x.get("name") or "") for x in load(edit) if x.get("src")] \
            + [(u, "") for u in used]:
        if src not in out and kind_of(src) and (edit / src).is_file():
            out[src] = {"src": src, "kind": kind_of(src), "name": name or Path(src).name}
    return list(out.values())


def remove(edit, i):
    items = load(edit)
    if 0 <= i < len(items):
        x = items.pop(i)
        if x.get("src"):
            (Path(edit) / x["src"]).unlink(missing_ok=True)
    return _save(edit, items)


def demo():
    import tempfile
    e = Path(tempfile.mkdtemp(prefix="assets_demo_"))
    png = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJ"
           "RU5ErkJggg==")
    assert load(e) == [] and add(e, []) == [] and not (e / "assets.json").exists()
    out = add(e, [{"url": "https://x.com/a/status/1", "say": "  the   launch "}, {"url": "https://github.com/a/b"},
                  {"url": "javascript:alert(1)"}, {"url": "https://x.com/a/status/1"}, {"url": "file:///etc/passwd"},
                  {"image": png, "name": "../chart.png", "say": "chart"}, {"image": "data:text/html;base64,PGI+"}, "junk"])
    assert [x["kind"] for x in out] == ["link", "link", "image"], out
    assert out[0] == {"kind": "link", "url": "https://x.com/a/status/1", "site": "x", "say": "the launch"}, out[0]
    assert out[1]["site"] == "github" and site("https://www.youtube.com/watch?v=1") == "youtube" and site("https://docs.python.org") == "web"
    assert out[2]["src"] == "assets/asset-img1.png" and out[2]["name"] == "chart.png" and (e / out[2]["src"]).is_file()
    assert json.loads((e / "assets.json").read_text(encoding="utf-8"))["items"] == out
    for _ in range(askhook.MAX_IMAGES + 2):
        add(e, [{"image": png}])
    assert sum(x["kind"] == "image" for x in load(e)) == askhook.MAX_IMAGES + 3, "more images than a note can carry"
    # files: staged uploads (New video) and streamed ones (the editor), videos and images alike
    st = Path(tempfile.mkdtemp(prefix="assets_staged_"))
    (st / "demo.mov").write_bytes(b"v" * 10)
    (st / "pic.webp").write_bytes(b"i" * 10)
    (st / "notes.txt").write_bytes(b"t")
    outside = e.parent / (e.name + "-outside.mp4")
    outside.write_bytes(b"x")
    n = len(load(e))
    out = add(e, [{"file": str(st / "demo.mov"), "say": "the demo"}, {"file": str(st / "pic.webp")},
                  {"file": str(st / "notes.txt")}, {"file": str(outside)}, {"file": str(st / ".." / outside.name)}], staged=st)
    assert [x["kind"] for x in out[n:]] == ["video", "image"], out[n:]
    assert out[n] == {"kind": "video", "src": "assets/asset-vid1.mov", "name": "demo.mov", "say": "the demo"}, out[n]
    assert out[n + 1]["src"] == "assets/asset-img10.webp" and (e / out[n]["src"]).read_bytes() == b"v" * 10
    assert len(add(e, [{"file": str(st / "demo.mov")}])) == n + 2, "a file without a staging folder is dropped"
    import io
    out = save_stream(e, "../clip.MP4", io.BytesIO(b"c" * 5), 5, "  my clip ")
    assert out[-1] == {"kind": "video", "src": "assets/asset-vid2.mp4", "name": "clip.MP4", "say": "my clip"}, out[-1]
    for bad, size, words in (("a.txt", 3, "Add a video"), ("b.png", askhook.MAX_IMAGE + 1, "over 15 MB"), ("c.mp4", 9, "stopped")):
        try:
            save_stream(e, bad, io.BytesIO(b"z" * 3), size)
            raise AssertionError(bad)
        except ValueError as err:
            assert words in str(err), err
    assert not list((e / "assets").glob("*.part")), "a stopped upload leaves no file behind"
    big = "data:image/png;base64," + "A" * (askhook.MAX_IMAGE * 4 // 3 + 8)
    n = len(load(e))
    remove(e, 2)
    assert not (e / "assets/asset-img1.png").exists() and len(load(e)) == n - 1
    assert len(add(e, [{"image": big}])) == n - 1, "an image over 15 MB is dropped"
    add(e, [{"url": f"https://example.com/{i}"} for i in range(MAX_ITEMS + 5)])
    assert len(load(e)) == MAX_ITEMS, "50 of any kind"
    try:
        save_stream(e, "d.mp4", io.BytesIO(b"d"), 1)
        raise AssertionError("past MAX_ITEMS")
    except ValueError as err:
        assert "50 at most" in str(err)
    # the Media panel: files into media/ under their own names, not asked of Claude (assets.json untouched)
    n = len(load(e))
    assert save_media(e, "../My pic.png", io.BytesIO(b"p" * 4), 4) == "media/My pic.png"
    assert save_media(e, "My pic.png", io.BytesIO(b"q" * 4), 4) == "media/My pic-2.png" and len(load(e)) == n
    for bad in (".png", "x.html"):
        try:
            save_media(e, bad, io.BytesIO(b"z"), 1)
            raise AssertionError(bad)
        except ValueError:
            pass
    ms = media(e, ["media/My pic.png", "images/gone.png"])
    assert [m["src"] for m in ms][:2] == ["media/My pic-2.png", "media/My pic.png"] or [m["src"] for m in ms][:2] == ["media/My pic.png", "media/My pic-2.png"], ms
    assert len([m for m in ms if m["src"].startswith("media/")]) == 2 and not any(m["src"] == "images/gone.png" for m in ms), ms
    for _ in range(len(load(e))):
        remove(e, 0)
    assert load(e) == [] and not (e / "assets.json").exists() and remove(e, 5) == []
    print("assets demo ok")


if __name__ == "__main__":
    if sys.argv[1:2] == ["demo"]:
        demo()
    elif sys.argv[1:2] == ["show"] and len(sys.argv) > 2:
        print(json.dumps({"items": load(sys.argv[2])}, indent=1))
    else:
        print(__doc__)
