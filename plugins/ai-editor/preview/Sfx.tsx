// Stands in for remotion/src/Sfx.tsx in the preview bundles (build.mjs): the render reads the cues with
// getInputProps(), which throws inside a <Player>, so here the page hands them over instead. A src starting with "/"
// is the review page's own route (a dropped song, a library sound); from / dur / vol: a dropped clip's trim and level.
import React from "react";
import { Audio, Sequence, staticFile, useVideoConfig } from "remotion";

type Cue = { t: number; src: string; from?: number; dur?: number; vol?: number; _d?: number };
export const cues: { current: Cue[]; music?: { src: string } | null } = { current: [] };
const url = (s: string) => (s.startsWith("/") ? s : staticFile(s));

export const Sfx: React.FC = () => {
  const { fps } = useVideoConfig();
  return (
    <>
      {cues.music ? <Audio src={url(cues.music.src)} /> : null}
      {cues.current.map((c) => {
        const d = c.dur ?? c._d;   // bounded, so an audio tag is up only while its cue plays
        return (
          <Sequence key={`${c.src}${c.t}`} from={Math.round(c.t * fps)} durationInFrames={d ? Math.max(1, Math.ceil(d * fps)) : undefined} layout="none">
            <Audio src={url(c.src)} trimBefore={c.from ? Math.round(c.from * fps) : undefined} volume={Math.min(1, c.vol ?? 1)} />
          </Sequence>
        );
      })}
    </>
  );
};
