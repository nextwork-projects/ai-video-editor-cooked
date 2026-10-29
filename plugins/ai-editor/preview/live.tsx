// The review page's live player (lib/ai_editor/review.html, the edit): the real StyleEdit composition in a <Player>,
// its plan from review.py /live/plan, so a change on the page is the frame on screen at once (CapCut's way), not an
// overlay over a rendered MP4. window.CookedLive.mount(el, plan) returns a stand-in for the page's <video>: the
// page's code (currentTime, paused, play, pause, events, requestVideoFrameCallback) runs on it unchanged.
import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { Player, PlayerRef } from "@remotion/player";
import { StyleEdit } from "../src/StyleEdit";
import { cues } from "./Sfx";

type Plan = Record<string, unknown> & { width: number; height: number; fps: number; durationInFrames: number;
  sfx?: typeof cues.current; music?: { src: string } };
type Frame = (now: number, m: { mediaTime: number; presentedFrames: number }) => void;
(window as unknown as { remotion_staticBase: string }).remotion_staticBase = "/live/media";   // staticFile(rel) -> the edit's file

class Live extends EventTarget {
  plan: Plan;
  p: PlayerRef | null = null;
  rate = 1;
  quiet = 0;   // until then a pause and play are the Player's own around a seek while playing: the page never sees them
  cbs: Frame[] = [];
  n = 0;
  stat = { frames: 0, skipped: 0, last: -1 };   // frames drawn while playing, and frames jumped over (dropped)
  pend: number | null = null;   // a seek or mute asked for before the Player is up
  mute = false;
  draw?: (p: Plan, rate: number) => void;
  constructor(plan: Plan) { super(); this.plan = plan; }
  fire(t: string) { this.dispatchEvent(new Event(t)); }
  get fps() { return this.plan.fps; }
  get duration() { return this.plan.durationInFrames / this.plan.fps; }
  get videoWidth() { return this.plan.width; }
  get videoHeight() { return this.plan.height; }
  get currentTime() { return this.p ? this.p.getCurrentFrame() / this.fps : this.pend ?? 0; }
  set currentTime(t: number) {
    if (!this.p) { this.pend = +t || 0; return; }
    if (this.p.isPlaying()) this.quiet = performance.now() + 400;
    this.fire("seeking");
    this.p.seekTo(Math.max(0, Math.min(this.plan.durationInFrames - 1, Math.round((+t || 0) * this.fps))));
    this.stat.last = -1;
    this.fire("seeked");
    this.fire("timeupdate");
  }
  get paused() { return !(this.p?.isPlaying() || performance.now() < this.quiet); }
  play() { this.p?.play(); return Promise.resolve(); }
  pause() { this.quiet = 0; this.p?.pause(); }
  get muted() { return this.p ? this.p.isMuted() : this.mute; }
  set muted(m: boolean) { this.mute = !!m; if (m) this.p?.mute(); else this.p?.unmute(); this.fire("volumechange"); }
  get volume() { return this.p?.getVolume() ?? 1; }
  set volume(x: number) { this.p?.setVolume(Math.max(0, Math.min(1, x))); this.fire("volumechange"); }
  get playbackRate() { return this.rate; }
  set playbackRate(r: number) { if (r === this.rate) return; this.rate = r; this.draw?.(this.plan, r); this.fire("ratechange"); }
  requestVideoFrameCallback(f: Frame) { this.cbs.push(f); return ++this.n; }
  cancelVideoFrameCallback() { this.cbs = []; }
  /** A new plan: drawn at once, on the same frame and play state. */
  setPlan(plan: Plan) {
    cues.current = plan.sfx ?? [];
    cues.music = plan.music ?? null;
    this.plan = plan;
    this.draw?.(plan, this.rate);
  }
  attach(p: PlayerRef) {
    this.p = p;
    if (this.mute) p.mute();
    if (this.pend) p.seekTo(Math.round(this.pend * this.fps));
    p.addEventListener("play", () => { if (performance.now() >= this.quiet) this.fire("play"); });
    p.addEventListener("pause", () => { if (performance.now() >= this.quiet) this.fire("pause"); });
    p.addEventListener("ended", () => { this.fire("pause"); this.fire("ended"); });
    p.addEventListener("timeupdate", () => this.fire("timeupdate"));
    p.addEventListener("mutechange", () => this.fire("volumechange"));
    p.addEventListener("frameupdate", (e: { detail: { frame: number } }) => {
      const f = e.detail.frame, s = this.stat;
      if (p.isPlaying()) {
        if (s.last >= 0 && f > s.last + 1) s.skipped += f - s.last - 1;
        s.frames++;
        s.last = f;
      }
      const cbs = this.cbs;
      this.cbs = [];
      cbs.forEach((cb) => cb(performance.now(), { mediaTime: f / this.fps, presentedFrames: s.frames }));
    });
    this.fire("loadedmetadata");
    this.fire("loadeddata");
  }
  /** Playback so far: frames drawn, frames skipped, and the footage <video>'s own dropped count. */
  stats() {
    const q = [...(this.p?.getContainerNode()?.querySelectorAll("video") ?? [])].map((x) => x.getVideoPlaybackQuality());
    return { ...this.stat, last: undefined, decoded: q.reduce((a, x) => a + x.totalVideoFrames, 0), dropped: q.reduce((a, x) => a + x.droppedVideoFrames, 0) };
  }
}

const View: React.FC<{ live: Live }> = ({ live }) => {
  const [s, setS] = useState({ plan: live.plan, rate: live.rate });
  const ref = useRef<PlayerRef>(null);
  live.draw = (plan, rate) => setS({ plan, rate });
  useEffect(() => { if (ref.current) live.attach(ref.current); }, [live]);
  const { plan, rate } = s;
  return (
    <Player ref={ref} component={StyleEdit as unknown as React.FC<Record<string, unknown>>} inputProps={plan}
      durationInFrames={plan.durationInFrames} compositionWidth={plan.width} compositionHeight={plan.height} fps={plan.fps}
      playbackRate={rate} numberOfSharedAudioTags={0} clickToPlay={false} spaceKeyToPlayOrPause={false}
      doubleClickToFullscreen={false} moveToBeginningWhenEnded={false} style={{ width: "100%", height: "100%" }} acknowledgeRemotionLicense />
  );
};

function mount(el: HTMLElement, plan: Plan) {
  const live = new Live(plan);
  live.setPlan(plan);
  el.addEventListener("click", () => live.fire("click"));
  createRoot(el).render(<View live={live} />);
  return live;
}

(window as unknown as { CookedLive: { mount: typeof mount } }).CookedLive = { mount };
