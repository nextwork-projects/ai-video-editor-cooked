// The Scene composition: a scene.json (lib/ai_editor/SCENE.md) drawn item by item, the same live in the review page's
// player (preview/live.tsx mountScene) and for the export (scene.py render). Every element is an item with its own
// transform, so the page moves, crops and trims each one and the export is what the page shows.
// Track order is draw order (the first visual track is the bottom); inside a track a later item draws on top.
import React, { useLayoutEffect, useMemo, useRef, useState } from "react";
import { AbsoluteFill, Audio, CalculateMetadataFunction, Img, OffthreadVideo, Sequence, Video, getRemotionEnvironment, staticFile,
  useCurrentFrame, useVideoConfig } from "remotion";
import { Captions, CaptionStyle, Chunk, useFamily } from "./Captions";
import { Card, CardView } from "./StyleEdit";
import { ease, pickMotion, prog } from "./motion";
import { resolveLook, useFonts } from "./look";

type Key = [number, number, string?];
export type Asset = { src: string; url?: string; proxy?: string; kind?: string; w?: number; h?: number; duration?: number; alpha?: boolean };
type Box = { color: string; pad?: number | [number, number]; radius?: number; block?: boolean };
export type Item = {
  id: string; type: "video" | "image" | "text" | "shape" | "audio" | "captions" | "card"; start: number; end: number; name?: string;
  asset?: string; in?: number; speed?: number; volume?: number; fade_in?: number; fade_out?: number; locked?: boolean;
  x?: number; y?: number; w?: number; h?: number; rotation?: number; opacity?: number; fit?: "cover" | "contain";
  crop?: { l?: number; t?: number; r?: number; b?: number } | null; radius?: number;
  shadow?: { blur?: number; y?: number; opacity?: number } | null; border?: { width: number; color: string } | null;
  anim?: { in?: string; out?: string; dur?: number } | null; keys?: Record<string, Key[]>; grade?: { brightness?: number; saturate?: number };
  text?: string; font?: string; weight?: number; size?: number; color?: string; align?: "left" | "center" | "right"; line_height?: number;
  box?: Box | null; outline?: { color: string; width: number } | null; fill?: string; stroke?: { color: string; width: number } | null;
  words?: { w: string; start: number; end: number; p?: number; emph?: boolean; big?: number }[]; style?: CaptionStyle;
  pages?: { start: number; end: number; treat?: Chunk["treat"]; treat_color?: string; face?: "light"; lines?: number }[];
  motion?: string; card?: Card; look?: Record<string, unknown>;
};
export type Track = { id: string; kind: "visual" | "audio" | "captions"; name?: string; hidden?: boolean; muted?: boolean; locked?: boolean;
  magnet?: boolean; items: Item[] };
export type SceneDoc = { width: number; height: number; fps: number; duration: number; background?: string; assets: Record<string, Asset>;
  tracks: Track[] };

export const sceneMeta: CalculateMetadataFunction<SceneDoc> = ({ props }) => ({
  width: props.width, height: props.height, fps: props.fps, durationInFrames: Math.max(1, Math.round(props.duration * props.fps)) });

const EASES: Record<string, string> = { linear: "none", in: "power2.in", out: "power2.out", inout: "sine.inOut" };
/** A keyed value at t (seconds from the item's start): the last key at or before t, eased toward the next on its ease. */
export const keyAt = (ks: Key[], t: number) => {
  let i = 0;
  for (let j = 0; j < ks.length; j++) if (ks[j][0] <= t + 1e-6) i = j;
  const k = ks[i], n = ks[i + 1];
  if (!n || t < k[0] || (k[2] ?? "linear") === "hold") return k[1];
  return k[1] + (n[1] - k[1]) * ease(EASES[k[2] ?? "linear"] ?? "none")(Math.min(1, (t - k[0]) / Math.max(1e-6, n[0] - k[0])));
};

/** An asset's URL: the page's route or the render's link (url), else its file under the public folder. */
const urlOf = (a?: Asset) => { const u = a?.url ?? a?.proxy ?? a?.src ?? ""; return /^(\/|https?:|blob:|data:)/.test(u) ? u : staticFile(u); };
const live = () => !getRemotionEnvironment().isRendering;

/** Where a visual item is at t, after its keys and its entrance and exit (anim). */
const placed = (it: Item, lt: number, W: number, H: number) => {
  const k = (p: string, v: number) => (it.keys?.[p]?.length ? keyAt(it.keys[p], lt) : v);
  const s = k("scale", 1);
  let o = k("opacity", it.opacity ?? 1), sc = 1, ty = 0;
  const a = it.anim, d = a?.dur ?? 0.3, len = it.end - it.start;
  const fx = (kind: string | undefined, p: number) => {
    if (kind === "fade") o *= p;
    else if (kind === "pop") { sc *= 0.86 + 0.14 * p; o *= Math.min(1, p * 2); }
    else if (kind === "slide-up") { ty += (1 - p) * H * 0.05; o *= p; }
  };
  if (a) { fx(a.in, prog(lt, 0, d, "power3.out")); fx(a.out, 1 - prog(lt, len - d, d, "power1.in")); }
  return { x: k("x", it.x ?? W / 2), y: k("y", it.y ?? H / 2), w: k("w", it.w ?? W), h: k("h", it.h ?? H), r: k("rotation", it.rotation ?? 0), s: s * sc, o, ty };
};

/** The box a picture or clip sits in: its crop shown, fitted (cover or contain), rounded, shadowed, bordered. */
const Frame: React.FC<{ it: Item; a?: Asset; lt: number; W: number; H: number; children: (st: React.CSSProperties) => React.ReactNode }> = ({ it, a, lt, W, H, children }) => {
  const p = placed(it, lt, W, H);
  const c = { l: 0, t: 0, r: 0, b: 0, ...(it.crop ?? {}) };
  const sw = a?.w ?? p.w, sh = a?.h ?? p.h, cw = sw * (1 - c.l - c.r), ch = sh * (1 - c.t - c.b);
  const f = (it.fit === "contain" ? Math.min : Math.max)(p.w / cw, p.h / ch);
  const g = it.grade;
  const media: React.CSSProperties = { position: "absolute", width: sw * f, height: sh * f, left: (p.w - cw * f) / 2 - c.l * sw * f,
    top: (p.h - ch * f) / 2 - c.t * sh * f, maxWidth: "none", ...(g ? { filter: `brightness(${g.brightness ?? 1}) saturate(${g.saturate ?? 1})` } : {}) };
  const sh_ = it.shadow;
  return (
    <div data-sc={it.id} style={{ position: "absolute", left: p.x - p.w / 2, top: p.y - p.h / 2, width: p.w, height: p.h, opacity: p.o,
      transform: `translateY(${p.ty}px) rotate(${p.r}deg) scale(${p.s})`, borderRadius: it.radius ?? 0, overflow: "hidden",
      boxShadow: sh_ ? `0 ${sh_.y ?? 12}px ${sh_.blur ?? 30}px rgba(0,0,0,${sh_.opacity ?? 0.35})` : undefined, background: it.type === "shape" ? it.fill : undefined }}>
      {children(media)}
      {it.border || it.stroke ? <div style={{ position: "absolute", inset: 0, borderRadius: it.radius ?? 0,
        border: `${(it.border ?? it.stroke)!.width}px solid ${(it.border ?? it.stroke)!.color}` }} /> : null}
    </div>
  );
};

// volume is a gain: 1 is the file as it is, up to VMAX (+12 dB). The export's ffmpeg volume filter applies it as is; the
// page's player needs the Web Audio API for a gain above 1 (an element's own volume stops at 1): useWebAudioApi
export const VMAX = 3.981;
const vol = (it: Item, fps: number, muted: boolean) => muted ? 0 : (f: number) => {
  const t = f / fps, len = it.end - it.start;
  return Math.max(0, Math.min(VMAX, (it.volume ?? 1) * Math.min(1, it.fade_in ? t / it.fade_in : 1, it.fade_out ? (len - t) / it.fade_out : 1)));
};
const amp = () => live() ? { useWebAudioApi: true } : {};

const VideoItem: React.FC<{ it: Item; a?: Asset; W: number; H: number; muted: boolean; hidden: boolean }> = ({ it, a, W, H, muted, hidden }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const V = live() ? Video : OffthreadVideo;
  const props = { src: urlOf(a), trimBefore: Math.round((it.in ?? 0) * fps), playbackRate: it.speed ?? 1,
    volume: (it.volume ?? 1) <= 0 ? 0 : vol(it, fps, muted), muted: muted || (it.volume ?? 1) <= 0, ...amp() };
  if (hidden) return muted || (it.volume ?? 1) <= 0 ? null : <Audio {...props} />;
  // a clip with alpha (VP9 WebM): the page's <video> keeps it; the export extracts its frames as PNG to keep it
  const alpha = !live() && a?.alpha ? { transparent: true } : {};
  return <Frame it={it} a={a} lt={frame / fps} W={W} H={H}>{(st) => <V {...props} {...alpha} style={st} pauseWhenBuffering={live()} />}</Frame>;
};

const ImageItem: React.FC<{ it: Item; a?: Asset; W: number; H: number }> = ({ it, a, W, H }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return <Frame it={it} a={a} lt={frame / fps} W={W} H={H}>{(st) => <Img src={urlOf(a)} style={st} />}</Frame>;
};

const ShapeItem: React.FC<{ it: Item; W: number; H: number }> = ({ it, W, H }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return <Frame it={{ ...it, crop: null }} lt={frame / fps} W={W} H={H}>{() => null}</Frame>;
};

/** The outline of a box behind each line (Instagram's text background): one rounded box per line, lines touching, the
 *  steps where a wider line meets a narrower one turned with a small inside curve. ls: [left, right, top, bottom] per
 *  line, top to bottom; a gap (an empty line) starts a new shape. */
export function lineBoxPath(ls: number[][], R: number): string {
  const groups: number[][][] = [];
  ls.forEach((l, i) => (i && Math.abs(ls[i - 1][3] - l[2]) < 0.5 ? groups[groups.length - 1].push(l) : groups.push([l])));
  const f = (n: number) => +n.toFixed(2);
  return groups.map((g) => {
    const pts: [number, number, number][] = [];   // the outline's corners, clockwise from the top left: x, y, radius
    const rad = (...ds: number[]) => Math.max(0, Math.min(R, ...ds.map((d) => Math.abs(d) / 2)));
    const h = (l: number[]) => l[3] - l[2];
    pts.push([g[0][0], g[0][2], rad(g[0][1] - g[0][0], h(g[0]))], [g[0][1], g[0][2], rad(g[0][1] - g[0][0], h(g[0]))]);
    for (let i = 0; i + 1 < g.length; i++) {   // the right side going down
      const d = g[i + 1][1] - g[i][1], y = g[i][3], c = rad(d, h(g[i]), h(g[i + 1]));
      if (Math.abs(d) >= 0.5) pts.push([g[i][1], y, c], [g[i + 1][1], y, c]);
    }
    const n = g[g.length - 1];
    pts.push([n[1], n[3], rad(n[1] - n[0], h(n))], [n[0], n[3], rad(n[1] - n[0], h(n))]);
    for (let i = g.length - 2; i >= 0; i--) {   // the left side going up
      const d = g[i][0] - g[i + 1][0], y = g[i][3], c = rad(d, h(g[i]), h(g[i + 1]));
      if (Math.abs(d) >= 0.5) pts.push([g[i + 1][0], y, c], [g[i][0], y, c]);
    }
    // each corner: in along the edge from the previous corner, a quarter curve round it, out towards the next
    const K = 0.5523, out: string[] = [];
    pts.forEach(([x, y, c], i) => {
      const [px, py] = pts[(i + pts.length - 1) % pts.length], [nx, ny] = pts[(i + 1) % pts.length];
      const u = (ax: number, ay: number) => { const L = Math.hypot(ax - x, ay - y) || 1; return [(ax - x) / L, (ay - y) / L]; };
      const [ux, uy] = u(px, py), [vx, vy] = u(nx, ny);
      const a = [x + ux * c, y + uy * c], b = [x + vx * c, y + vy * c];
      out.push(`${i ? "L" : "M"}${f(a[0])} ${f(a[1])}`);
      if (c > 0) out.push(`C${f(a[0] - ux * c * K)} ${f(a[1] - uy * c * K)} ${f(b[0] - vx * c * K)} ${f(b[1] - vy * c * K)} ${f(b[0])} ${f(b[1])}`);
    });
    return out.join("") + "Z";
  }).join("");
}

/** Text: as wide as its words up to w, centred on x, y; a box behind each line (TikTok's and Instagram's look) or one
 *  block box. Each line's box is measured from where the browser broke the lines and drawn as one outline behind
 *  them: the lines touch, every line gets the same side padding, the first and last get the top and bottom padding. */
const TextItem: React.FC<{ it: Item; W: number; H: number }> = ({ it, W, H }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const family = useFamily(it.font ?? "TikTok Sans", it.weight ?? 700);
  const ref = useRef<HTMLDivElement>(null), span = useRef<HTMLSpanElement>(null);
  const [shape, setShape] = useState<{ d: string; w: number; h: number } | null>(null);
  const p = placed(it, frame / fps, W, H), fs = it.size ?? Math.min(W, H) * 0.05, b = it.box, lh = it.line_height ?? 1.2;
  const pad = Array.isArray(b?.pad) ? b!.pad : [b?.pad ?? fs * 0.25, b?.pad ?? fs * 0.1];
  const lines = !!b && !b.block;
  useLayoutEffect(() => {   // after every layout: where the lines broke, in the element's own px (its transform and the player's scale taken off)
    const e = ref.current, sp = span.current;
    if (!lines || !e || !sp) return void (shape && setShape(null));
    const tf = e.style.transform;
    e.style.transform = "none";
    const cr = e.getBoundingClientRect(), k = cr.width ? e.offsetWidth / cr.width : 1, L = lh * fs, top = pad[1];
    const rows: number[][] = [];
    const tn = sp.firstChild, rg = document.createRange(), rs: DOMRect[] = [];
    if (tn) for (const m of (tn.textContent ?? "").matchAll(/\S+/g)) {   // word by word: a space where a line broke gets no box
      rg.setStart(tn, m.index!); rg.setEnd(tn, m.index! + m[0].length); rs.push(...Array.from(rg.getClientRects()));
    }
    for (const r of rs) {
      if (r.width < 0.5) continue;
      const i = Math.max(0, Math.floor((((r.top + r.bottom) / 2 - cr.top) * k - top) / L));
      const x0 = (r.left - cr.left) * k - pad[0], x1 = (r.right - cr.left) * k + pad[0];
      rows[i] = rows[i] ? [Math.min(rows[i][0], x0), Math.max(rows[i][1], x1)] : [x0, x1];
    }
    e.style.transform = tf;
    const ls: number[][] = [];
    rows.forEach((r, i) => r && ls.push([r[0], r[1], top + i * L - (i && rows[i - 1] ? 0 : pad[1]), top + (i + 1) * L + (rows[i + 1] ? 0 : pad[1])]));
    const next = { d: lineBoxPath(ls, b!.radius ?? 0), w: e.offsetWidth, h: e.offsetHeight };
    if (!shape || shape.d !== next.d || shape.w !== next.w || shape.h !== next.h) setShape(next);
  });
  if (!family) return null;
  return (
    <div ref={ref} data-sc={it.id} style={{ position: "absolute", left: p.x, top: p.y, transform: `translate(-50%, -50%) translateY(${p.ty}px) rotate(${p.r}deg) scale(${p.s})`,
      opacity: p.o, width: "max-content", maxWidth: p.w, textAlign: it.align ?? "center", whiteSpace: "pre-wrap", overflowWrap: "anywhere",
      fontFamily: `${family}, "Apple Color Emoji", "Noto Color Emoji"`, fontWeight: it.weight ?? 700, fontSize: fs, lineHeight: lh,
      color: it.color ?? "#FFFFFF", ...(b?.block ? { background: b.color, padding: `${pad[1]}px ${pad[0]}px`, borderRadius: b.radius ?? 0 } : {}),
      ...(lines ? { padding: `${pad[1]}px ${pad[0]}px`, boxSizing: "border-box" } : {}) }}>
      {lines && shape ? <svg width={shape.w} height={shape.h} style={{ position: "absolute", left: 0, top: 0, overflow: "visible" }}>
        <path d={shape.d} fill={b!.color} /></svg> : null}
      <span ref={span} style={{ position: "relative", ...(it.outline ? { WebkitTextStroke: `${it.outline.width}px ${it.outline.color}`, paintOrder: "stroke fill" } : {}) } as React.CSSProperties}>
        {it.text}</span>
    </div>
  );
};

/** A built cooked. card (an overlay format, a framed shot): StyleEdit's own CardView at the item's box, on the scene clock. */
const CardItem: React.FC<{ it: Item; t: number; W: number; H: number }> = ({ it, t, W, H }) => {
  const look = resolveLook(it.look as never);
  const fonts = useFonts(look);
  if (!fonts.ready || !it.card) return null;
  const p = placed(it, t - it.start, W, H);
  const card = { ...it.card, start: it.start, end: it.end, rotation: p.r, opacity: p.o,
    box: [((p.x - p.w / 2) / W) * 100, ((p.y - p.h / 2) / H) * 100, (p.w / W) * 100, (p.h / H) * 100] } as Card;
  return <CardView card={card} t={t} covered={false} light={false} look={look} m={pickMotion(it.motion)} fonts={fonts} />;
};

/** The scene time of a moment of an asset (the raw take): where a clip on a visual track shows it, else null. */
const clipMap = (tracks: Track[], asset?: string) => {
  const clips = tracks.filter((tr) => tr.kind === "visual").flatMap((tr) => tr.items).filter((x) => x.type === "video" && x.asset === asset);
  return (s: number, endOf = false): number | null => {
    for (const c of clips) {
      const sp = c.speed ?? 1, a = c.in ?? 0, b = a + (c.end - c.start) * sp;
      if (s >= a - 1e-6 && (endOf ? s <= b + 1e-6 : s < b)) return c.start + (s - a) / sp;
    }
    return null;
  };
};

/** Caption pages on the scene clock: a raw take's words through the clips that show them (a restored piece gets its
 *  words back), paged as saved (p, pages) or words_per_caption at a time. */
const chunksOf = (it: Item, tracks: Track[]): Chunk[] => {
  const map = it.asset ? clipMap(tracks, it.asset) : (s: number) => s;
  const words = (it.words ?? []).map((w) => {
    const s = map(w.start);
    if (s === null) return null;
    const e = map(w.end, true);
    return { text: w.w, start: s, end: e === null || e < s ? s + Math.min(0.4, w.end - w.start) : e, p: w.p, emph: w.emph, big: w.big };
  }).filter(Boolean) as (Chunk["words"][number] & { p?: number })[];
  const groups: (typeof words)[] = [];
  const n = Math.max(1, Number((it.style as { words_per_caption?: number })?.words_per_caption ?? 3));
  for (const w of words) {
    const last = groups[groups.length - 1], prev = last?.[last.length - 1];
    const same = it.pages ? prev && prev.p === w.p && w.start - prev.end < 0.5 : prev && last.length < n && w.start - prev.end < 0.6;
    if (same) last.push(w); else groups.push([w]);
  }
  return groups.map((g, i) => {
    const pg = it.pages?.[g[0].p ?? -1];
    const ps = pg ? map(pg.start) : null, pe = pg ? map(pg.end, true) : null;
    const start = Math.min(g[0].start, ps ?? Infinity), nx = groups[i + 1]?.[0].start ?? Infinity;
    const end = Math.min(nx, Math.max(g[g.length - 1].end, pe !== null && pe > start ? pe : 0));
    return { text: g.map((w) => w.text).join(" "), start, end, words: g, ...(pg ? { treat: pg.treat, treat_color: pg.treat_color, face: pg.face, lines: pg.lines } : {}) };
  });
};

const CaptionsItem: React.FC<{ it: Item; t: number; tracks: Track[] }> = ({ it, t, tracks }) => {
  const chunks = useMemo(() => chunksOf(it, tracks), [it, tracks]);
  return <Captions style={it.style ?? {}} chunks={chunks} t={t} m={pickMotion(it.motion)} />;
};

export const SceneEdit: React.FC<SceneDoc> = ({ tracks, assets, background }) => {
  const frame = useCurrentFrame();
  const { fps, width: W, height: H } = useVideoConfig();
  const t = frame / fps;
  const pre = live() ? Math.round(fps) : 0;   // the player mounts the next clip a second early, so a cut never waits on a seek
  const seq = (it: Item, child: React.ReactNode, premount = false) => (
    <Sequence key={it.id} from={Math.round(it.start * fps)} durationInFrames={Math.max(1, Math.round(it.end * fps) - Math.round(it.start * fps))}
      premountFor={premount && pre ? pre : undefined}>{child}</Sequence>);
  return (
    <AbsoluteFill style={{ backgroundColor: background ?? "#000000", overflow: "hidden" }}>
      {tracks.map((tr) => (
        <AbsoluteFill key={tr.id}>
          {tr.items.map((it) => {
            const a = it.asset ? assets[it.asset] : undefined;
            if (tr.kind === "audio")
              return tr.muted || !a ? null : seq(it, <Audio src={urlOf(a)} trimBefore={Math.round((it.in ?? 0) * fps)} playbackRate={it.speed ?? 1}
                volume={vol(it, fps, false)} {...amp()} />);
            if (it.type === "video") return seq(it, <VideoItem it={it} a={a} W={W} H={H} muted={!!tr.muted} hidden={!!tr.hidden} />, true);
            if (tr.hidden) return null;
            if (it.type === "card") return t >= it.start && t < it.end + 0.4 ? <CardItem key={it.id} it={it} t={t} W={W} H={H} /> : null;
            if (it.type === "captions") return t >= it.start && t < it.end ? <CaptionsItem key={it.id} it={it} t={t} tracks={tracks} /> : null;
            if (it.type === "image") return seq(it, <ImageItem it={it} a={a} W={W} H={H} />);
            if (it.type === "text") return seq(it, <TextItem it={it} W={W} H={H} />);
            if (it.type === "shape") return seq(it, <ShapeItem it={it} W={W} H={H} />);
            return null;
          })}
        </AbsoluteFill>
      ))}
    </AbsoluteFill>
  );
};
